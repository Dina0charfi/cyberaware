#!/usr/bin/env python3
"""
DarkWatch (version gratuite) — surveillance de fuites de données
==================================================================

Reproduction fonctionnelle et gratuite de l'agent "DarkWatch" présenté dans
la démo CyberAware (Hydatis). Scénario : détecter si des emails d'employés
d'une banque apparaissent dans des fuites de données publiées.

Ce fichier est la version CLI (ligne de commande), pensée pour tourner en
tâche planifiée (cron) et ne signaler que les NOUVELLES fuites d'un jour
sur l'autre grâce à darkwatch_state.json.

Pour une interface visuelle (dashboard façon CyberAware), voir server.py.

Aucun modèle ML, aucun dataset : la détection vient de l'API gratuite
XposedOrNot (xon_api.py), le score de risque est calculé par cette même
API à partir de règles connues.

Usage :
    python3 darkwatch.py mehdi.t@banque-abc.example autre@banque-abc.example
    python3 darkwatch.py --file emails_example.txt
"""

import json
import sys
import time
from pathlib import Path
from datetime import datetime, timezone

from risk_report import build_report
from xon_api import check_email, get_analytics

STATE_FILE = Path(__file__).parent / "darkwatch_state.json"
RATE_LIMIT_DELAY = 0.6  # reste sous la limite gratuite de 2 req/sec


def load_state() -> dict:
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text())
    return {}


def save_state(state: dict) -> None:
    STATE_FILE.write_text(json.dumps(state, indent=2, ensure_ascii=False))


def run(emails: list[str]) -> None:
    state = load_state()
    now = datetime.now(timezone.utc).isoformat()
    any_new = False

    for email in emails:
        try:
            found = set(check_email(email))
        except Exception as e:
            print(f"[ERREUR] {email}: {e}")
            continue

        previously_known = set(state.get(email, {}).get("breaches", []))
        new_breaches = found - previously_known

        if new_breaches:
            any_new = True
            time.sleep(RATE_LIMIT_DELAY)
            analytics = get_analytics(email)
            print(build_report(email, new_breaches, analytics))
        else:
            print(f"[OK] {email} — aucune nouvelle fuite ({len(found)} connue(s) au total).")

        state[email] = {"breaches": sorted(found), "last_checked": now}
        time.sleep(RATE_LIMIT_DELAY)

    save_state(state)

    if not any_new:
        print("\nRésumé : aucune nouvelle exposition détectée aujourd'hui.")


def main():
    args = sys.argv[1:]
    if not args:
        print(__doc__)
        sys.exit(1)

    if args[0] == "--file":
        emails = [
            line.strip()
            for line in Path(args[1]).read_text().splitlines()
            if line.strip() and not line.startswith("#")
        ]
    else:
        emails = args

    run(emails)


if __name__ == "__main__":
    main()
