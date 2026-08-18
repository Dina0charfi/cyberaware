"""
auto_simulate.py — boucle d'auto-jeu du serious game, en mode démo uniquement
(``launch_all.py --simulate``).

Pourquoi ce fichier existe : en usage normal, personne ne joue tout seul —
c'est un humain qui choisit une cible et un vecteur dans le dashboard, et le
résultat dépend d'un vrai clic sur le lien ou d'un vrai choix explicite (voir
attempts.py). Pour que le mode démo montre de l'activité sans surveillance
humaine, cette boucle joue à la place d'un humain : elle choisit une cible et
un vecteur au hasard, envoie la simulation exactement comme le ferait le
bouton du dashboard (``attempts.start_attempt``), puis résout elle-même la
tentative — pas via un vrai clic sur le lien (personne ne le suit ici), mais
via un tirage pondéré sur ``compute_success_probability()``, la même formule
déjà utilisée ailleurs à titre indicatif avant l'envoi. C'est le seul endroit
de tout le serious game où un résultat est "inventé" plutôt que déduit d'un
vrai événement — un compromis assumé, uniquement actif en mode démo, pour que
--simulate ait quelque chose à montrer sans qu'on ait à cliquer soi-même.

Jamais lancée seule : importée et démarrée par server.py uniquement quand
SERIOUSGAME_AUTO_SIMULATE=1 (mis par launch_all.py --simulate), le même
principe que NETSCOPE_AUTO_SCAN et DARKWATCH_AUTO_SCAN pour les autres agents.
"""

import random
import threading
import time

import attempts
from targets import TARGETS, VECTORS, compute_success_probability

SIMULATE_INTERVAL_SECONDS = 20  # une tentative jouée automatiquement toutes les ~20s


def _play_one_round() -> None:
    target = random.choice(TARGETS)
    vector_key = random.choice(list(VECTORS.keys()))

    result = attempts.start_attempt(target["id"], vector_key)
    token = result["token"]

    # Pas de vrai clic possible ici (personne ne suit le lien) : le résultat
    # est tiré au sort, pondéré par la même probabilité indicative que le
    # reste du jeu affiche déjà avant l'envoi (voir compute_success_probability).
    # Sous ce seuil -> clicked (tombé dans le piège) ; au-dessus, deux fois
    # plus de chances de "reported" que d'"ignored", pour que la démo ne
    # montre pas uniquement des employés qui ne réagissent jamais.
    probability = compute_success_probability(target["risk"], vector_key)
    roll = random.random()
    if roll < probability:
        action = "clicked"
    elif roll < probability + (1 - probability) * (2 / 3):
        action = "reported"
    else:
        action = "ignored"

    outcome = attempts.resolve_attempt(token, action)
    print(
        f"[serious_game][auto_simulate] {target['name']} / {VECTORS[vector_key]['label']} "
        f"-> {action} (risque {outcome['risk_before']} -> {outcome['risk_after']})"
    )


def run_auto_simulate(stop_event: threading.Event | None = None) -> None:
    print(
        f"[serious_game][auto_simulate] Boucle de démo démarrée — une tentative "
        f"jouée automatiquement toutes les ~{SIMULATE_INTERVAL_SECONDS:.0f}s."
    )
    while stop_event is None or not stop_event.is_set():
        try:
            _play_one_round()
        except Exception as e:
            print(f"[serious_game][auto_simulate] Erreur pendant le tour (ignorée) : {e}")

        waited = 0.0
        while waited < SIMULATE_INTERVAL_SECONDS:
            if stop_event is not None and stop_event.is_set():
                return
            time.sleep(min(1.0, SIMULATE_INTERVAL_SECONDS - waited))
            waited += 1.0
