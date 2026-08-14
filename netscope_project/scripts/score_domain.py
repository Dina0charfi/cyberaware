"""
Script de test rapide pour l'agent NetScope.
Lancer avec : python scripts/score_domain.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from netscope_agent.scorer import NetScopeScorer

if __name__ == "__main__":
    scorer = NetScopeScorer()

    # Remplace ces valeurs par de vraies features extraites d'une requête DNS
    exemple = {f: 0 for f in scorer.features}

    result = scorer.score_domain(exemple)
    print(result)
