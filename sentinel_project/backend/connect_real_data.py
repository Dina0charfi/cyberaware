"""
Connecte un VRAI fichier de sign-in logs (téléchargé depuis ton tenant Entra ID gratuit)
au modèle entraîné sur CERT, pour obtenir de vrais résultats — pas des exemples fabriqués.

Utilisation :
    1. Télécharge tes vrais sign-in logs depuis Entra admin center (JSON)
    2. python3 connect_real_data.py chemin/vers/tes_vrais_logs.json

Sortie :
    rapport_donnees_reelles.csv — un score de risque et une décision pour chaque
    connexion réelle de ton tenant de test
"""

import sys
import json
import math
from datetime import datetime
from pathlib import Path

import joblib
import pandas as pd

from decision_engine import decide_action, generate_description, is_sensitive_department, ACTION_LABELS
from feature_engineering import build_feature_vector

BASE_DIR = Path(__file__).parent
MODEL_PATH = BASE_DIR / "model" / "isolation_forest_sentinel.joblib"
BOUNDS_PATH = BASE_DIR / "model" / "model_score_bounds.json"


def compute_risk_score(raw_score, bounds):
    normalized = (raw_score - bounds["min"]) / (bounds["max"] - bounds["min"])
    normalized = max(0.0, min(1.0, normalized))
    return max(0, min(100, int(round((1 - normalized) * 100))))


def load_real_entra_export(filepath: str) -> list:
    """Charge le JSON téléchargé depuis Entra admin center. Le format exact peut varier
    légèrement selon la version du portail — ce chargeur gère les deux structures les
    plus courantes (liste directe, ou objet avec une clé 'value')."""
    data = json.loads(Path(filepath).read_text(encoding="utf-8"))
    if isinstance(data, dict) and "value" in data:
        return data["value"]
    if isinstance(data, list):
        return data
    raise ValueError("Format inattendu : ni une liste, ni un objet avec 'value'. "
                      "Ouvre le fichier et vérifie sa structure à la main.")


def normalize_event(raw: dict) -> dict:
    """Adapte-le si les noms de champs de TON export réel diffèrent — ils peuvent varier
    légèrement selon la version du portail Entra. Regarde d'abord la sortie de
    'python3 -c "import json; print(json.dumps(json.load(open(TON_FICHIER))[0], indent=2))"'
    pour voir les vrais noms de champs avant d'ajuster ici si besoin."""
    created = raw.get("createdDateTime") or raw.get("CreatedDateTime")
    timestamp = datetime.fromisoformat(created.replace("Z", "+00:00"))

    device = raw.get("deviceDetail", {}) or raw.get("DeviceDetail", {}) or {}
    status = raw.get("status", {}) or raw.get("Status", {}) or {}

    return {
        "user": raw.get("userPrincipalName") or raw.get("UserPrincipalName", "utilisateur_inconnu"),
        "timestamp": timestamp,
        "device_id": device.get("deviceId") or device.get("DeviceId") or "poste_inconnu",
    }


def main():
    if len(sys.argv) < 2:
        print("Utilisation : python3 connect_real_data.py chemin/vers/tes_vrais_logs.json")
        sys.exit(1)

    real_filepath = sys.argv[1]
    print(f"Chargement du VRAI fichier : {real_filepath}")
    raw_events = load_real_entra_export(real_filepath)
    print(f"{len(raw_events)} vraies connexions trouvées dans ton tenant de test.\n")

    model = joblib.load(MODEL_PATH)
    bounds = json.loads(BOUNDS_PATH.read_text(encoding="utf-8"))

    events = [normalize_event(e) for e in raw_events]
    events.sort(key=lambda e: e["timestamp"])

    known_devices_by_user = {}
    results = []

    for event in events:
        user = event["user"]
        ts = event["timestamp"]
        hour = ts.hour

        known = known_devices_by_user.setdefault(user, set())
        is_new_device = event["device_id"] not in known
        known.add(event["device_id"])

        # Pas d'info département dans un simple export sign-in logs — à enrichir plus tard
        # avec un appel séparé à l'annuaire (/users/{id}) si besoin. Ici : traité comme standard.
        sensitive = False

        features = {
            "hour": hour,
            "is_off_hours": int(hour < 8 or hour >= 17),
            "is_new_device": int(is_new_device),
            "is_weekend": int(ts.weekday() >= 5),
            "is_holiday": 0,  # à enrichir avec le calendrier tunisien si besoin (voir notebook)
        }

        vector = build_feature_vector(features, sensitive)
        raw_score = model.decision_function([vector])[0]
        risk_score = compute_risk_score(raw_score, bounds)
        action = decide_action(risk_score, sensitive)
        description = generate_description(features, sensitive)

        results.append({
            "user": user,
            "timestamp": ts,
            "risk_score": risk_score,
            "action": ACTION_LABELS[action],
            "description": description,
        })

    report = pd.DataFrame(results).sort_values("risk_score", ascending=False)
    report.to_csv("rapport_donnees_reelles.csv", index=False)

    print("=== RÉSULTATS SUR TES VRAIES DONNÉES ===\n")
    print(report.to_string(index=False))
    print(f"\nRapport complet sauvegardé : rapport_donnees_reelles.csv")


if __name__ == "__main__":
    main()
