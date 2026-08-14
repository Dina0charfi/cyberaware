"""
PhishHunter — Outils de l'agent
=================================
Fonctions que le LLM peut choisir d'appeler lui-même (tool use / function
calling), pour enquêter davantage ou agir sur un email, de façon autonome.

Chaque fonction retourne un dictionnaire simple (sérialisable en JSON),
qui est renvoyé au LLM comme résultat de l'appel d'outil.
"""

from datetime import datetime, timezone
from src.store import memory_store
from src.crisisbot_client import notify_crisisbot

try:
    import whois  # pip install python-whois — interroge directement les serveurs WHOIS, gratuit, sans clé API
    WHOIS_AVAILABLE = True
except ImportError:
    WHOIS_AVAILABLE = False


def check_domain_age(domain: str) -> dict:
    """
    Vérifie depuis quand un domaine existe, via une requête WHOIS directe
    (gratuite, aucune clé API nécessaire). Un domaine très récent (quelques
    jours/semaines) est un signal fort de campagne de phishing.
    """
    if not domain:
        return {"error": "Aucun domaine fourni"}

    if not WHOIS_AVAILABLE:
        return {"error": "Le module python-whois n'est pas installé (pip install python-whois)"}

    try:
        w = whois.whois(domain)
        creation_date = w.creation_date
        if isinstance(creation_date, list):
            creation_date = creation_date[0]

        if creation_date is None:
            return {"domain": domain, "creation_date": None, "age_days": None,
                    "note": "Date de création non disponible pour ce domaine"}

        if creation_date.tzinfo is None:
            creation_date = creation_date.replace(tzinfo=timezone.utc)

        age_days = (datetime.now(timezone.utc) - creation_date).days

        return {
            "domain": domain,
            "creation_date": creation_date.isoformat(),
            "age_days": age_days,
            "note": "Domaine très récent (< 30 jours) : signal fort de phishing" if age_days < 30
                    else ("Domaine récent (< 180 jours) : à surveiller" if age_days < 180
                          else "Domaine établi depuis longtemps")
        }
    except Exception as e:
        return {"error": f"Impossible de vérifier ce domaine : {e}"}


def block_email(email_id: int) -> dict:
    """Bloque définitivement l'email et alerte l'employé concerné. Action finale et irréversible."""
    entry = memory_store.block_email(email_id)
    if entry is None:
        return {"error": f"Email {email_id} introuvable"}
    print(f"[AGENT] Email {email_id} bloqué automatiquement ({entry['sender']})")
    notify_crisisbot(
        source_agent="phishhunter",
        severity="high",
        description=f"Email de phishing bloqué automatiquement — expéditeur {entry['sender']}",
    )
    return {"status": "blocked", "email_id": email_id}


def escalate_to_human(email_id: int, reason: str) -> dict:
    """Envoie le cas à un analyste sécurité humain, pour un cas jugé ambigu. Action finale."""
    entry = memory_store.escalate_email(email_id, reason)
    if entry is None:
        return {"error": f"Email {email_id} introuvable"}
    print(f"[AGENT] Email {email_id} escaladé vers un humain — raison : {reason}")
    notify_crisisbot(
        source_agent="phishhunter",
        severity="medium",
        description=f"Email suspect escaladé pour revue humaine — {reason}",
    )
    return {"status": "escalated", "email_id": email_id, "reason": reason}


def deliver_normally(email_id: int) -> dict:
    """Juge l'email sûr et le laisse suivre son chemin normalement. Action finale."""
    entry = memory_store.mark_delivered(email_id)
    if entry is None:
        return {"error": f"Email {email_id} introuvable"}
    print(f"[AGENT] Email {email_id} jugé sûr, livré normalement")
    return {"status": "delivered", "email_id": email_id}


# ----------------------------------------------------------------------
# Déclaration des outils au format "function calling" compatible OpenAI/Groq
# ----------------------------------------------------------------------
TOOL_DEFINITIONS = [
    {
        "type": "function",
        "function": {
            "name": "check_domain_age",
            "description": (
                "Vérifie depuis quand le domaine expéditeur existe (recherche WHOIS). "
                "Utile quand le domaine est suspect mais ne correspond à aucune marque connue "
                "dans les signaux déjà détectés — un domaine très récent renforce la suspicion."
            ),
            "parameters": {
                "type": "object",
                "properties": {"domain": {"type": "string", "description": "Le nom de domaine à vérifier, ex: example.com"}},
                "required": ["domain"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "block_email",
            "description": "Bloque définitivement l'email et alerte l'employé. À utiliser uniquement pour les cas clairement dangereux.",
            "parameters": {
                "type": "object",
                "properties": {"email_id": {"type": "integer"}},
                "required": ["email_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "escalate_to_human",
            "description": "Envoie le cas à un analyste sécurité humain. À utiliser pour les cas ambigus où tu n'es pas certain.",
            "parameters": {
                "type": "object",
                "properties": {
                    "email_id": {"type": "integer"},
                    "reason": {"type": "string", "description": "Explique brièvement pourquoi ce cas nécessite une revue humaine."},
                },
                "required": ["email_id", "reason"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "deliver_normally",
            "description": "Juge l'email sûr et le laisse suivre son chemin normalement. À utiliser pour les cas clairement sûrs.",
            "parameters": {
                "type": "object",
                "properties": {"email_id": {"type": "integer"}},
                "required": ["email_id"],
            },
        },
    },
]

TOOL_FUNCTIONS = {
    "check_domain_age": check_domain_age,
    "block_email": block_email,
    "escalate_to_human": escalate_to_human,
    "deliver_normally": deliver_normally,
}

# Outils dont l'appel termine la décision de l'agent (une seule action finale par email)
FINAL_ACTION_TOOLS = {"block_email", "escalate_to_human", "deliver_normally"}
