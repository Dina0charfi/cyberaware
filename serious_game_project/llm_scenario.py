"""
llm_scenario.py — rédige le texte de la tentative d'attaque.

Même principe que llm_summary.py chez DarkWatch : le LLM ne décide jamais ce
qui s'est passé — l'action de la cible (clicked/ignored/reported) vient déjà
d'un vrai événement (vrai clic sur le lien de simulation, ou vrai bouton
cliqué dans l'interface) avant même que ce module soit appelé (voir
attempts.py, resolve_attempt). Le LLM sert uniquement à rédiger un texte
différent à chaque tentative plutôt que de répéter toujours la même phrase
pour un même vecteur/action.

Sans GROQ_API_KEY, un jeu de phrases pré-écrites prend le relais — le jeu
reste jouable, juste avec moins de variété dans le texte.
"""

import json
import os
import urllib.request
import urllib.error

GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
GROQ_MODEL = os.environ.get("GROQ_MODEL", "llama-3.3-70b-versatile")

SYSTEM_PROMPT = """Tu écris un court passage narratif (2-3 phrases, en français) pour un
serious game de cybersécurité destiné à des employés de banque. Le joueur
incarne un pentester qui teste un(e) employé(e) fictif(ve) avec un vecteur
d'ingénierie sociale donné. L'action de la cible t'est déjà donnée (une parmi
quatre : "clicked" = est tombée dans le piège, "opened" = a regardé mais
s'est arrêtée avant d'agir, "ignored" = n'a pas réagi du tout, "reported" =
a activement signalé la tentative) — tu ne la choisis jamais, tu ne fais que
la raconter.

Règles strictes :
- Ne jamais changer l'action fournie ni en inventer une autre.
- Rester réaliste et pédagogique, pas dramatique ni comique.
- Mentionner un détail crédible et concret cohérent avec l'action exacte
  (ex. pour "opened" : a ouvert l'email puis hésité ; pour "ignored" : n'a
  même pas remarqué le message ; pour "reported" : a utilisé le bouton de
  signalement ou prévenu l'IT), pas une généralité vague.
- Répondre UNIQUEMENT en JSON valide avec une seule clé "narrative"."""


_FALLBACK_TEMPLATES = {
    "clicked": (
        "{name} tombe dans le piège : sous la pression du moment, "
        "l'action attendue est effectuée sans vérification préalable."
    ),
    "opened": (
        "{name} ouvre la tentative de {vector_lower}, hésite, puis "
        "s'arrête avant d'aller plus loin."
    ),
    "ignored": (
        "{name} ne remarque même pas cette tentative de {vector_lower} "
        "au milieu du reste — aucune réaction, dans un sens comme dans l'autre."
    ),
    "reported": (
        "{name} repère un signe inhabituel dans cette tentative de "
        "{vector_lower} et la signale activement au lieu de simplement l'ignorer."
    ),
}


def _fallback_text(target: dict, vector_label: str, action: str) -> str:
    template = _FALLBACK_TEMPLATES[action]
    return template.format(name=target["name"], vector_lower=vector_label.lower())


def generate_scenario(target: dict, vector_label: str, action: str) -> str:
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        return _fallback_text(target, vector_label, action)

    user_prompt = json.dumps({
        "target_name": target["name"],
        "department": target["dept"],
        "risk_score": target["risk"],
        "modules_completed": f"{target['modules_done']}/{target['modules_total']}",
        "vector": vector_label,
        "action": action,
    }, ensure_ascii=False)

    payload = json.dumps({
        "model": GROQ_MODEL,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        "response_format": {"type": "json_object"},
        "temperature": 0.8,
        "max_tokens": 200,
    }).encode("utf-8")

    req = urllib.request.Request(
        GROQ_URL,
        data=payload,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
    )

    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode())
        text = data["choices"][0]["message"]["content"]
        parsed = json.loads(text)
        narrative = parsed.get("narrative")
        if narrative:
            return narrative
    except (urllib.error.URLError, KeyError, json.JSONDecodeError, TimeoutError):
        pass

    return _fallback_text(target, vector_label, action)
