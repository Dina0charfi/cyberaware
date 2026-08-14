"""
Génère une explication et une recommandation en langage naturel à partir des
données DÉJÀ calculées par le pipeline (score ML, facteurs SHAP, profil de
risque humain). Le LLM ne reclasse jamais l'alerte lui-même — il rédige
uniquement une synthèse de ce qu'on lui fournit.

Utilise l'API Groq (gratuite, hébergée — pas d'installation locale, contrairement
à Ollama) si une clé est configurée. Sinon, retombe sur un texte généré par
template à partir des vraies données — pas d'IA générative dans ce cas, mais
toujours fonctionnel et 100% gratuit.

Clé gratuite : https://console.groq.com/keys
"""

import json
import os

import requests

GROQ_API_KEY = os.environ.get("GROQ_API_KEY")
GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
GROQ_MODEL = os.environ.get("GROQ_MODEL", "llama-3.1-8b-instant")

SYSTEM_PROMPT = """Tu es un assistant qui rédige des synthèses courtes pour un \
analyste SOC (Security Operations Center). Tu reçois les résultats déjà \
calculés d'un modèle de détection DNS : un score de risque, les facteurs qui \
ont pesé dans la décision (issus d'une analyse SHAP), et le profil de risque \
humain de l'utilisateur du poste.

Règles strictes :
- Ne jamais inventer de données absentes du JSON fourni.
- Ne jamais reclasser l'alerte (suspect/normal) : c'est déjà décidé en amont.
- Rester factuel et concis, ton d'analyste, pas de superlatifs inutiles.
- Répondre UNIQUEMENT en JSON valide avec exactement deux clés :
  "explanation" (1-2 phrases expliquant pourquoi ce domaine est suspect, en \
te basant sur les facteurs fournis) et "recommendation" (1 phrase d'action \
concrète et réaliste pour l'analyste). Pas de texte avant ou après le JSON."""


def _template_fallback(incident: dict) -> dict:
    """
    Génère explication + recommandation sans LLM, uniquement à partir des
    vraies données (facteurs SHAP, score, profil). Utilisé quand Groq n'est
    pas disponible (pas de clé, quota dépassé, erreur réseau) — reste honnête,
    pas de texte inventé.
    """
    factors = incident.get("factors", [])
    increasing = [f["label"] for f in factors if f.get("direction") == "increase"]

    if increasing:
        factors_text = ", ".join(increasing[:3]).lower()
        explanation = (
            f"Le domaine {incident.get('domain', 'observé')} obtient un score de "
            f"risque de {incident.get('ml_score', '?')}/100 ({incident.get('risk_level', '?')}), "
            f"principalement en raison de : {factors_text}."
        )
    else:
        explanation = (
            f"Le domaine {incident.get('domain', 'observé')} obtient un score de "
            f"risque de {incident.get('ml_score', '?')}/100 ({incident.get('risk_level', '?')})."
        )

    user = incident.get("user", {})
    priority = user.get("priority", "faible")
    if priority == "élevée":
        recommendation = "Isoler le poste et lancer une investigation prioritaire, le facteur humain aggrave le risque."
    elif priority == "moyenne":
        recommendation = "Vérifier le poste et le contexte utilisateur avant de décider d'un isolement."
    else:
        recommendation = "Investiguer le trafic réseau indépendamment du profil utilisateur, qui n'aggrave pas le risque ici."

    return {"explanation": explanation, "recommendation": recommendation}


def generate_explanation(incident: dict) -> dict:
    if not GROQ_API_KEY:
        return _template_fallback(incident)

    try:
        response = requests.post(
            GROQ_URL,
            headers={
                "Authorization": f"Bearer {GROQ_API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "model": GROQ_MODEL,
                "messages": [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": json.dumps(incident, ensure_ascii=False)},
                ],
                "response_format": {"type": "json_object"},
                "temperature": 0.3,
                "max_tokens": 300,
            },
            timeout=15,
        )
        response.raise_for_status()
        text = response.json()["choices"][0]["message"]["content"]
        parsed = json.loads(text)
        if "explanation" in parsed and "recommendation" in parsed:
            return parsed
        return _template_fallback(incident)
    except Exception:
        return _template_fallback(incident)