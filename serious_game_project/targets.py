"""
targets.py — profils fictifs des employés de "Banque ABC" pour le serious game.

Les scores de risque et le nombre de modules complétés viennent de la
capture d'écran fournie par l'utilisateur (données déjà arrondies/fictives,
pas connectées à une vraie plateforme de formation pour l'instant). Voir
README.md de ce projet pour comment brancher de vraies données plus tard.
"""

from datetime import datetime, timezone

TARGETS = [
    {"id": "sarra",   "name": "Sarra B.",   "dept": "Finance",    "risk": 22, "modules_done": 8, "modules_total": 9},
    {"id": "mehdi",    "name": "Mehdi T.",   "dept": "Agences",    "risk": 74, "modules_done": 3, "modules_total": 9},
    {"id": "nour",     "name": "Nour H.",    "dept": "Direction",  "risk": 15, "modules_done": 8, "modules_total": 9},
    {"id": "youssef",  "name": "Youssef R.", "dept": "Agences",    "risk": 66, "modules_done": 3, "modules_total": 9},
    {"id": "ines",     "name": "Ines M.",    "dept": "Commercial", "risk": 30, "modules_done": 6, "modules_total": 9},
    {"id": "rania",    "name": "Rania S.",   "dept": "Agences",    "risk": 45, "modules_done": 5, "modules_total": 9},
    {"id": "karim",    "name": "Karim L.",   "dept": "Agences",    "risk": 70, "modules_done": 2, "modules_total": 9},
    {"id": "fatma",    "name": "Fatma Z.",   "dept": "Agences",    "risk": 52, "modules_done": 4, "modules_total": 9},
    {"id": "walid",    "name": "Walid B.",   "dept": "Commercial", "risk": 28, "modules_done": 5, "modules_total": 9},
    {"id": "yassine",  "name": "Yassine H.", "dept": "IT",         "risk": 12, "modules_done": 8, "modules_total": 9},
    {"id": "salma",    "name": "Salma G.",   "dept": "RH",         "risk": 40, "modules_done": 5, "modules_total": 9},
]

TARGETS_BY_ID = {t["id"]: t for t in TARGETS}

# Copie figée des risques de départ, pour pouvoir tout remettre à zéro
# (voir /api/campaign/reset dans server.py) sans redémarrer le serveur.
INITIAL_RISK_BY_ID = {t["id"]: t["risk"] for t in TARGETS}

# Bornes appliquées après chaque tentative : le risque ne doit jamais
# atteindre 0 (personne n'est totalement infaillible) ni 100 (personne
# n'est totalement une passoire) — même logique que compute_success_probability.
MIN_RISK = 5
MAX_RISK = 95

# --------------------------------------------------------------------------
# Modèle d'action à 4 états, inspiré d'un vrai outil de simulation de
# phishing (genre KnowBe4/Proofpoint) : l'employé ne "réussit" ou n'"échoue"
# pas seulement en binaire, son comportement a une nuance.
#
#   clicked  -> est tombé dans le piège (a cliqué / suivi l'instruction) : le SEUL état d'échec réel.
#   opened   -> a ouvert / regardé, mais s'est arrêté avant d'agir : prudence partielle.
#   ignored  -> n'a pas réagi du tout : ne s'est pas fait avoir, mais n'a pas non plus alerté qui que ce soit.
#   reported -> a activement signalé la tentative : la meilleure réaction possible.
#
# IMPORTANT — depuis la version "vrai lien trackable" (voir attempts.py),
# ce ne sont plus des tirages au sort qui décident de l'action : "clicked"
# vient d'un vrai clic sur le lien de /track/<token> (une vraie requête HTTP),
# et "reported"/"ignored" viennent d'un vrai bouton cliqué dans l'interface.
# "opened" reste défini ici pour la cohérence du schéma mais n'est pas encore
# atteignable par une action réelle — réservé pour un futur flux "aperçu du
# lien avant de cliquer".
# --------------------------------------------------------------------------
ACTIONS = ("clicked", "opened", "ignored", "reported")

ACTION_META = {
    "clicked":  {"label": "A cliqué sur le lien / suivi l'instruction", "verdict": "fail",    "icon": "🖱️"},
    "opened":   {"label": "A regardé mais s'est arrêté avant d'agir",   "verdict": "partial", "icon": "👀"},
    "ignored":  {"label": "N'a pas réagi",                              "verdict": "partial", "icon": "🙈"},
    "reported": {"label": "A signalé la tentative",                    "verdict": "success",  "icon": "🚩"},
}

# Le risque bouge différemment selon la NATURE de la réaction, pas juste
# selon un succès/échec binaire : signaler activement fait baisser le risque
# bien plus qu'ignorer passivement (même si les deux "échouent" l'attaque),
# et cliquer est la seule réaction qui le fait vraiment remonter.
ACTION_RISK_DELTA = {
    "clicked": 6,
    "opened": -3,
    "ignored": -1,
    "reported": -6,
}


def is_attacker_success(action: str) -> bool:
    """Du point de vue du pentester (le joueur) : seule 'clicked' compte comme une réussite."""
    return action == "clicked"


def apply_attack_outcome(target: dict, action: str) -> int:
    """
    Met à jour le risque de la cible selon l'action observée et renvoie la
    nouvelle valeur. Modifie `target` en place (le même dict que celui
    référencé dans TARGETS et TARGETS_BY_ID, donc l'état reste cohérent
    partout où la cible est lue).
    """
    delta = ACTION_RISK_DELTA[action]
    target["risk"] = max(MIN_RISK, min(MAX_RISK, target["risk"] + delta))
    return target["risk"]


def reset_all_risks() -> None:
    """Remet chaque cible à son risque de départ (utilisé par /api/campaign/reset)."""
    for target in TARGETS:
        target["risk"] = INITIAL_RISK_BY_ID[target["id"]]


# --------------------------------------------------------------------------
# Historique des tentatives — en mémoire, comme le compteur de campagne dans
# server.py. Une entrée par tentative, pour reconstruire "combien de fois
# Karim a échoué au phishing" comme dans l'exemple du document de référence.
# --------------------------------------------------------------------------
ATTEMPT_LOG: list[dict] = []


def record_attempt(target_id: str, vector_key: str, action: str) -> dict:
    entry = {
        "target_id": target_id,
        "vector": vector_key,
        "action": action,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    ATTEMPT_LOG.append(entry)
    return entry


def get_target_history(target_id: str) -> list[dict]:
    """Historique chronologique (du plus ancien au plus récent) pour une cible."""
    return [e for e in ATTEMPT_LOG if e["target_id"] == target_id]


def get_target_stats(target_id: str) -> dict:
    """
    Agrège l'historique par vecteur, ex. {"phishing": {"attempts": 3, "clicked": 2,
    "opened": 0, "ignored": 0, "reported": 1}} — sert à afficher "2 échecs / 3" comme
    dans l'exemple du document de référence, vecteur par vecteur.
    """
    stats: dict = {}
    for entry in get_target_history(target_id):
        v = stats.setdefault(entry["vector"], {"attempts": 0, "clicked": 0, "opened": 0, "ignored": 0, "reported": 0})
        v["attempts"] += 1
        v[entry["action"]] += 1
    return stats


def get_global_vector_stats() -> dict:
    """
    Comme `get_target_stats`, mais agrégé sur TOUTES les cibles à la fois —
    utile pour une lecture "campagne de sensibilisation" plutôt que "par
    employé" : ex. combien de personnes au total ont cliqué sur le QR code,
    combien ont rempli le faux formulaire de gain, tous employés confondus.
    """
    stats: dict = {}
    for entry in ATTEMPT_LOG:
        v = stats.setdefault(entry["vector"], {"attempts": 0, "clicked": 0, "opened": 0, "ignored": 0, "reported": 0})
        v["attempts"] += 1
        v[entry["action"]] += 1
    return stats


def reset_history() -> None:
    """Vide l'historique (utilisé par /api/campaign/reset)."""
    ATTEMPT_LOG.clear()


# Chaque vecteur a un poids qui module la probabilité de réussite par
# rapport au score de risque brut de la cible — reflète qu'à score de
# risque égal, tous les vecteurs d'attaque ne sont pas aussi efficaces
# en moyenne (l'appât "gain immédiat" du faux formulaire joue sur la
# pression émotionnelle).
VECTORS = {
    "phishing": {
        "label": "Email de phishing ciblé",
        "icon": "📧",
        "weight": 1.0,
        "agent": "PhishHunter",
        "defense_note": (
            "PhishHunter analyse ce type d'email en temps réel (score ML + "
            "explication SHAP) avant même qu'il n'atteigne la boîte de réception."
        ),
    },
    "whatsapp": {
        "label": "Message WhatsApp frauduleux",
        "icon": "🟢",
        "weight": 1.1,
        "agent": "PhishHunter",
        "defense_note": (
            "PhishHunter analyse le texte du message pour repérer l'urgence "
            "artificielle et l'usurpation de marque — les mêmes signaux "
            "s'appliquent à un message WhatsApp qu'à un SMS ou un email, le "
            "canal ne change pas l'analyse du contenu."
        ),
    },
    "loterie": {
        "label": "Faux formulaire \"Vous avez gagné 20 000 DT\"",
        "icon": "🎉",
        "weight": 1.2,
        "agent": "Sentinel",
        "defense_note": (
            "Une victime qui remplit ce type de formulaire déclenche souvent "
            "juste après une connexion ou une opération inhabituelle sur ses "
            "comptes — c'est ce que Sentinel est conçu pour repérer, pas le "
            "formulaire lui-même."
        ),
    },
    "qrcode": {
        "label": "QR code piégé (quishing)",
        "icon": "🔳",
        "weight": 1.05,
        "agent": "NetScope",
        "defense_note": (
            "Un QR code piégé redirige vers un domaine malveillant — c'est "
            "exactement le type de requête DNS suspecte que NetScope est "
            "entraîné à détecter, même sur un domaine jamais vu auparavant."
        ),
    },
}


def compute_success_probability(risk: float, vector_key: str) -> float:
    """
    Probabilité ESTIMÉE = score de risque de la cible × poids du vecteur,
    plafonnée entre 2% et 95%. Depuis la version "vrai lien trackable", cette
    valeur n'est plus utilisée pour tirer le résultat au sort — elle est
    seulement affichée à titre indicatif avant l'envoi de la simulation (voir
    attempts.py, start_attempt) ; le résultat réel dépend d'un vrai clic ou
    d'un vrai choix explicite dans l'interface.
    """
    weight = VECTORS[vector_key]["weight"]
    raw = (risk / 100.0) * weight
    return max(0.02, min(0.95, raw))
