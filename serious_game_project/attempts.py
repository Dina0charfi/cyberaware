"""
attempts.py — suivi RÉEL des tentatives du serious game.

Avant cette version, le résultat d'une tentative (clicked/opened/ignored/
reported) était un tirage au sort pondéré (random.random()). Ici, il ne l'est
plus : une tentative reste "pending" tant qu'aucun événement réel ne s'est
produit, et n'est finalisée que par l'un de ces deux événements observables :

  - un VRAI clic sur le lien de la simulation -> GET /track/<token> dans
    server.py, une vraie requête HTTP déclenchée par le navigateur, pas une
    simulation JS. Finalise l'action à "clicked".
  - un choix explicite dans l'interface (bouton "Signaler" ou "Ignorer") ->
    POST /api/resolve dans server.py. Finalise l'action à "reported" ou
    "ignored".

Tant que rien de tout ça ne s'est produit, la tentative reste en attente et
ne compte pas dans les statistiques de campagne — pour ne pas fausser le
taux d'exploitation avec des simulations jamais résolues.
"""

import os
import uuid
from datetime import datetime, timezone

from targets import (
    TARGETS_BY_ID, VECTORS, ACTION_META,
    apply_attack_outcome, is_attacker_success,
    record_attempt, get_target_stats, compute_success_probability,
)
from llm_scenario import generate_scenario
import mailer
import whatsapp

# URL publique utilisée pour construire le VRAI lien inséré dans un email
# envoyé pour de vrai (voir mailer.py). En local, ça reste localhost — donc
# cliquable uniquement depuis la même machine. Pour qu'un vrai destinataire
# externe (téléphone, autre PC) puisse cliquer, il faut mettre ici l'IP locale
# du poste ou une URL de tunnel (ngrok...), voir README.md.
PUBLIC_URL = os.environ.get("SERIOUSGAME_PUBLIC_URL", f"http://localhost:{os.environ.get('SERIOUSGAME_PORT', '8880')}").rstrip("/")

# Tentatives en attente d'un vrai événement, en mémoire — comme le reste de
# l'état du jeu (voir server.py). Clé = token unique généré à l'envoi.
PENDING: dict[str, dict] = {}

# Compteur de campagne — vit ici (et pas dans server.py) car il n'est mis à
# jour qu'au moment de la RÉSOLUTION d'une tentative, pas à son envoi.
campaign = {"attempts": 0, "successes": 0}


def reset_campaign() -> None:
    campaign["attempts"] = 0
    campaign["successes"] = 0


def reset_pending() -> None:
    """Oublie les tentatives envoyées mais jamais résolues (utilisé par /api/campaign/reset)."""
    PENDING.clear()


def build_scenario_content(target: dict, vector_key: str, track_url: str) -> dict:
    """
    Construit le message affiché au joueur pour un vecteur donné. `track_url`
    est le VRAI lien qui, s'il est suivi, déclenche /track/<token> côté
    serveur — c'est cette URL qui fait office d'appât, quel que soit le
    vecteur narratif (email, QR code, WhatsApp, faux gain...).
    """
    vector = VECTORS[vector_key]
    name = target["name"]
    link = f'<a href="{track_url}" target="_blank" rel="noopener">%s</a>'

    # Détails déterministes (dérivés de l'id de la cible, pas aléatoires) pour
    # que le même employé voie toujours les mêmes "faux" détails d'une
    # tentative à l'autre — plus crédible qu'un texte générique, sans pour
    # autant introduire de vrai hasard dans le jeu.
    seed = sum(ord(c) for c in target["id"])
    fake_last_digits = f"{(seed * 37) % 10000:04d}"
    fake_city = ["Tunis", "Sfax", "Sousse", "Nabeul", "Bizerte"][seed % 5]
    fake_ip = f"{100 + seed % 50}.{20 + seed % 80}.{seed % 200}.{seed % 250}"
    now = datetime.now()
    fake_datetime = now.strftime("%d/%m/%Y à %Hh%M")
    case_ref = f"ABC-{now.strftime('%Y%m')}-{seed % 9000 + 1000}"

    templates = {
        "phishing": {
            "type": "email",
            "sender": "Banque ABC — Sécurité <securite@abc-tn-notifications.com>",
            "subject": f"Alerte sécurité — connexion inhabituelle sur votre compte •••• {fake_last_digits}",
            "body": (
                f"Bonjour {name},<br><br>"
                f"Nous avons détecté une connexion à votre espace client depuis un appareil non "
                f"reconnu le {fake_datetime}, depuis la région de {fake_city} (IP {fake_ip}).<br><br>"
                f"Si vous n'êtes pas à l'origine de cette connexion, votre compte peut avoir été "
                f"compromis. Par mesure de précaution, l'accès à certains services (virements, "
                f"paiements en ligne) a été temporairement restreint.<br><br>"
                f"Merci de confirmer votre identité sous 24h pour lever cette restriction. Passé ce "
                f"délai, une vérification en agence sera nécessaire.<br><br>"
                + (link % "Confirmer mon identité et sécuriser mon compte") +
                f"<br><br>Référence dossier : {case_ref}<br>"
                f"Cordialement,<br>Service Sécurité — Banque ABC<br>"
                f"<span style=\"font-size:11px;color:#9AA2AD;\">Cet email est envoyé automatiquement, "
                f"merci de ne pas y répondre directement.</span>"
            ),
        },
        "whatsapp": {
            "type": "whatsapp",
            "sender": "Banque ABC Assistance ✅ (compte non officiel, numéro personnel)",
            "subject": f"Vérification de sécurité requise — dossier {case_ref}",
            "body": (
                f"Bonjour {name}, je suis Amine, conseiller au service sécurité de Banque ABC. 👋<br><br>"
                f"Notre système a signalé une tentative de connexion suspecte sur votre compte "
                f"(•••• {fake_last_digits}) le {fake_datetime} depuis {fake_city}. Par précaution, "
                f"certaines opérations sont bloquées en attendant une vérification rapide de votre "
                f"identité.<br><br>"
                f"Pouvez-vous confirmer que c'est bien vous en suivant ce lien sécurisé ? Ça prend "
                f"2 minutes et ça évitera un blocage complet du compte.<br><br>"
                + (link % "Vérifier mon identité maintenant") +
                f"<br><br>Dossier : {case_ref}. N'hésitez pas si vous avez des questions 🙏"
            ),
        },
        "loterie": {
            "type": "loterie",
            "sender": "\"Banque ABC — Service Promotions\" (adresse suspecte)",
            "subject": "🎉 Félicitations ! Vous avez gagné 20 000 DT",
            "body": (
                f"Bonjour {name}, votre compte a été tiré au sort parmi nos clients fidèles et vous "
                f"avez gagné <b>20 000 DT</b> ! Remplissez le formulaire ci-dessous (nom, RIB, CIN) sous "
                f"48h pour débloquer le virement, sans quoi le gain sera attribué à un autre gagnant."
                f"<br><br>" + (link % "Remplir le formulaire pour réclamer mon gain")
            ),
        },
        "qrcode": {
            "type": "qrcode",
            "sender": "Affiche dans la salle de pause",
            "subject": "QR code — \"Nouveau menu de la cantine, scannez-moi !\"",
            "body": (
                f"Un QR code collé dans la salle de pause promet le nouveau menu de la cantine. "
                f"Scanne-le ci-dessous avec ton téléphone (ou clique dessus depuis ce navigateur) "
                f"pour voir ce qui se passe vraiment.<br><br>" + (link % "Voir le menu (lien du QR code)")
            ),
        },
    }

    content = dict(templates[vector_key])
    content["vector_label"] = vector["label"]
    content["vector_icon"] = vector["icon"]
    content["track_url"] = track_url  # URL brute (sans balise <a>) — utile côté front pour générer un vrai QR code image
    return content


def start_attempt(
    target_id: str, vector_key: str, real_email: str | None = None,
    real_whatsapp: str | None = None,
) -> dict:
    """
    `real_email` est optionnel : si fourni ET que SMTP est configuré dans
    .env (voir mailer.py), un VRAI email est envoyé à cette adresse avec le
    vrai lien de tracking dedans — il faut alors vraiment ouvrir sa boîte
    mail et cliquer pour déclencher "clicked", pas juste cliquer dans le jeu.
    `real_whatsapp` fonctionne de la même façon pour un vrai message WhatsApp
    (voir whatsapp.py, GREEN API) : si un numéro est fourni ET que GREEN API
    est configuré dans .env, le message part vraiment et automatiquement,
    sans action manuelle. Les deux sont indépendants et fonctionnent avec
    n'importe quel vecteur — si rien n'est fourni ou que le service n'est pas
    configuré, le comportement est identique à avant : message affiché dans
    le navigateur uniquement, avec le même lien réellement trackable.
    """
    if target_id not in TARGETS_BY_ID:
        raise ValueError(f"Cible inconnue : {target_id}")
    if vector_key not in VECTORS:
        raise ValueError(f"Vecteur inconnu : {vector_key}")

    token = uuid.uuid4().hex
    track_url = f"{PUBLIC_URL}/track/{token}"

    target = TARGETS_BY_ID[target_id]
    scenario = build_scenario_content(target, vector_key, track_url)

    email_status = None
    if real_email:
        sent, message = mailer.send_real_email(real_email, scenario["subject"], scenario["body"])
        email_status = {"sent": sent, "message": message, "to": real_email}

    whatsapp_status = None
    if real_whatsapp:
        sent, message = whatsapp.send_real_whatsapp(real_whatsapp, scenario["body"])
        whatsapp_status = {"sent": sent, "message": message, "to": real_whatsapp}

    PENDING[token] = {
        "token": token,
        "target_id": target_id,
        "vector_key": vector_key,
        "real_email": real_email,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "resolved": False,
        "action": None,
        "result": None,
    }

    return {
        "token": token,
        "target": target,
        "vector": {"key": vector_key, **VECTORS[vector_key]},
        "scenario": scenario,
        "email_status": email_status,  # None si aucune adresse réelle n'a été fournie
        "whatsapp_status": whatsapp_status,  # None si aucun numéro WhatsApp réel n'a été fourni
        # Purement indicatif : n'influence plus le résultat (voir compute_success_probability).
        "estimated_probability": round(compute_success_probability(target["risk"], vector_key) * 100, 1),
    }


def resolve_attempt(token: str, action: str) -> dict:
    """
    Finalise une tentative suite à un VRAI événement. Idempotent : si la
    tentative est déjà résolue (ex. la personne revisite le lien après avoir
    déjà signalé), on renvoie le résultat déjà figé sans rien recompter —
    sinon un simple rafraîchissement de page fausserait les statistiques.
    """
    if token not in PENDING:
        raise KeyError(f"Tentative inconnue ou expirée : {token}")

    entry = PENDING[token]
    if entry["resolved"]:
        return entry["result"]

    target = TARGETS_BY_ID[entry["target_id"]]
    vector_key = entry["vector_key"]
    vector = VECTORS[vector_key]

    risk_before = target["risk"]
    risk_after = apply_attack_outcome(target, action)
    record_attempt(entry["target_id"], vector_key, action)
    narrative = generate_scenario(target, vector["label"], action)

    campaign["attempts"] += 1
    success = is_attacker_success(action)
    if success:
        campaign["successes"] += 1
    exploitation_rate = round(100 * campaign["successes"] / campaign["attempts"], 1)

    entry["resolved"] = True
    entry["action"] = action
    entry["result"] = {
        "token": token,
        "target": target,
        "vector": {"key": vector_key, **vector},
        "action": action,
        "action_label": ACTION_META[action]["label"],
        "action_verdict": ACTION_META[action]["verdict"],
        "action_icon": ACTION_META[action]["icon"],
        "success": success,
        "narrative": narrative,
        "defense_note": vector["defense_note"],
        "related_agent": vector["agent"],
        "risk_before": risk_before,
        "risk_after": risk_after,
        "target_stats": get_target_stats(entry["target_id"]),
        "campaign": {
            "attempts": campaign["attempts"],
            "successes": campaign["successes"],
            "exploitation_rate": exploitation_rate,
        },
    }
    return entry["result"]


def get_attempt(token: str) -> dict | None:
    return PENDING.get(token)
