#!/usr/bin/env python3
"""
server.py — dashboard web pour CrisisBot
================================================================

Agent de réponse à incident : quand un autre agent (Sentinel, NetScope,
PhishHunter, DarkWatch) détecte une menace sérieuse, CrisisBot prend le
relais et déroule un "runbook" de réponse automatique — isoler le poste,
notifier le RSSI et la Direction, activer la cellule de crise, préparer
la communication interne — puis notifie les bonnes personnes (Slack /
Teams / Email — simulé dans cette démo).

Aucune dépendance externe : uniquement http.server, comme DarkWatch.
Rien à installer.

Usage :
    python3 server.py
    (ou "py server.py" sous Windows)

Puis ouvrir http://localhost:8878 (adapte le port avec la variable
d'env CRISISBOT_PORT si besoin).
"""

import json
import os
import sys
import time
import http.server
import socketserver
from pathlib import Path
from datetime import datetime, timezone
from urllib.parse import urlparse, parse_qs

from llm_comms import generate_comms_message, is_configured as llm_configured, FALLBACK_MESSAGE
from notifications import send_slack_notification, is_slack_configured
import auth

PORT = int(os.environ.get("CRISISBOT_PORT", "8878"))
BASE_DIR = Path(__file__).parent
STATE_FILE = BASE_DIR / "crisisbot_state.json"
ACTIONS_LOG = BASE_DIR / "crisisbot_actions.log"

# Le "runbook" de réponse automatique — chaque étape a une durée simulée
# (en secondes) utilisée à la fois pour l'animation côté client et pour
# calculer le temps total de traitement affiché à la fin.
RUNBOOK = [
    {
        "id": "isolate_host",
        "icon": "🔒",
        "title": "Isoler le poste affecté",
        "detail": "Débranchement réseau automatique du poste concerné pour stopper la propagation.",
        "duration": 20,
    },
    {
        "id": "notify_ciso",
        "icon": "🛡️",
        "title": "Notifier le RSSI",
        "detail": "Alerte immédiate envoyée avec les indicateurs de compromission détectés.",
        "duration": 15,
    },
    {
        "id": "notify_direction",
        "icon": "📊",
        "title": "Notifier la Direction",
        "detail": "Résumé exécutif transmis pour déclenchement éventuel de la cellule de crise.",
        "duration": 25,
    },
    {
        "id": "activate_crisis_cell",
        "icon": "👥",
        "title": "Activer la cellule de crise",
        "detail": "Convocation automatique des référents IT, sécurité et communication sur un canal dédié.",
        "duration": 60,
    },
    {
        "id": "prepare_comms",
        "icon": "📣",
        "title": "Préparer la communication interne",
        "detail": "Modèle de message prêt pour informer les équipes sans créer de panique.",
        "duration": 90,
        "message": FALLBACK_MESSAGE,
    },
]

TOTAL_SECONDS = sum(s["duration"] for s in RUNBOOK)
WEBHOOK_TARGETS = ["Slack", "Teams", "Email"]

DEFAULT_INCIDENT = "Rançongiciel détecté sur un poste"


def load_state() -> dict:
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    return {"last_simulation_at": None, "last_incident": None, "last_source": None}


def save_state(state: dict) -> None:
    STATE_FILE.write_text(json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8")


def log_action(entry: dict) -> None:
    with ACTIONS_LOG.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def format_duration(total_seconds: int) -> str:
    minutes, seconds = divmod(total_seconds, 60)
    if minutes and seconds:
        return f"{minutes} minutes {seconds:02d}"
    if minutes:
        return f"{minutes} minutes"
    return f"{seconds} secondes"


def days_since(iso_ts: str) -> int:
    then = datetime.fromisoformat(iso_ts)
    now = datetime.now(timezone.utc)
    return max(0, (now - then).days)


def build_status() -> dict:
    state = load_state()
    last = state.get("last_simulation_at")
    return {
        "state": "idle",
        "last_simulation_at": last,
        "days_since": days_since(last) if last else None,
        "last_incident": state.get("last_incident"),
        "last_source": state.get("last_source"),
        "webhook_targets": WEBHOOK_TARGETS,
        "slack_configured": is_slack_configured(),
    }


def build_steps_for(incident: str) -> tuple[list, bool]:
    """
    Copie le runbook pour cet incident précis. L'étape "communication interne"
    reçoit un message rédigé par le LLM (Groq) s'il est configuré, sinon le
    message générique par défaut — le runbook lui-même (quelles actions, dans
    quel ordre) reste 100% déterministe, le LLM ne fait que rédiger le texte.
    """
    steps = [dict(s) for s in RUNBOOK]  # copie superficielle, ne mute pas RUNBOOK
    used_llm = False

    if llm_configured():
        generated = generate_comms_message(incident)
        if generated:
            for s in steps:
                if s["id"] == "prepare_comms":
                    s["message"] = generated
            used_llm = True

    return steps, used_llm


def run_simulation(incident: str, source: str = "manual") -> dict:
    now = datetime.now(timezone.utc).isoformat()
    steps, used_llm = build_steps_for(incident)

    comms_message = next((s["message"] for s in steps if s["id"] == "prepare_comms"), FALLBACK_MESSAGE)
    slack_text = (
        f":rotating_light: *CrisisBot — Incident traité*\n"
        f"*Incident :* {incident}\n"
        f"*Déclenché par :* {source}\n\n"
        f"{comms_message}"
    )
    notification_sent = send_slack_notification(slack_text)

    state = {"last_simulation_at": now, "last_incident": incident, "last_source": source}
    save_state(state)
    log_action({
        "timestamp": now,
        "incident": incident,
        "source": source,
        "steps": [s["id"] for s in steps],
        "total_seconds": TOTAL_SECONDS,
        "llm_used_for_comms": used_llm,
        "notification_sent": notification_sent,
    })
    return {
        "incident": incident,
        "source": source,
        "steps": steps,
        "total_seconds": TOTAL_SECONDS,
        "total_label": format_duration(TOTAL_SECONDS),
        "webhook_targets": WEBHOOK_TARGETS,
        "started_at": now,
        "llm_used_for_comms": used_llm,
        "notification_sent": notification_sent,
    }


class Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(BASE_DIR), **kwargs)

    def do_GET(self):
        parsed = urlparse(self.path)

        if parsed.path.startswith("/login"):
            self._send_html(auth.render_login_page())
            return

        if parsed.path.startswith("/logout"):
            self.send_response(302)
            self.send_header("Location", "/login")
            self.send_header("Set-Cookie", f"{auth.COOKIE_NAME}=; Path=/; Max-Age=0")
            self.end_headers()
            return

        # Protège le dashboard et /api/status — mais PAS /api/webhook/incident
        # (voir do_POST) : ce point d'entrée est appelé par les 4 autres agents
        # sans navigateur ni cookie, il doit rester joignable sans connexion.
        if auth.AUTH_ENABLED and not self._is_authenticated():
            self.send_response(302)
            self.send_header("Location", "/login")
            self.end_headers()
            return

        if parsed.path == "/api/status":
            self._send_json(build_status())
            return
        super().do_GET()

    def _read_json_body(self) -> dict | None:
        """Lit et parse le corps JSON de la requête. Retourne None (et répond
        400) si le corps est manquant/mal formé, plutôt que de laisser
        json.loads planter la requête sans réponse propre au client — ce
        point d'entrée est appelé automatiquement par les 4 autres agents,
        il doit rester robuste à une requête malformée."""
        length = int(self.headers.get("Content-Length", 0) or 0)
        raw = self.rfile.read(length) if length else b"{}"
        try:
            return json.loads(raw or b"{}")
        except json.JSONDecodeError as e:
            self._send_json({"error": "invalid_json", "message": str(e)}, status=400)
            return None

    def do_POST(self):
        parsed = urlparse(self.path)

        if parsed.path.startswith("/login"):
            length = int(self.headers.get("Content-Length", 0) or 0)
            raw_body = self.rfile.read(length).decode("utf-8") if length else ""
            form = parse_qs(raw_body)
            email = (form.get("email") or [""])[0]
            password = (form.get("password") or [""])[0]
            if auth.check_credentials(email, password):
                auth.record_login(email, source_agent="crisisbot")
                cookie_value = auth.make_session_cookie(email)
                self.send_response(302)
                self.send_header("Location", "/")
                self.send_header("Set-Cookie", f"{auth.COOKIE_NAME}={cookie_value}; Path=/; HttpOnly; SameSite=Lax")
                self.end_headers()
            else:
                self._send_html(auth.render_login_page(error=True))
            return

        if parsed.path == "/api/simulate":
            # Protégé — déclenché depuis le bouton du dashboard, donc par un
            # humain déjà connecté si l'auth est activée.
            if auth.AUTH_ENABLED and not self._is_authenticated():
                self._send_json({"error": "unauthorized"}, status=401)
                return
            body = self._read_json_body()
            if body is None:
                return
            incident = (body.get("incident") or DEFAULT_INCIDENT).strip()
            self._send_json(run_simulation(incident, source="manual"))
            return

        if parsed.path == "/api/webhook/incident":
            # Point d'entrée pour les AUTRES agents (Sentinel, NetScope,
            # PhishHunter, DarkWatch) : quand l'un d'eux détecte une menace
            # sérieuse, il peut appeler ce webhook pour déclencher le
            # runbook de CrisisBot automatiquement, sans intervention humaine.
            body = self._read_json_body()
            if body is None:
                return
            source_agent = body.get("source_agent", "agent_inconnu")
            severity = body.get("severity", "high")
            description = body.get("description") or DEFAULT_INCIDENT
            result = run_simulation(description, source=source_agent)
            result["severity"] = severity
            self._send_json(result)
            return

        self.send_response(404)
        self.end_headers()

    def _is_authenticated(self) -> bool:
        cookies = auth.parse_cookie_header(self.headers.get("Cookie"))
        return auth.verify_session_cookie(cookies.get(auth.COOKIE_NAME)) is not None

    def _send_html(self, content: str) -> None:
        try:
            body = content.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        except (ConnectionAbortedError, ConnectionResetError, BrokenPipeError):
            pass

    def _send_json(self, data: dict, status: int = 200) -> None:
        try:
            body = json.dumps(data).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        except (ConnectionAbortedError, ConnectionResetError, BrokenPipeError):
            pass

    def copyfile(self, source, outputfile):
        try:
            super().copyfile(source, outputfile)
        except (ConnectionAbortedError, ConnectionResetError, BrokenPipeError):
            pass

    def log_message(self, format, *args):
        pass

    def handle_one_request(self):
        try:
            super().handle_one_request()
        except (ConnectionAbortedError, ConnectionResetError, BrokenPipeError):
            pass


class ThreadingServer(socketserver.ThreadingMixIn, socketserver.TCPServer):
    daemon_threads = True
    allow_reuse_address = True


if __name__ == "__main__":
    try:
        httpd = ThreadingServer(("", PORT), Handler)
    except OSError as e:
        print(f"Impossible d'ouvrir le port {PORT} : {e}")
        print(
            "Ce port est probablement déjà utilisé. Essaie un autre port :\n"
            '    $env:CRISISBOT_PORT = "8090"\n'
            "    py server.py"
        )
        sys.exit(1)

    with httpd:
        print(f"CrisisBot dashboard disponible sur : http://localhost:{PORT}")
        print("Ctrl+C pour arrêter.")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            pass
