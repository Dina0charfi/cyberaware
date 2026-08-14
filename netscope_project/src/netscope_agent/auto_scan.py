"""
auto_scan.py — boucle autonome de NetScope
==============================================
Contrairement à /analyze et /analyze-traffic (appelés à la demande par le
dashboard) et à /isolate (déclenché par un clic humain), cette boucle
tourne SEULE en arrière-plan pendant que l'API est démarrée : elle
échantillonne du trafic périodiquement, score chaque domaine, et pour tout
domaine jugé suspect avec un score élevé, agit automatiquement (journalise
l'incident + notifie CrisisBot) — sans attendre qu'un analyste clique sur
"Isoler". Même principe que l'agent autonome de DarkWatch (agent.py).

Aujourd'hui la source est le même échantillon CSV que /sample-traffic
(models/sample_traffic.csv) — le jour du branchement sur de vrais logs DNS,
seule la fonction _pick_one_row() doit changer (lire le vrai flux au lieu
du CSV), le reste de la boucle (score → décision → action) ne bouge pas.
"""

import threading
import time
from pathlib import Path

import pandas as pd

from netscope_agent.actions import get_user_for_host, record_isolation

SCAN_INTERVAL_SECONDS = 25
AUTO_ACT_THRESHOLD = 80.0  # score ML au-delà duquel on agit sans attendre un humain

BASE_DIR = Path(__file__).resolve().parents[2]
SAMPLE_PATH = BASE_DIR / "models" / "sample_traffic.csv"

# Domaines déjà traités automatiquement pendant cette exécution du process,
# pour ne pas ré-isoler en boucle le même domaine à chaque tirage aléatoire.
_already_acted: set[str] = set()


def _pick_one_row():
    if not SAMPLE_PATH.exists():
        return None
    df = pd.read_csv(SAMPLE_PATH)
    if df.empty:
        return None
    return df.sample(n=1).iloc[0]


def _scan_once(scorer) -> None:
    row = _pick_one_row()
    if row is None:
        return

    domain = row.get("domain", "unknown")
    features_row = {f: row[f] for f in scorer.features}
    result = scorer.score_domain(features_row)

    if result["ml_score"] >= AUTO_ACT_THRESHOLD and domain not in _already_acted:
        user = get_user_for_host(domain)
        record_isolation(
            domain=domain,
            user=user.get("name", "inconnu"),
            ml_score=result["ml_score"],
            source="auto_scan",
        )
        _already_acted.add(domain)
        print(f"[NetScope][auto_scan] Domaine isolé automatiquement : {domain} "
              f"(score {result['ml_score']}) — CrisisBot notifié.")


def run_auto_scan(scorer, stop_event: threading.Event | None = None) -> None:
    print(f"[NetScope][auto_scan] Boucle autonome démarrée — scan toutes les ~{SCAN_INTERVAL_SECONDS:.0f}s, "
          f"action automatique si score ML ≥ {AUTO_ACT_THRESHOLD:.0f}.")

    while stop_event is None or not stop_event.is_set():
        try:
            _scan_once(scorer)
        except Exception as e:
            print(f"[NetScope][auto_scan] Erreur pendant le scan (ignorée) : {e}")

        waited = 0.0
        while waited < SCAN_INTERVAL_SECONDS:
            if stop_event is not None and stop_event.is_set():
                return
            time.sleep(min(1.0, SCAN_INTERVAL_SECONDS - waited))
            waited += 1.0
