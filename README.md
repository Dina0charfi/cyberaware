# CyberAware

## Overview

CyberAware est un portfolio de 5 agents de cybersécurité indépendants mais interconnectés, développé pendant un stage. Chaque agent couvre un domaine différent — fuites de données, trafic DNS suspect, phishing par email, menace interne, réponse à incident — avec une architecture commune et une charte visuelle unifiée.

Le principe transversal appliqué aux 5 agents : un score ou une règle décide, un LLM peut expliquer ou rédiger, mais **ne décide jamais seul** — sauf deux exceptions explicitement assumées (le mode agentique de PhishHunter et le mode autonome `agent.py` de DarkWatch), où le LLM choisit une action finale parmi un ensemble fermé et prédéfini d'options, jamais librement. Chaque agent reste pleinement fonctionnel sans aucune clé API : en l'absence d'une clé, le comportement bascule automatiquement sur des règles simples plutôt que de planter.

Aucun des 5 agents n'est branché à un vrai système bancaire (Active Directory, Exchange, SIEM) — faute d'accès pendant le stage. Ce point est documenté explicitement agent par agent plus bas plutôt que masqué.

## Architecture

```
                    launch_all.py (port 8000, page d'accueil)
                              │
       ┌───────────┬──────────┼──────────┬───────────┐
   DarkWatch    NetScope  PhishHunter  Sentinel   CrisisBot
    :8877        :8001      :8002       :8003       :8878
       │            │           │           │           ▲
       └────────────┴───────────┴───────────┴── notify_crisisbot()
                                                  (best-effort, HTTP POST,
                                                   pas d'authentification)
                                                          │
                                                 POST /api/webhook/incident
                                                          │
                                                Slack Incoming Webhook (réel)
```

Les 4 agents de détection (DarkWatch, NetScope, PhishHunter, Sentinel) suivent le même schéma : Perception → Scoring → Raisonnement → Action → Mémoire/log. CrisisBot est différent par construction : il ne score rien, il orchestre une réponse standardisée à partir d'une décision déjà prise en amont par un autre agent.

Chaque agent tourne indépendamment (son propre venv, son propre port) et communique avec CrisisBot via un petit client HTTP dupliqué dans chaque projet (`crisisbot_client.py`) — un appel best-effort, timeout court, qui ne bloque jamais l'agent appelant si CrisisBot est injoignable.

## Agents

### DarkWatch — surveillance de fuites de données

- **Rôle** : détecte si des comptes email surveillés apparaissent dans des fuites de données publiques.
- **Technologie** : Python 3.9+, bibliothèque standard uniquement (`http.server`) — aucune dépendance externe.
- **Entrée** : liste d'emails à surveiller (`emails_example.txt`, statique).
- **Sortie** : alerte + action recommandée (reset mot de passe, notification, escalade), notification CrisisBot si risque high/critical.
- **Intégrations** : API externe **XposedOrNot** (`[IMPLEMENTED]`, vraies données de fuites, gratuite, sans clé) ; LLM Groq pour la décision d'action (`[IMPLEMENTED + DEMO]`, avec repli par règles si pas de clé) ; branchement Active Directory (`[PREPARED FOR REAL INTEGRATION]`, `email_sources.py::from_active_directory()`, lève `NotImplementedError`, jamais appelée).
- **Statut** : trois modes d'usage distincts et à ne pas confondre — mode dashboard intégré (`server.py`, port 8877), mode CLI ponctuel (`darkwatch.py`), mode agent autonome en boucle (`agent.py`, non lancé par `launch_all.py`).

### NetScope — détection de domaines DNS suspects

- **Rôle** : repère un trafic DNS qui ressemble statistiquement à de l'exfiltration de données ou du command-and-control.
- **Technologie** : Python, FastAPI + Uvicorn ; modèle LightGBM (`scikit-learn`/`lightgbm`) + SHAP pour l'explicabilité.
- **Entrée** : 16 features statistiques calculées sur le nom de domaine et la réponse DNS.
- **Sortie** : score de risque 0-100, niveau (Faible/Moyen/Élevé/Critique), facteurs SHAP principaux.
- **Intégrations** : webhook `/webhook/traffic-event` (`[IMPLEMENTED]`, secret partagé HMAC) ; boucle interne `auto_scan.py` (`[IMPLEMENTED + DEMO]`, échantillonne un CSV local) ; calcul de features en direct à partir d'un simple nom de domaine (`[IMPLEMENTED]`, `live_features.py`, avec résolution DNS réelle).
- **Statut** : deux seuils distincts à ne pas confondre — 50 (verdict suspect/normal, affichage) et 80 (`AUTO_ACT_THRESHOLD`, isolement automatique sans humain).

### PhishHunter — détection de phishing par email

- **Rôle** : classe un email entrant en Safe / Suspicious / Phishing.
- **Technologie** : Python, FastAPI + Uvicorn ; Word2Vec (embedding 200 dim, `gensim`) + 12 features tabulaires + régression logistique.
- **Entrée** : email (expéditeur, sujet, corps).
- **Sortie** : score 0-100, classification, signaux déclenchés, explication en langage naturel.
- **Intégrations** : webhook `/webhook/email` (`[IMPLEMENTED]`, alimenté par un simulateur) ; agent autonome avec tool use (`[IMPLEMENTED]`, Groq, function calling, décide `block_email`/`escalate_to_human`/`deliver_normally`) ; branchement Microsoft Graph/Gmail (`[PREPARED FOR REAL INTEGRATION]`, squelette dans le webhook, gestion de la validation Graph non implémentée).
- **Statut** : le seul agent avec deux niveaux de décision distincts et assumés — un chemin déterministe fiable (score ≥ 70 → CrisisBot direct), et un chemin agentique plus riche pour la démonstration du raisonnement LLM outillé.

### Sentinel — détection de connexions anormales (menace interne)

- **Rôle** : repère une connexion suspecte (horaire, poste, département) et propose une réponse proportionnée.
- **Technologie** : Python, FastAPI + Uvicorn ; Isolation Forest non supervisé (`scikit-learn`), 7 features "universelles".
- **Entrée** : événement de connexion (utilisateur, poste, date/heure, département).
- **Sortie** : score de risque 0-100, action (`no_action`/`monitor`/`trigger_training`/`escalate_to_human`), explication en langage naturel.
- **Intégrations** : webhook `/api/webhook/signin-event` (`[IMPLEMENTED]`, secret partagé, gère la poignée de main de validation) ; branchement Entra ID/SIEM (`[PREPARED FOR REAL INTEGRATION]`, non connecté — les logs de connexion ne supportent pas nativement les webhooks Microsoft Graph, un polling ou un relais SIEM serait nécessaire).
- **Statut** : le modèle a été délibérément réduit à des features réutilisables sans réentraînement sur de vraies données (voir section Machine Learning Models).

### CrisisBot — réponse à incident automatisée

- **Rôle** : reçoit les alertes des 4 autres agents et déroule un runbook de réponse standardisé.
- **Technologie** : Python 3.9+, bibliothèque standard uniquement — même philosophie que DarkWatch.
- **Entrée** : incident (`source_agent`, `severity`, `description`), envoyé par webhook ou saisi manuellement.
- **Sortie** : déroulé du runbook (5 étapes chronométrées), message de communication interne, notification Slack.
- **Intégrations** : Slack Incoming Webhook (`[IMPLEMENTED]`, message réel envoyé, pas simulé) ; Teams et Email (`[CONCEPTUAL]`, mentionnés dans l'interface, jamais codés) ; LLM Groq pour la rédaction du message (`[IMPLEMENTED + DEMO]`, repli générique si pas de clé).
- **Statut** : seul agent sans aucun modèle ML — orchestration pure (type SOAR), pas de classification.

## Global Pipeline

```
Detection (perception d'une donnée brute)
     → Analysis (extraction de features)
     → Scoring (modèle ML ou score externe)
     → Decision (règles/seuils, ou LLM parmi des choix fermés)
     → Response (action simulée + notification CrisisBot si grave)
```

## Technology Stack

- **Langage** : Python 3.9+ sur les 5 agents.
- **Frameworks web** : FastAPI + Uvicorn (NetScope, PhishHunter, Sentinel) ; `http.server` de la bibliothèque standard (DarkWatch, CrisisBot).
- **Machine Learning** : `scikit-learn`, `lightgbm`, `xgboost` (NetScope) ; `gensim` (Word2Vec, PhishHunter) ; `scikit-learn` (Isolation Forest, Sentinel) ; `shap` (explicabilité, NetScope) ; `joblib` (sérialisation des modèles).
- **LLM** : Groq (Llama 3.x, gratuit) pour DarkWatch, PhishHunter, CrisisBot ; Hugging Face Inference API (modèles de repli multiples) pour Sentinel.
- **Frontend** : HTML/CSS/JS vanilla sur les 5 dashboards, charte graphique commune, aucun framework front.
- **Autres** : `python-whois` (PhishHunter, vérification d'âge de domaine), `holidays` (Sentinel, jours fériés tunisiens), `python-dotenv` (variables d'environnement).

## Project Structure

```
internship/
├── darkwatch_project/       agent DarkWatch (stdlib pure)
├── netscope_project/        agent NetScope (FastAPI + ML)
│   ├── src/netscope_agent/  scorer, api, live_features, auto_scan, actions
│   ├── models/               netscope_model.pkl, netscope_features.pkl
│   └── notebooks/            entraînement (Kaggle)
├── phishhunter_project/     agent PhishHunter (FastAPI + ML + agent LLM)
│   ├── src/
│   │   ├── api/main.py       point d'entrée FastAPI
│   │   ├── agent/             boucle agentique réelle (agent_loop.py, tools.py)
│   │   ├── features/extract.py
│   │   ├── scoring/engine.py
│   │   └── store/memory_store.py
│   └── models/                phishhunter_model.pkl, word2vec, scaler, feature_names.json
├── sentinel_project/
│   ├── backend/               app.py, feature_engineering.py, decision_engine.py
│   └── kaggle-notebook/        entraînement (Kaggle)
├── crisisbot_project/       agent CrisisBot (stdlib pure)
├── launch_all.py             lance les 5 agents + page d'accueil (port 8000)
├── event_simulator.py        simule des événements pour PhishHunter/Sentinel/NetScope/DarkWatch en mode --simulate
├── rapport_de_stage.tex / internship_report.tex   rapports de stage (FR/EN)
└── README.md                  ce fichier
```

Chaque `*_project/` contient son propre `.env.example`, `.gitignore` et `requirements.txt` (sauf DarkWatch et CrisisBot, qui n'ont aucune dépendance externe).

## Installation

Prérequis : Python 3.9 ou supérieur.

```powershell
# Pour chaque projet avec dépendances (netscope_project, phishhunter_project, sentinel_project/backend) :
cd <projet>
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
```

DarkWatch et CrisisBot n'ont besoin d'aucune installation (bibliothèque standard uniquement).

## Configuration

Chaque projet a un `.env.example` documenté — copie-le en `.env` et renseigne tes propres clés :

```powershell
cd <projet>
copy .env.example .env
```

Toutes les clés sont optionnelles : chaque agent reste fonctionnel sans clé API (repli automatique sur des règles). `launch_all.py` transmet l'environnement du terminal à tous les sous-process, donc définir les clés une seule fois avant de lancer suffit :

```powershell
$env:GROQ_API_KEY = "..."     # DarkWatch, PhishHunter (agent), CrisisBot
$env:HF_TOKEN = "..."         # Sentinel
python launch_all.py
```

NetScope ne nécessite aucune clé pour fonctionner (ML pur) — Groq y est optionnel, uniquement pour l'explication en langage naturel.

## Running the Project

Tout lancer d'un coup, avec page d'accueil sur `http://localhost:8000` :

```powershell
python launch_all.py                # mode silencieux (par défaut)
python launch_all.py --simulate     # + flux d'événements factices, agents réagissent automatiquement
```

Ou chaque agent séparément (voir tableau des ports plus bas pour la commande exacte de chacun).

## Agent-to-Agent Communication

| De | Vers | Mécanisme | Authentification |
|---|---|---|---|
| DarkWatch | CrisisBot | `notify_crisisbot()`, POST best-effort | Aucune |
| NetScope | CrisisBot | `notify_crisisbot()`, POST best-effort | Aucune |
| PhishHunter | CrisisBot | `notify_crisisbot()`, POST best-effort | Aucune |
| Sentinel | CrisisBot | `notify_crisisbot()`, POST best-effort | Aucune |
| Externe → NetScope | `POST /webhook/traffic-event` | Push | Secret partagé (`?x_webhook_secret=`) |
| Externe → Sentinel | `POST /api/webhook/signin-event` | Push, gère la validation | Secret partagé |
| Externe → PhishHunter | `POST /webhook/email` | Push | Aucune actuellement |
| Externe → CrisisBot | `POST /api/webhook/incident` | Push | **Aucune** |

## External Integrations

| Integration | Agent | Status | Configuration |
|---|---|---|---|
| XposedOrNot (breach data) | DarkWatch | Implemented | Aucune clé requise |
| Groq (LLM) | DarkWatch, PhishHunter, CrisisBot | Implemented | `GROQ_API_KEY` |
| Hugging Face Inference | Sentinel | Implemented | `HF_TOKEN` |
| Slack Incoming Webhook | CrisisBot | Implemented | `SLACK_WEBHOOK_URL` |
| SHAP | NetScope | Implemented | Aucune (local) |
| WHOIS | PhishHunter (agent) | Implemented | Aucune clé (requêtes publiques) |
| Active Directory / Entra ID | DarkWatch | Prepared | `email_sources.py::from_active_directory()`, squelette non implémenté |
| Firewall/Proxy DNS réel | NetScope | Prepared | Remplacer `_pick_one_row()` dans `auto_scan.py` par une vraie source |
| Exchange / Google Workspace | PhishHunter | Prepared | `/webhook/email` fonctionnel, à connecter à une vraie boîte |
| SIEM / Entra ID sign-in logs | Sentinel | Prepared | `/api/webhook/signin-event` fonctionnel, à connecter à une vraie source |
| Teams, Email (CrisisBot) | CrisisBot | Conceptual | Jamais implémenté, seulement mentionné dans l'UI |

## Machine Learning Models

| Agent | Modèle | Dataset d'entraînement | Métrique |
|---|---|---|---|
| NetScope | LightGBM (tuné Optuna) | CIC-Bell-DNSExF2021 (Kaggle, 102 762 lignes) | F1 CV ≈ 0.831 |
| PhishHunter | Word2Vec (200 dim) + Régression logistique | Notebook d'entraînement non présent dans ce dossier ; production reproduit exactement les features du notebook | Non confirmé (notebook absent) |
| Sentinel | Isolation Forest (non supervisé) | CERT Insider Threat Detection Research (Kaggle) | Stabilité vérifiée (corrélation de rang 1.000 entre graines) |
| DarkWatch | Aucun — score fourni par l'API XposedOrNot | — | — |
| CrisisBot | Aucun — orchestration pure | — | — |

## Datasets

- **NetScope** : CIC-Bell-DNS-Exfiltration 2021 (`dhoogla/cicbelldnsexf2021`, Kaggle), 102 762 requêtes DNS labellisées.
- **Sentinel** : CERT Insider Threat Detection Research (`mrajaxnp/cert-insider-threat-detection-research`, Kaggle), 3,5M événements de connexion, recalibrés sur des horaires bancaires tunisiens réels.
- **PhishHunter** : dataset d'entraînement non présent dans ce dossier (163 700 emails mentionnés dans la documentation existante, non re-vérifié directement).
- **DarkWatch / CrisisBot** : aucun dataset — pas de modèle entraîné.

## API Endpoints

Voir le tableau "Agent-to-Agent Communication" ci-dessus pour les webhooks inter-agents. Endpoints principaux par agent :

- **DarkWatch** (`:8877`) : `/api/emails`, `/api/scan`, `/api/check`, `/api/reset`
- **NetScope** (`:8001`) : `/analyze`, `/webhook/traffic-event`, `/sample-traffic`, `/isolate`, `/health`
- **PhishHunter** (`:8002`) : `/analyze`, `/webhook/email`, `/emails`, `/emails/{id}`, `/emails/{id}/block`, `/agent/analyze/{id}`, `/seed-demo`, `/health`
- **Sentinel** (`:8003`) : `/api/cases`, `/api/analyze`, `/api/analyze-live`, `/api/webhook/signin-event`
- **CrisisBot** (`:8878`) : `/api/status`, `/api/simulate`, `/api/webhook/incident`

## Development / Demo Mode

`python launch_all.py --simulate` active `event_simulator.py`, qui envoie des événements factices aux 4 agents de détection (au même format que de vraies intégrations) pour qu'ils réagissent automatiquement et notifient CrisisBot — utile pour une démonstration sans dépendre d'un vrai système externe. Sans `--simulate`, aucun agent ne notifie CrisisBot tout seul.

Ce qui est simulé partout : les données d'entrée (emails, connexions, trafic DNS proviennent d'échantillons locaux, pas de vraies sources externes) et les actions de sortie (isolement de poste, reset de mot de passe, blocage d'email sont journalisés mais n'exécutent aucune action réelle sur un vrai système). Exception : la détection DarkWatch (vraie API XposedOrNot) et la notification Slack de CrisisBot (vrai message envoyé) sont réelles de bout en bout.

## Future Real Integrations

Points de branchement déjà préparés dans le code, non connectés faute d'accès à un vrai système pendant le stage :

- **Active Directory / Microsoft Graph** (DarkWatch) — `email_sources.py::from_active_directory()`.
- **SIEM / Entra ID sign-in logs** (Sentinel) — `/api/webhook/signin-event` déjà fonctionnel mécaniquement.
- **Exchange / Google Workspace** (PhishHunter) — `/webhook/email` déjà fonctionnel mécaniquement.
- **Firewall/Proxy DNS réel** (NetScope) — `auto_scan.py::_pick_one_row()` isolé pour faciliter le remplacement.

## Security Notes

- Chaque projet a son propre `.env.example` (placeholders uniquement) et `.gitignore` (exclut `.env`). Ne jamais committer un `.env` réel.
- Aucun dépôt Git local n'existe dans ce projet à ce jour — donc aucun secret n'a été poussé où que ce soit depuis cette machine.
- Toutes les actions "d'isolement" ou de "reset" sont simulées (journalisées, jamais exécutées sur un vrai système) — voir Demo Mode ci-dessus.
- Les webhooks entrants (NetScope, Sentinel) sont protégés par un secret partagé ; les échanges internes entre agents (`notify_crisisbot()`) et le webhook d'incident de CrisisBot utilisent le même principe best-effort simple que le reste de la démo, cohérent avec un environnement de test.

## Troubleshooting

- **Port déjà utilisé** : chaque agent affiche un message clair et une commande pour changer de port via variable d'environnement (ex. `CRISISBOT_PORT`).
- **Clé API manquante** : chaque agent continue de fonctionner en mode dégradé (règles simples ou message générique) plutôt que de planter.
- **`UnicodeEncodeError` sous Windows** : `launch_all.py` force `PYTHONUTF8=1` dans l'environnement des sous-process pour éviter les crashs liés aux accents/emoji dans les logs redirigés.
- **Webhook qui renvoie 401** : vérifie que le secret est bien envoyé comme paramètre d'URL (`?x_webhook_secret=...`), pas comme en-tête HTTP — un piège classique avec FastAPI.
- **Modèle introuvable** (NetScope) : place `netscope_model.pkl` et `netscope_features.pkl` dans `models/` (voir `models/README.md`).

## Project Status

| Component | Status |
|---|---|
| DarkWatch | Fonctionnel, détection réelle (API externe) |
| NetScope | Fonctionnel, ML réel entraîné et validé |
| PhishHunter | Fonctionnel, ML + agent LLM réels |
| Sentinel | Fonctionnel, ML réel entraîné et validé |
| CrisisBot | Fonctionnel, sortie Slack réelle |
| Intégrations bancaires réelles | Non connectées (hors périmètre du stage) |
| Présentation de soutenance (.pptx) | Non générée (contenu prêt, blocage technique) |
