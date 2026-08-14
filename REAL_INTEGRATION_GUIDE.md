# Guide de branchement réel — de la démo aux vraies sources de données

Ce document répond à une seule question, agent par agent : **qu'est-ce qu'il faut concrètement pour remplacer les données simulées par de vraies données** (annuaire d'entreprise, boîte mail, SIEM, trafic DNS réel) ?

Pour chaque agent : ce qui existe déjà dans le code (le point de branchement préparé), ce qu'il faut mettre en place côté système externe, et le niveau d'effort réaliste. Rien ici n'est branché aujourd'hui — c'est un plan, pas un état actuel.

---

## 1. DarkWatch → Active Directory / Microsoft Entra ID

**Ce qui existe déjà** : `email_sources.py` centralise la récupération de la liste des comptes à surveiller derrière une seule fonction, `get_monitored_emails()`. Le mode par défaut (`from_file()`) lit un fichier texte statique. Un second mode, `from_active_directory()`, est déjà écrit en squelette mais lève volontairement `NotImplementedError` tant qu'il n'est pas connecté.

**Ce qu'il faut côté Microsoft Entra ID** :
1. Enregistrer une application dans le portail Azure (Entra ID → Inscriptions d'applications).
2. Lui accorder la permission API `User.Read.All` (application, pas déléguée — le script tourne sans utilisateur connecté).
3. Obtenir le **consentement administrateur** sur cette permission (une action que seul un admin IT de la banque peut faire).
4. Récupérer `tenant_id`, `client_id`, `client_secret` (ou, mieux, un certificat plutôt qu'un secret pour la production).

**Ce qu'il faut coder** : implémenter `from_active_directory()` avec un appel `GET https://graph.microsoft.com/v1.0/users` (authentifié via le flow OAuth2 *client credentials*, adapté aux appels machine-à-machine sans utilisateur), puis filtrer sur le département ou le groupe pertinent plutôt que de récupérer tous les comptes de l'entreprise.

**Variables d'environnement à ajouter** : `AZURE_TENANT_ID`, `AZURE_CLIENT_ID`, `AZURE_CLIENT_SECRET`, `DARKWATCH_EMAIL_SOURCE=active_directory`.

**Effort réaliste** : faible côté code (une fonction à écrire, l'architecture est déjà prête) — le vrai obstacle est administratif : obtenir l'inscription d'application et le consentement admin dans le tenant de l'entreprise.

---

## 2. NetScope → Firewall / Proxy réel (Fortinet, Palo Alto, ou SIEM)

**Ce qui existe déjà**, deux mécanismes en parallèle, tous deux fonctionnels mécaniquement :
- `POST /webhook/traffic-event` — un vrai point d'entrée HTTP, protégé par un secret partagé (`NETSCOPE_WEBHOOK_SECRET`), qui accepte soit des features déjà calculées, soit un simple nom de domaine (les features sont alors calculées en direct par `live_features.py`, avec une vraie résolution DNS).
- `auto_scan.py::_pick_one_row()` — la boucle interne, qui pioche aujourd'hui une ligne dans un CSV local (`sample_traffic.csv`). C'est la **seule fonction à remplacer** pour brancher un vrai flux en mode pull.

**Ce qu'il faut côté infrastructure réseau** :
- **Option push** (recommandée) : configurer le firewall/proxy (Fortinet FortiGate, Palo Alto, ou le SIEM qui centralise déjà les logs DNS) pour envoyer un `POST` vers `http://<serveur>:8001/webhook/traffic-event?x_webhook_secret=...` à chaque requête DNS sortante jugée pertinente. La plupart des firewalls d'entreprise supportent l'envoi de logs vers un webhook HTTP personnalisé, ou passent par un SIEM (Splunk, QRadar, Microsoft Sentinel) qui peut lui-même déclencher ce webhook via une règle de corrélation.
- **Option pull** : remplacer `_pick_one_row()` par une requête vers l'API du SIEM (ex. Splunk REST API, ou Microsoft Sentinel Log Analytics query) qui retourne les dernières requêtes DNS suspectes.

**Variables d'environnement à ajouter** : `NETSCOPE_WEBHOOK_SECRET` (déjà présent, juste à définir avec une vraie valeur avant toute exposition réseau réelle — la valeur par défaut actuelle est un placeholder explicite).

**Effort réaliste** : faible côté code. L'essentiel du travail est côté équipe réseau/SOC de la banque, pour configurer l'envoi des logs DNS vers ce webhook.

---

## 3. PhishHunter → Exchange Online / Google Workspace

**Ce qui existe déjà** : `POST /webhook/email` est un vrai point d'entrée HTTP fonctionnel, actuellement alimenté par `event_simulator.py`.

**Ce qu'il faut côté Microsoft 365 (le cas le plus probable pour une banque)** :
1. Enregistrer une application Azure (comme pour DarkWatch), avec la permission `Mail.Read` (application).
2. Créer un **abonnement Microsoft Graph** (`POST /subscriptions`) sur la ressource `me/mailFolders('Inbox')/messages`, avec `notificationUrl` pointant vers `/webhook/email`.
3. Gérer la **requête de validation initiale** : à la création de l'abonnement, Graph envoie un `validationToken` en paramètre d'URL, que le endpoint doit renvoyer tel quel en texte brut sous 10 secondes — ce n'est pas encore géré dans le code actuel, c'est la première chose à ajouter.
4. Gérer le **renouvellement périodique** de l'abonnement (Microsoft Graph expire les abonnements mail après environ 3 jours maximum) — nécessite une tâche planifiée qui rappelle `PATCH /subscriptions/{id}` avant expiration.
5. Adapter le parsing : Graph n'envoie pas le contenu de l'email dans la notification (juste un ID) — il faut un second appel `GET /messages/{id}` pour récupérer le contenu réel.

**Pour Google Workspace**, l'équivalent est Gmail API + Google Cloud Pub/Sub (`users.watch()`), avec une logique de renouvellement similaire (abonnement expirant sous 7 jours).

**Variables d'environnement à ajouter** : `AZURE_TENANT_ID`, `AZURE_CLIENT_ID`, `AZURE_CLIENT_SECRET` (ou `GOOGLE_SERVICE_ACCOUNT_JSON` pour Workspace).

**Effort réaliste** : moyen. Le endpoint existe, mais la validation Graph, le renouvellement d'abonnement et le second appel pour récupérer le contenu sont trois briques à ajouter, pas juste une clé à configurer.

---

## 4. Sentinel → SIEM / Microsoft Entra ID (logs de connexion)

**Point important déjà vérifié pendant le stage** : les **logs de connexion (sign-in) de Microsoft Graph ne supportent pas nativement les webhooks** — contrairement aux emails, Graph ne peut pas pousser un événement de connexion en temps réel vers un endpoint externe.

**Ce qui existe déjà** : `POST /api/webhook/signin-event` est un vrai point d'entrée fonctionnel, avec la poignée de main de validation déjà gérée. C'est la couche réception qui est prête — il manque la source qui l'alimenterait en vrai.

**Deux options réalistes côté branchement** :
- **Polling périodique** : interroger `GET /auditLogs/signIns` (permission `AuditLog.Read.All`) toutes les X minutes, et pousser chaque nouvelle connexion vers `/api/webhook/signin-event` soi-même (un petit script relais, pas une modification de Sentinel).
- **Relais SIEM** (option la plus réaliste en contexte bancaire) : le SIEM de la banque (déjà connecté à Entra ID) relaie les événements de connexion suspects vers ce webhook via une règle de corrélation — une banque ne donnerait vraisemblablement pas un accès Graph direct à un stagiaire ou à un système externe non audité.

**Variables d'environnement à ajouter** : `SENTINEL_WEBHOOK_SECRET` (déjà présent, à définir) ; `AZURE_TENANT_ID` / `AZURE_CLIENT_ID` / `AZURE_CLIENT_SECRET` uniquement si l'option polling est choisie.

**Effort réaliste** : faible côté code si le SIEM relaie déjà (juste pointer la règle de corrélation vers le webhook) ; moyen si un script de polling doit être écrit.

---

## 5. CrisisBot → Teams et Email (Slack est déjà réel)

**Ce qui existe déjà** : Slack fonctionne réellement (`notifications.py`, Incoming Webhook), sur un schéma directement réutilisable pour les deux prochaines cibles. Teams et Email sont prévus dans l'interface et peuvent être ajoutés sur le même modèle.

**Teams — ce qu'il faut** : créer un **Incoming Webhook** sur le canal Teams cible (Connecteurs du canal → Incoming Webhook), qui donne une URL similaire à celle de Slack. Le format du message diffère (Teams attend une "Adaptive Card" JSON, pas le format `blocks` de Slack) mais le principe est identique à `notifications.py::send_slack_notification()` — une fonction `send_teams_notification()` du même type suffirait.

**Email — ce qu'il faut** : soit un compte SMTP dédié (le plus simple, `smtplib` de la bibliothèque standard suffit, cohérent avec la philosophie "zéro dépendance" de CrisisBot), soit l'API Microsoft Graph `sendMail` si on veut rester dans l'écosystème 365 déjà utilisé ailleurs.

**Variables d'environnement à ajouter** : `TEAMS_WEBHOOK_URL` ; `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD` (ou les identifiants Graph si cette voie est choisie).

**Effort réaliste** : faible pour Teams (même schéma que Slack, déjà maîtrisé dans le code) ; faible à moyen pour Email selon l'option choisie.

---

## Résumé — effort par intégration

| Intégration | Code déjà prêt | Obstacle principal | Effort |
|---|---|---|---|
| DarkWatch → Entra ID | Squelette présent | Consentement admin Azure | Faible (admin) |
| NetScope → Firewall/SIEM | Deux mécanismes prêts | Configuration réseau côté SOC | Faible |
| PhishHunter → Exchange/Gmail | Webhook présent | Validation Graph + renouvellement d'abonnement | Moyen |
| Sentinel → SIEM/Entra ID | Webhook présent | Graph ne supporte pas le push nativement | Faible à moyen |
| CrisisBot → Teams | Rien (à écrire) | Aucun, juste à coder | Faible |
| CrisisBot → Email | Rien (à écrire) | Aucun, juste à coder | Faible |

Aucune de ces intégrations n'a été activée pendant le stage, faute d'accès à un vrai tenant Microsoft 365 ou à un vrai SIEM d'entreprise — ce tableau documente ce qu'il faudrait faire, pas ce qui a été fait.
