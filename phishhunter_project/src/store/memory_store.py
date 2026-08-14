"""
PhishHunter — Store en mémoire des emails analysés
=====================================================
Stocke le résultat de chaque analyse (via /analyze ou /webhook/email) pour
que le dashboard puisse les afficher. Volontairement simple (liste Python
en mémoire) pour ce projet — à remplacer par une vraie base de données
(PostgreSQL) en production, car ce store est vidé à chaque redémarrage
du serveur.
"""

import itertools
from datetime import datetime, timezone

_emails: list[dict] = []
_id_counter = itertools.count(1)


def add_email(sender: str, subject: str, body: str, analysis: dict, source: str = "manual") -> dict:
    """Ajoute un email analysé au store et retourne l'entrée créée."""
    entry = {
        "id": next(_id_counter),
        "sender": sender,
        "subject": subject or "(sans objet)",
        "body": body,
        "received_at": datetime.now(timezone.utc).isoformat(),
        "source": source,  # "manual" (via /analyze) ou "webhook"
        "blocked": False,
        "escalated": False,
        "escalation_reason": None,
        "agent_status": "pending",   # pending | delivered | blocked | escalated
        "agent_trace": [],           # liste des actions/outils utilisés par l'agent
        **analysis,  # risk_score, classification, sender_domain, explanation, triggered_signals
    }
    _emails.insert(0, entry)  # les plus récents en premier
    return entry


def list_emails() -> list[dict]:
    """Retourne la liste résumée des emails (sans le corps complet), triée par date décroissante."""
    return [
        {
            "id": e["id"],
            "sender": e["sender"],
            "subject": e["subject"],
            "risk_score": e["risk_score"],
            "classification": e["classification"],
            "received_at": e["received_at"],
            "blocked": e["blocked"],
        }
        for e in _emails
    ]


def get_email(email_id: int) -> dict | None:
    """Retourne le détail complet d'un email par son id, ou None si introuvable."""
    for e in _emails:
        if e["id"] == email_id:
            return e
    return None


def block_email(email_id: int) -> dict | None:
    """Marque un email comme bloqué (action déclenchée par le bouton du dashboard, ou par l'agent)."""
    entry = get_email(email_id)
    if entry:
        entry["blocked"] = True
        entry["agent_status"] = "blocked"
    return entry


def escalate_email(email_id: int, reason: str) -> dict | None:
    """Marque un email comme escaladé vers un analyste humain (action de l'agent)."""
    entry = get_email(email_id)
    if entry:
        entry["escalated"] = True
        entry["escalation_reason"] = reason
        entry["agent_status"] = "escalated"
    return entry


def mark_delivered(email_id: int) -> dict | None:
    """Marque un email comme jugé sûr et délivré normalement (action de l'agent)."""
    entry = get_email(email_id)
    if entry:
        entry["agent_status"] = "delivered"
    return entry


def set_agent_trace(email_id: int, trace: list) -> dict | None:
    """Enregistre la trace des outils utilisés par l'agent pour ce mail."""
    entry = get_email(email_id)
    if entry:
        entry["agent_trace"] = trace
    return entry


def clear_all():
    """Vide le store (utile pour les tests/démos)."""
    _emails.clear()
