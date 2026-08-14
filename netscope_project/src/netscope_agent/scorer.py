"""
Coeur de l'agent NetScope : charge le modèle entraîné et calcule un score
de risque (0-100) pour un domaine DNS donné, avec une explication SHAP des
facteurs qui ont le plus pesé dans la décision.

Utilisation :
    from netscope_agent.scorer import NetScopeScorer

    scorer = NetScopeScorer()
    result = scorer.score_domain({"rr_name_entropy": 3.9, ...})
"""

from pathlib import Path
from typing import Any

import joblib
import pandas as pd
import shap

MODELS_DIR = Path(__file__).resolve().parents[2] / "models"

# Traduction des noms de features bruts en libellés lisibles pour un analyste,
# affichés dans "Facteurs principaux" côté page.
FEATURE_LABELS = {
    "rr_name_entropy": "Entropie du nom de domaine élevée",
    "rr_name_length": "Nom de domaine long",
    "entropy": "Complexité du nom élevée",
    "FQDN_count": "Plusieurs requêtes FQDN",
    "subdomain_length": "Sous-domaine long",
    "numeric": "Beaucoup de caractères numériques",
    "special": "Caractères spéciaux présents",
    "labels": "Nombreux niveaux de sous-domaines",
    "labels_max": "Label DNS très long",
    "labels_average": "Longueur moyenne des labels élevée",
    "len": "Nom de domaine long",
    "subdomain": "Présence de sous-domaine",
    "rr_count": "Nombreux enregistrements DNS",
    "a_records": "Beaucoup d'adresses IP associées",
    "ttl_mean": "TTL faible (rotation rapide)",
    "ttl_variance": "TTL instable",
}


def risk_level(score: float) -> str:
    if score < 30:
        return "Faible"
    elif score < 60:
        return "Moyen"
    elif score < 80:
        return "Élevé"
    return "Critique"


def human_priority(score: int) -> str:
    if score >= 70:
        return "élevée"
    elif score >= 40:
        return "moyenne"
    return "faible"


class NetScopeScorer:
    def __init__(
        self,
        model_path: Path = MODELS_DIR / "netscope_model.pkl",
        features_path: Path = MODELS_DIR / "netscope_features.pkl",
        threshold: float = 50.0,
    ):
        if not model_path.exists() or not features_path.exists():
            raise FileNotFoundError(
                "Modèle introuvable. Place netscope_model.pkl et "
                "netscope_features.pkl dans le dossier models/ "
                "(voir models/README.md)."
            )
        self.model = joblib.load(model_path)
        self.features = joblib.load(features_path)
        self.threshold = threshold

        # TreeExplainer fonctionne pour RandomForest/XGBoost/LightGBM/
        # HistGradientBoosting sans données de fond. Si le modèle final est
        # un Logistic Regression, ça échoue proprement et on désactive SHAP
        # plutôt que de planter l'API.
        try:
            self.explainer = shap.TreeExplainer(self.model)
        except Exception:
            self.explainer = None

    def explain(self, x: pd.DataFrame, top_n: int = 4) -> list[dict[str, Any]]:
        if self.explainer is None:
            return []

        shap_values = self.explainer.shap_values(x)
        if isinstance(shap_values, list):
            values = shap_values[1][0]
        else:
            values = shap_values[0]

        contributions = sorted(
            zip(self.features, values), key=lambda t: abs(t[1]), reverse=True
        )

        factors = []
        for feat, val in contributions[:top_n]:
            factors.append({
                "feature": feat,
                "label": FEATURE_LABELS.get(feat, feat),
                "impact": round(float(val), 4),
                "direction": "increase" if val > 0 else "decrease",
            })
        return factors

    def score_domain(self, row: dict[str, Any]) -> dict[str, Any]:
        """
        row : dict contenant les valeurs des features listées dans self.features.
        Les clés manquantes lèvent une erreur explicite plutôt qu'un NaN silencieux.
        """
        missing = [f for f in self.features if f not in row]
        if missing:
            raise ValueError(f"Features manquantes dans row : {missing}")

        x = pd.DataFrame([row])[self.features]
        proba = self.model.predict_proba(x)[0][1]
        score = round(float(proba) * 100, 1)

        return {
            "ml_score": score,
            "risk_level": risk_level(score),
            "verdict": "suspect" if score > self.threshold else "normal",
            "factors": self.explain(x),
        }