"""
PhishHunter — Moteur de scoring
=================================
Charge le modèle final (Word2Vec + Logistic Regression + features cyber)
une seule fois au démarrage de l'application, puis calcule un score de
dangerosité (0-100) pour chaque email reçu.
"""

import json
import numpy as np
import joblib
from pathlib import Path
from gensim.models import Word2Vec

from src.features.extract import (
    extract_all_features, simple_tokenize, email_to_vector, FEATURE_ORDER
)

MODELS_DIR = Path(__file__).resolve().parents[2] / "models"


class PhishHunterEngine:
    def __init__(self):
        print("[PhishHunter] Chargement des modèles...")

        self.model = joblib.load(MODELS_DIR / "phishhunter_model.pkl")
        self.w2v_model = Word2Vec.load(str(MODELS_DIR / "phishhunter_word2vec.model"))
        self.scaler = joblib.load(MODELS_DIR / "phishhunter_scaler.pkl")

        with open(MODELS_DIR / "phishhunter_feature_names.json", "r", encoding="utf-8") as f:
            self.feature_names = json.load(f)

        # Sécurité : vérifie que l'ordre des features correspond bien à ce qui est attendu
        if self.feature_names != FEATURE_ORDER:
            print("[PhishHunter][ATTENTION] L'ordre des features chargé diffère de FEATURE_ORDER "
                  "défini dans extract.py — vérifie la cohérence avant de continuer.")

        print("[PhishHunter] Modèles chargés avec succès.")

    def analyze(self, sender: str, subject: str, body: str) -> dict:
        """
        Analyse un email et retourne un score de dangerosité (0-100),
        une classification, et les features déclenchées (pour l'explication LLM).
        """
        # 1. Extraction des features tabulaires (Phase 3)
        features_dict, meta = extract_all_features(sender, subject, body)
        tabular_vector = np.array([[features_dict[f] for f in self.feature_names]], dtype=float)
        tabular_scaled = self.scaler.transform(tabular_vector)

        # 2. Embedding Word2Vec du texte (NLP)
        tokens = simple_tokenize(meta["text"])
        text_embedding = email_to_vector(tokens, self.w2v_model, vector_size=200).reshape(1, -1)

        # 3. Concaténation embedding + features tabulaires (même ordre qu'à l'entraînement)
        X = np.hstack([text_embedding, tabular_scaled])

        # 4. Prédiction
        proba_phishing = self.model.predict_proba(X)[0][1]
        risk_score = round(proba_phishing * 100)

        if risk_score >= 70:
            classification = "Phishing"
        elif risk_score >= 40:
            classification = "Suspicious"
        else:
            classification = "Safe"

        # 5. Liste des features "déclenchées" (utile pour le LLM et le dashboard)
        triggered = []
        if features_dict["is_typosquat"]:
            triggered.append({
                "signal": "typosquat",
                "detail": f"Domaine proche de la marque « {meta['typosquat_brand']} » "
                          f"(distance {features_dict['typosquat_distance']})"
            })
        if features_dict["has_urgency"]:
            triggered.append({"signal": "urgency", "detail": "Langage d'urgence détecté dans le texte"})
        if features_dict["has_ip_url"]:
            triggered.append({"signal": "ip_url", "detail": "Lien pointant vers une adresse IP brute"})
        if features_dict["domain_entropy"] > 3.5:
            triggered.append({"signal": "domain_entropy", "detail": "Nom de domaine à l'apparence générée automatiquement"})
        if not features_dict["has_sender_info"]:
            triggered.append({"signal": "no_sender_info", "detail": "Expéditeur non identifiable"})

        # Cas important : le score peut être élevé à cause du texte (Word2Vec)
        # sans qu'aucune règle explicite ne se soit déclenchée. Sans ce signal,
        # le dashboard afficherait "aucun signal détecté" avec un score rouge —
        # une incohérence trompeuse pour l'utilisateur.
        if not triggered and risk_score >= 40:
            triggered.append({
                "signal": "semantic_pattern",
                "detail": "Le contenu de l'email présente des similarités textuelles avec des emails "
                          "de phishing connus (détecté par l'analyse sémantique), sans signal structurel "
                          "explicite (domaine, urgence). Une vérification manuelle est recommandée."
            })

        return {
            "risk_score": risk_score,
            "classification": classification,
            "sender_domain": meta["sender_domain"],
            "features": features_dict,
            "triggered_signals": triggered,
        }


# Instance unique, chargée une seule fois (importée par l'API)
engine = None

def get_engine() -> PhishHunterEngine:
    global engine
    if engine is None:
        engine = PhishHunterEngine()
    return engine
