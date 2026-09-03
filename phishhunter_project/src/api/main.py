"""
PhishHunter — API FastAPI
===========================
Lancer en local :
    uvicorn src.api.main:app --reload

Documentation interactive générée automatiquement :
    http://127.0.0.1:8000/docs

Dashboard :
    http://127.0.0.1:8000/dashboard/
"""

import urllib.parse

from fastapi import FastAPI, Request, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import PlainTextResponse, HTMLResponse, RedirectResponse
from pydantic import BaseModel
from typing import Optional
from pathlib import Path
from starlette.middleware.base import BaseHTTPMiddleware

# IMPORTANT : charger le .env AVANT d'importer les modules qui lisent
# les clés API au chargement (explain.py, agent_loop.py) — sinon ces
# modules ne verront jamais les variables et les appels échoueront.
from dotenv import load_dotenv
load_dotenv()

from src.scoring.engine import get_engine
from src.llm.explain import generate_explanation
from src.store import memory_store
from src.agent.agent_loop import run_agent
from src.crisisbot_client import notify_crisisbot
from src import auth

app = FastAPI(
    title="PhishHunter API",
    description="Agent IA de détection de phishing en temps réel",
    version="0.1.0",
)

# Chemins accessibles SANS connexion même quand CYBERAWARE_AUTH_ENABLED=1 :
# /webhook/email est appelé par l'intégration Graph/Gmail ou la passerelle SMTP
# (machine-à-machine, pas un humain avec un cookie de session). Désactivé par
# défaut (voir auth.py) -> aucun changement de comportement tant que
# CYBERAWARE_AUTH_ENABLED=1 n'est pas défini.
_AUTH_EXEMPT_PATHS = {"/webhook/email", "/health", "/login", "/logout"}


class AuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if not auth.AUTH_ENABLED or request.url.path in _AUTH_EXEMPT_PATHS:
            return await call_next(request)
        if auth.verify_session_cookie(request.cookies.get(auth.COOKIE_NAME)) is None:
            return RedirectResponse("/login", status_code=302)
        return await call_next(request)


app.add_middleware(AuthMiddleware)


@app.get("/login")
def login_page():
    return HTMLResponse(auth.render_login_page(brand_accent="4338CA"))


@app.post("/login")
async def login_submit(request: Request):
    raw_body = (await request.body()).decode("utf-8")
    form = urllib.parse.parse_qs(raw_body)
    email = (form.get("email") or [""])[0]
    password = (form.get("password") or [""])[0]
    if auth.check_credentials(email, password):
        auth.record_login(email, source_agent="phishhunter")
        response = RedirectResponse("/dashboard/", status_code=302)
        response.set_cookie(auth.COOKIE_NAME, auth.make_session_cookie(email), httponly=True, samesite="lax")
        return response
    return HTMLResponse(auth.render_login_page(error=True, brand_accent="4338CA"))


@app.get("/logout")
def logout():
    response = RedirectResponse("/login", status_code=302)
    response.delete_cookie(auth.COOKIE_NAME)
    return response


STATIC_DIR = Path(__file__).resolve().parents[2] / "static"
app.mount("/dashboard", StaticFiles(directory=str(STATIC_DIR), html=True), name="dashboard")


class EmailInput(BaseModel):
    sender: str
    subject: Optional[str] = ""
    body: str


class AnalyzeResponse(BaseModel):
    risk_score: int
    classification: str
    sender_domain: Optional[str]
    explanation: str
    triggered_signals: list


@app.on_event("startup")
def load_model_on_startup():
    """Charge le modèle une seule fois, au démarrage du serveur (pas à chaque requête)."""
    get_engine()


@app.get("/health")
def health_check():
    return {"status": "ok"}


def _run_full_analysis(sender: str, subject: str, body: str, source: str) -> dict:
    """Pipeline complet : modèle ML -> score, puis LLM -> explication, puis stockage."""
    engine = get_engine()
    result = engine.analyze(sender=sender, subject=subject, body=body)

    explanation = generate_explanation(
        risk_score=result["risk_score"],
        classification=result["classification"],
        sender_domain=result["sender_domain"],
        triggered_signals=result["triggered_signals"],
    )

    analysis = {
        "risk_score": result["risk_score"],
        "classification": result["classification"],
        "sender_domain": result["sender_domain"],
        "explanation": explanation,
        "triggered_signals": result["triggered_signals"],
    }

    entry = memory_store.add_email(sender=sender, subject=subject, body=body, analysis=analysis, source=source)
    return entry


@app.post("/analyze", response_model=AnalyzeResponse)
def analyze_email(email: EmailInput):
    """
    Point d'entrée principal : reçoit un email, retourne le score de
    dangerosité, la classification, et une explication en langage naturel.
    L'email est aussi enregistré et visible sur le dashboard.
    """
    entry = _run_full_analysis(email.sender, email.subject or "", email.body, source="manual")

    return AnalyzeResponse(
        risk_score=entry["risk_score"],
        classification=entry["classification"],
        sender_domain=entry["sender_domain"],
        explanation=entry["explanation"],
        triggered_signals=entry["triggered_signals"],
    )


@app.post("/webhook/email")
async def receive_email_webhook(request: Request, validationToken: str = None):
    """
    Point d'entrée pour l'intégration webhook (Microsoft Graph / Gmail API).

    Poignée de main de validation Microsoft Graph : dès la création d'un
    abonnement (POST /subscriptions) avec cette URL comme notificationUrl,
    Microsoft envoie IMMÉDIATEMENT une requête ici avec ?validationToken=xxx
    en paramètre d'URL, SANS corps JSON. Il faut renvoyer ce token tel quel
    en texte brut sous 10 secondes, sinon Microsoft rejette l'abonnement.
    Ce bloc doit être géré AVANT toute tentative de lecture du corps JSON
    (sinon `await request.json()` plante sur cet appel-là, qui n'a pas de
    corps). Même principe que le webhook de Sentinel (voir sentinel_project/
    backend/app.py).

    NOTE : ceci reste un squelette pour le reste de l'intégration réelle :
    - le parsing du payload réel envoyé par la plateforme (différent de la
      structure simplifiée ci-dessous — Microsoft Graph envoie une notification
      "légère", juste l'ID du message, il faut un second appel GET pour
      récupérer le vrai contenu avec un token OAuth)
    - le renouvellement périodique de l'abonnement (Microsoft Graph : max ~72h)

    Pour tester ce endpoint sans attendre une vraie boîte Exchange/Gmail,
    voir la commande curl fournie dans le README.
    """
    if validationToken is not None:
        return PlainTextResponse(content=validationToken, status_code=200)

    payload = await request.json()

    sender = payload.get("sender", "")
    subject = payload.get("subject", "")
    body = payload.get("body", "")

    if not sender or not body:
        raise HTTPException(status_code=400, detail="Payload incomplet (sender/body manquant)")

    entry = _run_full_analysis(sender, subject, body, source="webhook")

    if entry["risk_score"] >= 70:
        print(f"[ALERTE] Email dangereux détecté — score {entry['risk_score']}/100 — {sender}")
        severity = "critical" if entry["risk_score"] >= 90 else "high"
        notify_crisisbot(
            source_agent="phishhunter",
            severity=severity,
            description=f"Email de phishing à haut risque détecté — score {entry['risk_score']}/100 — expéditeur {sender}",
        )

    return {"status": "processed", "risk_score": entry["risk_score"], "id": entry["id"]}


@app.get("/emails")
def get_emails():
    """Liste des emails analysés (résumé), pour le dashboard. Plus récents en premier."""
    return memory_store.list_emails()


@app.get("/emails/{email_id}")
def get_email_detail(email_id: int):
    """Détail complet d'un email analysé (explication, signaux, etc.), pour le dashboard."""
    entry = memory_store.get_email(email_id)
    if entry is None:
        raise HTTPException(status_code=404, detail="Email introuvable")
    return entry


@app.post("/emails/{email_id}/block")
def block_email(email_id: int):
    """Action déclenchée par le bouton 'Bloquer l'email et alerter l'employé' du dashboard."""
    entry = memory_store.block_email(email_id)
    if entry is None:
        raise HTTPException(status_code=404, detail="Email introuvable")
    return {"status": "blocked", "id": email_id}


@app.post("/agent/analyze/{email_id}")
def agent_decide(email_id: int):
    """
    Lance l'agent autonome sur un email déjà analysé (score déjà calculé).
    L'agent RAISONNE et CHOISIT lui-même l'action à prendre (bloquer,
    escalader, ou délivrer), en utilisant éventuellement l'outil de
    vérification d'âge de domaine avant de décider.
    """
    entry = memory_store.get_email(email_id)
    if entry is None:
        raise HTTPException(status_code=404, detail="Email introuvable")

    result = run_agent(
        email_id=email_id,
        risk_score=entry["risk_score"],
        classification=entry["classification"],
        sender_domain=entry["sender_domain"],
        triggered_signals=entry["triggered_signals"],
    )

    memory_store.set_agent_trace(email_id, result["trace"])

    return result


@app.post("/seed-demo")
def seed_demo_data():
    """
    Remplit le dashboard avec des exemples réalistes (mêmes emails que la
    maquette initiale du projet), analysés par le vrai pipeline ML + LLM.
    Utile pour une démo ou une soutenance sans dépendre d'une vraie boîte mail.
    """
    memory_store.clear_all()

    demo_emails = [
        {
            "sender": "no-reply@sharepoint-online.com",
            "subject": "Nouveau document partagé avec vous",
            "body": "Un collègue a partagé un document avec vous sur SharePoint. Cliquez pour consulter le fichier.",
        },
        {
            "sender": "facturation@fournisseur-officiel.example",
            "subject": "Facture juillet 2026",
            "body": "Veuillez trouver ci-joint votre facture du mois de juillet 2026. Merci de votre confiance.",
        },
        {
            "sender": "support@banque-partenere-secure.com",
            "subject": "URGENT — Mise à jour de vos identifiants sous 24h",
            "body": "Cliquez ici immédiatement pour confirmer votre mot de passe avant expiration de votre compte.",
        },
        {
            "sender": "rh@banque-abc.example",
            "subject": "Planning congés d'été",
            "body": "Merci de valider votre planning de congés d'été avant vendredi via le portail RH habituel.",
        },
        {
            "sender": "newsletter@linkedin.com",
            "subject": "Votre résumé hebdomadaire",
            "body": "Découvrez les publications les plus populaires de votre réseau cette semaine.",
        },
    ]

    created = [_run_full_analysis(e["sender"], e["subject"], e["body"], source="manual") for e in demo_emails]
    return {"status": "seeded", "count": len(created)}