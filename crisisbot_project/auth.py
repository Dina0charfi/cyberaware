"""
auth.py — authentification légère partagée par les 6 agents CyberAware.
==========================================================================
Copié à l'identique dans chaque projet (même principe que crisisbot_client.py
déjà dupliqué 5 fois dans ce portfolio) : pas de package partagé entre projets,
pour que chaque agent reste lançable seul, indépendamment des autres.

Principe :
  - UN SEUL compte "démo" (pas de vraie base d'utilisateurs — aucun agent de ce
    portfolio n'a de vraie base de données), identifiants dans l'environnement
    (.env à la racine du projet, chargé par launch_all.py puis propagé à tous
    les sous-process — voir launch_all.py::start_app()). Identifiant = une
    adresse email (CYBERAWARE_ADMIN_EMAIL), pas un pseudo.
  - Session SANS état côté serveur : le cookie lui-même contient
    "email.expiration.signature", signé avec HMAC-SHA256 et un secret partagé
    (CYBERAWARE_SESSION_SECRET). Aucun agent n'a besoin de stocker les sessions
    actives quelque part — chacun peut vérifier un cookie tout seul, même émis
    par un autre agent, tant qu'ils partagent le même secret.
  - Le cookie est posé SANS attribut Domain -> il reste "host-only" pour
    "localhost". Les cookies ne sont pas cloisonnés par PORT (seulement par
    hôte/domaine) : un cookie posé en se connectant sur le port 8000 est donc
    automatiquement envoyé par le navigateur aux ports 8877, 8001, 8002, 8003,
    8878, 8880 aussi — se connecter une fois authentifie les 6 agents.
  - Chaque connexion réussie est journalisée (log_login_event) ET transmise en
    best-effort au VRAI webhook de Sentinel (notify_sentinel_login), pour
    qu'une vraie connexion humaine (pas un événement simulé) puisse être
    scorée par Isolation Forest — hors horaires, nouvel appareil, etc. Voir
    record_login(), appelée par chaque serveur juste après une connexion
    réussie.
  - DÉSACTIVÉ PAR DÉFAUT (CYBERAWARE_AUTH_ENABLED != "1") : si cette variable
    n'est pas définie, AUCUN agent ne demande de connexion — comportement
    strictement identique à avant l'ajout de ce module. Filet de sécurité
    volontaire : si quoi que ce soit se passe mal avec l'auth, il suffit de ne
    pas définir la variable pour retrouver le comportement d'origine.
"""

import hashlib
import hmac
import json
import os
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

AUTH_ENABLED = os.environ.get("CYBERAWARE_AUTH_ENABLED") == "1"
SESSION_SECRET = os.environ.get("CYBERAWARE_SESSION_SECRET", "change-moi-avant-toute-vraie-utilisation")
ADMIN_EMAIL = os.environ.get("CYBERAWARE_ADMIN_EMAIL", "admin@cyberaware.local")
ADMIN_PASSWORD = os.environ.get("CYBERAWARE_ADMIN_PASSWORD", "cyberaware2026")
SESSION_MAX_AGE = 8 * 3600  # 8h — une session expire automatiquement, pas de vraie révocation à gérer côté serveur
COOKIE_NAME = "cw_session"

# Chemin du fichier de log des connexions — idéalement un chemin ABSOLU unique
# défini par launch_all.py (CYBERAWARE_LOGIN_LOG, propagé à tous les
# sous-process), pour que les 6 agents écrivent tous dans le MÊME fichier
# malgré des dossiers de travail différents. Repli sur un fichier local à côté
# de cette copie de auth.py si l'agent est lancé seul, sans launch_all.py.
_LOGIN_LOG_ENV = os.environ.get("CYBERAWARE_LOGIN_LOG")
LOGIN_LOG_PATH = Path(_LOGIN_LOG_ENV) if _LOGIN_LOG_ENV else Path(__file__).parent / "login_history.jsonl"

# Webhook RÉEL de Sentinel (même format que event_simulator.py) — pour que
# chaque vraie connexion humaine soit scorée par le vrai modèle Isolation
# Forest, pas seulement journalisée passivement.
SENTINEL_URL = os.environ.get("CYBERAWARE_SENTINEL_URL", "http://localhost:8003")
SENTINEL_WEBHOOK_SECRET = os.environ.get("SENTINEL_WEBHOOK_SECRET", "change-moi-avant-toute-vraie-utilisation")


def check_credentials(email: str, password: str) -> bool:
    """Comparaison à temps constant (comme hmac.compare_digest déjà utilisé
    sur les secrets webhook de NetScope/Sentinel) pour éviter une fuite
    d'information par mesure de timing sur un identifiant/mot de passe correct."""
    return hmac.compare_digest(email or "", ADMIN_EMAIL) and hmac.compare_digest(password or "", ADMIN_PASSWORD)


def make_session_cookie(email: str) -> str:
    """Construit une valeur de cookie signée : "email.expiration.signature".
    Pas de session stockée côté serveur, tout est auto-contenu dans le cookie."""
    expiry = str(int(time.time()) + SESSION_MAX_AGE)
    payload = f"{email}.{expiry}"
    signature = hmac.new(SESSION_SECRET.encode(), payload.encode(), hashlib.sha256).hexdigest()
    return f"{payload}.{signature}"


def verify_session_cookie(cookie_value: str | None) -> str | None:
    """Retourne l'email si le cookie est valide et non expiré, sinon None.
    Jamais d'exception — un cookie absent/corrompu/expiré est juste traité
    comme "non connecté", jamais comme une erreur serveur."""
    if not cookie_value:
        return None
    # rsplit (pas split) : l'email lui-même peut contenir des points (ex.
    # "admin@cyberaware.local" contient un "." dans le domaine !). Un simple
    # split(".") casserait le cookie en plus de 3 morceaux et ferait échouer
    # la vérification à tous les coups. rsplit(".", 2) découpe seulement les
    # 2 DERNIERS points (expiry et signature ne contiennent jamais de point),
    # donc l'email garde ses points intacts.
    parts = cookie_value.rsplit(".", 2)
    if len(parts) != 3:
        return None
    email, expiry, signature = parts
    payload = f"{email}.{expiry}"
    expected = hmac.new(SESSION_SECRET.encode(), payload.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(signature, expected):
        return None
    try:
        if int(expiry) < int(time.time()):
            return None
    except ValueError:
        return None
    return email


def parse_cookie_header(header_value: str | None) -> dict:
    """Parse minimaliste d'un en-tête Cookie: HTTP — stdlib pure, aucune
    dépendance, pour les 4 agents qui tournent sur http.server (DarkWatch,
    CrisisBot, Serious Game, launch_all.py). Les 3 agents FastAPI (NetScope,
    PhishHunter, Sentinel) utilisent request.cookies, fourni nativement."""
    cookies = {}
    if not header_value:
        return cookies
    for part in header_value.split(";"):
        if "=" in part:
            k, _, v = part.strip().partition("=")
            cookies[k] = v
    return cookies


def log_login_event(email: str, source_agent: str = "unknown") -> None:
    """
    Journalise CHAQUE connexion réussie dans un fichier JSON Lines
    (login_history.jsonl) — une ligne = un événement, format simple à relire
    ou à rejouer plus tard (par exemple vers Sentinel, voir notify_sentinel_login
    ci-dessous, ou pour analyse manuelle). Best-effort : une erreur d'écriture
    (disque plein, permissions...) est ignorée plutôt que de bloquer la connexion.
    """
    entry = {
        "email": email,
        "source_agent": source_agent,  # quel dashboard a vu cette connexion (darkwatch, netscope, launch_all...)
        "at": datetime.now(timezone.utc).isoformat(),
    }
    try:
        with open(LOGIN_LOG_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception as e:
        print(f"[auth] Impossible d'écrire dans le journal de connexions ({e}) — ignoré.")


def notify_sentinel_login(email: str, source_agent: str = "unknown") -> None:
    """
    Transmet CETTE connexion réelle au vrai webhook de Sentinel
    (/api/webhook/signin-event) — donc scorée par le vrai Isolation Forest,
    exactement comme une connexion Entra ID/SIEM réelle (hors horaires,
    nouvel appareil...). Best-effort, même principe que crisisbot_client.py :
    timeout court, toute exception (Sentinel pas lancé, etc.) est avalée
    silencieusement, une connexion ne doit JAMAIS échouer à cause de ça.
    """
    payload = json.dumps({
        "userPrincipalName": email,
        "createdDateTime": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "deviceId": f"login-{source_agent}",
        "department": "",
    }).encode("utf-8")
    url = f"{SENTINEL_URL}/api/webhook/signin-event?x_webhook_secret={SENTINEL_WEBHOOK_SECRET}"
    req = urllib.request.Request(url, data=payload, method="POST", headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=3) as resp:
            resp.read()
    except Exception as e:
        print(f"[auth] Sentinel injoignable pour notifier la connexion de {email} ({e}) — ignoré.")


def record_login(email: str, source_agent: str = "unknown") -> None:
    """Point d'entrée unique appelé par chaque serveur juste après une
    connexion réussie — journalise ET notifie Sentinel."""
    log_login_event(email, source_agent)
    notify_sentinel_login(email, source_agent)


def render_login_page(error: bool = False, brand_accent: str = "2563EB") -> str:
    """Page de connexion générique, même design sur les 7 endroits (charte
    CYBERAWARE déjà partagée par la sidebar 'cwsb' des 6 dashboards)."""
    error_html = (
        '<p class="error">Adresse email ou mot de passe incorrect.</p>' if error else ""
    )
    return f"""<!DOCTYPE html>
<html lang="fr"><head><meta charset="utf-8">
<title>Connexion — CYBERAWARE</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>
  * {{ box-sizing: border-box; }}
  body {{
    margin: 0; min-height: 100vh; display: flex; align-items: center; justify-content: center;
    background: #14181F; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Arial, sans-serif;
  }}
  .card {{ background: #1a1f29; border: 1px solid #262b35; border-radius: 16px; padding: 40px 36px; width: 100%; max-width: 360px; }}
  .brand {{ display: flex; align-items: center; gap: 10px; margin-bottom: 28px; }}
  .logo {{ width: 36px; height: 36px; border-radius: 9px; background: #{brand_accent}; color: #fff; display: flex;
    align-items: center; justify-content: center; font-weight: 700; font-family: ui-monospace, Menlo, monospace; }}
  .brand .name {{ font-weight: 700; font-size: 15px; color: #fff; }}
  .brand .by {{ font-size: 11px; color: #7A8296; }}
  h1 {{ font-size: 18px; color: #fff; margin: 0 0 4px; }}
  p.sub {{ color: #7A8296; font-size: 13px; margin: 0 0 24px; }}
  label {{ display: block; font-size: 12.5px; font-weight: 600; color: #C7CCD6; margin: 14px 0 6px; }}
  input {{ width: 100%; padding: 11px 12px; border-radius: 8px; border: 1px solid #262b35; background: #14181F;
    color: #fff; font-size: 14px; }}
  input:focus {{ outline: 2px solid #{brand_accent}; border-color: #{brand_accent}; }}
  button {{ margin-top: 22px; width: 100%; background: #{brand_accent}; color: #fff; border: none; border-radius: 9px;
    padding: 12px; font-size: 14px; font-weight: 700; cursor: pointer; }}
  button:hover {{ opacity: 0.9; }}
  .error {{ background: #3a1414; border: 1px solid #5c1f1f; color: #ff8a8a; border-radius: 8px; padding: 10px 12px;
    font-size: 13px; margin: 0 0 4px; }}
</style></head>
<body>
  <form class="card" method="POST" action="/login">
    <div class="brand">
      <div class="logo">CA</div>
      <div><div class="name">CYBERAWARE</div><div class="by">by Hydatis</div></div>
    </div>
    <h1>Connexion</h1>
    <p class="sub">Espace client — Banque ABC</p>
    {error_html}
    <label for="email">Adresse email</label>
    <input id="email" name="email" type="email" autofocus required>
    <label for="password">Mot de passe</label>
    <input id="password" name="password" type="password" required>
    <button type="submit">Se connecter</button>
  </form>
</body></html>"""
