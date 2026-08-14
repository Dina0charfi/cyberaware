"""
PhishHunter — Boucle agentique (tool use)
============================================
Contrairement à src/llm/explain.py (qui fait toujours la même tâche fixe :
reformuler un score en explication), ce module donne au LLM la capacité de
RAISONNER et de CHOISIR lui-même quelles actions entreprendre, à partir des
outils disponibles (src/agent/tools.py).

Utilise l'API Anthropic (Claude) car le tool use nécessite un modèle qui le
supporte de façon fiable — les modèles gratuits Hugging Face utilisés pour
les explications simples ne sont pas assez fiables pour cet usage.
Nécessite la variable d'environnement ANTHROPIC_API_KEY (voir .env.example).
"""

import os
import json
import anthropic

from src.agent.tools import TOOL_DEFINITIONS, TOOL_FUNCTIONS, FINAL_ACTION_TOOLS

client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))
MODEL_NAME = "claude-sonnet-4-6"

SYSTEM_PROMPT = """Tu es l'agent de décision de PhishHunter, un système de détection de phishing.

Un modèle de Machine Learning a déjà calculé un score de risque (0-100) et une liste de
signaux détectés pour un email donné. Ton rôle est de DÉCIDER de l'action appropriée :

- Si le cas est clairement dangereux (score élevé ET signaux cohérents) : appelle block_email
- Si le cas est clairement sûr (score faible, aucun signal) : appelle deliver_normally
- Si le cas est ambigu (score moyen, signaux contradictoires, ou information manquante) :
  tu peux d'abord utiliser check_domain_age pour enquêter davantage, PUIS décider,
  ou appeler escalade_to_human si le doute persiste après vérification

Règles importantes :
- Tu dois TOUJOURS terminer par un appel à exactement UNE des actions finales
  (block_email, escalate_to_human, ou deliver_normally) — jamais aucune, jamais plusieurs.
- N'utilise check_domain_age que si c'est vraiment utile pour trancher un cas ambigu,
  pas systématiquement.
- Base ta décision sur les faits fournis (score, signaux, résultat WHOIS si consulté),
  jamais sur une supposition non vérifiée.
"""


def run_agent(email_id: int, risk_score: int, classification: str, sender_domain: str,
              triggered_signals: list, max_turns: int = 4) -> dict:
    """
    Lance la boucle agentique pour un email donné. Retourne la trace complète
    des outils utilisés et l'action finale décidée.
    """
    signals_text = "\n".join(f"- {s['signal']} : {s['detail']}" for s in triggered_signals) or "Aucun signal détecté"

    user_message = f"""Nouvel email à traiter (id={email_id}) :

Score de risque calculé par le modèle ML : {risk_score}/100
Classification : {classification}
Domaine expéditeur : {sender_domain or "non identifiable"}

Signaux déjà détectés par le modèle :
{signals_text}

Décide de l'action appropriée pour cet email."""

    messages = [{"role": "user", "content": user_message}]
    trace = []
    final_action_taken = None

    for turn in range(max_turns):
        response = client.messages.create(
            model=MODEL_NAME,
            max_tokens=800,
            system=SYSTEM_PROMPT,
            tools=TOOL_DEFINITIONS,
            messages=messages,
        )

        messages.append({"role": "assistant", "content": response.content})

        if response.stop_reason != "tool_use":
            # Le modèle a répondu sans appeler d'outil -> on arrête (sécurité anti-boucle infinie)
            break

        tool_results = []
        for block in response.content:
            if block.type != "tool_use":
                continue

            fn = TOOL_FUNCTIONS.get(block.name)
            if fn is None:
                result = {"error": f"Outil inconnu : {block.name}"}
            else:
                result = fn(**block.input)

            trace.append({"tool": block.name, "input": block.input, "result": result})

            tool_results.append({
                "type": "tool_result",
                "tool_use_id": block.id,
                "content": json.dumps(result, ensure_ascii=False),
            })

            if block.name in FINAL_ACTION_TOOLS:
                final_action_taken = block.name

        messages.append({"role": "user", "content": tool_results})

        if final_action_taken:
            break

    # Garde-fou : si l'agent n'a jamais pris de décision finale après max_turns,
    # on escalade automatiquement par sécurité plutôt que de laisser l'email sans statut.
    if final_action_taken is None:
        from src.agent.tools import escalate_to_human
        result = escalate_to_human(email_id, "L'agent n'a pas pu conclure automatiquement (limite de tours atteinte)")
        trace.append({"tool": "escalate_to_human", "input": {"email_id": email_id}, "result": result})
        final_action_taken = "escalate_to_human"

    return {
        "email_id": email_id,
        "final_action": final_action_taken,
        "trace": trace,
    }
