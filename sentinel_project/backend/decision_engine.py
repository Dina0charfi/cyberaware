"""
Configuration et moteur de décision — version adaptée au modèle CERT réduit
(7 features universelles, réutilisable directement sur Entra ID/Google).
"""

TUNISIA_CONFIG = {
    "departements_sensibles": [
        "Direction Generale", "Conformite", "Direction Financiere",
        "Direction des Systemes d'Information",
    ],
}


def is_sensitive_department(department: str) -> bool:
    return department in TUNISIA_CONFIG["departements_sensibles"]


def decide_action(risk_score: int, sensitive: bool) -> str:
    t_monitor = 25 if not sensitive else 15
    t_train = 55 if not sensitive else 40
    t_escalate = 85 if not sensitive else 65

    if risk_score < t_monitor:
        return "no_action"
    elif risk_score < t_train:
        return "monitor"
    elif risk_score < t_escalate:
        return "trigger_training"
    else:
        return "escalate_to_human"


ACTION_LABELS = {
    "no_action": "Aucune action",
    "monitor": "Sous surveillance",
    "trigger_training": "Formation ciblée assignée automatiquement",
    "escalate_to_human": "Escaladé à un analyste sécurité",
}


def generate_description(features: dict, sensitive: bool) -> str:
    raisons = []
    if features.get("is_off_hours"):
        raisons.append(f"connexion hors horaires habituels ({features['hour']}h)")
    if features.get("is_new_device"):
        raisons.append("depuis un poste/appareil non habituel pour cet utilisateur")
    if features.get("is_weekend"):
        raisons.append("le week-end")
    if features.get("is_holiday"):
        raisons.append("un jour férié")
    if sensitive:
        raisons.append("dans un département sensible")

    if not raisons:
        return "Aucun signal particulier détecté."
    return "Connexion signalée : " + ", ".join(raisons) + "."