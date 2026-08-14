"""
API FastAPI pour l'agent NetScope.
Lancer avec : uvicorn netscope_agent.api:app --reload --app-dir src
Puis ouvrir : http://localhost:8000/
"""

import hmac
import os
import threading
from pathlib import Path
from netscope_agent.scorer import NetScopeScorer
from netscope_agent.actions import get_user_for_host, record_isolation
from netscope_agent.auto_scan import run_auto_scan, AUTO_ACT_THRESHOLD, _already_acted
from netscope_agent.live_features import extract_all_features_live
import pandas as pd
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

app = FastAPI(title="NetScope Agent")
scorer = NetScopeScorer()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

STATIC_DIR = Path(__file__).resolve().parents[2] / "static"
MODELS_DIR = Path(__file__).resolve().parents[2] / "models"
DATA_DIR = Path(__file__).resolve().parents[2] / "data"
SAMPLE_PATH = MODELS_DIR / "sample_traffic.csv"

app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

# Doit correspondre à NETSCOPE_WEBHOOK_SECRET côté firewall/proxy/SIEM qui
# appellerait /webhook/traffic-event (même principe que Sentinel/PhishHunter).
WEBHOOK_SECRET = os.environ.get("NETSCOPE_WEBHOOK_SECRET", "change-moi-avant-toute-vraie-utilisation")

_auto_scan_stop = threading.Event()


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
    return FileResponse(STATIC_DIR / "netscope.html")


@app.get("/sample-traffic")
def sample_traffic(n: int = 4):
    """
    Charge l'échantillon réel exporté depuis le notebook (features + vrai label),
    le score avec le modèle entraîné, et associe chaque hôte à un profil de
    risque humain. Sert de flux de trafic pour la page.
    """
    if not SAMPLE_PATH.exists():
        raise HTTPException(
            status_code=404,
            detail=(
                "sample_traffic.csv introuvable dans models/. "
                "Exécute la cellule d'export du notebook (section 15) et "
                "place le fichier dans models/."
            ),
        )

    df = pd.read_csv(SAMPLE_PATH)
    rows = df.sample(n=min(n, len(df))).to_dict(orient="records")

    results = []
    for row in rows:
        features_row = {f: row[f] for f in scorer.features}
        score = scorer.score_domain(features_row)
        domain = row.get("domain", "unknown")
        results.append({
            "domain": domain,
            "true_label": row.get("true_label"),
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

    return {"domain": payload.domain, "features_computed_live": computed_live, **result}


@app.get("/health")
def health():
    return {
        "status": "ok",
        "model_loaded": scorer.model is not None,
        "sample_available": SAMPLE_PATH.exists(),
    }