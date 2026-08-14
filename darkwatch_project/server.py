#!/usr/bin/env python3
"""
server.py — dashboard web pour DarkWatch (version gratuite)
================================================================

Petit serveur local qui affiche une interface visuelle inspirée de la
démo CyberAware : liste des comptes surveillés, bouton "Lancer le scan",
et alerte rouge en cas de fuite détectée.

Aucune dépendance externe (Flask, etc.) : uniquement http.server, qui
fait partie de la bibliothèque standard de Python. Rien à installer.

C'est une couche de PRÉSENTATION seulement : elle appelle les mêmes
fonctions gratuites (xon_api.py) que le script CLI darkwatch.py. Il n'y a
toujours aucun modèle ML ni dataset entraîné derrière.

Usage :
    python3 server.py
    (ou "py server.py" sous Windows)

Puis ouvrir http://localhost:8877 dans un navigateur (adapte le port si
tu le changes ci-dessous).
"""

import json
import os
import sys
import threading
import time
import http.server
import socketserver
from pathlib import Path
from urllib.parse import urlparse, parse_qs

from xon_api import check_email, get_analytics, RateLimitError
from llm_summary import generate_summary, is_configured
from crisisbot_client import notify_crisisbot
from email_sources import get_monitored_emails

HIGH_RISK_LABELS = {"high", "critical"}

# 8000 est parfois réservé par Windows (Hyper-V/WSL) et refuse la
# connexion avec une erreur de permission plutôt que "port occupé".
# 8877 est un port peu utilisé, sinon override avec la variable d'env
# DARKWATCH_PORT (ex. $env:DARKWATCH_PORT = "8080").
PORT = int(os.environ.get("DARKWATCH_PORT", "8877"))
BASE_DIR = Path(__file__).parent
EMAILS_FILE = BASE_DIR / "emails_example.txt"
RATE_LIMIT_DELAY = 0.6


def load_emails() -> list[str]:
    return get_monitored_emails(EMAILS_FILE)


def check_one(email: str) -> dict:
    """Vérifie un seul email à la volée (saisi dans la barre de recherche)."""
    breaches = check_email(email)
    entry = {"email": email, "breaches": sorted(breaches), "found": bool(breaches)}
    if breaches:
        analytics = get_analytics(email)
        metrics = (analytics or {}).get("BreachMetrics") or {}
        risk = (metrics.get("risk") or [{}])[0]
        entry["risk_label"] = risk.get("risk_label", "Inconnu")
        entry["risk_score"] = risk.get("risk_score", 0)
        if is_configured():
            entry["ai_summary"] = generate_summary(email, sorted(breaches), analytics)
        if entry["risk_label"].lower() in HIGH_RISK_LABELS:
            notify_crisisbot(
                source_agent="darkwatch",
                severity=entry["risk_label"].lower(),
                description=f"Fuite de données à risque {entry['risk_label']} détectée pour {email}",
            )
    return entry


def scan_all() -> list[dict]:
    results = []
    for email in load_emails():
        breaches = check_email(email)
        entry = {"email": email, "breaches": sorted(breaches), "found": bool(breaches)}
        if breaches:
            time.sleep(RATE_LIMIT_DELAY)
            analytics = get_analytics(email)
            metrics = (analytics or {}).get("BreachMetrics") or {}
            risk = (metrics.get("risk") or [{}])[0]
            entry["risk_label"] = risk.get("risk_label", "Inconnu")
            entry["risk_score"] = risk.get("risk_score", 0)
            if is_configured():
                entry["ai_summary"] = generate_summary(email, sorted(breaches), analytics)
            if entry["risk_label"].lower() in HIGH_RISK_LABELS:
                notify_crisisbot(
                    source_agent="darkwatch",
                    severity=entry["risk_label"].lower(),
                    description=f"Fuite de données à risque {entry['risk_label']} détectée pour {email}",
                )
        results.append(entry)
        time.sleep(RATE_LIMIT_DELAY)
    return results


_auto_scan_already_notified = set()


def auto_scan_loop(interval: int = 45) -> None:
    """
    Boucle autonome facultative : vérifie les comptes surveillés en tâche de
    fond, comme le ferait agent.py, mais directement dans le process du
    dashboard pour que `launch_all.py --simulate` fasse réagir DarkWatch tout
    seul (comme les 3 autres agents), sans commande séparée à lancer.
    Activée uniquement si DARKWATCH_AUTO_SCAN=1 (mis par launch_all.py --simulate).
    Un email n'est notifié qu'une fois par run (évite de spammer Slack toutes
    les 45s avec la même fuite déjà connue).
    """
    print(f"[DarkWatch] Auto-scan activé — vérifie les comptes surveillés toutes les {interval}s.")
    while True:
        try:
            for email in load_emails():
                breaches = check_email(email)
                if breaches:
                    time.sleep(RATE_LIMIT_DELAY)
                    analytics = get_analytics(email)
                    metrics = (analytics or {}).get("BreachMetrics") or {}
                    risk = (metrics.get("risk") or [{}])[0]
                    risk_label = risk.get("risk_label", "Inconnu")
                    if risk_label.lower() in HIGH_RISK_LABELS and email not in _auto_scan_already_notified:
                        notify_crisisbot(
                            source_agent="darkwatch",
                            severity=risk_label.lower(),
                            description=f"Fuite de données à risque {risk_label} détectée pour {email} (auto-scan)",
                        )
                        _auto_scan_already_notified.add(email)
                time.sleep(RATE_LIMIT_DELAY)
        except RateLimitError as e:
            print(f"[DarkWatch] Auto-scan : limite de débit atteinte, on ignore ce cycle ({e}).")
        except Exception as e:
            print(f"[DarkWatch] Auto-scan : erreur ignorée ({e}).")
        time.sleep(interval)


class Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(BASE_DIR), **kwargs)

    def do_GET(self):
        parsed = urlparse(self.path)
        try:
            if parsed.path == "/api/emails":
                self._send_json({"emails": load_emails()})
                return
            elif parsed.path == "/api/scan":
                self._send_json({"results": scan_all()})
                return
            elif parsed.path == "/api/check":
                qs = parse_qs(parsed.query)
                email = (qs.get("email") or [""])[0].strip()
                if not email:
                    self._send_json({"error": "email manquant"})
                    return
                self._send_json(check_one(email))
                return
        except RateLimitError as e:
            self._send_json({"error": "rate_limit", "message": str(e)})
            return

        if self.path.startswith("/api/reset"):
            # Action simulée : dans ce projet gratuit/démo, on ne touche à
            # aucun vrai compte. En prod, ceci appellerait ton IAM/AD.
            self._send_json({"status": "ok", "message": "Réinitialisation simulée (démo)"})
        else:
            super().do_GET()

    def _send_json(self, data: dict) -> None:
        try:
            body = json.dumps(data).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        except (ConnectionAbortedError, ConnectionResetError, BrokenPipeError):
            # Le navigateur a fermé la connexion avant la fin de la réponse
            # (requête annulée, onglet fermé...) — sans gravité, on ignore.
            pass

    def copyfile(self, source, outputfile):
        try:
            super().copyfile(source, outputfile)
        except (ConnectionAbortedError, ConnectionResetError, BrokenPipeError):
            # Idem pour les fichiers statiques (index.html, etc.)
            pass

    def log_message(self, format, *args):
        pass  # silence les logs de requêtes dans la console

    def handle_one_request(self):
        try:
            super().handle_one_request()
        except (ConnectionAbortedError, ConnectionResetError, BrokenPipeError):
            pass


class ThreadingServer(socketserver.ThreadingMixIn, socketserver.TCPServer):
    # Gère plusieurs requêtes en parallèle (un navigateur ouvre souvent
    # plusieurs connexions à la fois pour une même page).
    daemon_threads = True
    allow_reuse_address = True


if __name__ == "__main__":
    try:
        httpd = ThreadingServer(("", PORT), Handler)
    except OSError as e:
        print(f"Impossible d'ouvrir le port {PORT} : {e}")
        print(
            "Ce port est probablement réservé par Windows ou déjà utilisé. "
            "Essaie un autre port, par exemple :\n"
            '    $env:DARKWATCH_PORT = "8090"\n'
            "    py server.py"
        )
        sys.exit(1)

    if os.environ.get("DARKWATCH_AUTO_SCAN") == "1":
        threading.Thread(target=auto_scan_loop, daemon=True).start()

    with httpd:
        print(f"DarkWatch dashboard disponible sur : http://localhost:{PORT}")
        print("Ctrl+C pour arrêter.")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            pass
