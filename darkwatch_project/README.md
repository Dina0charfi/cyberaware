# DarkWatch (version gratuite)

Reproduction fonctionnelle de l'agent **DarkWatch** de la démo CyberAware
(Hydatis) : surveillance d'emails/domaines dans des fuites de données
publiées, avec alerte et recommandation d'action. Deux façons de
l'utiliser : en ligne de commande, ou avec un dashboard web.

Projet réalisé sans modèle de machine learning et sans dataset à
entraîner — voir la section *Architecture* ci-dessous, utile pour la
soutenance.

Trois façons de l'utiliser, du script au vrai agent autonome :

| | Manuel | Automatique |
|---|---|---|
| Ligne de commande | `darkwatch.py` | `agent.py` (tourne seul, en boucle) |
| Interface | `server.py` (clique sur "Scan") | — |

## Fichiers du projet

| Fichier | Rôle |
|---|---|
| `xon_api.py` | Client pour l'API gratuite XposedOrNot (partagé par tous) |
| `llm_summary.py` | Raisonnement IA : résumé (`generate_summary`) et **décision autonome** (`decide_action`), via Groq (gratuit) |
| `darkwatch.py` | Version CLI manuelle : vérifie une liste d'emails, ne signale que les nouvelles fuites |
| `risk_report.py` | Met en forme le rapport d'alerte pour la CLI |
| `agent.py` | **Le vrai agent autonome** : boucle perception → mémoire → décision → action, sans intervention humaine |
| `server.py` | Dashboard web : petit serveur local + API JSON |
| `index.html` | Interface visuelle façon CyberAware (cartes, alerte, bouton d'action) |
| `emails_example.txt` | Liste d'emails à surveiller (scénario banque) |
| `darkwatch_state.json` | Généré automatiquement — mémoire des fuites déjà vues |
| `agent_actions.log` | Généré par `agent.py` — journal de toutes les décisions prises |

## Installation

Aucune dépendance externe. Tout est écrit avec la bibliothèque standard
de Python 3.9+ (`urllib`, `http.server`, `json`, `pathlib`). Rien à
installer avec `pip`.

## Option 1 — Ligne de commande

```bash
python3 darkwatch.py --file emails_example.txt
```

Garde un historique (`darkwatch_state.json`) pour ne re-signaler une
fuite déjà vue. Adaptée à une exécution planifiée (cron, voir plus bas).

## Option 2 — Dashboard web (façon CyberAware)

```bash
python3 server.py
```

Puis ouvre **http://localhost:8000** dans un navigateur. Tu retrouves la
même mise en page que la démo : liste des comptes surveillés, bouton
"Lancer le scan dark web avec DarkWatch →", et en cas de fuite, une
alerte rouge avec le niveau de risque et un bouton "Forcer la
réinitialisation du mot de passe" (action simulée dans cette version
gratuite — à brancher sur un vrai AD/IAM en production).

`server.py` sert `index.html` et expose trois routes JSON : `/api/emails`
(liste des comptes), `/api/scan` (lance la vérification), `/api/reset`
(action simulée). Le front-end en JavaScript appelle ces routes — aucun
framework (pas de Flask, React, etc.), juste `http.server` côté serveur
et du JS natif côté navigateur.

Remarque : `emails_example.txt` contient des adresses `@banque-abc.example`
fictives (domaine réservé pour la documentation), donc aucune fuite ne
sera trouvée pour ces adresses précises — normal, c'est pour illustrer le
format. Remplace-les par de vraies adresses pour un vrai test.

## Option 3 — Agent autonome (le vrai "Agent IA")

`darkwatch.py` et `server.py` demandent une action humaine (lancer la
commande, cliquer sur "Scan"). `agent.py` non : une fois démarré, il
tourne seul et prend ses propres décisions. C'est la différence entre un
script et un agent, au sens propre du terme :

1. **Perception** — interroge XposedOrNot pour chaque email surveillé.
2. **Mémoire** — compare avec `darkwatch_state.json`, ignore le déjà-vu.
3. **Raisonnement** — si nouvelle fuite : le LLM (Groq) analyse les
   données et **choisit** une action (`reset_password`, `notify_only`,
   `escalate_ciso`, ou `ignore_false_positive`) — ce n'est pas juste un
   résumé, c'est une vraie décision structurée (JSON).
4. **Action** — exécute (simule) cette décision, et la journalise dans
   `agent_actions.log`.
5. Attend l'intervalle configuré, recommence tout seul.

```bash
# Une seule passe (pour tester/démontrer en live)
python3 agent.py --file emails_example.txt --once

# Boucle continue, vérifie toutes les heures, jusqu'à Ctrl+C
python3 agent.py --file emails_example.txt --interval 3600
```

Sans `GROQ_API_KEY` configurée, l'agent tourne quand même : le
raisonnement retombe sur des règles simples (score de risque → action),
donc l'autonomie ne dépend pas de l'IA générative, seule la finesse de
la décision en dépend. Ça permet de bien séparer, pour la soutenance,
ce qui relève de l'agentivité (boucle + décision + action) de ce qui
relève spécifiquement de l'IA générative (la qualité du raisonnement).

## Architecture — pourquoi aucun modèle ML n'est nécessaire

"Un email a-t-il fuité ?" est une recherche dans une base de données déjà
constituée, pas un problème de prédiction. Le projet s'appuie sur deux
endpoints gratuits et sans clé de l'API
[XposedOrNot](https://xposedornot.com/api_doc) :

1. **`/v1/check-email/{email}`** — dit si l'email apparaît dans une fuite
   connue, et laquelle.
2. **`/v1/breach-analytics?email={email}`** — donne un score de risque et
   le détail des données exposées. Ce score est calculé par XposedOrNot
   à partir de règles connues, pas par un modèle entraîné par nous.

La CLI garde un historique local pour ne jamais re-signaler une fuite
déjà vue. Le dashboard web n'est qu'une couche de présentation par-dessus
les mêmes fonctions (`xon_api.py`) — front-end et back-end existent ici
uniquement pour l'affichage, pas parce que la détection en aurait besoin.

### Couche IA générative (optionnelle) — pour la soutenance

Si l'encadrant attend une composante IA plus visible, `llm_summary.py`
ajoute un vrai résumé en langage naturel généré par un LLM gratuit
(Groq — inscription gratuite, sans carte bancaire). Elle est
**entièrement optionnelle** : sans configuration, tout le reste du
projet fonctionne normalement avec le rapport template.

**Configuration (variable d'environnement — rien n'est écrit en dur dans
le code) :**

1. Crée un compte gratuit sur [console.groq.com](https://console.groq.com)
   et génère une clé sur [console.groq.com/keys](https://console.groq.com/keys).
2. Configure la variable d'environnement `GROQ_API_KEY` :

   **PowerShell (Windows), pour la session en cours :**
   ```powershell
   $env:GROQ_API_KEY = "ta_clé_ici"
   py server.py
   ```
   Si tu fermes le terminal, il faut la retaper. Pour la rendre
   permanente : `setx GROQ_API_KEY "ta_clé_ici"` puis rouvrir un nouveau
   terminal.

   **macOS/Linux (bash/zsh) :**
   ```bash
   export GROQ_API_KEY="ta_clé_ici"
   python3 server.py
   ```

3. Relance `darkwatch.py` ou `server.py` : dès qu'une fuite est
   détectée, un résumé "🤖 Résumé IA (Groq)" apparaît en plus du rapport
   habituel, sur la CLI comme sur le dashboard web.

Aucun package à installer pour ça non plus : l'appel à Groq se fait avec
`urllib` (stdlib), pas de SDK externe.

## Limites connues (tier gratuit)

- Limite XposedOrNot : 2 requêtes/seconde, 100/jour par IP — suffisant
  pour quelques dizaines de comptes par jour, pas pour un domaine entier
  avec des milliers de comptes.
- Vérification par domaine entier (`/v1/domain-breaches`) : gratuite
  aussi, mais nécessite une clé API obtenue en prouvant la propriété du
  domaine — non utilisée ici car `banque-abc.example` est fictif.
- Couvre les fuites déjà indexées publiquement (comme HIBP). Le vrai
  scraping du dark web en temps réel (forums .onion, Telegram) est un
  chantier d'infrastructure séparé.

## Pour une surveillance automatique récurrente (CLI)

```bash
0 8 * * * cd /chemin/vers/le/projet && python3 darkwatch.py --file emails_example.txt >> darkwatch.log 2>&1
```
