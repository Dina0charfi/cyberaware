"""
actions.py — logique d'action partagée entre l'API (endpoint /isolate,
déclenché par un humain qui clique) et auto_scan.py (boucle autonome qui
décide seule). Centralisée ici pour ne journaliser l'incident et notifier
CrisisBot qu'à un seul endroit, peu importe qui a déclenché l'action.
"""

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from netscope_agent.scorer import human_priority
from netscope_agent.crisisbot_client import notify_crisisbot

BASE_DIR = Path(__file__).resolve().parents[2]
DATA_DIR = BASE_DIR / "data"
USERS_PATH = DATA_DIR / "users.json"
INCIDENTS_PATH = DATA_DIR / "incidents.json"

with open(USERS_PATH, encoding="utf-8") as f:
    USERS = json.load(f)


def get_user_for_host(host: str) -> dict:
    """
    Assigne un utilisateur de façon déterministe à un identifiant de poste,
    pour que le même host retombe toujours sur le même profil (simule une
    jointure avec un vrai annuaire / plateforme de simulation de phishing,
    ex. GoPhish, KnowBe4 — à remplacer par un vrai lookup en production).
    """
    idx = int(hashlib.sha256(host.encode()).hexdigest(), 16) % len(USERS)
    user = dict(USERS[idx])
    user["priority"] = human_priority(user["human_risk_score"])
    return user


def record_isolation(domain: str, user: str, ml_score: float, source: str = "manual") -> dict:
    """
    Journalise l'isolement d'un poste (data/incidents.json) et notifie
    CrisisBot. `source` distingue une action humaine ("manual", depuis le
    bouton du dashboard) d'une décision autonome ("auto_scan").
    """
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    incident = {
        "domain": domain,
        "user": user,
        "ml_score": ml_score,
        "isolated_at": datetime.now(timezone.utc).isoformat(),
        "source": source,
    }

    incidents = []
    if INCIDENTS_PATH.exists():
        with open(INCIDENTS_PATH, encoding="utf-8") as f:
            incidents = json.load(f)
    incidents.append(incident)
    with open(INCIDENTS_PATH, "w", encoding="utf-8") as f:
        json.dump(incidents, f, indent=2, ensure_ascii=False)

    SOURCE_LABELS = {
        "auto_scan": "automatiquement (auto_scan)",
        "webhook": "automatiquement (webhook firewall/proxy)",
    }
    label = SOURCE_LABELS.get(source, "par un analyste")
    notify_crisisbot(
        source_agent="netscope",
        severity="high",
        description=f"Domaine suspect isolé {label} : {domain} (poste de {user}, score ML {ml_score})",
    )

    return {"status": "isolated", **incident}
