"""
crisisbot_client.py — notifie CrisisBot quand CET agent détecte quelque chose
d'assez grave pour déclencher une réponse à incident.

Appel "best-effort" : si CrisisBot n'est pas lancé (ou indisponible), cet
appel échoue silencieusement (timeout court) — il ne doit JAMAIS bloquer ni
faire planter l'agent appelant. C'est volontairement une copie identique
dans chaque projet plutôt qu'un package partagé, pour que chaque agent
reste indépendant et lançable seul.
"""

import json
import os
import urllib.request
import urllib.error

CRISISBOT_URL = os.environ.get("CRISISBOT_URL", "http://localhost:8878/api/webhook/incident")


def notify_crisisbot(source_agent: str, severity: str, description: str) -> bool:
    """Retourne True si CrisisBot a bien reçu la notification, False sinon (jamais d'exception)."""
    payload = json.dumps({
        "source_agent": source_agent,
        "severity": severity,
        "description": description,
    }).encode("utf-8")
    req = urllib.request.Request(
        CRISISBOT_URL,
        data=payload,
        method="POST",
        headers={"Content-Type": "application/json", "User-Agent": f"{source_agent}/1.0"},
    )
    try:
        with urllib.request.urlopen(req, timeout=3) as resp:
            resp.read()
        return True
    except Exception as e:
        print(f"[crisisbot_client] CrisisBot injoignable depuis {source_agent} ({e}) — ignoré.")
        return False
