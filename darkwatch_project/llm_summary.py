"""
llm_summary.py — couche IA générative optionnelle (via variable d'env)
==========================================================================

Ce module ajoute un VRAI appel à un LLM pour générer un résumé/risque en
langage naturel, comme demandé pour la soutenance. Il est entièrement
optionnel : si aucune clé n'est configurée, le reste du projet continue
de fonctionner avec le rapport basé sur un template (voir risk_report.py).

Fournisseur choisi : Groq (https://console.groq.com), parce que :
  - inscription gratuite, sans carte bancaire
  - quota gratuit généreux (30 req/min, 14 400 req/jour)
  - API compatible OpenAI, donc un simple POST HTTP suffit (pas besoin
    d'installer le SDK openai ou groq — on reste 100% stdlib avec urllib)

Configuration (variable d'environnement, PAS de clé écrite dans le code) :

  PowerShell (Windows), pour la session en cours :
      $env:GROQ_API_KEY = "ta_clé_ici"
      py server.py

  Pour la rendre permanente sous Windows :
      setx GROQ_API_KEY "ta_clé_ici"
      (rouvre ensuite un nouveau terminal)

  macOS/Linux (bash/zsh) :
      export GROQ_API_KEY="ta_clé_ici"
      python3 server.py

Récupérer une clé gratuite : https://console.groq.com/keys (compte
gratuit, "Create API Key").
"""

import json
import os
import urllib.request
import urllib.error

GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
GROQ_MODEL = "llama-3.3-70b-versatile"


def is_configured() -> bool:
    """Vrai si une clé API est présente dans l'environnement."""
    return bool(os.environ.get("GROQ_API_KEY"))


def _call_groq(prompt: str, max_tokens: int = 300) -> str | None:
    """Appel bas niveau à Groq. Retourne le texte brut, ou None si ça échoue."""
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        return None

    payload = json.dumps({
        "model": GROQ_MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.2,
        "max_tokens": max_tokens,
    }).encode("utf-8")

    req = urllib.request.Request(
        GROQ_URL,
        data=payload,
        method="POST",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            # Sans User-Agent explicite, Cloudflare bloque parfois les
            # requêtes urllib par défaut (Python-urllib/x.x) avec un 403.
            "User-Agent": "DarkWatch-Free/1.0",
        },
    )

    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            data = json.loads(resp.read().decode())
        return data["choices"][0]["message"]["content"].strip()
    except urllib.error.HTTPError as e:
        detail = e.read().decode(errors="replace")[:300]
        print(f"[llm_summary] Appel LLM échoué (HTTP {e.code}) : {detail}")
        return None
    except (urllib.error.URLError, KeyError, IndexError) as e:
        print(f"[llm_summary] Appel LLM échoué : {e}")
        return None


def generate_summary(email: str, breaches: list[str], analytics: dict) -> str | None:
    """Demande au LLM un résumé de risque en français pour un CISO.

    Retourne None si aucune clé n'est configurée, ou si l'appel échoue —
    dans ce cas, risk_report.py retombe automatiquement sur le rapport
    basé sur un template (aucune IA générative n'est requise pour que le
    projet fonctionne).
    """
    prompt = (
        "Tu es un assistant cybersécurité. Voici les données brutes d'une "
        "fuite détectée pour un compte d'entreprise. Rédige un résumé court "
        "(3-4 phrases, en français) pour le CISO : explique le risque, "
        "pourquoi, et l'action recommandée. Sois direct, pas de formules de "
        "politesse.\n\n"
        f"Email concerné : {email}\n"
        f"Fuites : {', '.join(breaches)}\n"
        f"Données analytiques (JSON) : {json.dumps(analytics, ensure_ascii=False)[:3000]}"
    )
    return _call_groq(prompt, max_tokens=300)


VALID_ACTIONS = {"reset_password", "notify_only", "escalate_ciso", "ignore_false_positive"}


def _fallback_decision(analytics: dict) -> dict:
    """Décision par règles simples, utilisée si aucun LLM n'est configuré
    ou si l'appel échoue. Garantit que l'agent reste fonctionnel sans IA."""
    metrics = (analytics or {}).get("BreachMetrics") or {}
    risk = (metrics.get("risk") or [{}])[0]
    label = (risk.get("risk_label") or "").lower()
    if label in ("high", "critical"):
        action = "reset_password"
    elif label in ("moderate",):
        action = "notify_only"
    else:
        action = "notify_only"
    return {
        "action": action,
        "risk_level": risk.get("risk_label", "Inconnu"),
        "summary": "Décision par règles (pas de LLM configuré) : basée uniquement sur le score de risque XposedOrNot.",
    }


def decide_action(email: str, breaches: list[str], analytics: dict) -> dict:
    """Le cœur de l'agent : demande au LLM de RAISONNER et de CHOISIR une
    action, pas seulement de résumer. Retourne un dict avec les clés
    "action" (une des VALID_ACTIONS), "risk_level" et "summary".

    Si aucune clé n'est configurée ou si l'appel échoue, retombe sur
    _fallback_decision() — l'agent continue de fonctionner et de prendre
    des décisions (moins finement) même sans IA générative.
    """
    if not is_configured():
        return _fallback_decision(analytics)

    prompt = (
        "Tu es un agent de cybersécurité autonome. On te donne les données "
        "brutes d'une fuite détectée pour un compte d'entreprise. Tu dois "
        "DÉCIDER d'une action, pas juste la décrire.\n\n"
        f"Email concerné : {email}\n"
        f"Fuites : {', '.join(breaches)}\n"
        f"Données analytiques (JSON) : {json.dumps(analytics, ensure_ascii=False)[:3000]}\n\n"
        "Réponds UNIQUEMENT avec un objet JSON valide, sans texte autour, "
        "avec exactement ces clés :\n"
        '  "action" : une valeur parmi "reset_password", "notify_only", '
        '"escalate_ciso", "ignore_false_positive"\n'
        '  "risk_level" : "low", "moderate", "high" ou "critical"\n'
        '  "summary" : 2-3 phrases en français expliquant ta décision'
    )

    raw = _call_groq(prompt, max_tokens=250)
    if not raw:
        return _fallback_decision(analytics)

    try:
        # Le modèle répond parfois avec du texte autour du JSON malgré la
        # consigne — on extrait juste la partie entre la première et la
        # dernière accolade.
        start, end = raw.index("{"), raw.rindex("}") + 1
        decision = json.loads(raw[start:end])
        if decision.get("action") not in VALID_ACTIONS:
            raise ValueError(f"action invalide reçue du LLM : {decision.get('action')}")
        return decision
    except (ValueError, json.JSONDecodeError) as e:
        print(f"[llm_summary] Réponse LLM invalide ({e}), retour aux règles simples.")
        return _fallback_decision(analytics)
