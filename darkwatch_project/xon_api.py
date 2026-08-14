"""
xon_api.py — petit client pour l'API gratuite XposedOrNot
============================================================

Regroupe les deux appels API utilisés par le projet, pour que
`darkwatch.py` (script CLI) et `server.py` (dashboard web) partagent le
même code au lieu de le dupliquer.

Aucune clé API, aucune dépendance externe : uniquement `urllib`, qui
fait partie de la bibliothèque standard de Python.
"""

import json
import urllib.parse
import urllib.request
import urllib.error

CHECK_EMAIL_URL = "https://api.xposedornot.com/v1/check-email/{email}"
ANALYTICS_URL = "https://api.xposedornot.com/v1/breach-analytics?email={email}"


class RateLimitError(Exception):
    """Levée quand on dépasse le quota gratuit de XposedOrNot (429)."""
    pass


def _get_json(url: str) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": "DarkWatch-Free/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return {}
        if e.code == 429:
            raise RateLimitError(
                "Quota gratuit dépassé (2 req/sec, 25/heure, 100/jour). "
                "Attends quelques minutes puis réessaie."
            )
        raise


def check_email(email: str) -> list[str]:
    """Retourne la liste des fuites connues pour cet email (vide si aucune)."""
    # L'email est encodé pour l'URL (urllib.parse.quote) — sans ça, un email
    # contenant un "+" ou un autre caractère spécial (courant en pratique,
    # ex. "user+test@gmail.com") cassait silencieusement la requête.
    data = _get_json(CHECK_EMAIL_URL.format(email=urllib.parse.quote(email)))
    if data.get("status") != "success":
        return []
    breaches = data.get("breaches", [[]])
    return breaches[0] if breaches else []


def get_analytics(email: str) -> dict:
    """Retourne le détail des fuites + score de risque calculé par l'API."""
    return _get_json(ANALYTICS_URL.format(email=urllib.parse.quote(email)))
