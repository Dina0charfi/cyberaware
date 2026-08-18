#!/usr/bin/env python3
"""
server.py — dashboard + API du serious game "Dans la peau de l'attaquant"
================================================================
Le joueur choisit une cible fictive (employé de "Banque ABC") et un vecteur
d'ingénierie sociale. Le résultat n'est PLUS un tirage au sort : il dépend
d'un vrai événement observable (voir attempts.py) —

  1. POST /api/attack crée une tentative "en attente" et renvoie un message
     simulé contenant un vrai lien cliquable : /track/<token>.
  2. Si ce lien est réellement suivi (vraie requête HTTP du navigateur,
     typiquement ouverte dans un nouvel onglet), GET /track/<token> finalise
     la tentative à "clicked" et affiche une page pédagogique.
  3. Sinon, l'utilisateur peut trancher explicitement dans l'interface via
     POST /api/resolve avec action="reported" ou "ignored".

Tant qu'aucun de ces deux événements réels ne s'est produit, la tentative
reste en attente et ne compte dans aucune statistique.

Le texte qui accompagne le résultat est rédigé par un LLM (Groq) une fois
l'action réelle connue — même principe que les autres agents CyberAware :
le LLM raconte, il ne décide jamais.

Aucune dépendance externe : uniquement http.server, comme DarkWatch et
CrisisBot. Rien à installer.

Usage :
    python3 server.py
    (ou "py server.py" sous Windows)

Puis ouvrir http://localhost:8880 (adapte le port avec la variable d'env
SERIOUSGAME_PORT si besoin — 8880 est choisi pour ne jamais entrer en
conflit avec les 5 autres agents : 8000 (accueil), 8877-8879, 8001-8003).
"""

import json
import os
import sys
import threading
import html as html_lib
import http.server
import socketserver
from pathlib import Path
from urllib.parse import urlparse


def _load_dotenv(path: Path) -> None:
    """
    Charge un fichier .env (KEY=VALUE, une paire par ligne) dans os.environ,
    sans dépendance externe (pas de python-dotenv — même philosophie
    "stdlib uniquement" que le reste de ce module). Une variable déjà
    présente dans l'environnement réel n'est jamais écrasée. Les lignes
    vides ou commençant par "#" sont ignorées.
    """
    if not path.is_file():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


_load_dotenv(Path(__file__).parent / ".env")

from targets import (
    TARGETS, TARGETS_BY_ID, VECTORS, reset_all_risks, reset_history,
    get_target_history, get_target_stats, get_global_vector_stats,
)
import attempts
import mailer
import whatsapp
import auto_simulate

PORT = int(os.environ.get("SERIOUSGAME_PORT", "8880"))  # 8880 : premier port libre après les 5 autres agents (8000, 8877-8879, 8001-8003)
BASE_DIR = Path(__file__).parent
STATIC_DIR = BASE_DIR / "static"

VALID_MANUAL_ACTIONS = ("reported", "ignored")  # "clicked" ne peut venir QUE d'un vrai clic sur /track/<token>


def render_landing_page(result: dict) -> str:
    """
    Page renvoyée par un vrai clic sur le lien de simulation (/track/<token>).
    S'ouvre dans un nouvel onglet — d'où le bouton "fermer cet onglet" plutôt
    qu'un renvoi automatique vers le jeu.
    """
    esc = html_lib.escape
    return f"""<!DOCTYPE html>
<html lang="fr"><head><meta charset="utf-8">
<title>Simulation — {esc(result['action_label'])}</title>
<style>
  body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    background: #F1F2F6; color: #14181F; margin: 0; padding: 56px 24px; }}
  .card {{ max-width: 560px; margin: 0 auto; background: #FFFFFF; border: 1px solid #E5E7EB;
    border-radius: 14px; padding: 28px; }}
  .badge {{ display: inline-block; padding: 6px 14px; border-radius: 999px; font-weight: 700;
    font-size: 13.5px; margin-bottom: 16px; background: #DC26261A; color: #DC2626; }}
  p {{ line-height: 1.6; font-size: 15px; }}
  .defense {{ background: #EA580C1A; border: 1px solid #EA580C40; border-radius: 10px;
    padding: 16px; font-size: 13.5px; margin-top: 20px; }}
  button {{ margin-top: 24px; background: #14181F; color: white; border: none; border-radius: 10px;
    padding: 10px 18px; font-size: 13.5px; font-weight: 600; cursor: pointer; }}
</style></head>
<body>
  <div class="card">
    <span class="badge">{esc(result['action_icon'])} Vous venez de cliquer sur ce lien</span>
    <p>{esc(result['narrative'])}</p>
    <p style="color:#5B6472;font-size:13px;">
      Dans une vraie situation, ce lien aurait pu mener à un faux formulaire de connexion,
      un téléchargement de malware, ou une demande de vos identifiants.
    </p>
    <div class="defense">🎓 <b>Ce qu'il faut retenir côté défense</b><br><br>{esc(result['defense_note'])}</div>
    <button onclick="window.close()">Fermer cet onglet</button>
  </div>
</body></html>"""


def render_qr_landing_page(result: dict) -> str:
    """
    Variante de la page de révélation spécifique au vecteur "qrcode" — reprend
    le design de la landing page de sensibilisation déployée séparément sur
    Netlify (sensibilisation_quishing/quishing_landing_page.html), pour que
    l'affichage soit identique que le lien soit suivi depuis le jeu (vrai
    tracking, "clicked") ou depuis l'affiche autonome (pas de tracking).
    """
    esc = html_lib.escape
    return f"""<!DOCTYPE html>
<html lang="fr"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Quishing landing page</title>
<style>
  * {{ box-sizing: border-box; }}
  body {{
    margin: 0; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Arial, sans-serif;
    background: linear-gradient(180deg, #0f172a, #1e293b);
    min-height: 100vh; display: flex; align-items: center; justify-content: center; padding: 24px;
  }}
  .card {{ background: #fff; border-radius: 16px; max-width: 560px; width: 100%; padding: 40px 32px;
    box-shadow: 0 20px 60px rgba(0,0,0,0.35); }}
  .badge {{ display: inline-flex; align-items: center; gap: 8px; background: #fee2e2; color: #dc2626;
    font-weight: 700; font-size: 13px; letter-spacing: 0.04em; text-transform: uppercase;
    padding: 6px 12px; border-radius: 999px; margin-bottom: 20px; }}
  h1 {{ font-size: 26px; color: #1e293b; margin: 0 0 12px; line-height: 1.3; }}
  p.lead {{ color: #64748b; font-size: 16px; line-height: 1.6; margin: 0 0 28px; }}
  .signals {{ background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 12px; padding: 20px 24px; margin-bottom: 24px; }}
  .signals h2 {{ font-size: 15px; color: #1e293b; margin: 0 0 12px; }}
  .signals ul {{ margin: 0; padding-left: 20px; color: #1e293b; font-size: 14px; line-height: 1.9; }}
  .signals li strong {{ color: #dc2626; }}
  .footer-note {{ display: flex; align-items: flex-start; gap: 10px; background: #ecfdf5;
    border: 1px solid #bbf7d0; border-radius: 12px; padding: 16px 18px; font-size: 13px; color: #166534; line-height: 1.6; }}
  .footer-note b {{ color: #16a34a; }}
  button {{ margin-top: 24px; background: #14181F; color: white; border: none; border-radius: 10px;
    padding: 10px 18px; font-size: 13.5px; font-weight: 600; cursor: pointer; }}
</style></head>
<body>
  <div class="card">
    <span class="badge">⚠ Simulation interne — Quishing</span>
    <h1>Vous venez de scanner un QR code piégé.</h1>
    <p class="lead">{esc(result['narrative'])}</p>
    <div class="signals">
      <h2>Comment repérer un QR code piégé la prochaine fois :</h2>
      <ul>
        <li><strong>Autocollant collé par-dessus</strong> un QR code officiel — vérifiez qu'il n'est pas superposé.</li>
        <li><strong>Contexte inhabituel</strong> — affiche apparue soudainement, urgence artificielle.</li>
        <li><strong>URL affichée après le scan</strong> — vérifiez le nom de domaine avant de cliquer.</li>
        <li><strong>Demande d'identifiants ou de paiement</strong> juste après le scan.</li>
        <li><strong>Absence de logo, de HTTPS ou de charte graphique</strong> cohérente.</li>
      </ul>
    </div>
    <div class="footer-note">
      <span>✅</span>
      <span><b>Ce qu'il faut retenir côté défense :</b> {esc(result['defense_note'])}</span>
    </div>
    <button onclick="window.close()">Fermer cet onglet</button>
  </div>
</body></html>"""


def render_whatsapp_landing_page(result: dict) -> str:
    """
    Variante de la page de révélation spécifique au vecteur "whatsapp" — même
    esprit que render_qr_landing_page, adaptée au prétexte WhatsApp.
    """
    esc = html_lib.escape
    return f"""<!DOCTYPE html>
<html lang="fr"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Whatsapp phishing landing page</title>
<style>
  * {{ box-sizing: border-box; }}
  body {{
    margin: 0; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Arial, sans-serif;
    background: linear-gradient(180deg, #0f172a, #1e293b);
    min-height: 100vh; display: flex; align-items: center; justify-content: center; padding: 24px;
  }}
  .card {{ background: #fff; border-radius: 16px; max-width: 560px; width: 100%; padding: 40px 32px;
    box-shadow: 0 20px 60px rgba(0,0,0,0.35); }}
  .badge {{ display: inline-flex; align-items: center; gap: 8px; background: #fee2e2; color: #dc2626;
    font-weight: 700; font-size: 13px; letter-spacing: 0.04em; text-transform: uppercase;
    padding: 6px 12px; border-radius: 999px; margin-bottom: 20px; }}
  h1 {{ font-size: 26px; color: #1e293b; margin: 0 0 12px; line-height: 1.3; }}
  p.lead {{ color: #64748b; font-size: 16px; line-height: 1.6; margin: 0 0 28px; }}
  .signals {{ background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 12px; padding: 20px 24px; margin-bottom: 24px; }}
  .signals h2 {{ font-size: 15px; color: #1e293b; margin: 0 0 12px; }}
  .signals ul {{ margin: 0; padding-left: 20px; color: #1e293b; font-size: 14px; line-height: 1.9; }}
  .signals li strong {{ color: #dc2626; }}
  .footer-note {{ display: flex; align-items: flex-start; gap: 10px; background: #ecfdf5;
    border: 1px solid #bbf7d0; border-radius: 12px; padding: 16px 18px; font-size: 13px; color: #166534; line-height: 1.6; }}
  .footer-note b {{ color: #16a34a; }}
  button {{ margin-top: 24px; background: #14181F; color: white; border: none; border-radius: 10px;
    padding: 10px 18px; font-size: 13.5px; font-weight: 600; cursor: pointer; }}
</style></head>
<body>
  <div class="card">
    <span class="badge">⚠ Simulation interne — Phishing WhatsApp</span>
    <h1>Vous venez de cliquer sur un lien reçu par WhatsApp.</h1>
    <p class="lead">{esc(result['narrative'])}</p>
    <div class="signals">
      <h2>Comment repérer un message WhatsApp frauduleux la prochaine fois :</h2>
      <ul>
        <li><strong>Numéro inconnu, même avec une photo de profil crédible</strong> — une banque ne contacte jamais un client via un numéro WhatsApp personnel.</li>
        <li><strong>Urgence artificielle</strong> — "sous 24h", "compte bloqué" : la pression de temps sert à empêcher de vérifier.</li>
        <li><strong>Lien raccourci ou domaine inhabituel</strong> — vérifiez l'URL complète avant de cliquer.</li>
        <li><strong>Demande d'informations bancaires</strong> par chat — un canal qu'une banque n'utilise jamais pour ça.</li>
        <li><strong>Un doute suffit</strong> — contactez directement votre agence par un canal officiel connu, jamais via le lien reçu.</li>
      </ul>
    </div>
    <div class="footer-note">
      <span>✅</span>
      <span><b>Ce qu'il faut retenir côté défense :</b> {esc(result['defense_note'])}</span>
    </div>
    <button onclick="window.close()">Fermer cet onglet</button>
  </div>
</body></html>"""


def render_loterie_form_page(entry: dict, target: dict) -> str:
    """
    VRAI faux formulaire du vecteur "loterie" (/claim/<token>, GET) — contrairement
    aux autres vecteurs où suivre le lien suffit à déclencher "clicked", ici
    l'ouverture de la page ne résout PAS la tentative : seule la VRAIE soumission
    de ce formulaire (bouton "Réclamer mon gain" cliqué -> POST /claim/<token>,
    voir Handler.do_POST) le fait. Les champs sont volontairement non validés
    côté serveur et leur contenu n'est jamais conservé : ce qui compte pour la
    simulation, c'est le fait d'avoir soumis le formulaire, pas les données tapées.
    """
    esc = html_lib.escape
    return f"""<!DOCTYPE html>
<html lang="fr"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Réclamer votre gain — Banque ABC</title>
<style>
  * {{ box-sizing: border-box; }}
  body {{
    margin: 0; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Arial, sans-serif;
    background: linear-gradient(180deg, #0f172a, #1e293b);
    min-height: 100vh; display: flex; align-items: center; justify-content: center; padding: 24px;
  }}
  .card {{ background: #fff; border-radius: 16px; max-width: 480px; width: 100%; padding: 40px 32px;
    box-shadow: 0 20px 60px rgba(0,0,0,0.35); }}
  .badge {{ display: inline-flex; align-items: center; gap: 8px; background: #fef3c7; color: #b45309;
    font-weight: 700; font-size: 13px; letter-spacing: 0.04em; text-transform: uppercase;
    padding: 6px 12px; border-radius: 999px; margin-bottom: 20px; }}
  h1 {{ font-size: 24px; color: #1e293b; margin: 0 0 10px; line-height: 1.3; }}
  p.lead {{ color: #64748b; font-size: 15px; line-height: 1.6; margin: 0 0 24px; }}
  label {{ display: block; font-size: 13px; font-weight: 600; color: #1e293b; margin: 14px 0 6px; }}
  input {{ width: 100%; padding: 10px 12px; border: 1px solid #cbd5e1; border-radius: 8px;
    font-size: 14px; font-family: inherit; }}
  input:focus {{ outline: 2px solid #f59e0b; border-color: #f59e0b; }}
  button {{ margin-top: 24px; width: 100%; background: #b45309; color: white; border: none; border-radius: 10px;
    padding: 13px 18px; font-size: 14.5px; font-weight: 700; cursor: pointer; }}
  .fineprint {{ font-size: 11.5px; color: #9ca3af; margin-top: 14px; line-height: 1.5; }}
</style></head>
<body>
  <div class="card">
    <span class="badge">🎉 Réclamation de gain</span>
    <h1>Bravo {esc(target['name'])}, réclamez vos 20 000 DT</h1>
    <p class="lead">Remplissez ce formulaire pour débloquer le virement sur votre compte. Traitement sous 48h après validation.</p>
    <form method="POST" action="/claim/{esc(entry['token'])}">
      <label for="nom">Nom complet</label>
      <input id="nom" name="nom" type="text" placeholder="{esc(target['name'])}" required>
      <label for="telephone">Numéro de téléphone</label>
      <input id="telephone" name="telephone" type="tel" placeholder="+216 XX XXX XXX" required>
      <label for="rib">RIB (compte bancaire)</label>
      <input id="rib" name="rib" type="text" placeholder="TN59 XXXX XXXX XXXX XXXX XXXX" required>
      <label for="cin">Numéro CIN</label>
      <input id="cin" name="cin" type="text" placeholder="00000000" required>
      <button type="submit">Réclamer mon gain</button>
    </form>
    <p class="fineprint">Simulation interne CyberAware — aucune donnée réelle saisie ici n'est enregistrée ni transmise à qui que ce soit ; seul le fait d'avoir soumis ce formulaire est utilisé, à des fins pédagogiques.</p>
  </div>
</body></html>"""


def render_loterie_landing_page(result: dict) -> str:
    """
    Variante de la page de révélation spécifique au vecteur "loterie" (faux
    formulaire "vous avez gagné 20 000 DT") — même esprit que les autres
    landing pages thématiques.
    """
    esc = html_lib.escape
    return f"""<!DOCTYPE html>
<html lang="fr"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Fausse loterie landing page</title>
<style>
  * {{ box-sizing: border-box; }}
  body {{
    margin: 0; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Arial, sans-serif;
    background: linear-gradient(180deg, #0f172a, #1e293b);
    min-height: 100vh; display: flex; align-items: center; justify-content: center; padding: 24px;
  }}
  .card {{ background: #fff; border-radius: 16px; max-width: 560px; width: 100%; padding: 40px 32px;
    box-shadow: 0 20px 60px rgba(0,0,0,0.35); }}
  .badge {{ display: inline-flex; align-items: center; gap: 8px; background: #fee2e2; color: #dc2626;
    font-weight: 700; font-size: 13px; letter-spacing: 0.04em; text-transform: uppercase;
    padding: 6px 12px; border-radius: 999px; margin-bottom: 20px; }}
  h1 {{ font-size: 26px; color: #1e293b; margin: 0 0 12px; line-height: 1.3; }}
  p.lead {{ color: #64748b; font-size: 16px; line-height: 1.6; margin: 0 0 28px; }}
  .signals {{ background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 12px; padding: 20px 24px; margin-bottom: 24px; }}
  .signals h2 {{ font-size: 15px; color: #1e293b; margin: 0 0 12px; }}
  .signals ul {{ margin: 0; padding-left: 20px; color: #1e293b; font-size: 14px; line-height: 1.9; }}
  .signals li strong {{ color: #dc2626; }}
  .footer-note {{ display: flex; align-items: flex-start; gap: 10px; background: #ecfdf5;
    border: 1px solid #bbf7d0; border-radius: 12px; padding: 16px 18px; font-size: 13px; color: #166534; line-height: 1.6; }}
  .footer-note b {{ color: #16a34a; }}
  button {{ margin-top: 24px; background: #14181F; color: white; border: none; border-radius: 10px;
    padding: 10px 18px; font-size: 13.5px; font-weight: 600; cursor: pointer; }}
</style></head>
<body>
  <div class="card">
    <span class="badge">⚠ Simulation interne — Faux gain / formulaire frauduleux</span>
    <h1>Vous venez de cliquer sur le lien "Réclamer mon gain".</h1>
    <p class="lead">{esc(result['narrative'])}</p>
    <div class="signals">
      <h2>Comment repérer une fausse loterie la prochaine fois :</h2>
      <ul>
        <li><strong>Vous n'avez jamais participé à un tirage au sort</strong> — un vrai gain ne tombe jamais du hasard sans inscription préalable.</li>
        <li><strong>Gain disproportionné et délai artificiel</strong> ("48h sinon perdu") — la pression empêche de vérifier calmement.</li>
        <li><strong>Demande de RIB, CIN ou identifiants</strong> pour "débloquer" un virement — aucune banque ne demande ça par email/SMS/WhatsApp.</li>
        <li><strong>Expéditeur ou domaine suspect</strong> — comparez toujours avec l'adresse officielle connue de votre banque.</li>
        <li><strong>Le réflexe qui sauve</strong> — appeler directement son agence via un numéro déjà connu, jamais celui fourni dans le message.</li>
      </ul>
    </div>
    <div class="footer-note">
      <span>✅</span>
      <span><b>Ce qu'il faut retenir côté défense :</b> {esc(result['defense_note'])}</span>
    </div>
    <button onclick="window.close()">Fermer cet onglet</button>
  </div>
</body></html>"""


class Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(STATIC_DIR), **kwargs)

    def do_GET(self):
        parsed = urlparse(self.path)

        if parsed.path == "/api/targets":
            self._send_json({
                "targets": TARGETS, "vectors": VECTORS,
                "smtp_configured": mailer.is_configured(),
                "whatsapp_configured": whatsapp.is_configured(),
            })
            return

        if parsed.path == "/api/campaign":
            # by_vector : compteurs agrégés sur TOUTES les cibles, par vecteur — ex.
            # "combien de personnes au total ont cliqué sur le QR code" ou "combien
            # ont rempli le faux formulaire de gain", pour une lecture campagne de
            # sensibilisation plutôt que par employé individuel.
            self._send_json({**attempts.campaign, "by_vector": get_global_vector_stats()})
            return

        if parsed.path.startswith("/api/history/"):
            target_id = parsed.path.removeprefix("/api/history/")
            if target_id not in TARGETS_BY_ID:
                self._send_json({"error": f"Cible inconnue : {target_id}"}, status=404)
                return
            self._send_json({
                "target_id": target_id,
                "history": get_target_history(target_id),
                "stats": get_target_stats(target_id),
            })
            return

        if parsed.path.startswith("/api/attempt/"):
            token = parsed.path.removeprefix("/api/attempt/")
            entry = attempts.get_attempt(token)
            if entry is None:
                self._send_json({"error": "Tentative inconnue ou expirée"}, status=404)
                return
            self._send_json({"resolved": entry["resolved"], **(entry["result"] or {})})
            return

        if parsed.path.startswith("/track/"):
            token = parsed.path.removeprefix("/track/")
            entry = attempts.get_attempt(token)
            if entry is None:
                self._send_html("<h1>Lien invalide ou expiré</h1>", status=404)
                return
            # Un vrai clic navigateur sur ce lien = l'action "clicked", sauf si la
            # tentative a déjà été résolue autrement avant (voir resolve_attempt : idempotent).
            result = attempts.resolve_attempt(token, "clicked")
            if result["vector"]["key"] == "qrcode":
                self._send_html(render_qr_landing_page(result))
            elif result["vector"]["key"] == "whatsapp":
                self._send_html(render_whatsapp_landing_page(result))
            elif result["vector"]["key"] == "loterie":
                self._send_html(render_loterie_landing_page(result))
            else:
                self._send_html(render_landing_page(result))
            return

        if parsed.path.startswith("/claim/"):
            token = parsed.path.removeprefix("/claim/")
            entry = attempts.get_attempt(token)
            if entry is None:
                self._send_html("<h1>Lien invalide ou expiré</h1>", status=404)
                return
            if entry["resolved"]:
                # Déjà soumis (ou résolu autrement, ex. signalé dans l'interface entre
                # temps) : on réaffiche le résultat déjà figé, jamais le formulaire à nouveau.
                self._send_html(render_loterie_landing_page(entry["result"]))
                return
            # Ouvrir la page ne résout PAS la tentative pour ce vecteur — contrairement
            # à /track/<token>, seule la VRAIE soumission du formulaire (POST ci-dessous)
            # compte comme être tombé dans le piège.
            target = TARGETS_BY_ID[entry["target_id"]]
            self._send_html(render_loterie_form_page(entry, target))
            return

        if parsed.path == "/":
            self.path = "/index.html"

        super().do_GET()

    def do_POST(self):
        parsed = urlparse(self.path)

        if parsed.path == "/api/attack":
            body = self._read_json_body()
            if body is None:
                return
            try:
                result = attempts.start_attempt(
                    body.get("target_id"), body.get("vector"),
                    real_email=body.get("real_email") or None,
                    real_whatsapp=body.get("real_whatsapp") or None,
                )
            except ValueError as e:
                self._send_json({"error": str(e)}, status=400)
                return
            self._send_json(result)
            return

        if parsed.path == "/api/resolve":
            body = self._read_json_body()
            if body is None:
                return
            token = body.get("token")
            action = body.get("action")
            if action not in VALID_MANUAL_ACTIONS:
                self._send_json(
                    {"error": f"action doit être {' ou '.join(VALID_MANUAL_ACTIONS)} ('clicked' ne peut venir que d'un vrai clic sur le lien)"},
                    status=400,
                )
                return
            try:
                result = attempts.resolve_attempt(token, action)
            except KeyError as e:
                self._send_json({"error": str(e)}, status=404)
                return
            self._send_json(result)
            return

        if parsed.path == "/api/campaign/reset":
            attempts.reset_campaign()
            attempts.reset_pending()
            reset_all_risks()  # repart avec les risques de départ, pas ceux accumulés pendant la partie précédente
            reset_history()    # idem pour l'historique par cible/vecteur
            self._send_json(attempts.campaign)
            return

        if parsed.path.startswith("/claim/"):
            token = parsed.path.removeprefix("/claim/")
            entry = attempts.get_attempt(token)
            if entry is None:
                self._send_html("<h1>Lien invalide ou expiré</h1>", status=404)
                return
            # Lit le formulaire HTML classique (application/x-www-form-urlencoded),
            # pas du JSON — c'est un vrai <form method="POST"> qui soumet ici (voir
            # render_loterie_form_page). Le contenu des champs n'est jamais utilisé
            # ni conservé : seul le fait d'avoir soumis compte pour la simulation.
            length = int(self.headers.get("Content-Length", 0) or 0)
            self.rfile.read(length)  # on lit le corps pour vider le socket, mais on l'ignore
            # VRAIE soumission du faux formulaire = tombé dans le piège, que la
            # tentative soit déjà résolue ou non (resolve_attempt est idempotent).
            result = attempts.resolve_attempt(token, "clicked")
            self._send_html(render_loterie_landing_page(result))
            return

        self.send_response(404)
        self.end_headers()

    def _read_json_body(self):
        length = int(self.headers.get("Content-Length", 0) or 0)
        raw = self.rfile.read(length) if length else b"{}"
        try:
            return json.loads(raw or b"{}")
        except json.JSONDecodeError as e:
            self._send_json({"error": "invalid_json", "message": str(e)}, status=400)
            return None

    def _send_json(self, data, status: int = 200) -> None:
        try:
            body = json.dumps(data, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        except (ConnectionAbortedError, ConnectionResetError, BrokenPipeError):
            pass

    def _send_html(self, content: str, status: int = 200) -> None:
        try:
            body = content.encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        except (ConnectionAbortedError, ConnectionResetError, BrokenPipeError):
            pass

    def log_message(self, format, *args):
        pass

    def handle_one_request(self):
        try:
            super().handle_one_request()
        except (ConnectionAbortedError, ConnectionResetError, BrokenPipeError):
            pass


class ThreadingServer(socketserver.ThreadingMixIn, socketserver.TCPServer):
    daemon_threads = True
    allow_reuse_address = True


if __name__ == "__main__":
    try:
        httpd = ThreadingServer(("", PORT), Handler)
    except OSError as e:
        print(f"Impossible d'ouvrir le port {PORT} : {e}")
        print(
            "Ce port est probablement déjà utilisé. Essaie un autre port :\n"
            '    $env:SERIOUSGAME_PORT = "8090"\n'
            "    py server.py"
        )
        sys.exit(1)

    with httpd:
        print(f"Serious game disponible sur : http://localhost:{PORT}")
        print(f"Les liens /track/... générés utiliseront : {attempts.PUBLIC_URL}")
        if "localhost" in attempts.PUBLIC_URL or "127.0.0.1" in attempts.PUBLIC_URL:
            print(
                "  -> Cette URL n'est PAS joignable depuis un autre appareil (téléphone). "
                "Pour un test externe (ngrok, IP Wi-Fi...), définis SERIOUSGAME_PUBLIC_URL "
                "AVANT de lancer 'py server.py', dans le MEME terminal."
            )
        auto_simulate_stop = threading.Event()
        if os.environ.get("SERIOUSGAME_AUTO_SIMULATE") == "1":
            # Même principe que NETSCOPE_AUTO_SCAN / DARKWATCH_AUTO_SCAN : cette
            # boucle ne tourne jamais par défaut, uniquement quand launch_all.py
            # est lancé avec --simulate.
            threading.Thread(
                target=lambda: auto_simulate.run_auto_simulate(stop_event=auto_simulate_stop),
                daemon=True,
            ).start()

        print("Ctrl+C pour arrêter.")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            pass
        finally:
            auto_simulate_stop.set()
