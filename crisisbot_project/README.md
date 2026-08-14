# CrisisBot

Agent de réponse à incident : quand un autre agent (Sentinel, NetScope,
PhishHunter, DarkWatch) détecte une menace sérieuse, CrisisBot prend le
relais et déroule un **runbook de réponse automatique** — isoler le poste,
notifier le RSSI et la Direction, activer la cellule de crise, préparer la
communication interne — puis notifie les bonnes personnes (Slack / Teams /
Email — simulé dans cette démo).

Même architecture que DarkWatch : aucune dépendance externe, uniquement
`http.server` (bibliothèque standard Python 3.9+). Rien à installer.

## Fichiers

| Fichier | Rôle |
|---|---|
| `server.py` | Dashboard web + API JSON (statut, simulation, webhook entrant) |
| `index.html` | Interface visuelle — runbook animé, statut, bouton de simulation |
| `crisisbot_state.json` | Généré automatiquement — dernière simulation |
| `crisisbot_actions.log` | Généré automatiquement — journal des runbooks exécutés |

## Lancer

```bash
python3 server.py
```

Puis ouvre **http://localhost:8878**.

## API

- `GET /api/status` — état actuel (dernière simulation, jours écoulés)
- `POST /api/simulate` — déclenche une simulation du runbook depuis le dashboard
- `POST /api/webhook/incident` — point d'entrée pour qu'**un autre agent**
  déclenche CrisisBot automatiquement, sans passer par le dashboard :

  ```bash
  curl -X POST http://localhost:8878/api/webhook/incident \
    -H "Content-Type: application/json" \
    -d '{"source_agent": "sentinel", "severity": "high", "description": "Connexion anormale — poste compromis"}'
  ```

## Limites (démo)

Le webhook Slack / Teams / Email est **simulé** — rien n'est réellement
envoyé. Pour un vrai déclenchement, il faudrait brancher une clé API
(webhook Slack, connecteur Teams, ou SMTP), sur le même principe que
GROQ_API_KEY / HF_TOKEN dans les autres projets.
