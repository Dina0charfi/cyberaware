"""
Sentinel — API backend (v3, modèle CERT réduit à 7 features essentielles)
----------------------------------------------------------------------------
Utilise le modèle entraîné dans sentinel_cert_essentiel_FINAL.ipynb — 7 features
universelles (heure, week-end, jour férié, hors-horaires, département sensible,
nouveau poste/appareil), sans USB/fichier leurre/email — pensé pour être réutilisable
directement sur de vrais logs Entra ID/Google, sans réentraînement.

Lancement :
    pip install -r requirements.txt
    uvicorn app:app --reload --port 8000
"""

import hmac
import json
import os
import threading
import time
import urllib.parse
from collections import namedtuple
from pathlib import Path

# IMPORTANT : charger le .env AVANT d'importer llm_explanation — ce module lit
# HF_TOKEN au moment de son import (os.environ.get au niveau module), donc si
# le .env est chargé après, la clé ne sera jamais vue et le LLM restera désactivé.
from dotenv import load_dotenv
load_dotenv(override=True)

import joblib
from sklearn.ensemble import IsolationForest
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse, HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from starlette.middleware.base import BaseHTTPMiddleware

from decision_engine import decide_action, generate_description, is_sensitive_department, ACTION_LABELS
from feature_engineering import build_feature_vector
from llm_explanation import generate_llm_explanation
from crisisbot_client import notify_crisisbot
import auth

app = FastAPI(title="Sentinel API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Chemins accessibles SANS connexion même quand CYBERAWARE_AUTH_ENABLED=1 :
# /api/webhook/signin-event est appelé par un vrai SIEM/Microsoft Graph
# (protégé par son propre secret partagé + poignée de main de validation, pas
# par un cookie de session humaine). Désactivé par défaut (voir auth.py) ->
# aucun changement de comportement tant que CYBERAWARE_AUTH_ENABLED=1 n'est
# pas défini.
_AUTH_EXEMPT_PATHS = {"/api/webhook/signin-event", "/login", "/logout"}


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
    return HTMLResponse(auth.render_login_page(brand_accent="2563EB"))


@app.post("/login")
async def login_submit(request: Request):
    raw_body = (await request.body()).decode("utf-8")
    form = urllib.parse.parse_qs(raw_body)
    email = (form.get("email") or [""])[0]
    password = (form.get("password") or [""])[0]
    if auth.check_credentials(email, password):
        auth.record_login(email, source_agent="sentinel")
        response = RedirectResponse("/", status_code=302)
        response.set_cookie(auth.COOKIE_NAME, auth.make_session_cookie(email), httponly=True, samesite="lax")
        return response
    return HTMLResponse(auth.render_login_page(error=True, brand_accent="2563EB"))


@app.get("/logout")
def logout():
    response = RedirectResponse("/login", status_code=302)
    response.delete_cookie(auth.COOKIE_NAME)
    return response

BASE_DIR = Path(__file__).parent
DATA_PATH = BASE_DIR / "data" / "cases.json"
MODEL_PATH = BASE_DIR / "model" / "isolation_forest_sentinel.joblib"
BOUNDS_PATH = BASE_DIR / "model" / "model_score_bounds.json"

CASES = json.loads(DATA_PATH.read_text(encoding="utf-8"))
CASES_BY_ID = {c["id"]: c for c in CASES}

# ModelState regroupe le modèle ET ses bornes dans UN SEUL objet immuable. Sous
# forte charge, chaque requête lit juste "_state" (une simple lecture de
# référence Python, garantie atomique par le GIL — jamais de verrou nécessaire)
# au lieu de lire MODEL puis BOUNDS séparément, ce qui éliminerait tout risque
# de lire un modèle tout neuf combiné à d'anciennes bornes. Voir retrain_model()
# plus bas : le réentraînement remplace TOUTE la référence _state d'un coup,
# jamais ses champs un par un.
ModelState = namedtuple("ModelState", ["model", "bounds"])
_state = ModelState(
    joblib.load(MODEL_PATH),
    json.loads(BOUNDS_PATH.read_text(encoding="utf-8")),
)
print(f"Modèle chargé : {MODEL_PATH.name} | bornes : {_state.bounds}")

# Calendrier tunisien (jours fériés, y compris les fêtes religieuses à date mobile) —
# utilisé pour calculer is_holiday automatiquement, sans jamais le demander à l'utilisateur.
try:
    import holidays
    TN_HOLIDAYS = holidays.Tunisia(years=[2024, 2025, 2026, 2027])
    print(f"[Sentinel] Calendrier tunisien chargé : {len(TN_HOLIDAYS)} jours fériés (2024-2027).")
except ImportError:
    TN_HOLIDAYS = None
    print("[Sentinel] ⚠️ Bibliothèque 'holidays' absente — is_holiday sera toujours calculé à False. "
          "Lance : pip install holidays")

# Mémoire partagée des postes/appareils connus par utilisateur — utilisée à la fois par
# /api/analyze-live (formulaire de test) et /api/webhook/signin-event (vrais événements),
# pour que "nouveau poste" soit calculé automatiquement, jamais coché à la main.
known_devices_by_user = {}


def compute_risk_score(raw_score: float, bounds: dict) -> int:
    normalized = (raw_score - bounds["min"]) / (bounds["max"] - bounds["min"])
    normalized = max(0.0, min(1.0, normalized))
    return max(0, min(100, int(round((1 - normalized) * 100))))


# --------------------------------------------------------------------------
# RÉENTRAÎNEMENT — Isolation Forest est non supervisé (aucune étiquette requise),
# donc réentraînable directement sur les cas déjà connus (data/cases.json), sans
# attendre un vrai jugement humain "c'était une vraie anomalie ou pas".
#
# Conçu pour NE JAMAIS BLOQUER sous forte charge (beaucoup de requêtes/utilisateurs
# en même temps) :
#   - LECTURE (score_vector, appelée par toutes les requêtes de scoring) : AUCUN
#     verrou. Elle lit juste la référence "_state" une fois — une simple lecture
#     de variable, atomique grâce au GIL de Python. Des centaines de requêtes
#     simultanées peuvent donc scorer en parallèle sans jamais s'attendre entre
#     elles, même pendant qu'un réentraînement tourne en fond.
#   - ÉCRITURE (retrain_model) : le .fit() (la partie lente, potentiellement
#     plusieurs secondes) se fait entièrement AVANT de toucher _state. Une fois
#     le nouveau modèle prêt, on ne fait qu'UNE seule réassignation atomique
#     ("_state = ModelState(...)") — les requêtes en cours de lecture voient soit
#     l'ancien état complet, soit le nouveau complet, jamais un mélange.
#   - CONCURRENCE ENTRE RÉENTRAÎNEMENTS : _retrain_gate (un Lock, pas juste un
#     Event) garantit qu'un seul réentraînement tourne à la fois, via
#     acquire(blocking=False) — un test-et-verrouille atomique en une seule
#     opération, donc aucune race condition possible même si 50 requêtes
#     déclenchent un réentraînement au même instant.
#   - UN SEUL thread de fond fait tout le travail (_retrain_worker_loop, démarré
#     une fois au démarrage du serveur), plutôt qu'un thread créé par requête
#     comme dans une première version : sous forte charge (beaucoup de cas créés
#     d'un coup), create_case() ne fait plus que _retrain_requested.set() — une
#     opération quasi instantanée qui NE crée jamais de nouveau thread — et
#     laisse ce thread unique regrouper tous les cas arrivés entre deux passages
#     en un seul réentraînement, au lieu d'empiler des dizaines de .fit() en
#     parallèle qui saturerait le CPU.
# --------------------------------------------------------------------------

_retrain_gate = threading.Lock()          # garantit un SEUL réentraînement à la fois
_retrain_requested = threading.Event()    # signal "au moins un nouveau cas est arrivé"
RETRAIN_MIN_CASES = 15  # pas de réentraînement en dessous de ce seuil — trop peu de cas rendrait le modèle instable/surajusté
LAST_RETRAIN = {"at": None, "cases_used": None}


def score_vector(vector: list) -> tuple[float, int]:
    """
    Calcule (raw_score, risk_score). Lecture SANS verrou — voir le commentaire
    au-dessus de _retrain_gate pour pourquoi c'est sûr : "_state" est toujours
    lu comme un tout cohérent (modèle + bornes), jamais un mélange ancien/neuf.
    """
    state = _state  # une seule lecture de référence, atomique (GIL)
    raw_score = float(state.model.decision_function([vector])[0])
    risk_score = compute_risk_score(raw_score, state.bounds)
    return raw_score, risk_score


def retrain_model(min_cases: int = RETRAIN_MIN_CASES) -> dict:
    """
    Réentraîne l'Isolation Forest sur TOUS les cas actuellement connus. Le calcul
    lourd (.fit) se fait AVANT tout remplacement de _state — les requêtes de
    scoring continuent d'utiliser l'ancien modèle, sans interruption, pendant
    tout le temps que dure le réentraînement. L'ancien modèle est sauvegardé sous
    un nom horodaté avant d'être remplacé, pour pouvoir revenir en arrière si le
    nouveau modèle se comporte mal.
    """
    global _state

    if not _retrain_gate.acquire(blocking=False):
        # Un réentraînement tourne déjà (ex. déclenché par un autre thread juste
        # avant) : on ne fait rien plutôt que de lancer un .fit() en double.
        return {"status": "skipped", "reason": "Un réentraînement est déjà en cours"}

    try:
        if len(CASES) < min_cases:
            return {
                "status": "skipped",
                "reason": f"Pas assez de cas ({len(CASES)}/{min_cases}) pour réentraîner sans risquer un surapprentissage",
            }

        vectors = [
            build_feature_vector(c["features"], is_sensitive_department(c["department"]))
            for c in CASES
        ]

        new_model = IsolationForest(n_estimators=200, contamination="auto", random_state=42)
        new_model.fit(vectors)  # partie lente — les autres threads continuent de scorer avec l'ancien _state pendant ce temps

        raw_scores = new_model.decision_function(vectors)
        new_bounds = {"min": float(raw_scores.min()), "max": float(raw_scores.max())}

        model_dir = MODEL_PATH.parent
        model_dir.mkdir(parents=True, exist_ok=True)
        backup_path = model_dir / f"isolation_forest_sentinel_{time.strftime('%Y%m%d-%H%M%S')}.joblib"
        joblib.dump(_state.model, backup_path)  # garde l'ancien modèle avant de l'écraser

        joblib.dump(new_model, MODEL_PATH)
        BOUNDS_PATH.write_text(json.dumps(new_bounds), encoding="utf-8")

        _state = ModelState(new_model, new_bounds)  # réassignation atomique unique — sans verrou, sans bloquer les lectures

        LAST_RETRAIN["at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
        LAST_RETRAIN["cases_used"] = len(vectors)

        print(f"[Sentinel][retrain] Modèle réentraîné sur {len(vectors)} cas — ancien modèle sauvegardé sous {backup_path.name}")
        return {"status": "retrained", "cases_used": len(vectors), "new_bounds": new_bounds, "backup": backup_path.name}
    finally:
        _retrain_gate.release()


def _retrain_worker_loop() -> None:
    """
    Unique thread de fond qui fait TOUT le réentraînement, démarré une seule fois
    au démarrage du serveur (voir start_retrain_worker). Attend le signal
    _retrain_requested, le réinitialise immédiatement, puis réentraîne une fois.
    Si 50 utilisateurs créent un cas en même temps, ils appellent tous juste
    _retrain_requested.set() (opération quasi instantanée, aucun thread créé) —
    ce thread unique regroupe tout ça en un seul passage dès qu'il est libre,
    au lieu de lancer 50 réentraînements en parallèle qui saturerait le CPU.
    """
    while True:
        _retrain_requested.wait()
        _retrain_requested.clear()
        try:
            retrain_model()
        except Exception as e:
            print(f"[Sentinel][retrain] Erreur pendant le réentraînement (ignorée) : {e}")


@app.on_event("startup")
def start_retrain_worker():
    threading.Thread(target=_retrain_worker_loop, daemon=True).start()


class AnalyzeRequest(BaseModel):
    case_id: str


class LiveAnalyzeRequest(BaseModel):
    user: str
    pc: str
    department: str
    date: str    # format YYYY-MM-DD, ex: "2026-07-27"
    hour: int    # 0-23 — c'est tout ce qu'une vraie connexion fournirait


class NewCaseRequest(BaseModel):
    user: str
    pc: str
    department: str
    date: str
    heure: str
    hour: int
    scenario: str = ""
    is_off_hours: bool = False
    is_new_device: bool = False
    is_weekend: bool = False
    is_holiday: bool = False


@app.post("/api/retrain")
def manual_retrain():
    """Déclenche un réentraînement immédiat (synchrone) — pratique pour une démo
    ou une soutenance : renvoie directement le résultat au lieu de tourner en
    arrière-plan comme le déclenchement automatique de create_case()."""
    return retrain_model()


@app.get("/api/model-info")
def model_info():
    """État actuel du modèle — nombre de cas connus, dernières bornes, dernier
    réentraînement le cas échéant. Utile pour montrer que le modèle a vraiment
    changé après un réentraînement (comparer new_bounds avant/après)."""
    return {
        "cases_total": len(CASES),
        "retrain_min_cases": RETRAIN_MIN_CASES,
        "current_bounds": dict(_state.bounds),
        "last_retrain": LAST_RETRAIN,
    }


@app.get("/api/cases")
def list_cases():
    return [
        {
            "id": c["id"], "user": c["user"], "pc": c["pc"],
            "department": c["department"], "date": c["date"], "heure": c["heure"],
        }
        for c in CASES
    ]


@app.post("/api/analyze")
def analyze(req: AnalyzeRequest):
    case = CASES_BY_ID.get(req.case_id)
    if not case:
        raise HTTPException(status_code=404, detail="Cas introuvable")

    started = time.time()
    sensitive = is_sensitive_department(case["department"])

    vector = build_feature_vector(case["features"], sensitive)
    raw_score, risk_score = score_vector(vector)

    action = decide_action(risk_score, sensitive)
    description = generate_description(case["features"], sensitive)
    llm_explanation = generate_llm_explanation(
        case["user"], case["department"], risk_score, ACTION_LABELS[action], case["features"]
    )

    steps = [
        {"label": "Perception", "detail": f"{case['user']} — poste {case['pc']} — {case['date']} {case['heure']}"},
        {"label": "Raisonnement ML", "detail": f"Isolation Forest (score brut {raw_score:.4f}) → risk score {risk_score}/100"},
        {"label": "Décision", "detail": f"Département {case['department']} ({'sensible' if sensitive else 'standard'}) → {ACTION_LABELS[action]}"},
        {"label": "Explication", "detail": llm_explanation or description},
    ]

    if action == "escalate_to_human":
        notify_crisisbot(
            source_agent="sentinel",
            severity="high",
            description=f"Connexion anormale escaladée — {case['user']} (poste {case['pc']}, {case['department']}, score {risk_score}/100)",
        )

    return {
        "case_id": case["id"], "user": case["user"], "pc": case["pc"], "department": case["department"],
        "risk_score": risk_score, "raw_score": round(float(raw_score), 4),
        "action": action, "action_label": ACTION_LABELS[action],
        "description": description, "llm_explanation": llm_explanation,
        "steps": steps, "processing_time_ms": round((time.time() - started) * 1000, 2),
    }


@app.post("/api/analyze-live")
def analyze_live(req: LiveAnalyzeRequest):
    """
    Simule une vraie connexion : on ne reçoit que ce qu'un vrai système fournirait
    (date, heure, poste, utilisateur, département) — TOUT le reste (hors-horaires,
    week-end, jour férié, nouveau poste) est calculé automatiquement, exactement
    comme le ferait le webhook /api/webhook/signin-event sur un vrai événement.
    """
    started = time.time()

    from datetime import datetime as dt
    ts = dt.fromisoformat(req.date)
    hour = req.hour

    known = known_devices_by_user.setdefault(req.user, set())
    is_new_device = req.pc not in known
    known.add(req.pc)

    is_holiday = ts.date() in TN_HOLIDAYS if TN_HOLIDAYS is not None else False

    features = {
        "hour": hour,
        "is_off_hours": int(hour < 8 or hour >= 17),
        "is_new_device": int(is_new_device),
        "is_weekend": int(ts.weekday() >= 5),
        "is_holiday": int(is_holiday),
    }

    sensitive = is_sensitive_department(req.department)
    vector = build_feature_vector(features, sensitive)
    raw_score, risk_score = score_vector(vector)
    action = decide_action(risk_score, sensitive)
    description = generate_description(features, sensitive)
    llm_explanation = generate_llm_explanation(
        req.user, req.department, risk_score, ACTION_LABELS[action], features
    )

    if action == "escalate_to_human":
        notify_crisisbot(
            source_agent="sentinel",
            severity="high",
            description=f"Connexion anormale escaladée — {req.user} (poste {req.pc}, {req.department}, score {risk_score}/100)",
        )

    return {
        "user": req.user, "pc": req.pc, "department": req.department,
        "computed_features": features,  # utile pour voir CE QUI a été déduit automatiquement
        "risk_score": risk_score, "raw_score": round(float(raw_score), 4),
        "action": action, "action_label": ACTION_LABELS[action],
        "description": description, "llm_explanation": llm_explanation,
        "processing_time_ms": round((time.time() - started) * 1000, 2),
    }


@app.post("/api/cases")
def create_case(req: NewCaseRequest):
    slug = "".join(c.lower() if c.isalnum() else "-" for c in req.user).strip("-")
    new_id = f"{slug}-{req.date}-{len(CASES) + 1}"

    new_case = {
        "id": new_id, "user": req.user, "pc": req.pc, "department": req.department,
        "date": req.date, "heure": req.heure, "scenario": req.scenario,
        "features": {
            "hour": req.hour, "is_off_hours": int(req.is_off_hours),
            "is_new_device": int(req.is_new_device), "is_weekend": int(req.is_weekend),
            "is_holiday": int(req.is_holiday),
        },
    }

    CASES.append(new_case)
    CASES_BY_ID[new_id] = new_case
    DATA_PATH.write_text(json.dumps(CASES, ensure_ascii=False, indent=2), encoding="utf-8")

    sensitive = is_sensitive_department(req.department)
    vector = build_feature_vector(new_case["features"], sensitive)
    raw_score, risk_score = score_vector(vector)
    action = decide_action(risk_score, sensitive)
    description = generate_description(new_case["features"], sensitive)
    llm_explanation = generate_llm_explanation(
        req.user, req.department, risk_score, ACTION_LABELS[action], new_case["features"]
    )

    # Réentraînement "à chaque fois" qu'un nouveau cas arrive — signal quasi
    # instantané (pas de nouveau thread créé ici), le worker unique démarré au
    # lancement du serveur s'en charge (voir _retrain_worker_loop). Reste
    # non-bloquant même si des centaines de cas arrivent d'un coup.
    _retrain_requested.set()

    return {
        "id": new_id, "status": "created",
        "conclusion": {
            "risk_score": risk_score, "raw_score": round(float(raw_score), 4),
            "action": action, "action_label": ACTION_LABELS[action],
            "description": description, "llm_explanation": llm_explanation,
        },
    }


# --------------------------------------------------------------------------
# WEBHOOK — reçoit un événement de connexion EN TEMPS RÉEL, poussé par le SIEM
# ou directement par Microsoft Graph (change notifications), au lieu d'un
# fichier téléchargé à la main. C'est la partie qu'on contrôle côté Sentinel —
# pour qu'un vrai système externe puisse l'appeler, ce backend doit être
# accessible publiquement (déploiement Azure/Render, ou tunnel ngrok en test).
# --------------------------------------------------------------------------

SENTINEL_WEBHOOK_SECRET_DEFAULT = "change-moi-avant-toute-vraie-utilisation"
# Doit correspondre à SENTINEL_WEBHOOK_SECRET dans event_simulator.py. Était en dur
# jusqu'ici (donc réglable nulle part) — maintenant surchageable comme NetScope.
WEBHOOK_SECRET = os.environ.get("SENTINEL_WEBHOOK_SECRET", SENTINEL_WEBHOOK_SECRET_DEFAULT)


class WebhookSignInEvent(BaseModel):
    userPrincipalName: str
    createdDateTime: str          # format ISO, ex: "2026-07-27T03:12:00Z"
    deviceId: str = "poste_inconnu"
    department: str = ""


@app.post("/api/webhook/signin-event")
async def webhook_signin_event(request: Request, validationToken: str = None, x_webhook_secret: str = ""):
    """
    Point d'entrée pour un envoi automatique en temps réel (SIEM, Microsoft Graph
    change notifications, Logic App...). Traite l'événement immédiatement et
    retourne la décision — pas besoin d'attendre un script manuel.

    IMPORTANT — poignée de main de validation Microsoft Graph :
    quand tu crées un abonnement (POST /subscriptions) avec cette URL comme
    notificationUrl, Microsoft envoie IMMÉDIATEMENT une requête à cette même URL
    avec ?validationToken=xxx en paramètre, SANS le vrai corps d'événement.
    Il faut répondre par ce token en texte brut sous 10 secondes, sinon Microsoft
    rejette l'abonnement. Ce bloc gère ce cas avant d'essayer de lire un vrai
    événement.
    """
    if validationToken is not None:
        return PlainTextResponse(content=validationToken, status_code=200)

    if not hmac.compare_digest(x_webhook_secret, WEBHOOK_SECRET):
        raise HTTPException(status_code=401, detail="Secret webhook invalide")

    body = await request.json()
    event = WebhookSignInEvent(**body)

    from datetime import datetime as dt
    ts = dt.fromisoformat(event.createdDateTime.replace("Z", "+00:00"))
    hour = ts.hour

    known = known_devices_by_user.setdefault(event.userPrincipalName, set())
    is_new_device = event.deviceId not in known
    known.add(event.deviceId)

    sensitive = is_sensitive_department(event.department) if event.department else False

    features = {
        "hour": hour,
        "is_off_hours": int(hour < 8 or hour >= 17),
        "is_new_device": int(is_new_device),
        "is_weekend": int(ts.weekday() >= 5),
        "is_holiday": int(ts.date() in TN_HOLIDAYS) if TN_HOLIDAYS is not None else 0,
    }

    vector = build_feature_vector(features, sensitive)
    raw_score, risk_score = score_vector(vector)
    action = decide_action(risk_score, sensitive)
    description = generate_description(features, sensitive)
    llm_explanation = generate_llm_explanation(
        event.userPrincipalName, event.department or "non specifie", risk_score, ACTION_LABELS[action], features
    )

    # Événement temps réel (webhook SIEM/Graph) : c'est ici que CrisisBot a le
    # plus de valeur, puisqu'il n'y a justement personne devant un dashboard.
    if action == "escalate_to_human":
        notify_crisisbot(
            source_agent="sentinel",
            severity="high",
            description=f"Connexion anormale (webhook temps réel) — {event.userPrincipalName}, score {risk_score}/100",
        )

    return {
        "received_at": dt.now().isoformat(),
        "user": event.userPrincipalName,
        "risk_score": risk_score,
        "action": action,
        "action_label": ACTION_LABELS[action],
        "description": description,
        "llm_explanation": llm_explanation,
    }


# --------------------------------------------------------------------------
# Sert le frontend (index.html, add-user.html) sur ce MÊME port — plus besoin
# de lancer un serveur séparé (python -m http.server). Doit rester en tout
# dernier dans ce fichier : les routes API déclarées au-dessus (/api/...)
# sont prioritaires, ce montage ne récupère que ce qu'aucune route API
# n'a déjà pris en charge.
# --------------------------------------------------------------------------
FRONTEND_DIR = Path(__file__).parent.parent / "frontend"

print(f"\n[Sentinel] Recherche du frontend dans : {FRONTEND_DIR.resolve()}")
print(f"[Sentinel] Ce dossier existe : {FRONTEND_DIR.exists()}")

if FRONTEND_DIR.exists():
    contents = [f.name for f in FRONTEND_DIR.iterdir()]
    print(f"[Sentinel] Fichiers trouvés : {contents}")
    if "index.html" not in contents:
        print("[Sentinel] ⚠️ Le dossier existe mais NE CONTIENT PAS 'index.html' — c'est pour ça que '/' renvoie 404.")
    else:
        print("[Sentinel] ✅ index.html trouvé, le frontend devrait se charger normalement.\n")
    app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")
else:
    print("[Sentinel] ⚠️ DOSSIER INTROUVABLE — le frontend ne sera PAS servi (pas de crash, mais '/' restera 404).")
    print("[Sentinel]    Vérifie que 'frontend' est un dossier FRÈRE de 'backend' (même niveau), pas dedans.")
    print("[Sentinel]    L'API (/api/...) continue de fonctionner normalement.\n")