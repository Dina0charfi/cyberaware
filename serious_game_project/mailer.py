"""
mailer.py — envoi RÉEL d'email pour le serious game, via SMTP standard
(stdlib smtplib + email), sans dépendance externe à installer.

Optionnel par design : si SMTP_HOST/SMTP_USER/SMTP_PASSWORD ne sont pas
configurés dans .env, aucun email n'est envoyé et le jeu reste jouable avec
le message affiché uniquement dans le navigateur (comportement précédent) —
même logique de repli que GROQ_API_KEY pour la narration.

Pour Gmail : utiliser un "mot de passe d'application" généré sur
https://myaccount.google.com/apppasswords (nécessite la validation en 2
étapes activée sur le compte) — JAMAIS le vrai mot de passe du compte. Ce
fichier ne voit et ne transmet que ce que TOI tu mets dans ton .env local ;
rien n'est envoyé ailleurs qu'au serveur SMTP que tu configures toi-même.
"""

import os
import smtplib
import ssl
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

SMTP_HOST = os.environ.get("SMTP_HOST", "")
SMTP_PORT = int(os.environ.get("SMTP_PORT", "587"))
SMTP_USER = os.environ.get("SMTP_USER", "")
SMTP_PASSWORD = os.environ.get("SMTP_PASSWORD", "")
SMTP_FROM_NAME = os.environ.get("SMTP_FROM_NAME", "Simulation CyberAware")


def is_configured() -> bool:
    return bool(SMTP_HOST and SMTP_USER and SMTP_PASSWORD)


def send_real_email(to_address: str, subject: str, html_body: str) -> tuple[bool, str]:
    """
    Envoie un vrai email via le compte SMTP configuré dans .env. Renvoie
    toujours (succès, message) plutôt que de lever une exception jusqu'en
    haut — un envoi raté ne doit jamais empêcher la tentative de rester
    jouable en mode "affiché dans le navigateur seulement".
    """
    if not is_configured():
        return False, "SMTP non configuré dans .env — email non envoyé, message affiché dans le navigateur uniquement."

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = f"{SMTP_FROM_NAME} <{SMTP_USER}>"
    msg["To"] = to_address
    msg.attach(MIMEText(html_body, "html"))

    try:
        context = ssl.create_default_context()
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=10) as server:
            server.starttls(context=context)
            server.login(SMTP_USER, SMTP_PASSWORD)
            server.sendmail(SMTP_USER, [to_address], msg.as_string())
        return True, f"Email envoyé à {to_address}"
    except Exception as e:
        return False, f"Échec de l'envoi : {e}"
