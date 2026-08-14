"""
PhishHunter — Boucle agentique (tool use, via Groq — gratuit)
================================================================
Contrairement à src/llm/explain.py (qui fait toujours la même tâche fixe :
reformuler un score en explication), ce module donne au LLM la capacité de
RAISONNER et de CHOISIR lui-même quelles actions entreprendre, à partir des
outils disponibles (src/agent/tools.py).

Utilise l'API Groq (gratuite, sans carte bancaire), qui supporte le tool use
de façon fiable avec des modèles Llama. Nécessite la variable d'environnement
GROQ_API_KEY (voir .env.example) — génère une clé gratuite sur
https://console.groq.com/keys
"""

import os
import json
from groq import Groq

from src.agent.tools import TOOL_DEFINITIONS, TOOL_FUNCTIONS, FINAL_ACTION_TOOLS

client = Groq(api_key=os.environ.get("GROQ_API_KEY"))
MODEL_NAME = "llama-3.3-70b-versatile"

SYSTEM_PROMPT = """Tu es l'agent de décision de PhishHunter, un système de détection de phishing.

Un modèle de Machine Learning a déjà calculé un score de risque (0-100) et une liste de
signaux détectés pour un email donné. Ton rôle est de DÉCIDER de l'action appropriée :

- Si le cas est clairement dangereux (score élevé ET signaux cohérents) : appelle block_email
- Si le cas est clairement sûr (score faible, aucun signal) : appelle deliver_normally
- Si le cas est ambigu (score moyen, signaux contradictoires, ou information manquante) :
  tu peux d'abord utiliser check_domain_age pour enquêter davantage, PUIS décider,
  ou appeler escalate_to_human si le doute persiste après vérification

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

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_message},
    ]
    trace = []
    final_action_taken = None
    llm_failure_reason = None

    for turn in range(max_turns):
        try:
            response = client.chat.completions.create(
                model=MODEL_NAME,
                messages=messages,
                tools=TOOL_DEFINITIONS,
                tool_choice="auto",
                max_tokens=800,
            )
        except Exception as e:
            # Le modèle Llama via Groq échoue parfois à formater un appel de
            # fonction valide (tool_use_failed) — ou la clé/API peut être
            # temporairement indisponible. Dans tous les cas, on n'expose
            # jamais une 500 au frontend : on arrête la boucle et on laisse
            # le garde-fou ci-dessous escalader automatiquement vers un humain.
            print(f"[PhishHunter][AGENT] Appel LLM échoué (tour {turn + 1}) : {e}")
            trace.append({"tool": "llm_call_failed", "input": {}, "result": {"error": str(e)}})
            llm_failure_reason = str(e)
            break

        msg = response.choices[0].message

        # Reconstruit le message assistant pour l'historique (format attendu par l'API)
        assistant_entry = {"role": "assistant", "content": msg.content or ""}
        if msg.tool_calls:
            assistant_entry["tool_calls"] = [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {"name": tc.function.name, "arguments": tc.function.arguments},
                }
                for tc in msg.tool_calls
            ]
        messages.append(assistant_entry)

        if not msg.tool_calls:
            # Le modèle a répondu sans appeler d'outil -> on arrête (sécurité anti-boucle infinie)
            break

        for tool_call in msg.tool_calls:
            fn_name = tool_call.function.name
            try:
                args = json.loads(tool_call.function.arguments)
            except json.JSONDecodeError:
                args = {}

            fn = TOOL_FUNCTIONS.get(fn_name)
            result = fn(**args) if fn else {"error": f"Outil inconnu : {fn_name}"}

            trace.append({"tool": fn_name, "input": args, "result": result})

            messages.append({
                "role": "tool",
                "tool_call_id": tool_call.id,
                "content": json.dumps(result, ensure_ascii=False),
            })

            if fn_name in FINAL_ACTION_TOOLS:
                final_action_taken = fn_name

        if final_action_taken:
            break

    # Garde-fou : si l'agent n'a jamais pris de décision finale (limite de tours
    # atteinte, OU échec de l'appel LLM), on escalade automatiquement par
    # sécurité plutôt que de laisser l'email sans statut / de renvoyer une 500.
    if final_action_taken is None:
        from src.agent.tools import escalate_to_human
        reason = (
            f"Appel au LLM impossible ({llm_failure_reason})" if llm_failure_reason
            else "L'agent n'a pas pu conclure automatiquement (limite de tours atteinte)"
        )
        result = escalate_to_human(email_id, reason)
        trace.append({"tool": "escalate_to_human", "input": {"email_id": email_id}, "result": result})
        final_action_taken = "escalate_to_human"

    return {
        "email_id": email_id,
        "final_action": final_action_taken,
        "trace": trace,
    }
