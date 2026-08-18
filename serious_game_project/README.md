# Serious Game — Dans la peau de l'attaquant

Mini-jeu pédagogique : le joueur incarne un pentester qui teste des employés fictifs de « Banque ABC » avec différents vecteurs d'ingénierie sociale (phishing, QR code, WhatsApp, faux formulaire de gain). Chaque tentative renvoie vers l'agent CyberAware qui détecterait ce vecteur en conditions réelles.

> Chaque vecteur génère un vrai lien trackable (voir "Comment ça marche" ci-dessous) — le vecteur WhatsApp est envoyé automatiquement via GREEN API (voir "Envoyer un vrai message WhatsApp, automatiquement").

## Comment ça marche

- `targets.py` : 11 profils fictifs (score de risque, modules de formation complétés) et les 4 vecteurs d'attaque avec leur poids et leur lien vers l'agent concerné.
- Le résultat n'est **plus un tirage au sort** : chaque tentative envoie un vrai message simulé (`attempts.py`, `build_scenario_content`) contenant un vrai lien cliquable (`/track/<token>`). Trois façons réelles de résoudre une tentative :
  - **clicked** — le lien est réellement suivi (une vraie requête HTTP `GET /track/<token>` déclenchée par le navigateur) — le seul état qui compte comme une réussite pour le joueur/pentester.
  - **reported** — bouton "🚩 Signaler cette tentative" cliqué dans l'interface (meilleure réaction possible).
  - **ignored** — bouton "🙈 Ignorer sans agir" cliqué dans l'interface.
  - *(un 4e état, `opened`, existe dans le schéma pour une évolution future — pas encore atteignable par une action réelle.)*
- Tant qu'aucun de ces événements réels ne s'est produit, la tentative reste `pending` et ne compte dans aucune statistique — pas de résultat inventé en attendant.
- Le risque de la cible évolue après résolution selon l'action observée : `clicked` fait monter le risque de 6 points, `reported` le fait baisser de 6, `ignored` de 1 — toujours borné entre 5 et 95. `POST /api/campaign/reset` remet les risques à leur valeur de départ.
- Chaque tentative résolue est journalisée en mémoire (cible, vecteur, action, horodatage) — consultable via `GET /api/history/<target_id>`, et affichée directement dans le jeu (nombre de tentatives déjà faites contre une cible avec un vecteur donné, avant même d'attaquer).
- `llm_scenario.py` : rédige le texte qui accompagne le résultat via Groq, une fois l'action réelle connue. Le LLM ne décide jamais de l'action, il la raconte seulement — même principe que les autres agents CyberAware.
- `attempts.py` : gère les tentatives en attente, le contenu du message simulé par vecteur, et la finalisation d'une tentative.
- `mailer.py` : envoi optionnel d'un VRAI email (SMTP standard, aucune dépendance externe) quand une adresse réelle est fournie. Désactivé par défaut (aucune config requise) — si `SMTP_HOST`/`SMTP_USER`/`SMTP_PASSWORD` ne sont pas renseignés dans `.env`, le jeu reste en mode "affiché dans le navigateur uniquement".
- `server.py` : serveur `http.server` (aucune dépendance à installer), expose l'API, sert `static/index.html`, et affiche la page atterrissage réelle de `/track/<token>` quand le lien est suivi.
- Le compteur de campagne, les tentatives en attente et l'historique sont volontairement en mémoire, pas persistés : redémarrer le serveur repart à zéro.

## Envoyer un vrai email (optionnel)

Par défaut, le message simulé n'est affiché que dans le navigateur — le lien de tracking reste réel, mais rien ne part vers une vraie boîte mail. Pour tester avec un vrai envoi :

1. Dans `.env`, renseigne `SMTP_HOST`, `SMTP_USER`, `SMTP_PASSWORD` (voir `.env.example` pour la config Gmail avec un mot de passe d'application — jamais ton vrai mot de passe).
2. Redémarre le serveur.
3. Sur l'écran de sélection du vecteur, un champ "Envoyer un VRAI email à" apparaît — renseigne une adresse réelle (la tienne, par exemple) avant de choisir un vecteur.
4. Le message part vraiment. Il faut alors ouvrir cette boîte mail et cliquer sur le lien pour déclencher "clicked" — cliquer dans le jeu ne suffit plus dans ce cas.

Limite à connaître : le lien de tracking pointe par défaut vers `http://localhost:8880`, donc cliquable uniquement depuis la machine qui fait tourner le serveur. Pour qu'un vrai destinataire externe (téléphone, autre PC) puisse cliquer, il faut changer `SERIOUSGAME_PUBLIC_URL` dans `.env` pour l'IP locale du poste (même réseau Wi-Fi) ou une URL de tunnel.

## Envoyer un vrai message WhatsApp, automatiquement (optionnel)

Même principe que l'email, mais via **GREEN API** (`whatsapp.py`, appel HTTP direct, pas de SDK à installer) — ton propre téléphone (avec WhatsApp) sert de passerelle d'envoi, comme httpSMS le faisait pour le SMS. L'envoi est **entièrement automatique** : pas de lien à ouvrir ni de bouton "Envoyer" à cliquer toi-même, le message part directement quand la simulation est lancée.

1. Crée un compte sur https://console.green-api.com (email/Google).
2. Crée une instance (le plan gratuit "Developer" suffit pour tester).
3. Dans la console, scanne le QR code affiché avec l'appli WhatsApp de ton téléphone (Paramètres > Appareils liés > Lier un appareil) — ton numéro devient la passerelle d'envoi.
4. Récupère `idInstance` et `apiTokenInstance` dans la console.
5. Dans `.env`, renseigne `GREENAPI_ID_INSTANCE` et `GREENAPI_API_TOKEN` — voir `.env.example`.
6. Redémarre le serveur. Sur l'écran de sélection du vecteur, un champ "Envoyer un VRAI message WhatsApp à" apparaît — renseigne le numéro du destinataire (format international, ex. `+21612345678`).
7. Le message WhatsApp part vraiment et automatiquement depuis ton téléphone lié. Comme pour l'email, il faut alors que le destinataire ouvre le message reçu et suive le lien pour déclencher "clicked" — le lien de tracking doit donc être joignable depuis l'appareil qui reçoit le message (même limite `SERIOUSGAME_PUBLIC_URL` que ci-dessus : ngrok ou IP locale).

Ton téléphone doit rester allumé et connecté à internet (WhatsApp lié reste actif même appli fermée, comme WhatsApp Web) pour que les messages partent.

## Tester le vecteur QR code avec un vrai téléphone

Le vecteur `qrcode` affiche un vrai QR code scannable (généré via l'API publique `api.qrserver.com`, pas de dépendance à installer), qui encode le même lien `/track/<token>` que les autres vecteurs.

- **Depuis ce PC uniquement** (le plus simple) : lance le jeu normalement, choisis le vecteur QR code, et scanne l'image affichée avec l'appareil photo d'un téléphone connecté au **même réseau Wi-Fi** que ce PC. Par défaut le lien pointe vers `http://localhost:8880`, qui n'est donc **pas** joignable depuis un autre appareil — il faut l'étape suivante.
- **Pour que le téléphone puisse vraiment y accéder** :
  1. Trouve l'IP locale de ce PC sur le Wi-Fi : `ipconfig` (Windows), cherche "Adresse IPv4" sous l'adaptateur Wi-Fi (ex. `192.168.1.42`).
  2. Démarre le serveur avec cette IP :
     ```powershell
     $env:SERIOUSGAME_PUBLIC_URL = "http://192.168.1.42:8880"
     py server.py
     ```
  3. Ouvre le jeu depuis ce PC à `http://192.168.1.42:8880` (pas `localhost`), choisis le vecteur QR code, et scanne avec le téléphone (même Wi-Fi) — le scan déclenche un vrai `GET /track/<token>` et finalise la tentative à `clicked`.
  4. Si le pare-feu Windows bloque, autorise Python sur les réseaux privés quand la popup apparaît (ou autorise le port 8880 manuellement).

## Mode démo automatique (`launch_all.py --simulate`)

Lancé seul (`py server.py`), le jeu ne fait jamais rien tout seul — il faut
un humain qui choisit une cible et un vecteur dans le dashboard. Lancé via
`python launch_all.py --simulate` depuis la racine du projet, la variable
`SERIOUSGAME_AUTO_SIMULATE=1` démarre en plus une boucle en arrière-plan
(`auto_simulate.py`) qui joue toute seule : elle choisit une cible et un
vecteur au hasard, envoie la simulation, puis tranche le résultat via un
tirage pondéré sur la même probabilité indicative déjà affichée ailleurs
dans le jeu (`compute_success_probability`) — c'est le seul endroit de tout
le serious game où un résultat est tiré au sort plutôt que déduit d'un vrai
clic, et uniquement en mode démo. Une tentative est jouée toutes les ~20
secondes ; le détail de chaque tour est visible dans `_launch_logs/serious game.log`
à la racine du projet.

## Lancer le jeu

```bash
cd serious_game_project
cp .env.example .env   # optionnel : ajouter une clé Groq, et/ou une config SMTP pour un vrai envoi
python3 server.py
```

Puis ouvrir http://localhost:8880 (port dédié, distinct des 5 autres agents)

## API

| Méthode | Route | Rôle |
|---|---|---|
| GET | `/api/targets` | Liste des cibles, des vecteurs, et si l'envoi d'un vrai email est configuré |
| GET | `/api/campaign` | Stats de la campagne en cours |
| GET | `/api/history/<target_id>` | Historique et stats par vecteur pour une cible |
| GET | `/api/attempt/<token>` | État d'une tentative (`pending` ou résolue) — utilisé par l'interface pour détecter un clic réel dans un autre onglet |
| GET | `/track/<token>` | Le vrai lien envoyé dans la simulation — le suivre finalise la tentative à `clicked` et affiche une page pédagogique |
| POST | `/api/attack` | `{target_id, vector, real_email?, real_whatsapp?}` → crée une tentative en attente + le message simulé (envoie aussi un vrai email si `real_email` est fourni et SMTP configuré, ou un vrai message WhatsApp automatiquement si `real_whatsapp` est fourni et GREEN API configuré) |
| POST | `/api/resolve` | `{token, action}` avec `action` = `reported` ou `ignored` → finalise une tentative suite à un choix explicite (`clicked` ne peut venir que du vrai lien) |
| POST | `/api/campaign/reset` | Remet le compteur, les tentatives en attente, les risques et l'historique à zéro |

## Brancher de vraies données plus tard

Les profils de `targets.py` sont fictifs. Pour les remplacer par de vraies données de formation, il suffit d'alimenter `TARGETS` (mêmes clés : `id`, `name`, `dept`, `risk`, `modules_done`, `modules_total`) depuis une vraie plateforme de sensibilisation (LMS) — le reste du jeu (contenu du message, tracking du lien, narration) n'a pas besoin de changer.

Pour aller plus loin vers une vraie campagne (au lieu d'un lien affiché dans l'interface), il suffirait d'envoyer le contenu de `build_scenario_content()` par un vrai canal (email via SMTP/Graph, WhatsApp...) à une vraie adresse — le mécanisme de tracking (`/track/<token>`) resterait identique.
