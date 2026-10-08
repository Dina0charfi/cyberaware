# Journal de stage — CyberAware @ Hydatis — Reconstruction honnête

**⚠️ Note méthodologique — à lire avant utilisation**

Ce document a été reconstruit à partir de trois sources uniquement :
1. Cette conversation (avant et après un résumé automatique de compaction).
2. Une ancienne session Cowork locale intitulée « DarkWatch data breach monitoring » (lue intégralement).
3. L'historique Git réel du dépôt `Cyberaware` (`.git/logs/HEAD` et confirmé par `git log`/`git ls-tree` exécutés par Dina), qui donne 2 horodatages **objectifs et vérifiables** : le **14 août 2026** (11:28, confirmé par `git log`) et le 17 août 2026.

Une deuxième ancienne session (« Project overview ») a été vérifiée et écartée : elle concerne un projet Django sans rapport (« Dep'Art »), aucune mention de CyberAware.

**Aucune preuve n'a été trouvée pour la période du 6 juillet à début août 2026.** Je n'ai pas accès à tes conversations Claude.ai (web/mobile) antérieures à l'usage de Cowork — seulement aux sessions locales de cet ordinateur. Cette zone reste donc **« Date à confirmer »**, à compléter par toi.

**Contradiction à signaler** : la période de stage indiquée se termine le 21 août 2026, mais une partie importante du travail documenté ci-dessous (système d'authentification, intégration DNS réelle, démo téléphone) porte des indices temporels (horodatages de fichiers, contexte système) situés **entre le 21 et le 27 août 2026** — donc après la date de fin annoncée. Je ne choisis pas arbitrairement une date : à toi de vérifier si le stage a été prolongé ou si la période exacte est différente.

---

## Tableau chronologique

| Date | Catégorie | Activité | Détails techniques | Résultat |
|---|---|---|---|---|
| Date à confirmer (avant mi-août 2026) | 🟢 RÉALISÉ | Développement d'un script en ligne de commande de vérification de fuites de données pour DarkWatch | Fichier initial `darkwatch_free.py`, puis restructuré en modules séparés : `xon_api.py` (client API partagé), `darkwatch.py` (CLI), `risk_report.py` (calcul du score de risque), utilisant l'API publique et gratuite **XposedOrNot** (sans clé requise) | Exécution confirmée en terminal (`py darkwatch.py --file emails_example.txt`), sortie réelle obtenue |
| Date à confirmer | 🟢 RÉALISÉ | Construction d'un tableau de bord web pour DarkWatch | `server.py` (Python stdlib `http.server`, sans framework) + `index.html` (JS natif), bouton « Lancer le scan » + zone de vérification rapide d'une adresse email | Dashboard fonctionnel confirmé sur `http://localhost:8877` |
| Date à confirmer | 🟢 RÉALISÉ | Test réel du pipeline de détection avec une adresse email personnelle | Vérification de `dcharfi2005@gmail.com` via l'API XposedOrNot | Une fuite réelle authentique détectée (Wattpad), score de risque calculé : 36/100 (« Modéré ») |
| Date à confirmer | 🟢 RÉALISÉ | Intégration d'une couche d'explication en langage naturel | Nouveau fichier `llm_summary.py`, appel à l'**API Groq (Llama 3.3)**, branché à la fois sur le CLI et le dashboard | Fonctionnel après correction d'un bug (voir tableau des bugs) |
| Date à confirmer | 🟢 RÉALISÉ (développement — test d'exécution non confirmé dans les échanges consultés) | Écriture d'un agent autonome pour DarkWatch | `agent.py` : boucle perception → décision (LLM) → action → journalisation dans `agent_actions.log`, modes `--once` et `--interval 3600` | Code livré ; aucune trace d'exécution/validation dans la conversation source — à vérifier par Dina |
| **14 août 2026** *(horodatage Git confirmé : `git log`, 11:28)* | 🟢 RÉALISÉ | Initialisation du dépôt Git du projet CyberAware | Premier commit (« Initial commit — CyberAware »), renommage de la branche `master` en `main`, fusion d'un README distant | Dépôt Git local opérationnel |
| **14 août 2026** *(horodatage Git réel)* | 🟢 RÉALISÉ | Ajout d'un simulateur d'événements | Fichier `event_simulator.py` ajouté au dépôt | Commit confirmé |
| **14 août 2026** *(vérifié par `git ls-tree -r HEAD`)* | 🟢 RÉALISÉ (précision importante) | Push des fichiers de configuration du modèle PhishHunter — **pas le modèle entraîné lui-même** | Suivis par Git : `.gitkeep`, `phishhunter_feature_names.json`, `phishhunter_known_brands.json`. Les poids réels du modèle (`.pkl` régression logistique, `.npy` embeddings Word2Vec) restent exclus par `phishhunter_project/.gitignore` (`*.pkl`, `*.model`, `*.npy`) et ne sont PAS suivis par Git, à aucun moment | Confirme la conclusion initiale de l'audit de portabilité : un nouveau collaborateur doit obtenir les fichiers modèle PhishHunter manuellement, seule leur configuration (features, marques connues) est versionnée |
| **17 août 2026** *(horodatage Git réel)* | 🟢 RÉALISÉ | Mise à jour majeure des 5 agents + ajout du Serious Game | Modifications sur les 5 agents existants, ajout de `serious_game_project`, ajout d'une page « Formation à la cybersécurité », ajout de 4 vidéos de sensibilisation | Commit confirmé (« modification les 5 agents + ajout seriousgame + page de formation... ») |
| Semaine du 18 au 27 août 2026 (regroupé — granularité jour par jour non disponible) | 🟢 RÉALISÉ | Correction d'un bug du vecteur « loterie » (Serious Game) | Le lien envoyé pointait directement vers `/track/<token>` (résolution immédiate), au lieu de `/claim/<token>` (faux formulaire de collecte prévu). Correction dans `attempts.py::start_attempt()` avec condition spécifique au vecteur `loterie` | Le lien mène désormais réellement au faux formulaire avant résolution de la tentative |
| Semaine du 18 au 27 août 2026 | 🟢 RÉALISÉ | Correction d'un bug d'affichage CSS sur le dashboard DarkWatch | Un `padding` hérité sur `body` entrait en conflit avec la disposition en sidebar (`cwsb-shell`) ajoutée depuis, causant un contenu mal positionné. Déplacement du padding vers la classe `.wrap` | Mise en page corrigée, vérifiée par comparaison avec `crisisbot_project/index.html` |
| Semaine du 18 au 27 août 2026 | 🔵 ANALYSÉ | Audit de portabilité du projet (« un nouveau collaborateur peut-il tout faire fonctionner ? ») | Vérification manuelle de chaque sous-projet, des dépendances et de la configuration | Un blocage réel identifié (modèles de PhishHunter exclus par `.gitignore`, à obtenir manuellement) + 2 lacunes de documentation mineures (README manquant pour Sentinel, mention obsolète dans le README racine) |
| Semaine du 18 au 27 août 2026 | 🟢 RÉALISÉ | Mise en ligne du dépôt sur GitLab interne | Résolution d'un conflit de remote déjà existant, push effectif de la branche `cyberaware-init` ; configuration du jeton d'authentification ngrok | Dépôt accessible sur GitLab interne Hydatis |
| Semaine du 18 au 27 août 2026 | 🟢 RÉALISÉ | Réentraînement continu du modèle Isolation Forest de Sentinel, avec gestion explicite de la concurrence | Structure `ModelState` (namedtuple immuable) échangée par réassignation atomique ; verrou non-bloquant (`Lock.acquire(blocking=False)`) empêchant deux réentraînements simultanés ; worker unique en arrière-plan au lieu d'un thread par requête | Lecture de scoring jamais bloquée sous forte charge (conception validée par relecture de code ; exécution non testée faute d'environnement disponible côté assistant — à valider manuellement) |
| Semaine du 18 au 27 août 2026 | 🟢 RÉALISÉ | Système d'authentification partagé (login/logout) entre les 6 agents + page d'accueil | `auth.py` dupliqué à l'identique dans 7 emplacements ; sessions sans état côté serveur (cookie signé HMAC-SHA256) ; cookie « host-only » partagé entre les ports (pas d'attribut Domain) ; activation optionnelle via `CYBERAWARE_AUTH_ENABLED` | Connexion unique authentifiant les 6 dashboards, activable/désactivable sans changer le comportement par défaut |
| Semaine du 18 au 27 août 2026 | 🟢 RÉALISÉ | Passage du formulaire de connexion à email + mot de passe, avec journalisation | Champ email (au lieu d'un identifiant générique) ; journalisation JSON Lines de chaque connexion (`login_history.jsonl`) ; transmission de chaque connexion réelle au webhook `/api/webhook/signin-event` de Sentinel pour scoring réel | Historique de connexions centralisé, exploitable par Sentinel |
| Semaine du 18 au 27 août 2026 | 🟢 RÉALISÉ (bug critique corrigé) | Diagnostic et correction d'un bug bloquant totalement la connexion | Le cookie de session utilisait `"."` comme séparateur (email.expiration.signature), mais l'email par défaut (`admin@cyberaware.local`) contient lui-même un point, cassant le découpage `split(".")` → vérification systématiquement en échec malgré des identifiants corrects. Corrigé par `rsplit(".", 2)` dans les 7 copies de `auth.py` | Connexion vérifiée fonctionnelle après correction et redémarrage — diagnostiqué en observant l'écran en direct avec Dina |
| Semaine du 18 au 27 août 2026 | 🟢 RÉALISÉ | Remplacement de la démonstration NetScope par un flux DNS réel | Nouveau module `live_feed.py` : mélange de domaines légitimes réels, domaines générés façon DGA, et un vrai domaine malveillant actif récupéré depuis le flux public **URLhaus (abuse.ch)** ; résolution DNS réelle via `dnspython` (`live_features.py`) au lieu de lire `sample_traffic.csv` (features pré-calculées, noms factices) | `/sample-traffic` et `auto_scan.py` interrogent désormais de vrais domaines en temps réel |
| Semaine du 18 au 27 août 2026 | 🟢 RÉALISÉ | Construction d'un « tap » DNS réel pour démonstration live (téléphone) | `dns_proxy.py` (serveur DNS local relayant vers 8.8.8.8, journalise chaque domaine interrogé) + `tail_bridge.py` (surveillance en direct du fichier de log façon `tail -f`, transmission au webhook réel de NetScope) | Testé en conditions réelles avec un téléphone (DNS pointé vers le PC) — domaines visités confirmés visibles dans les terminaux |
| Semaine du 18 au 27 août 2026 | 🟢 RÉALISÉ | Panneau « Trafic en direct » sur le dashboard NetScope | Endpoint `/live-feed` (historique en mémoire des 30 derniers événements webhook) ; sondage JavaScript toutes les 2 secondes ; lignes cliquables affichant le détail (score, facteurs SHAP, profil de risque humain corrélé) | Fonctionnel après rechargement forcé du navigateur (problème de cache initial, résolu) |
| Semaine du 18 au 27 août 2026 | 🔵 ANALYSÉ | Révision technique approfondie de NetScope, PhishHunter et Sentinel en vue de la soutenance orale | Relecture fonction par fonction des algorithmes (LightGBM+SHAP, Word2Vec+régression logistique, Isolation Forest) et du principe « le score/la règle décide, le LLM explique seulement » | Préparation à la soutenance, pas de modification de code associée |

---

## Bugs réellement rencontrés et corrigés

| # | Problème | Cause | Solution appliquée | Vérification |
|---|---|---|---|---|
| 1 | `HTTP Error 429: Too Many Requests` sur l'API XposedOrNot | Quota gratuit dépassé (25 req/h, 100/jour) à force de tests répétés | Gestion d'erreur ajoutée (`xon_api.py`/`server.py`), message « Quota gratuit dépassé » affiché au lieu de planter | Non re-testé explicitement après coup dans la conversation source |
| 2 | `PermissionError [WinError 10013]` en ouvrant le port 8000 | Port réservé par Windows (Hyper-V/WSL) | Port par défaut changé pour 8877, configurable via `DARKWATCH_PORT` | Confirmé — bind réussi sur 8877 |
| 3 | `HTTP Error 403: Forbidden` sur l'appel à l'API Groq | User-Agent par défaut de `urllib` bloqué par Cloudflare | Ajout d'un User-Agent personnalisé dans `llm_summary.py` | Confirmé fonctionnel par Dina (« oki ca marcheee ») |
| 4 | Lien du vecteur « loterie » (Serious Game) menait directement à la page de résultat | `/track/<token>` utilisé au lieu de `/claim/<token>` pour ce vecteur spécifique, sautant le faux formulaire | Condition ajoutée dans `attempts.py::start_attempt()` selon le vecteur | Vérifié par lecture du code (`server.py`) confirmant le comportement attendu de `/claim/<token>` |
| 5 | Import manquant de `parse_qs` dans `crisisbot_project/server.py` et `serious_game_project/server.py` | Seul `urlparse` était importé, pas `parse_qs`, alors que le code de connexion l'utilisait | Import corrigé (`from urllib.parse import urlparse, parse_qs`) | Vérifié par relecture de code |
| 6 | Conception initiale du réentraînement Sentinel présentant un risque de blocage sous forte charge | `threading.Event` avec `.is_set()` + `.set()` non atomiques, un thread créé par requête (risque de saturation) | Conception entièrement revue : `ModelState` immuable + verrou non-bloquant + worker unique | Revue de conception uniquement, non exécutée en environnement réel |
| 7 | **Connexion impossible malgré des identifiants corrects** | Cookie de session basé sur un séparateur `"."`, cassé par la présence d'un point dans l'email par défaut (`admin@cyberaware.local`) | `split(".")` remplacé par `rsplit(".", 2)` dans les 7 copies de `auth.py` | Confirmé fonctionnel par Dina après redémarrage |
| 8 | Bloc CSS mal positionné sur le dashboard DarkWatch | `padding` hérité sur `body`, en conflit avec la nouvelle disposition sidebar | Padding déplacé vers `.wrap` | Vérifié par comparaison avec un autre agent au pattern correct |

---

## A. Activités réellement réalisées (liste exhaustive)

- Script CLI + dashboard web DarkWatch, utilisant l'API gratuite XposedOrNot (pas HIBP, payante — écartée)
- Test réel positif de détection de fuite avec une adresse email personnelle
- Intégration d'explications en langage naturel via l'API Groq (Llama 3.3) pour DarkWatch
- Écriture de `agent.py` (boucle autonome DarkWatch) — code livré, exécution non confirmée
- Initialisation et mise en ligne du dépôt Git/GitLab du projet CyberAware
- Ajout du simulateur d'événements (`event_simulator.py`)
- Push des fichiers de configuration du modèle PhishHunter (`.gitkeep`, listes de features/marques connues) — le modèle entraîné lui-même reste exclu du dépôt (`.gitignore`)
- Ajout du Serious Game, de la page de formation et de 4 vidéos de sensibilisation
- Correction du bug du vecteur « loterie » du Serious Game
- Correction du bug CSS du dashboard DarkWatch
- Audit de portabilité du projet (dépendances, `.gitignore`, documentation)
- Réentraînement continu et thread-safe du modèle Isolation Forest de Sentinel
- Système d'authentification partagé (login/logout) sur les 6 agents + page d'accueil
- Passage à une authentification par email + mot de passe, avec journal de connexions
- Correction du bug critique de parsing du cookie de session
- Remplacement du flux de démonstration NetScope par une résolution DNS réelle + flux de menaces réel (URLhaus)
- Construction d'un proxy DNS local + pont de surveillance de log pour démonstration téléphone en direct
- Panneau de trafic en direct sur le dashboard NetScope, avec détail cliquable

## B. Activités seulement conçues / envisagées (discutées mais non développées)

- Intégration de **dnstap** (protocole réel de journalisation DNS des résolveurs comme BIND/Unbound), évoquée par l'encadrant comme approche de production — seule une alternative plus simple (proxy DNS + tail de log) a été réellement construite
- Vrai scraping continu du dark web (Tor, forums `.onion`, Telegram) avec classification NLP pour DarkWatch — discuté comme contexte/comparaison (DarkOwl, Recorded Future, Flare), jamais implémenté
- Affichage sur PhishHunter des derniers emails envoyés à l'adresse email connectée — identifié comme non réalisable en l'état (le stockage actuel n'a pas de champ destinataire), pistes proposées mais non développées
- Rendre `GROQ_API_KEY` permanent plutôt que défini par variable d'environnement de session — proposé, non mis en œuvre dans les échanges consultés

## C. Activités explicitement non réalisées

- Aucune connexion réelle à **Microsoft Graph**
- Aucune connexion réelle à un **Active Directory / Entra ID** réel
- Aucune connexion réelle à un **SIEM** ou un **firewall** commercial (Fortinet, PaloAlto…)
- Aucune intégration payante à **Have I Been Pwned** (écartée au profit d'XposedOrNot, gratuite)

---

## Ce qu'il te reste à faire

1. **Combler juillet → début août** : soit tu retrouves tes conversations Claude.ai (export ou copier-coller) et je les analyse avec la même rigueur, soit tu me donnes de mémoire un résumé semaine par semaine que je formaliserai en te citant comme source.
2. **Clarifier la date de fin réelle du stage** (21 août annoncé vs indices allant jusqu'au 27 août).
3. **Vérifier par toi-même** les deux points marqués « non testé/à valider » (le réentraînement Sentinel sous charge réelle, et `agent.py` de DarkWatch) avant de les présenter comme pleinement opérationnels dans un rapport officiel.
