"""
whatsapp.py — envoi RÉEL et AUTOMATIQUE d'un message WhatsApp pour le serious
game, via GREEN API (https://green-api.com), appelé directement en HTTP avec
urllib (bibliothèque standard, pas besoin d'installer de SDK).

Même principe que httpSMS (smser.py) : ton propre téléphone (avec WhatsApp
installé) sert de passerelle d'envoi. Tu scannes un QR code une seule fois
pour lier ton compte WhatsApp à une "instance" GREEN API gratuite, puis
chaque appel à l'API envoie vraiment le message depuis ce numéro — plus
besoin de cliquer sur un lien et d'appuyer sur "Envoyer" toi-même.

Mise en place (une fois) :
  1. Crée un compte sur https://console.green-api.com (email/Google).
  2. Crée une instance (le plan gratuit "Developer" suffit pour tester).
  3. Dans la console, scanne le QR code affiché avec l'appli WhatsApp de ton
     téléphone (Paramètres > Appareils liés > Lier un appareil) — ton numéro
     devient la passerelle d'envoi, comme le téléphone Android pour httpSMS.
  4. Récupère `idInstance` et `apiTokenInstance` affichés dans la console.
  5. Renseigne GREENAPI_ID_INSTANCE et GREENAPI_API_TOKEN dans .env.

Optionnel par design : si GREENAPI_ID_INSTANCE ou GREENAPI_API_TOKEN ne sont
pas configurés, aucun message n'est envoyé et le jeu reste jouable avec le
message affiché uniquement dans le navigateur — même logique de repli que
GROQ_API_KEY et SMTP_*.

Ton téléphone doit rester allumé et connecté à internet (WhatsApp lié reste
actif même appli fermée, comme WhatsApp Web) pour que les messages partent.
"""

import json
import os
import re
import urllib.error
import urllib.request

GREENAPI_ID_INSTANCE = os.environ.get("GREENAPI_ID_INSTANCE", "")
GREENAPI_API_TOKEN = os.environ.get("GREENAPI_API_TOKEN", "")

API_BASE = os.environ.get("GREENAPI_BASE_URL", "https://api.greenapi.com")


def is_configured() -> bool:
    return bool(GREENAPI_ID_INSTANCE and GREENAPI_API_TOKEN)


def _plain_text(html_body: str) -> str:
    """
    Le corps du scénario (`build_scenario_content`) est écrit en HTML, comme
    pour l'email/SMS. WhatsApp n'affiche pas de balises : on convertit le
    lien `<a href="...">texte</a>` en "texte : url" lisible en clair, remplace
    les <br> par des retours à la ligne, puis retire ce qu'il reste de balises.
    """
    text = re.sub(r'<a\s+href="([^"]+)"[^>]*>([^<]*)</a>', r"\2 : \1", html_body)
    text = text.replace("<br><br>", "\n\n").replace("<br>", "\n")
    text = re.sub(r"<[^>]+>", "", text)
    return text.strip()


# Traduction des chiffres arabes-indiens (٠-٩) et arabes-indiens étendus/persans
# (۰-۹) vers les chiffres ASCII — le clavier du téléphone peut produire ces
# chiffres-là selon la langue système, et le module `re` de Python les
# reconnaît comme des "\d" valides alors que GREEN API attend du 0-9 ASCII
# strict. Sans cette conversion, un numéro tapé avec ce clavier passe la
# regex Python mais est rejeté par GREEN API (chatId invalide).
_DIGIT_TRANSLATION = str.maketrans(
    "٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹",
    "01234567890123456789",
)


def _to_chat_id(to_number: str) -> str:
    """GREEN API attend un identifiant de chat au format '<numéro sans +>@c.us'."""
    normalized = to_number.translate(_DIGIT_TRANSLATION)
    digits = re.sub(r"[^0-9]", "", normalized)  # ASCII strict, pas [^\d] (trop large en Unicode)
    return f"{digits}@c.us"


def send_real_whatsapp(to_number: str, html_body: str) -> tuple[bool, str]:
    """
    Envoie un vrai message WhatsApp via GREEN API (déclenché depuis ton
    téléphone lié). Renvoie toujours (succès, message) plutôt que de lever
    une exception jusqu'en haut — un envoi raté ne doit jamais empêcher la
    tentative de rester jouable en mode "affiché dans le navigateur".
    """
    if not is_configured():
        return False, "GREEN API non configuré dans .env — message non envoyé, affiché dans le navigateur uniquement."

    chat_id = _to_chat_id(to_number)
    digits_only = chat_id.removesuffix("@c.us")
    if len(digits_only) < 8:
        return False, (
            f"Numéro invalide ({to_number!r} → {digits_only!r} après nettoyage) — "
            "attendu au format international, ex. +21612345678."
        )

    payload = json.dumps({
        "chatId": chat_id,
        "message": _plain_text(html_body),
    }).encode("utf-8")

    url = f"{API_BASE}/waInstance{GREENAPI_ID_INSTANCE}/sendMessage/{GREENAPI_API_TOKEN}"
    req = urllib.request.Request(
        url,
        data=payload,
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            resp.read()
        return True, f"Message WhatsApp envoyé à {to_number} (via ton téléphone lié)"
    except urllib.error.HTTPError as e:
        detail = e.read().decode(errors="ignore")
        return False, f"Échec de l'envoi (HTTP {e.code}) : {detail[:200]}"
    except Exception as e:
        return False, f"Échec de l'envoi : {e}"
