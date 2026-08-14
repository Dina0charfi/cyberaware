"""
email_sources.py — d'où viennent les emails surveillés par DarkWatch.
========================================================================
Aujourd'hui : lus depuis un fichier texte (emails_example.txt). Le jour
du branchement sur l'annuaire réel de la banque, on écrit la vraie
implémentation de from_active_directory() ci-dessous et on bascule
DARKWATCH_EMAIL_SOURCE=active_directory — server.py, agent.py et
darkwatch.py continuent d'appeler get_monitored_emails() exactement
comme avant, rien d'autre ne change.
"""

import os
from pathlib import Path


def from_file(path: Path) -> list[str]:
    """Source actuelle (démo) : un email par ligne, '#' pour commenter une ligne."""
    if not path.exists():
        return []
    return [
        line.strip()
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.startswith("#")
    ]


def from_active_directory() -> list[str]:
    """
    PAS ENCORE IMPLÉMENTÉ — récupérerait la liste des emails employés
    depuis l'annuaire réel de la banque (Microsoft Graph API `GET /users`,
    ou LDAP/Active Directory). Nécessite un app registration Azure AD avec
    la permission `User.Read.All`, une clé/certificat, et un tenant réel.

    Squelette prévu pour le jour du branchement (exemple avec Microsoft
    Graph, requête HTTP brute pour rester cohérent avec le reste du projet
    100% stdlib) :

        import urllib.request, json
        token = _get_graph_access_token()  # OAuth client credentials flow
        req = urllib.request.Request(
            "https://graph.microsoft.com/v1.0/users?$select=mail",
            headers={"Authorization": f"Bearer {token}"},
        )
        with urllib.request.urlopen(req) as resp:
            data = json.loads(resp.read())
        return [u["mail"] for u in data.get("value", []) if u.get("mail")]
    """
    raise NotImplementedError(
        "Source Active Directory pas encore branchée — nécessite un accès réel "
        "à l'annuaire de la banque (Microsoft Graph API). En attendant, laisse "
        "DARKWATCH_EMAIL_SOURCE sur 'file' (valeur par défaut)."
    )


def get_monitored_emails(fallback_path: Path) -> list[str]:
    """
    Point d'entrée UNIQUE utilisé par server.py, agent.py et darkwatch.py —
    ils n'appellent jamais from_file()/from_active_directory() directement,
    seulement celle-ci. Le jour du branchement, on change juste la variable
    d'environnement, aucun autre fichier du projet n'est touché.
    """
    source = os.environ.get("DARKWATCH_EMAIL_SOURCE", "file")
    if source == "active_directory":
        return from_active_directory()
    return from_file(fallback_path)
