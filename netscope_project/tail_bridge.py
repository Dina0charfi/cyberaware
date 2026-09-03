"""
tail_bridge.py — "tail" en direct le fichier de log du proxy DNS
(dns_proxy.py) et pousse chaque nouveau domaine observé vers le VRAI webhook
NetScope (/webhook/traffic-event) — exactement le même point d'entrée
qu'utiliserait un vrai firewall/proxy en production (voir api.py).

Principe du "tail" : on ouvre le fichier de log, on se place directement à
la FIN, puis on relit en boucle uniquement les nouvelles lignes ajoutées
depuis la dernière lecture — le même principe que la commande Unix `tail -f`,
réimplémenté ici en pur Python (aucune dépendance supplémentaire).

Chaîne complète pour la démo (3 process à lancer, dans l'ordre) :
    1. python launch_all.py         (NetScope + les 5 autres agents)
    2. python dns_proxy.py          (le "tap" DNS, en administrateur)
    3. python tail_bridge.py        (ce script)
Puis pointer le DNS du téléphone vers l'IP locale du PC (voir dns_proxy.py)
et naviguer normalement sur le téléphone — chaque domaine visité doit
apparaître ici ET déclencher une vraie analyse NetScope.
"""

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
LOG_PATH = BASE_DIR / "data" / "dns_queries.log"

NETSCOPE_URL = "http://localhost:8001"
# Doit correspondre à NETSCOPE_WEBHOOK_SECRET côté api.py (défaut si non
# défini dans netscope_project/.env — voir api.py::WEBHOOK_SECRET).
WEBHOOK_SECRET = "change-moi-avant-toute-vraie-utilisation"

POLL_INTERVAL = 0.5  # secondes entre deux relectures du fichier

# Évite de renotifier NetScope pour le même domaine en boucle si le téléphone
# le requête 50 fois par minute (comportement DNS normal, ex. pubs, telemetry) —
# on ne renotifie un domaine déjà vu que si ça fait plus de COOLDOWN secondes.
COOLDOWN_SECONDS = 30.0
_last_seen: dict[str, float] = {}


def _notify_netscope(domain: str) -> None:
    payload = json.dumps({"domain": domain}).encode("utf-8")
    url = f"{NETSCOPE_URL}/webhook/traffic-event?x_webhook_secret={urllib.parse.quote(WEBHOOK_SECRET)}"
    req = urllib.request.Request(url, data=payload, method="POST", headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            body = resp.read().decode("utf-8")
            print(f"[tail_bridge] {domain} -> NetScope : {body}")
    except Exception as e:
        print(f"[tail_bridge] NetScope injoignable pour {domain} ({e}) — ignoré "
              f"(vérifie que launch_all.py tourne bien).")


def _should_notify(domain: str) -> bool:
    now = time.time()
    last = _last_seen.get(domain)
    if last is not None and (now - last) < COOLDOWN_SECONDS:
        return False
    _last_seen[domain] = now
    return True


def run() -> None:
    print(f"[tail_bridge] Surveillance de {LOG_PATH} en direct (comme `tail -f`)...")
    while not LOG_PATH.exists():
        print("[tail_bridge] En attente de dns_proxy.py (fichier de log pas encore créé)...")
        time.sleep(1.0)

    with open(LOG_PATH, "r", encoding="utf-8") as f:
        f.seek(0, 2)  # se placer à la FIN du fichier — on ne traite que les NOUVELLES lignes
        while True:
            line = f.readline()
            if not line:
                time.sleep(POLL_INTERVAL)
                continue

            parts = line.rstrip("\n").split("\t")
            if len(parts) != 3:
                continue
            _, client_ip, domain = parts

            if domain and domain != "?" and _should_notify(domain):
                _notify_netscope(domain)


if __name__ == "__main__":
    run()
