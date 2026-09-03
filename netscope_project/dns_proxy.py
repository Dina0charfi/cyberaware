"""
dns_proxy.py — petit serveur/proxy DNS local, pour brancher un VRAI appareil
(ton téléphone) sur NetScope en direct.
=====================================================================
Concept (le "tap" DNS que ton encadrant a évoqué) : jusqu'ici, c'est NetScope
qui va CHOISIR des domaines et les résoudre lui-même (voir live_feed.py). Ici
on inverse le sens du flux — un vrai appareil (ton téléphone) pointe SON DNS
vers ce PC. Chaque requête DNS qu'il émet (donc chaque domaine que tu visites
en vrai, en navigant normalement sur ton téléphone) passe PHYSIQUEMENT par ce
proxy avant d'aller sur internet :

  1. le proxy relaie la requête TELLE QUELLE vers un vrai résolveur public
     (8.8.8.8, Google DNS) et renvoie la réponse au téléphone — la navigation
     continue de fonctionner normalement, le téléphone ne voit aucune
     différence ;
  2. en parallèle, il journalise le nom de domaine demandé dans
     data/dns_queries.log, une ligne par requête — c'est ce fichier que
     tail_bridge.py surveille ensuite en direct (comme `tail -f`) pour
     pousser chaque domaine vers le vrai webhook de NetScope.

On ne reconstruit JAMAIS le paquet DNS nous-mêmes (aucun risque de bug
d'encodage) : dnspython sert uniquement à LIRE le nom de domaine demandé pour
le journal ; le paquet brut (bytes) est relayé tel quel dans les deux sens.

Lancer :
    python dns_proxy.py

Puis, sur le téléphone (connecté au MÊME réseau WiFi que ce PC) : Réglages
Wi-Fi -> réseau connecté -> Configurer DNS -> Manuel -> mettre l'adresse IP
LOCALE de ce PC (visible avec `ipconfig`, ligne "Adresse IPv4", ex.
192.168.1.42). Débranche/remets le WiFi du téléphone pour que le changement
s'applique.

⚠️ Le port 53 est un port DNS standard — si Windows le refuse ("Permission
denied" / "Access is denied"), relance ce terminal "en tant qu'administrateur".
⚠️ Si le téléphone n'arrive pas à joindre ce PC : autorise le port UDP 53 en
entrée dans le Pare-feu Windows (Panneau de configuration -> Pare-feu Windows
Defender -> Paramètres avancés -> Règles de trafic entrant -> Nouvelle règle).
"""

import socket
import threading
import time
from pathlib import Path

import dns.message

LISTEN_HOST = "0.0.0.0"
LISTEN_PORT = 53
UPSTREAM_DNS = ("8.8.8.8", 53)  # vrai résolveur public — la navigation continue de marcher normalement

BASE_DIR = Path(__file__).resolve().parent
LOG_PATH = BASE_DIR / "data" / "dns_queries.log"
LOG_PATH.parent.mkdir(parents=True, exist_ok=True)


def _log_query(domain: str, client_ip: str) -> None:
    """Une ligne par requête DNS observée — c'est ce fichier que tail_bridge.py
    surveille en direct pour pousser vers NetScope. Best-effort : une erreur
    d'écriture ne doit jamais empêcher la requête d'être relayée normalement."""
    try:
        with open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write(f"{time.time():.3f}\t{client_ip}\t{domain}\n")
    except Exception as e:
        print(f"[dns_proxy] Impossible d'écrire le log ({e}) — ignoré.")


def _handle_query(data: bytes, client_addr, sock: socket.socket) -> None:
    domain = "?"
    try:
        msg = dns.message.from_wire(data)
        if msg.question:
            domain = str(msg.question[0].name).rstrip(".")
    except Exception:
        pass  # paquet non standard/mal formé -> on le relaie quand même, juste sans log de domaine

    _log_query(domain, client_addr[0])
    print(f"[dns_proxy] {client_addr[0]} -> {domain}")

    try:
        upstream_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        upstream_sock.settimeout(3.0)
        upstream_sock.sendto(data, UPSTREAM_DNS)
        response, _ = upstream_sock.recvfrom(4096)
        upstream_sock.close()
        sock.sendto(response, client_addr)
    except Exception as e:
        print(f"[dns_proxy] Erreur en relayant vers l'upstream ({e}) — pas de réponse envoyée "
              f"(le téléphone réessaiera ou tombera sur un timeout pour cette requête).")


def run() -> None:
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.bind((LISTEN_HOST, LISTEN_PORT))
    except PermissionError:
        print(f"[dns_proxy] Impossible d'ouvrir le port {LISTEN_PORT} (permission refusée). "
              f"Relance ce terminal en tant qu'administrateur.")
        return
    except OSError as e:
        print(f"[dns_proxy] Impossible d'ouvrir le port {LISTEN_PORT} ({e}). "
              f"Un autre programme l'utilise peut-être déjà (VPN, ICS...).")
        return

    print(f"[dns_proxy] Proxy DNS démarré sur {LISTEN_HOST}:{LISTEN_PORT} "
          f"(relai vers {UPSTREAM_DNS[0]}), log -> {LOG_PATH}")
    print("[dns_proxy] Configure le DNS de ton téléphone sur l'IP locale de ce PC pour commencer la démo.")

    while True:
        try:
            data, client_addr = sock.recvfrom(4096)
        except Exception as e:
            print(f"[dns_proxy] Erreur de réception (ignorée) : {e}")
            continue
        threading.Thread(target=_handle_query, args=(data, client_addr, sock), daemon=True).start()


if __name__ == "__main__":
    run()
