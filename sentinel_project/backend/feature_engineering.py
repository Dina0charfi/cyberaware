"""
Reconstruit le vecteur de features EXACTEMENT dans le même ordre que celui utilisé
pour entraîner le modèle CERT réduit (sentinel_cert_essentiel_FINAL.ipynb) — 7 features
"universelles", compatibles aussi bien avec CERT qu'avec de vrais logs Entra ID/Google.

⚠️ Ce modèle N'A PLUS les features spécifiques à CERT (USB, fichier leurre, emails) —
voir le notebook pour la justification de ce choix (réutilisabilité sans réentraînement).
"""

import math

FEATURE_COLS = [
    "hour_sin", "hour_cos", "is_weekend", "is_holiday",
    "is_off_hours", "is_sensitive_department", "is_new_device",
]


def build_feature_vector(features: dict, sensitive: bool) -> list:
    hour = features["hour"]
    hour_sin = math.sin(2 * math.pi * hour / 24)
    hour_cos = math.cos(2 * math.pi * hour / 24)

    return [
        hour_sin,
        hour_cos,
        features.get("is_weekend", 0),
        features.get("is_holiday", 0),
        features.get("is_off_hours", 0),
        int(sensitive),
        features.get("is_new_device", 0),  # remplace is_new_pc — même logique, nom plus générique
    ]