#!/usr/bin/env python3
"""
event_simulator.py — rejoue un flux de faux événements vers PhishHunter,
Sentinel et NetScope, uniquement en mode démo (`launch_all.py --simulate`).

Pourquoi ce fichier existe : en usage normal, chaque agent reste silencieux
tant que personne ne lui envoie rien (voir les commentaires dans
launch_all.py) — cohérent avec le principe "aucun agent ne s'auto-déclenche
sans qu'un vrai événement arrive". Pour une démo, il faut bien que quelque
chose leur envoie des événements plausibles : c'est le rôle unique de ce
script. Il n'invente aucune logique de décision — il se contente d'appeler
les vrais webhooks de chaque agent (les mêmes qu'un vrai SIEM, une vraie
boîte mail ou un vrai firewall appellerait), donc le comportement observé en
démo (score, action, notification CrisisBot) est le vrai comportement de
production, pas une version simplifiée.

NetScope et DarkWatch ont en plus leur propre boucle d'auto-scan interne
(activée séparément par launch_all.py via NETSCOPE_AUTO_SCAN / DARKWATCH_AUTO_SCAN) —
ce script ne s'occupe que des 3 points d'entrée "push" (webhooks) : PhishHunter,
Sentinel, et NetScope (qui a aussi un webhook en plus de son auto-scan).

Ce script n'est jamais lancé seul : il est importé et démarré par
launch_all.py --simulate, 25s après le démarrage des agents (le temps que
les modèles ML finissent de charger).
"""

import json
import os
import random
import threading
import time
import urllib.error
import urllib.request

PHISHHUNTER_URL = "http://localhost:8002/webhook/email"
SENTINEL_URL = "http://localhost:8003/api/webhook/signin-event"
NETSCOPE_URL = "http://localhost:8001/webhook/traffic-event"

# Mêmes valeurs par défaut que les agents eux-mêmes (voir sentinel_project/backend/app.py
# et netscope_project/src/netscope_agent/api.py) — si l'utilisateur a surchargé le
# secret dans son .env, il faut le même ici, sinon les deux webhooks renverront 401.
SENTINEL_WEBHOOK_SECRET = os.environ.get("SENTINEL_WEBHOOK_SECRET", "change-moi-avant-toute-vraie-utilisation")
NETSCOPE_WEBHOOK_SECRET = os.environ.get("NETSCOPE_WEBHOOK_SECRET", "change-moi-avant-toute-vraie-utilisation")

# --------------------------------------------------------------------------
# Jeux d'événements factices — volontairement variés (certains bénins,
# certains clairement suspects) pour que la démo montre les deux
# comportements possibles de chaque agent, pas uniquement des alertes.
# --------------------------------------------------------------------------

FAKE_EMAILS = [
    {
        "sender": "support@paypa1-secure-verify.com",
        "subject": "Action requise : votre compte sera suspendu sous 24h",
        "body": (
            "Cher client, nous avons détecté une activité inhabituelle sur votre compte. "
            "Cliquez immédiatement sur ce lien pour vérifier votre identité et éviter la "
            "suspension définitive : http://paypa1-secure-verify.com/confirm?id=8827"
        ),
    },
    {
        "sender": "rh@banque-abc.tn",
        "subject": "Planning des congés — semaine prochaine",
        "body": "Bonjour à tous, le planning des congés de la semaine prochaine est disponible sur l'intranet.",
    },
    {
        "sender": "it-support@banque-abc-secure.info",
        "subject": "URGENT — mise à jour de votre mot de passe expirée",
        "body": (
            "Votre mot de passe expire dans 2 heures. Merci de le renouveler immédiatement "
            "via ce lien sécurisé : http://banque-abc-secure.info/reset-password"
        ),
    },
    {
        "sender": "compta@banque-abc.tn",
        "subject": "Facture fournisseur — validation nécessaire",
        "body": "Bonjour, merci de valider la facture jointe avant vendredi. Cordialement.",
    },
]

FAKE_SIGNIN_EVENTS = [
    # Utilisateur standard, horaires normaux, poste connu -> ne devrait pas alarmer.
    {"userPrincipalName": "SDH2394", "hour": 9, "deviceId": "PC-3243", "department": "4 - Engineering"},
    # Département sensible + horaires décalés + nouveau poste -> profil à risque.
    {"userPrincipalName": "LJC0191", "hour": 3, "deviceId": "PC-INCONNU-01", "department": "Direction Financiere"},
    {"userPrincipalName": "TKM1539", "hour": 14, "deviceId": "PC-6953", "department": "4 - Engineering"},
    # Connexion de nuit sur un compte de la Direction Generale -> cas typique d'escalade.
    {"userPrincipalName": "MBK0442", "hour": 2, "deviceId": "PC-NOUVEAU-77", "department": "Direction Generale"},
]

FAKE_DOMAINS = [
    "login-microsoft-secure-auth.tk",   # domaine imitant Microsoft, TLD gratuit typique du phishing
    "banque-abc-portail-client.info",   # imite le nom de la banque elle-même
    "google.com",                       # domaine légitime, sert de contre-exemple
    "wikipedia.org",                    # domaine légitime
    "verify-account-update-secure.xyz", # vocabulaire "verify/update/secure" typique
]


def _post_json(url: str, payload: dict, timeout: int = 8) -> tuple[int, str]:
    """
    POST minimaliste en urllib (même style que notify_crisisbot dans les 4 agents) :
    pas de dépendance externe, échec silencieux en cas d'agent pas encore prêt —
    la démo ne doit jamais planter juste parce qu'un agent met plus de temps à
    démarrer que les autres.
    """
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, method="POST", headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", errors="replace")
    except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
        return 0, str(e)


def _send_fake_email():
    email = random.choice(FAKE_EMAILS)
    status, body = _post_json(PHISHHUNTER_URL, email)
    print(f"[event_simulator] PhishHunter <- email de {email['sender']}  (status={status})")


def _send_fake_signin():
    event = random.choice(FAKE_SIGNIN_EVENTS)
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc).replace(hour=event["hour"])
    payload = {
        "userPrincipalName": event["userPrincipalName"],
        "createdDateTime": now.isoformat().replace("+00:00", "Z"),
        "deviceId": event["deviceId"],
        "department": event["department"],
    }
    url = f"{SENTINEL_URL}?x_webhook_secret={SENTINEL_WEBHOOK_SECRET}"
    status, body = _post_json(url, payload)
    print(f"[event_simulator] Sentinel <- connexion {event['userPrincipalName']} ({event['department']}, {event['hour']}h)  (status={status})")


def _send_fake_traffic():
    domain = random.choice(FAKE_DOMAINS)
    payload = {"domain": domain}  # pas de features : NetScope les calcule en direct, comme un vrai firewall générique
    url = f"{NETSCOPE_URL}?x_webhook_secret={NETSCOPE_WEBHOOK_SECRET}"
    status, body = _post_json(url, payload)
    print(f"[event_simulator] NetScope <- requête DNS vers {domain}  (status={status})")


SENDERS = [_send_fake_email, _send_fake_signin, _send_fake_traffic]


def run_simulator(stop_event: threading.Event, interval_range: tuple[int, int] = (8, 18)) -> None:
    """
    Boucle principale : envoie un événement factice (choisi au hasard parmi les
    3 agents) toutes les 8 à 18 secondes, jusqu'à ce que stop_event soit levé
    (Ctrl+C dans launch_all.py). L'intervalle est volontairement irrégulier
    pour que la démo ressemble à un vrai flux plutôt qu'à un métronome.
    """
    print("[event_simulator] Démarré — un faux événement toutes les 8-18s vers PhishHunter/Sentinel/NetScope.")
    while not stop_event.is_set():
        sender = random.choice(SENDERS)
        try:
            sender()
        except Exception as e:
            print(f"[event_simulator] Erreur lors de l'envoi d'un événement : {e}")
        stop_event.wait(random.uniform(*interval_range))
    print("[event_simulator] Arrêté.")


if __name__ == "__main__":
    # Permet de tester ce fichier seul, sans passer par launch_all.py --simulate,
    # tant que les 3 agents tournent déjà (ports 8001/8002/8003).
    stop = threading.Event()
    try:
        run_simulator(stop)
    except KeyboardInterrupt:
        stop.set()
