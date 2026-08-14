"""
PhishHunter — Génération d'explications via LLM (Hugging Face Inference API)
==============================================================================
IMPORTANT (rappel de principe) : le LLM ne décide JAMAIS si un email est
dangereux. Il reçoit uniquement le score et les signaux déjà calculés par
le modèle ML (scoring/engine.py), et se contente de les traduire en une
explication claire pour un utilisateur non technique.

Ce module utilise l'API gratuite de Hugging Face (huggingface_hub).
Nécessite la variable d'environnement HF_TOKEN (voir .env.example) —
génère un token gratuit sur https://huggingface.co/settings/tokens
(rôle "Read" suffit).
"""

import os
from huggingface_hub import InferenceClient

# Modèles gratuits compatibles avec l'API "chat_completion" de Hugging Face.
# On essaie plusieurs modèles dans l'ordre, car la disponibilité sur le
# niveau gratuit de l'Inference API peut varier.
CANDIDATE_MODELS = [
    "HuggingFaceH4/zephyr-7b-beta",
    "Qwen/Qwen2.5-7B-Instruct",
    "meta-llama/Llama-3.2-3B-Instruct",
]

MODEL_NAME = CANDIDATE_MODELS[0]

client = InferenceClient(model=MODEL_NAME, token=os.environ.get("HF_TOKEN"))


def generate_explanation(risk_score: int, classification: str, sender_domain: str, triggered_signals: list) -> str:
    """
    Génère une explication en français, claire et courte, à partir du score
    et des signaux déjà détectés par le modèle ML — sans jamais laisser le
    LLM recalculer ou remettre en cause le score lui-même.
    """
    if not triggered_signals:
        return "Aucun signal de danger particulier détecté par le modèle."

    signals_text = "\n".join(f"- {s['signal']} : {s['detail']}" for s in triggered_signals)

    prompt = f"""Un modèle de Machine Learning a analysé un email et produit les résultats suivants :

Score de dangerosité : {risk_score}/100
Classification : {classification}
Domaine expéditeur : {sender_domain or "non identifiable"}

Signaux détectés par le modèle :
{signals_text}

Rédige une explication courte (2 à 4 puces maximum), claire et sans jargon technique,
destinée à un employé non spécialiste en cybersécurité, expliquant pourquoi cet email
a reçu ce score. Ne remets pas en cause le score ni les signaux fournis — explique-les
uniquement. Réponds uniquement avec les puces, sans phrase d'introduction."""

    for model_name in CANDIDATE_MODELS:
        try:
            attempt_client = InferenceClient(model=model_name, token=os.environ.get("HF_TOKEN"))
            response = attempt_client.chat_completion(
                messages=[{"role": "user", "content": prompt}],
                max_tokens=300,
                temperature=0.3,
            )
            return response.choices[0].message.content.strip()
        except Exception as e:
            print(f"[PhishHunter][LLM] Échec avec le modèle '{model_name}' : {e}")
            continue

    # Tous les modèles ont échoué -> fallback sans LLM
    print("[PhishHunter][LLM] Tous les modèles ont échoué, utilisation du fallback.")
    return _fallback_explanation(triggered_signals)


def _fallback_explanation(triggered_signals: list) -> str:
    """Explication de secours générée sans LLM, si l'API Hugging Face échoue."""
    lines = [f"- {s['detail']}" for s in triggered_signals]
    return "\n".join(lines)