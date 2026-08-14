"""
notifications.py — envoi RÉEL de notifications (Slack, pour l'instant),
en plus de la trace simulée déjà présente dans server.py.

Sans SLACK_WEBHOOK_URL configurée, cette fonction ne fait rien de réel —
CrisisBot reste entièrement fonctionnel en mode simulé, exactement comme
les autres agents sans clé API (GROQ_API_KEY, HF_TOKEN).

Créer un webhook Slack (gratuit, 5 minutes) :
  1. https://api.slack.com/apps -> "Create New App" -> "From scratch"
  2. Section "Incoming Webhooks" -> l'activer -> "Add New Webhook to Workspace"
  3. Choisir le canal, copier l'URL (https://hooks.slack.com/services/...)

Configuration (PowerShell) :
  $env:SLACK_WEBHOOK_URL = "https://hooks.slack.com/services/xxx/yyy/zzz"
  py server.py

Teams et Email suivraient exactement le même principe (une fonction
send_teams_notification / send_email_notification, avec leur propre
variable d'environnement) — pas encore branchés, à ajouter au besoin.
"""

import json
import os
import urllib.request
import urllib.error

SLACK_WEBHOOK_URL = os.environ.get("SLACK_WEBHOOK_URL")


def is_slack_configured() -> bool:
    return bool(SLACK_WEBHOOK_URL)


def send_slack_notification(text: str) -> bool:
    """Retourne True si le message a VRAIMENT été envoyé sur Slack, False sinon (jamais d'exception)."""
    if not SLACK_WEBHOOK_URL:
        return False

    payload = json.dumps({"text": text}).encode("utf-8")
    req = urllib.request.Request(
        SLACK_WEBHOOK_URL,
        data=payload,
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=8) as resp:
            resp.read()
        return True
    except Exception as e:
        print(f"[notifications] Envoi Slack échoué : {e}")
        return False
