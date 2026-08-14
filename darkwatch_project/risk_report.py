"""
risk_report.py — génération du rapport d'incident
====================================================

Ce module transforme les données brutes de l'API breach-analytics de
XposedOrNot en un rapport lisible, façon "brief pour le CISO" comme dans
la démo CyberAware.

Important pour la soutenance : ceci n'est PAS un modèle de machine
learning. Le score de risque ("risk_score" / "risk_label") est calculé
par l'API XposedOrNot elle-même, gratuitement, à partir de règles connues
(type de donnée exposée, force du hachage du mot de passe, etc.). Ce
module se contente de mettre en forme ces données en français.

Couche IA générative (optionnelle) : si la variable d'environnement
GROQ_API_KEY est configurée (voir llm_summary.py), le rapport inclut en
plus un résumé rédigé par un LLM gratuit (Groq). Sans clé configurée, le
rapport reste 100% fonctionnel avec seulement le template ci-dessous —
rien ne casse si tu n'as pas encore configuré l'IA.
"""

from datetime import datetime, timezone

from llm_summary import generate_summary, is_configured


def _extract_risk(analytics: dict) -> tuple[str, int]:
    """Lit le score de risque renvoyé par XposedOrNot (déjà calculé, gratuit)."""
    metrics = analytics.get("BreachMetrics") or {}
    risk = metrics.get("risk") or [{}]
    risk0 = risk[0] if risk else {}
    return risk0.get("risk_label", "Inconnu"), risk0.get("risk_score", 0)


def _extract_exposed_types(analytics: dict) -> list[str]:
    """Liste les types de données exposées (mots de passe, emails, etc.)."""
    details = (analytics.get("ExposedBreaches") or {}).get("breaches_details") or []
    types = set()
    for d in details:
        for t in d.get("xposed_data", "").split(";"):
            if t.strip():
                types.add(t.strip())
    return sorted(types)


def build_report(email: str, new_breaches: set[str], analytics: dict) -> str:
    """Construit le rapport texte affiché lors d'une détection.

    Essaie d'abord le résumé généré par LLM (si GROQ_API_KEY est
    configurée) et retombe automatiquement sur le rapport template si
    la clé est absente ou si l'appel échoue (pas de connexion, quota
    dépassé, etc.).
    """
    risk_label, risk_score = _extract_risk(analytics)
    exposed_types = _extract_exposed_types(analytics)
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    lines = []
    lines.append("\n🌑 FUITE DÉTECTÉE")
    lines.append(f"Compte concerné : {email}")
    lines.append(f"Détecté le      : {now}")
    lines.append(f"Nouvelle(s) fuite(s) : {', '.join(sorted(new_breaches))}")
    lines.append(f"Niveau de risque estimé : {risk_label} (score {risk_score}/10, calculé par XposedOrNot)")
    if exposed_types:
        lines.append(f"Données exposées : {', '.join(exposed_types)}")

    if is_configured():
        ai_text = generate_summary(email, sorted(new_breaches), analytics)
        if ai_text:
            lines.append("\n🤖 Résumé IA (Groq / llama-3.3-70b) :")
            lines.append(ai_text)
        else:
            lines.append("Action recommandée : forcer la réinitialisation du mot de passe de ce compte.")
    else:
        lines.append("Action recommandée : forcer la réinitialisation du mot de passe de ce compte.")

    return "\n".join(lines)
