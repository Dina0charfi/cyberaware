"""
smser.py — envoi RÉEL de SMS pour le serious game, via httpSMS
(https://httpsms.com), appelé directement en HTTP avec urllib (bibliothèque
standard, pas besoin d'installer de SDK).

httpSMS transforme ton propre téléphone Android en passerelle SMS : l'API
déclenche une notification push vers l'app Android installée sur ton
téléphone, qui envoie le SMS avec ta vraie carte SIM. Contrairement à
Twilio, la création de compte httpSMS ne nécessite PAS de vérifier un numéro
de téléphone (juste email/Google) — ça évite le blocage rencontré avec
Twilio sur les numéros tunisiens (erreur 0x07 à la création de compte).

Mise en place (une fois) :
  1. Installe l'app Android : https://github.com/NdoleStudio/httpsms/releases/latest/download/HttpSms.apk
  2. Crée un compte sur https://httpsms.com (email/Google, pas de vérif téléphone)
  3. Dans l'app, connecte-toi avec le même compte — ton numéro de téléphone
     apparaît automatiquement une fois l'app autorisée à envoyer des SMS.
  4. Récupère ta clé API sur https://httpsms.com/settings
  5. Renseigne HTTPSMS_API_KEY et HTTPSMS_FROM_NUMBER (ton numéro, format
     international, ex. +21612345678 — doit correspondre exactement au
     numéro affiché dans l'app) dans .env.

Optionnel par design : si HTTPSMS_API_KEY ou HTTPSMS_FROM_NUMBER ne sont pas
configurés, aucun SMS n'est envoyé et le jeu reste jouable avec le message
affiché uniquement dans le navigateur — même logique de repli que
GROQ_API_KEY et SMTP_*.
"""

import json
import os
import re
import urllib.error
import urllib.request

HTTPSMS_API_KEY = os.environ.get("HTTPSMS_API_KEY", "")
HTTPSMS_FROM_NUMBER = os.environ.get("HTTPSMS_FROM_NUMBER", "")

API_URL = "https://api.httpsms.com/v1/messages/send"


def is_configured() -> bool:
    return bool(HTTPSMS_API_KEY and HTTPSMS_FROM_NUMBER)


def _plain_text(html_body: str) -> str:
    """
    Le corps du scénario (`build_scenario_content`) est écrit en HTML, comme
    pour l'email. Un SMS n'affiche pas de balises : on convertit le lien
    `<a href="...">texte</a>` en "texte : url" lisible en clair, remplace les
    <br> par des retours à la ligne, puis retire ce qu'il reste de balises.
    """
    text = re.sub(r'<a\s+href="([^"]+)"[^>]*>([^<]*)</a>', r"\2 : \1", html_body)
    text = text.replace("<br><br>", "\n\n").replace("<br>", "\n")
    text = re.sub(r"<[^>]+>", "", text)
    return text.strip()


def send_real_sms(to_number: str, html_body: str) -> tuple[bool, str]:
    """
    Envoie un vrai SMS via httpSMS (déclenche l'envoi depuis ton téléphone
    Android). Renvoie toujours (succès, message) plutôt que de lever une
    exception jusqu'en haut — un envoi raté ne doit jamais empêcher la
    tentative de rester jouable en mode "affiché dans le navigateur".
    """
    if not is_configured():
        return False, "httpSMS non configuré dans .env — SMS non envoyé, message affiché dans le navigateur uniquement."

    payload = json.dumps({
        "content": _plain_text(html_body),
        "from": HTTPSMS_FROM_NUMBER,
        "to": to_number,
    }).encode("utf-8")

    req = urllib.request.Request(
        API_URL,
        data=payload,
        method="POST",
        headers={
            "x-api-key": HTTPSMS_API_KEY,
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            resp.read()
        return True, f"SMS envoyé à {to_number} (via ton téléphone Android)"
    except urllib.error.HTTPError as e:
        detail = e.read().decode(errors="ignore")
        return False, f"Échec de l'envoi (HTTP {e.code}) : {detail[:200]}"
    except Exception as e:
        return False, f"Échec de l'envoi : {e}"
