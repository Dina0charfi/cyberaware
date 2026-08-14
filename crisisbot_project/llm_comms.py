"""
llm_comms.py — génération du message de communication interne (optionnel)
==========================================================================

Même principe que DarkWatch/llm_summary.py : un LLM optionnel qui REDIGE
(jamais qui décide). CrisisBot décide déjà de la séquence d'actions de
façon 100% déterministe (le runbook, voir server.py) — le LLM sert
uniquement à rédiger un message de communication interne adapté à
l'incident réel, à la place du template statique, pour l'étape
"Préparer la communication interne".

Sans clé API configurée, cette étape retombe automatiquement sur un
message générique — CrisisBot reste entièrement fonctionnel sans IA
générative.

Fournisseur : Groq (https://console.groq.com), API compatible OpenAI,
gratuit, sans carte bancaire. 100% stdlib (urllib), comme le reste du
projet — aucune dépendance à installer.

Configuration :
  PowerShell (Windows) :
      $env:GROQ_API_KEY = "ta_clé_ici"
      py server.py
"""

import json
import os
import urllib.request
import urllib.error

GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
GROQ_MODEL = "llama-3.3-70b-versatile"

FALLBACK_MESSAGE = (
    "Un incident de sécurité est en cours de traitement par les équipes IT et "
    "sécurité. Aucune action n'est requise de votre part pour le moment — nous "
    "vous tiendrons informés dès que la situation sera résolue."
)


def is_configured() -> bool:
    return bool(os.environ.get("GROQ_API_KEY"))


def generate_comms_message(incident: str) -> str | None:
    """
    Demande au LLM de rédiger un message court de communication interne,
    adapté à l'incident réel. Retourne None si aucune clé n'est configurée
    ou si l'appel échoue — dans ce cas, server.py retombe sur FALLBACK_MESSAGE.
    """
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        return None

    prompt = (
        "Tu es le rédacteur de communication interne d'une entreprise en pleine "
        "gestion d'incident de cybersécurité. Rédige un message COURT (2-3 phrases, "
        "en français) destiné à TOUS les employés, à propos de l'incident suivant : "
        f"« {incident} ».\n\n"
        "Consignes : rassure sans minimiser, ne donne aucun détail technique "
        "exploitable, ne blâme personne, explique juste que les équipes gèrent "
        "la situation et que les employés seront tenus informés. Ton professionnel, "
        "pas de formules de politesse ni de signature."
    )

    payload = json.dumps({
        "model": GROQ_MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.4,
        "max_tokens": 200,
    }).encode("utf-8")

    req = urllib.request.Request(
        GROQ_URL,
        data=payload,
        method="POST",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "User-Agent": "CrisisBot-Free/1.0",
        },
    )

    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            data = json.loads(resp.read().decode())
        return data["choices"][0]["message"]["content"].strip()
    except urllib.error.HTTPError as e:
        detail = e.read().decode(errors="replace")[:300]
        print(f"[llm_comms] Appel LLM échoué (HTTP {e.code}) : {detail}")
        return None
    except (urllib.error.URLError, KeyError, IndexError) as e:
        print(f"[llm_comms] Appel LLM échoué : {e}")
        return None
