#!/usr/bin/env python3
"""
agent.py — DarkWatch en tant qu'agent IA autonome
=====================================================

darkwatch.py (CLI) et server.py (dashboard) demandent tous les deux une
action humaine : lancer la commande, ou cliquer sur "Scan". Ce fichier
est différent : une fois lancé, il tourne SEUL, indéfiniment, et prend
ses propres décisions. C'est ça qui en fait un agent, pas juste un script.

Boucle de l'agent, à chaque cycle :

    1. PERCEPTION   → interroge XposedOrNot pour chaque email surveillé
    2. MÉMOIRE      → compare avec darkwatch_state.json, ignore le déjà-vu
    3. RAISONNEMENT → si nouvelle fuite : le LLM (Groq) analyse et CHOISIT
                       une action (pas juste un résumé, une vraie décision)
    4. ACTION       → exécute (ou simule) cette décision, journalise
    5. attend `--interval` secondes, recommence tout seul

Sans GROQ_API_KEY configurée, le raisonnement retombe sur des règles
simples (llm_summary._fallback_decision) — l'agent continue de tourner
et de décider, juste avec moins de nuance.

Usage :
    python3 agent.py --file emails_example.txt --once
        (une seule passe, pour tester/démontrer)

    python3 agent.py --file emails_example.txt --interval 3600
        (tourne en continu, vérifie toutes les heures, Ctrl+C pour arrêter)
"""

import argparse
import json
import sys
import time
from pathlib import Path
from datetime import datetime, timezone

from xon_api import check_email, get_analytics, RateLimitError
from llm_summary import decide_action, is_configured
from crisisbot_client import notify_crisisbot
from email_sources import get_monitored_emails

BASE_DIR = Path(__file__).parent
STATE_FILE = BASE_DIR / "darkwatch_state.json"
ACTIONS_LOG = BASE_DIR / "agent_actions.log"
RATE_LIMIT_DELAY = 0.6

ACTION_LABELS = {
    "reset_password": "🔒 Réinitialisation du mot de passe forcée (simulée)",
    "notify_only": "📩 Notification envoyée au titulaire du compte (simulée)",
    "escalate_ciso": "🚨 Escalade au CISO (simulée — enverrait un email/Slack en prod)",
    "ignore_false_positive": "🟢 Ignoré (jugé faux positif par l'agent)",
}


def load_state() -> dict:
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text())
    return {}


def save_state(state: dict) -> None:
    STATE_FILE.write_text(json.dumps(state, indent=2, ensure_ascii=False))


def load_emails(path: Path) -> list[str]:
    return get_monitored_emails(path)


def log_action(email: str, breaches: set[str], decision: dict) -> None:
    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "email": email,
        "breaches": sorted(breaches),
        "decision": decision,
    }
    with ACTIONS_LOG.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def execute_action(email: str, decision: dict) -> None:
    action = decision.get("action", "notify_only")
    label = ACTION_LABELS.get(action, f"Action inconnue : {action}")
    print(f"\n🤖 AGENT — décision autonome pour {email}")
    print(f"   Risque : {decision.get('risk_level', '?')}")
    print(f"   Action : {label}")
    print(f"   Raison : {decision.get('summary', '(pas de résumé)')}")

    # Les décisions les plus graves déclenchent CrisisBot, qui prend le relais
    # (isoler, notifier RSSI/Direction, activer la cellule de crise...).
    if action in ("reset_password", "escalate_ciso"):
        severity = "critical" if action == "escalate_ciso" else "high"
        notify_crisisbot(
            source_agent="darkwatch",
            severity=severity,
            description=f"Fuite de données détectée pour {email} — {label}",
        )


def run_once(emails: list[str]) -> None:
    state = load_state()
    now = datetime.now(timezone.utc).isoformat()
    any_new = False

    for email in emails:
        try:
            found = set(check_email(email))
        except RateLimitError as e:
            print(f"[ERREUR] {email}: {e}")
            continue
        except Exception as e:
            print(f"[ERREUR] {email}: {e}")
            continue

        previously_known = set(state.get(email, {}).get("breaches", []))
        new_breaches = found - previously_known

        if new_breaches:
            any_new = True
            time.sleep(RATE_LIMIT_DELAY)
            try:
                analytics = get_analytics(email)
            except RateLimitError as e:
                print(f"[ERREUR] {email}: {e}")
                analytics = {}
            decision = decide_action(email, sorted(new_breaches), analytics)
            execute_action(email, decision)
            log_action(email, new_breaches, decision)
        else:
            print(f"[veille] {email} — rien de nouveau ({len(found)} fuite(s) connue(s)).")

        state[email] = {"breaches": sorted(found), "last_checked": now}
        time.sleep(RATE_LIMIT_DELAY)

    save_state(state)

    if not any_new:
        print("\nCycle terminé : aucune nouvelle exposition.")


def main():
    parser = argparse.ArgumentParser(description="DarkWatch — agent autonome")
    parser.add_argument("--file", required=True, help="Fichier avec un email par ligne")
    parser.add_argument("--interval", type=int, default=3600,
                         help="Secondes entre chaque cycle (défaut : 3600 = 1h)")
    parser.add_argument("--once", action="store_true", help="Une seule passe puis quitte")
    args = parser.parse_args()

    emails = load_emails(Path(args.file))
    if not emails:
        print("Aucun email trouvé dans le fichier.")
        sys.exit(1)

    print(f"Agent DarkWatch démarré — {len(emails)} compte(s) surveillé(s).")
    print(f"Raisonnement : {'LLM (Groq)' if is_configured() else 'règles simples (pas de GROQ_API_KEY)'}")

    if args.once:
        run_once(emails)
        return

    print(f"Boucle autonome activée — cycle toutes les {args.interval}s. Ctrl+C pour arrêter.\n")
    try:
        while True:
            run_once(emails)
            print(f"\n--- prochain cycle dans {args.interval}s ---")
            time.sleep(args.interval)
    except KeyboardInterrupt:
        print("\nAgent arrêté.")


if __name__ == "__main__":
    main()
