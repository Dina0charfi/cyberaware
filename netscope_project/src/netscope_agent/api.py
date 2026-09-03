"""
API FastAPI pour l'agent NetScope.
Lancer avec : uvicorn netscope_agent.api:app --reload --app-dir src
Puis ouvrir : http://localhost:8000/
"""

import hmac
import os
import threading
import time
import urllib.parse
from collections import deque
from pathlib import Path
from netscope_agent.scorer import NetScopeScorer
from netscope_agent.actions import get_user_for_host, record_isolation
from netscope_agent.auto_scan import run_auto_scan, AUTO_ACT_THRESHOLD, _already_acted
from netscope_agent.live_features import extract_all_features_live
from netscope_agent.live_feed import pick_live_domains
from netscope_agent import auth
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from starlette.middleware.base import BaseHTTPMiddleware

app = FastAPI(title="NetScope Agent")
scorer = NetScopeScorer()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Chemins accessibles SANS connexion même quand CYBERAWARE_AUTH_ENABLED=1 :
# /webhook/traffic-event est appelé par event_simulator.py ou un vrai
# firewall/proxy (protégé par son propre secret partagé, pas par un cookie de
# session humaine) ; /health sert aux checks de démarrage. Désactivé par
# défaut (auth.AUTH_ENABLED=False) -> aucun changement de comportement tant
# que CYBERAWARE_AUTH_ENABLED=1 n'est pas défini (voir auth.py).
_AUTH_EXEMPT_PATHS = {"/webhook/traffic-event", "/health", "/login", "/logout"}


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
    return HTMLResponse(auth.render_login_page(brand_accent="0F6E56"))


@app.post("/login")
async def login_submit(request: Request):
    raw_body = (await request.body()).decode("utf-8")
    form = urllib.parse.parse_qs(raw_body)
    email = (form.get("email") or [""])[0]
    password = (form.get("password") or [""])[0]
    if auth.check_credentials(email, password):
        auth.record_login(email, source_agent="netscope")
        response = RedirectResponse("/", status_code=302)
        response.set_cookie(auth.COOKIE_NAME, auth.make_session_cookie(email), httponly=True, samesite="lax")
        return response
    return HTMLResponse(auth.render_login_page(error=True, brand_accent="0F6E56"))


@app.get("/logout")
def logout():
    response = RedirectResponse("/login", status_code=302)
    response.delete_cookie(auth.COOKIE_NAME)
    return response

STATIC_DIR = Path(__file__).resolve().parents[2] / "static"
MODELS_DIR = Path(__file__).resolve().parents[2] / "models"
DATA_DIR = Path(__file__).resolve().parents[2] / "data"
SAMPLE_PATH = MODELS_DIR / "sample_traffic.csv"

app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

# Doit correspondre à NETSCOPE_WEBHOOK_SECRET côté firewall/proxy/SIEM qui
# appellerait /webhook/traffic-event (même principe que Sentinel/PhishHunter).
WEBHOOK_SECRET = os.environ.get("NETSCOPE_WEBHOOK_SECRET", "change-moi-avant-toute-vraie-utilisation")

_auto_scan_stop = threading.Event()

# Historique en mémoire des derniers événements reçus via /webhook/traffic-event
# (donc via tail_bridge.py + dns_proxy.py pendant la démo téléphone, ou via
# event_simulator.py en mode --simulate) — /sample-traffic (clic manuel) ne
# passe PAS par ce point d'entrée et n'y apparaît donc pas. deque(maxlen=30) :
# les plus anciens sont automatiquement éjectés, pas besoin de le vider à la
# main. Le dashboard sonde /live-feed toutes les quelques secondes pour
# afficher ces événements au fur et à mesure, sans que le navigateur ait
# besoin d'ouvrir une connexion permanente (websocket) — un simple polling
# suffit pour une démo.
LIVE_FEED_EVENTS: deque = deque(maxlen=30)


@app.on_event("startup")
def start_auto_scan():
    # Boucle autonome (perception -> score -> décision -> action), comme
    # l'agent DarkWatch : tourne seule pendant que l'API est démarrée.
    # Désactivée par défaut pour rester cohérente avec PhishHunter/Sentinel
    # (silencieux tant qu'on n'active pas explicitement le mode démo/live) —
    # activer avec NETSCOPE_AUTO_SCAN=1 (mis automatiquement par
    # `launch_all.py --simulate`).
    if os.environ.get("NETSCOPE_AUTO_SCAN") == "1":
        threading.Thread(target=lambda: run_auto_scan(scorer, stop_event=_auto_scan_stop), daemon=True).start()


@app.on_event("shutdown")
def stop_auto_scan():
    _auto_scan_stop.set()


@app.get("/")
def serve_page():
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/sample-traffic")
def sample_traffic(n: int = 4):
    """
    Tire n VRAIS noms de domaine (live_feed.py : mélange de domaines légitimes
    connus et de domaines générés façon DGA), effectue une VRAIE résolution
    DNS pour chacun (live_features.py, dnspython — requête réseau réelle, pas
    de valeurs pré-calculées), score le résultat avec le modèle entraîné, et
    associe chaque domaine à un profil de risque humain. Sert de flux de
    trafic "live" pour la page — remplace l'ancien flux basé sur
    models/sample_traffic.csv (features déjà calculées, noms factices
    "host-xxxxx.sample").
    """
    domains = pick_live_domains(n)

    results = []
    for domain in domains:
        features_row = extract_all_features_live(domain)
        try:
            score = scorer.score_domain(features_row)
        except ValueError:
            # Ne devrait pas arriver (extract_all_features_live couvre déjà
            # toutes les features attendues par le modèle) — on ignore juste
            # ce domaine plutôt que de faire échouer tout le tirage.
            continue
        results.append({
            "domain": domain,
            "user": get_user_for_host(domain),
            **score,
        })

    results.sort(key=lambda r: r["ml_score"], reverse=True)
    return {"results": results}


class DomainRequest(BaseModel):
    domain: str
    features: dict[str, float]


class IsolateRequest(BaseModel):
    domain: str
    user: str
    ml_score: float


class TrafficWebhookEvent(BaseModel):
    domain: str
    # Optionnel exprès : un vrai firewall/proxy générique ne connaît que le
    # domaine, pas les 16 statistiques déjà calculées. Si `features` est
    # absent, on les calcule nous-mêmes (voir live_features.py) — si un
    # système fournit déjà des features précalculées (comme le simulateur),
    # on les utilise directement sans rien recalculer.
    features: dict[str, float] | None = None


@app.post("/analyze")
def analyze(payload: DomainRequest):
    try:
        result = scorer.score_domain(payload.features)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return {
        "domain": payload.domain,
        **result,
    }


@app.post("/isolate")
def isolate(payload: IsolateRequest):
    """
    Enregistre une action d'isolement (déclenchée par le bouton de la page,
    donc par un analyste humain). En production, ce serait ici qu'on
    appellerait l'API du firewall/EDR pour couper le réseau du poste.
    Même fonction partagée que la boucle autonome (auto_scan.py), pour que
    l'incident et la notification CrisisBot ne soient journalisés qu'à un
    seul endroit.
    """
    return record_isolation(
        domain=payload.domain, user=payload.user, ml_score=payload.ml_score, source="manual",
    )


@app.post("/webhook/traffic-event")
def webhook_traffic_event(payload: TrafficWebhookEvent, x_webhook_secret: str = ""):
    """
    Point d'entrée pour un envoi automatique en temps réel depuis un
    firewall/proxy (Fortinet, PaloAlto...) ou un SIEM qui relaie ses logs DNS.

    Différence avec auto_scan.py : auto_scan va lui-même chercher (pull) un
    échantillon local toutes les 25s ; ceci reçoit (push) un événement envoyé
    depuis l'extérieur, exactement comme le ferait un vrai firewall configuré
    pour transmettre ses logs. C'est ce point d'entrée qu'on brancherait
    réellement le jour de l'intégration — le reste (score → décision →
    action) ne change pas.

    `x_webhook_secret` est un paramètre de requête (?x_webhook_secret=...),
    pas un en-tête HTTP — même convention que Sentinel.

    `features` est optionnel : un vrai firewall générique ne fournit que le
    domaine, pas les 16 statistiques déjà calculées — dans ce cas, elles sont
    calculées en direct (nom du domaine + une vraie résolution DNS) par
    `extract_all_features_live()`. Si l'appelant fournit déjà des features
    (comme le simulateur, qui rejoue un échantillon connu), elles sont
    utilisées telles quelles sans rien recalculer.
    """
    if not hmac.compare_digest(x_webhook_secret, WEBHOOK_SECRET):
        raise HTTPException(status_code=401, detail="Secret webhook invalide")

    features = payload.features
    computed_live = False
    if features is None:
        features = extract_all_features_live(payload.domain)
        computed_live = True

    try:
        result = scorer.score_domain(features)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    if result["ml_score"] >= AUTO_ACT_THRESHOLD and payload.domain not in _already_acted:
        user = get_user_for_host(payload.domain)
        record_isolation(
            domain=payload.domain,
            user=user.get("name", "inconnu"),
            ml_score=result["ml_score"],
            source="webhook",
        )
        _already_acted.add(payload.domain)

    # Ajouté EN PREMIER (appendleft) pour que /live-feed renvoie toujours les
    # événements les plus récents en tête, prêts à être affichés tels quels.
    # "user" (profil de risque humain) est inclus ici — pas seulement au
    # moment de l'isolement — pour que le dashboard puisse afficher le même
    # panneau de détail (score, facteurs, corrélation humaine) qu'un clic sur
    # /sample-traffic, y compris pour un événement en dessous du seuil d'action.
    LIVE_FEED_EVENTS.appendleft({
        "domain": payload.domain,
        "at": time.strftime("%H:%M:%S"),
        "user": get_user_for_host(payload.domain),
        **result,
    })

    return {"domain": payload.domain, "features_computed_live": computed_live, **result}


@app.get("/live-feed")
def live_feed():
    """
    Les derniers événements reçus en direct via /webhook/traffic-event (donc,
    pendant la démo, chaque domaine réellement visité sur le téléphone et
    relayé par dns_proxy.py + tail_bridge.py). Le dashboard sonde cet
    endpoint toutes les quelques secondes pour afficher le trafic au fur et
    à mesure, sans recharger la page.
    """
    return {"events": list(LIVE_FEED_EVENTS)}


@app.get("/health")
def health():
    return {
        "status": "ok",
        "model_loaded": scorer.model is not None,
        "sample_available": SAMPLE_PATH.exists(),
    }