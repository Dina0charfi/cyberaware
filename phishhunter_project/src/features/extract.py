"""
PhishHunter — Extraction des features
======================================
Ce fichier contient EXACTEMENT les mêmes fonctions que celles utilisées
dans le notebook Kaggle pour entraîner le modèle. Il est essentiel que
ce code reste identique à celui de l'entraînement — sinon les features
calculées en production ne correspondront pas à ce que le modèle attend.

Sources notebook : Phase 1 (signaux simples), Phase 3 (features cyber).
"""

import re
import math
import json
from collections import Counter
from pathlib import Path

# ----------------------------------------------------------------------
# Chargement de la liste des marques connues (générée depuis Kaggle)
# ----------------------------------------------------------------------
_BRANDS_PATH = Path(__file__).resolve().parents[2] / "models" / "phishhunter_known_brands.json"

try:
    with open(_BRANDS_PATH, "r", encoding="utf-8") as f:
        KNOWN_BRANDS = json.load(f)
except FileNotFoundError:
    # Fallback si le fichier n'a pas encore été copié dans models/
    KNOWN_BRANDS = [
        'paypal', 'amazon', 'apple', 'microsoft', 'google', 'facebook', 'netflix',
        'linkedin', 'ebay', 'dropbox', 'outlook', 'yahoo', 'instagram', 'twitter',
        'wellsfargo', 'chase', 'bankofamerica', 'irs', 'dhl', 'fedex', 'ups',
        'gmail', 'hotmail', 'adobe', 'spotify'
    ]

URGENCY_WORDS = [
    'urgent', 'immediately', 'action required', 'verify', 'suspend', 'expire',
    'click here', 'limited time', 'act now', 'confirm', 'password', 'account locked'
]

# Ordre EXACT des features tabulaires attendu par le modèle.
# Doit correspondre à ALL_TABULAR_FEATURES dans le notebook Kaggle.
FEATURE_ORDER = [
    'has_urgency', 'url_count', 'has_ip_url', 'word_count',
    'is_typosquat', 'typosquat_distance', 'domain_entropy', 'domain_length',
    'domain_digit_ratio', 'uppercase_ratio', 'exclamation_count', 'has_sender_info'
]


# ----------------------------------------------------------------------
# Signaux simples (Phase 1)
# ----------------------------------------------------------------------
def has_urgency(text: str) -> int:
    text_lower = str(text).lower()
    return int(any(w in text_lower for w in URGENCY_WORDS))


def count_urls(text: str) -> int:
    return len(re.findall(r'https?://\S+|www\.\S+', str(text)))


def has_ip_url(text: str) -> int:
    return int(bool(re.search(r'https?://\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}', str(text))))


def word_count(text: str) -> int:
    return len(str(text).split())


# ----------------------------------------------------------------------
# Domaine expéditeur (Phase 3)
# ----------------------------------------------------------------------
def extract_domain(sender: str):
    """Extrait le domaine depuis un champ sender du type 'Nom <user@domain.com>'."""
    if not sender:
        return None
    match = re.search(r'@([\w\.-]+)', sender)
    if match:
        return match.group(1).lower().strip()
    return None


def levenshtein(s1: str, s2: str) -> int:
    """Distance d'édition entre deux chaînes (nombre minimal de modifications)."""
    if len(s1) < len(s2):
        return levenshtein(s2, s1)
    if len(s2) == 0:
        return len(s1)
    previous_row = range(len(s2) + 1)
    for i, c1 in enumerate(s1):
        current_row = [i + 1]
        for j, c2 in enumerate(s2):
            insertions = previous_row[j + 1] + 1
            deletions = current_row[j] + 1
            substitutions = previous_row[j] + (c1 != c2)
            current_row.append(min(insertions, deletions, substitutions))
        previous_row = current_row
    return previous_row[-1]


def typosquat_score(domain):
    """Retourne (marque_la_plus_proche, distance_min) pour un domaine donné."""
    if not domain:
        return None, None
    domain_core = domain.split('.')[0]

    best_brand, best_dist = None, 999
    for brand in KNOWN_BRANDS:
        if domain_core == brand:
            return brand, 0
        dist = levenshtein(domain_core, brand)
        if dist < best_dist:
            best_brand, best_dist = brand, dist
    return best_brand, best_dist


def is_typosquat(domain, max_dist: int = 2) -> int:
    """1 si le domaine ressemble fortement à une marque connue (dist 1-2) sans l'être exactement."""
    brand, dist = typosquat_score(domain)
    if brand is None or dist is None:
        return 0
    return int(0 < dist <= max_dist)


def domain_entropy(domain) -> float:
    """Entropie de Shannon du domaine — plus élevé = plus 'aléatoire'."""
    if not domain:
        return 0.0
    domain_core = domain.split('.')[0]
    if len(domain_core) == 0:
        return 0.0
    counts = Counter(domain_core)
    length = len(domain_core)
    return -sum((c / length) * math.log2(c / length) for c in counts.values())


def domain_length(domain) -> float:
    return len(domain) if domain else 0.0


def domain_digit_ratio(domain) -> float:
    if not domain:
        return 0.0
    digits = sum(c.isdigit() for c in domain)
    return digits / len(domain) if len(domain) > 0 else 0.0


# ----------------------------------------------------------------------
# Signaux comportementaux (Phase 3)
# ----------------------------------------------------------------------
def uppercase_ratio(text: str) -> float:
    letters = [c for c in str(text) if c.isalpha()]
    if not letters:
        return 0.0
    return sum(c.isupper() for c in letters) / len(letters)


def exclamation_count(text: str) -> int:
    return str(text).count('!')


# ----------------------------------------------------------------------
# Tokenisation + vectorisation Word2Vec (NLP)
# ----------------------------------------------------------------------
def simple_tokenize(text: str):
    """Tokenisation simple : minuscules, mots alphabétiques de 2+ lettres."""
    return re.findall(r'\b[a-z]{2,}\b', str(text).lower())


def email_to_vector(tokens, w2v_model, vector_size: int = 200):
    """Moyenne des vecteurs Word2Vec des mots présents dans le vocabulaire."""
    import numpy as np
    vectors = [w2v_model.wv[word] for word in tokens if word in w2v_model.wv]
    if len(vectors) == 0:
        return np.zeros(vector_size)
    return np.mean(vectors, axis=0)


# ----------------------------------------------------------------------
# Fonction principale : email brut -> dict de features tabulaires
# ----------------------------------------------------------------------
def extract_all_features(sender: str, subject: str, body: str) -> dict:
    """
    Prend un email brut (sender, subject, body) et retourne un dictionnaire
    contenant toutes les features tabulaires, dans l'ordre attendu par le modèle.
    """
    text = f"{subject or ''} {body or ''}".strip()
    domain = extract_domain(sender)
    brand, typo_dist = typosquat_score(domain)
    has_sender_info = int(bool(sender and sender.strip()))

    features = {
        'has_urgency': has_urgency(text),
        'url_count': count_urls(text),
        'has_ip_url': has_ip_url(text),
        'word_count': word_count(text),
        'is_typosquat': is_typosquat(domain),
        'typosquat_distance': typo_dist if typo_dist is not None else 0,
        'domain_entropy': domain_entropy(domain),
        'domain_length': domain_length(domain),
        'domain_digit_ratio': domain_digit_ratio(domain),
        'uppercase_ratio': uppercase_ratio(text),
        'exclamation_count': exclamation_count(text),
        'has_sender_info': has_sender_info,
    }

    # Métadonnées utiles pour l'explication LLM (pas des features numériques)
    meta = {
        'text': text,
        'sender_domain': domain,
        'typosquat_brand': brand if features['is_typosquat'] else None,
    }

    return features, meta
