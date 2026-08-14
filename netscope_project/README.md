# NetScope Agent

Analyse le trafic DNS sortant, détecte les domaines suspects via un modèle ML
entraîné sur CIC-Bell-DNSExF2021, et retourne un score de risque (0-100).

## Structure

```
netscope_project/
├── models/                    modèle entraîné (.pkl) — voir models/README.md
├── notebooks/                 notebook d'entraînement (Kaggle) et script VS Code
├── scripts/
│   └── score_domain.py        test rapide en ligne de commande
├── src/netscope_agent/
│   ├── scorer.py               logique de scoring, réutilisable
│   └── api.py                  API FastAPI (endpoint /analyze)
├── .env.example
├── .gitignore
└── requirements.txt
```

## Installation

```
python -m venv venv
venv\Scripts\activate        (Windows)  ou  source venv/bin/activate   (Mac/Linux)
pip install -r requirements.txt
```

## Mettre le modèle en place

1. Exécuter le notebook sur Kaggle jusqu'à la section export (section 15 ou 17).
2. Télécharger `netscope_model.pkl` et `netscope_features.pkl` depuis l'onglet Output de Kaggle.
3. Les placer dans `models/`.

## Tester rapidement

```
python scripts/score_domain.py
```

## Lancer l'API

```
cp .env.example .env
uvicorn netscope_agent.api:app --reload --app-dir src
```

Puis :

```
POST http://localhost:8000/analyze
{
  "domain": "xj4k9z-relay-node.info",
  "features": { "rr_name_entropy": 3.9, "...": 0 }
}
```

## Prochaines étapes

- Vérifier l'absence de data leakage dans les features (voir conversation d'origine).
- Ajouter la notification webhook (Slack/Teams) quand `verdict == "suspect"`.
- Corréler avec le score de risque humain (module séparé, à connecter).
