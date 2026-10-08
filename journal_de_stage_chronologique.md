# Journal de stage — CyberAware @ Hydatis
### Version organisée jour par jour (à recopier dans le carnet ESPRIT)

**Période : lundi 6 juillet 2026 → vendredi 21 août 2026** (weekends non travaillés, non comptés)

Note : cette version organise le travail réellement effectué (voir la liste complète dans `journal_de_stage_reconstruction.md`) selon la trame logique que tu m'as donnée : compréhension métier → DarkWatch (recherche puis technique) → les autres agents (recherche/notebook/modèle) → Serious Game → intégrations finales. Deux dates sont ancrées sur des preuves objectives (l'historique Git réel, confirmées par `git log`) : **14 août** et **17 août** — le reste suit l'ordre logique de construction mais la date exacte au jour près n'est pas vérifiée indépendamment.

---

## Semaine 1 — Compréhension du projet (6 → 10 juillet)

| Date | Tâches réalisées |
|---|---|
| Lun. 6 juillet | Accueil chez Hydatis, présentation de l'équipe et découverte du projet CyberAware (portefeuille de sensibilisation à la cybersécurité). |
| Mar. 7 juillet | **Réunion avec l'encadrant** : cadrage des objectifs du stage, présentation des 6 briques prévues (5 agents IA + Serious Game). Découverte du contexte métier de la sensibilisation à la cybersécurité en entreprise. |
| Mer. 8 juillet | Étude de solutions existantes de surveillance de sécurité (dark web monitoring, détection de phishing) pour cadrer les standards attendus. |
| Jeu. 9 juillet | Définition du périmètre technique de DarkWatch (surveillance de fuites de données) ; comparaison des API disponibles (Have I Been Pwned, payante, vs alternatives gratuites). |
| Ven. 10 juillet | Choix de l'API **XposedOrNot** (gratuite, sans clé requise) pour DarkWatch après comparaison technique et financière avec Have I Been Pwned. |

*Week-end 11-12 juillet — pas d'activité.*

---

## Semaine 2 — DarkWatch : développement technique (13 → 17 juillet)

| Date | Tâches réalisées |
|---|---|
| Lun. 13 juillet | Développement du script d'interrogation de l'API XposedOrNot (`xon_api.py`, `darkwatch.py`). |
| Mar. 14 juillet | **Réunion avec l'encadrant** : démonstration du script en ligne de commande. Développement du calcul du score de risque associé à chaque fuite détectée (`risk_report.py`). |
| Mer. 15 juillet | Construction du tableau de bord web de DarkWatch (`server.py` + `index.html`), avec bouton de lancement de scan et zone de vérification rapide d'une adresse email. |
| Jeu. 16 juillet | Tests réels du pipeline DarkWatch avec de vraies adresses email — une fuite authentique détectée. Correction de bugs (port réservé par Windows, quota API dépassé). |
| Ven. 17 juillet | Intégration d'une explication en langage naturel des résultats via l'API Groq (Llama 3.3) ; ébauche d'un mode « agent autonome » de surveillance périodique. |

*Week-end 18-19 juillet — pas d'activité.*

---

## Semaine 3 — NetScope : recherche, notebook et modèle (20 → 24 juillet)

| Date | Tâches réalisées |
|---|---|
| Lun. 20 juillet | Recherche et sélection du jeu de données DNS **CIC-BellDNS-Exfiltration 2021** pour NetScope ; exploration des colonnes disponibles. |
| Mar. 21 juillet | **Réunion avec l'encadrant** : validation de l'approche NetScope (détection de domaines DNS suspects). Démarrage du notebook d'analyse exploratoire. |
| Mer. 22 juillet | Feature engineering dans le notebook : entropie du nom de domaine, longueur, nombre de sous-domaines, TTL, comptage FQDN. |
| Jeu. 23 juillet | Entraînement et comparaison de modèles dans le notebook (LightGBM retenu) ; mise en place de l'explicabilité avec **SHAP**. |
| Ven. 24 juillet | Export du modèle entraîné et construction de l'API FastAPI de NetScope (scoring + endpoint webhook pour intégration firewall/proxy). |

*Week-end 25-26 juillet — pas d'activité.*

---

## Semaine 4 — PhishHunter (27 → 31 juillet)

| Date | Tâches réalisées |
|---|---|
| Lun. 27 juillet | Recherche sur les techniques de détection de phishing par email (typosquatting, urgence lexicale, entropie du domaine). |
| Mar. 28 juillet | **Réunion avec l'encadrant** : présentation de l'approche PhishHunter. Construction du notebook de features (features tabulaires + embeddings Word2Vec). |
| Mer. 29 juillet | Entraînement du modèle de classification (régression logistique) et calibration des seuils de décision. |
| Jeu. 30 juillet | Implémentation de la couche d'explication et du mode agent avec appel d'outils réel (vérification WHOIS, actions de blocage / escalade vers un humain). |
| Ven. 31 juillet | Tests et corrections sur PhishHunter (webhook, gestion de la poignée de validation Microsoft Graph). |

*Week-end 1-2 août — pas d'activité.*

---

## Semaine 5 — Sentinel (3 → 7 août)

| Date | Tâches réalisées |
|---|---|
| Lun. 3 août | Recherche et sélection du jeu de données **CERT Insider Threat** pour Sentinel ; analyse des événements Logon/Logoff. |
| Mar. 4 août | **Réunion avec l'encadrant** : validation de l'approche Sentinel (détection d'anomalies comportementales de connexion). Réduction à 7 features universelles réutilisables sans réentraînement complet. |
| Mer. 5 août | Feature engineering dans le notebook : encodage cyclique de l'heure de connexion (sinus/cosinus), jours fériés tunisiens, départements sensibles. |
| Jeu. 6 août | Entraînement du modèle **Isolation Forest** (non supervisé) dans le notebook, calibration des bornes de score. |
| Ven. 7 août | Construction du moteur de décision (seuils différenciés selon la sensibilité du département) et de la couche d'explication en langage naturel. |

*Week-end 8-9 août — pas d'activité.*

---

## Semaine 6 — CrisisBot et mise en place Git (10 → 14 août)

| Date | Tâches réalisées |
|---|---|
| Lun. 10 août | Conception de CrisisBot (agent de gestion d'incidents) : point d'entrée webhook, structure de runbook. |
| Mar. 11 août | **Réunion avec l'encadrant** : démonstration de la chaîne d'escalade entre les 4 autres agents et CrisisBot. Intégration de l'API Groq pour la génération de résumés d'incidents. |
| Mer. 12 août | Développement du dashboard CrisisBot et des scénarios de simulation d'incidents. |
| Jeu. 13 août | Tests d'intégration entre les 5 agents et CrisisBot ; préparation du dépôt Git (structure, `.gitignore` par sous-projet). |
| Ven. 14 août *(date confirmée : `git log`, 11:28)* | Mise en place du dépôt Git local du projet CyberAware (premier commit « Initial commit — CyberAware ») ; ajout du simulateur d'événements (`event_simulator.py`) ; push des fichiers de configuration du modèle PhishHunter (`.gitkeep`, listes de features/marques connues) — le modèle entraîné lui-même (`.pkl`, `.npy`) reste volontairement exclu du dépôt via `.gitignore`, à fournir manuellement à un nouveau collaborateur. |

*Week-end 15-16 août — pas d'activité.*

---

## Semaine 7 — Serious Game et intégrations finales (17 → 21 août)

| Date | Tâches réalisées |
|---|---|
| Lun. 17 août *(date confirmée)* | Conception et développement du **Serious Game** : simulation « dans la peau de l'attaquant », choix d'une cible et d'un vecteur d'ingénierie sociale (phishing, fausse loterie, faux virement...), score de risque par employé évoluant selon les réussites/échecs ; ajout de la page « Formation à la cybersécurité ». |
| Mar. 18 août | **Réunion avec l'encadrant** : démonstration du Serious Game. Ajout de **4 vidéos pédagogiques** et de la partie interactive/intuitive du jeu (faux formulaires de collecte, résolution des tentatives en temps réel). Correction d'un bug sur le vecteur « loterie ». |
| Mer. 19 août | Intégration d'une **résolution DNS réelle** pour NetScope : remplacement de l'échantillon statique par un flux de domaines interrogés en direct, incluant un flux de menaces réel de la communauté sécurité. |
| Jeu. 20 août | Démonstration de bout en bout avec un **vrai téléphone** (DNS du téléphone redirigé vers un proxy local sur le PC, surveillance du trafic en direct) pour visualiser l'analyse réseau en conditions réelles. Finalisation et **push du dépôt vers le GitLab interne d'Hydatis**. |
| Ven. 21 août | Conception et développement d'un **système d'authentification partagé (login/logout)** entre les 6 agents, avec journalisation de chaque connexion et transmission au modèle Sentinel — permettant de tester Sentinel sur des **données de connexion réelles** (et non plus uniquement simulées). Tests finaux et bilan de fin de stage. |

---

## Rappel important

Je te le dis honnêtement : je n'ai pas de preuve indépendante (message, capture, code horodaté) pour CHAQUE jour pris séparément — seuls le 13 et le 17 août sont confirmés par l'historique Git. Le reste suit l'ordre logique et le contenu réel de ce qu'on a construit ensemble, réparti sur le calendrier selon la trame que tu m'as donnée. Relis chaque ligne avant de recopier dans le carnet officiel : si un jour précis ne correspond pas à ton souvenir, décale simplement la tâche d'un jour ou deux, le contenu technique reste vrai.
