"""
Sentinel — Génération d'explications via LLM (Hugging Face Inference API)
============================================================================
Même principe que PhishHunter/explain.py : le LLM ne décide JAMAIS de
l'action à prendre — decision_engine.py fait ça, de façon déterministe.
Le LLM reçoit uniquement le risk_score et les features déjà calculées,
et se contente de les traduire en explication claire pour un non-expert.

Nécessite HF_TOKEN dans les variables d'environnement (gratuit, sans carte
bancaire) — huggingface.co -> Settings -> Access Tokens -> New token (Read).
"""

import os
from huggingface_hub import InferenceClient

CANDIDATE_MODELS = [
    "Qwen/Qwen2.5-7B-Instruct",
    "HuggingFaceH4/zephyr-7b-beta",
    "meta-llama/Llama-3.2-3B-Instruct",
]

HF_TOKEN = os.environ.get("HF_TOKEN")

if HF_TOKEN:
    print(f"[Sentinel][LLM] HF_TOKEN détecté (commence par '{HF_TOKEN[:6]}...') — LLM activé.")
else:
    print("[Sentinel][LLM] ⚠️ HF_TOKEN non détecté — le LLM restera désactivé, "
          "la description par règles sera utilisée à la place. "
          "Vérifie ton fichier .env (HF_TOKEN=...) et qu'il est bien à côté de app.py.")


def generate_llm_explanation(user: str, department: str, risk_score: int,
                              action_label: str, features: dict) -> str | None:
    """
    Retourne une explication en français générée par LLM, ou None si HF_TOKEN
    est absent ou si tous les modèles échouent — dans ce cas, le reste de
    l'API continue de fonctionner normalement avec la description par règles.
    """
    if not HF_TOKEN:
        return None

    feature_lines = "\n".join(f"- {k}: {v}" for k, v in features.items())
    prompt = f"""Un modèle de détection d'anomalies a analysé une connexion et produit :

Utilisateur : {user}
Département : {department}
Score de risque : {risk_score}/100
Décision prise : {action_label}

Features calculées :
{feature_lines}

Rédige une explication courte (2-3 phrases), claire, sans jargon technique, destinée à un
employé non spécialiste en cybersécurité. N'invente aucun fait qui ne soit pas dans les
features ci-dessus. Ne remets pas en cause le score ni la décision — explique-les seulement."""

    for model_name in CANDIDATE_MODELS:
        try:
            client = InferenceClient(model=model_name, token=HF_TOKEN)
            response = client.chat_completion(
                messages=[{"role": "user", "content": prompt}],
                max_tokens=250,
                temperature=0.3,
            )
            return response.choices[0].message.content.strip()
        except Exception as e:
            print(f"[Sentinel][LLM] Échec avec '{model_name}' : {e}")
            continue

    return None