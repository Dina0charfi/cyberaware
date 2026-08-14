# PhishHunter — API de détection de phishing

Modèle final : **Word2Vec + Logistic Regression + features cybersécurité**
(entraîné sur 163 700 emails, 7 sources — voir le rapport méthodologique
pour le détail des phases 1 à 3).

## 1. Installation

```bash
python -m venv venv
source venv/bin/activate        # Windows : venv\Scripts\activate
pip install -r requirements.txt
```

## 2. Placer les fichiers du modèle

Télécharge depuis Kaggle (panneau "Output" de ton notebook) et place dans `models/` :

```
models/
├── phishhunter_model.pkl
├── phishhunter_word2vec.model
├── phishhunter_scaler.pkl
├── phishhunter_feature_names.json
└── phishhunter_known_brands.json
```

⚠️ Le dossier `models/` est vide dans ce projet — ces fichiers doivent être générés
depuis ton notebook Kaggle (cellule de sauvegarde finale) puis téléchargés manuellement.

## 3. Configurer le token du LLM (Hugging Face — gratuit)

1. Crée un compte gratuit sur https://huggingface.co
2. Génère un token : Settings → Access Tokens → New token (rôle "Read" suffit)

```bash
cp .env.example .env
# puis édite .env et renseigne ton vrai HF_TOKEN
```

⚠️ Le niveau gratuit de l'Inference API peut renvoyer une erreur de "cold start"
(modèle en cours de chargement côté Hugging Face) lors du tout premier appel —
réessaie après quelques secondes. Le code inclut un fallback qui affiche les
signaux bruts si l'appel échoue, pour que l'API reste fonctionnelle même sans LLM.

## 4. Lancer le serveur

```bash
uvicorn src.api.main:app --reload
```

L'API est alors disponible sur http://127.0.0.1:8000
Documentation interactive (Swagger) : http://127.0.0.1:8000/docs

## 5. Tester

```bash
curl -X POST http://127.0.0.1:8000/analyze \
  -H "Content-Type: application/json" \
  -d '{
    "sender": "support@banque-partenere-secure.com",
    "subject": "URGENT — Mise à jour de vos identifiants sous 24h",
    "body": "Cliquez ici immédiatement pour confirmer votre mot de passe avant expiration de votre compte."
  }'
```

Réponse attendue : un score de dangerosité élevé, classification "Phishing",
avec le signal "typosquat" détecté (partenere vs partenaire) et une explication
générée par le LLM.

## Structure du projet

```
phishhunter/
├── models/              ← fichiers du modèle (à ajouter manuellement, voir étape 2)
├── src/
│   ├── features/
│   │   └── extract.py   ← calcul des features (identique au notebook Kaggle)
│   ├── scoring/
│   │   └── engine.py    ← chargement du modèle + calcul du score 0-100
│   ├── llm/
│   │   └── explain.py   ← génération de l'explication via Claude
│   └── api/
│       └── main.py      ← routes FastAPI (/analyze, /webhook/email)
├── requirements.txt
├── .env.example
└── README.md
```

## Prochaines étapes

- Intégration webhook réelle (Microsoft Graph API / Gmail API) dans `/webhook/email`
  — actuellement un squelette à compléter (voir les TODO dans `src/api/main.py`)
- Système d'alerte (Slack/Teams/email) quand `risk_score >= 70`
- Dashboard consommant cette API
- RAG cybersécurité pour enrichir les explications avec des campagnes de phishing connues
