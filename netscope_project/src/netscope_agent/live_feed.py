"""
live_feed.py — source de "trafic" RÉELLE pour la démo NetScope.

Avant : /sample-traffic et auto_scan.py lisaient models/sample_traffic.csv,
un fichier de lignes déjà pré-calculées (les 16 features toutes prêtes) avec
des noms de domaine factices ("host-51623.sample") — pratique pour entraîner/
valider le modèle, mais ça ne fait AUCUNE vraie requête réseau : la démo ne
prouvait pas que NetScope sait vraiment interroger le DNS.

Ici : ce module choisit de VRAIS noms de domaine, et c'est
live_features.extract_all_features_live() (voir ce fichier) qui va faire une
VRAIE résolution DNS (dnspython, résolveur public standard) pour calculer les
6 features "réponse DNS" (rr_count, a_records, ttl_mean...) — donc chaque
domaine affiché dans la démo a réellement été interrogé au moment de l'appel,
pas relu depuis un CSV figé.

Trois catégories, mélangées à chaque appel :
  1. Domaines légitimes réels et connus (Google, Wikipédia, GitHub...) —
     résolvent normalement, le modèle est censé les classer "normal".
  2. Domaines générés façon DGA (Domain Generation Algorithm — la technique
     que de vrais malwares/botnets utilisent pour générer des noms
     pseudo-aléatoires afin d'éviter les listes noires statiques) : longs,
     haute entropie, sous un vrai TLD. Une vraie requête DNS leur est aussi
     envoyée — qu'ils résolvent ou tombent en NXDOMAIN (le cas le plus
     fréquent pour un vrai DGA, souvent sinkholé ou jamais enregistré), la
     réponse reçue est authentique, pas simulée. NetScope doit surtout les
     repérer via les features "nom" (entropie, longueur), exactement comme
     un vrai firewall qui ne verrait qu'un NXDOMAIN suspect.
  3. Un VRAI domaine malveillant, actif MAINTENANT : téléchargé depuis
     URLhaus (abuse.ch — projet public et gratuit de threat intelligence,
     alimenté par de vrais chercheurs/honeypots, pas une liste écrite à la
     main). Contrairement aux domaines DGA générés localement (suspects par
     construction mais pas forcément "réels"), celui-ci est un domaine
     réellement recensé comme malveillant par la communauté sécurité au
     moment du tirage. Se dégrade proprement (retombe sur légitime/DGA) si
     le flux est inaccessible (pas d'internet en salle d'oral, etc.).
"""

import random
import string
import time
import urllib.error
import urllib.request

# Flux "hosts file" public d'abuse.ch : une ligne par domaine malveillant
# actif, format "0.0.0.0 domaine-malveillant.com". Mis à jour en continu par
# de vrais chercheurs en sécurité — c'est ce qui rend le domaine "réel" plutôt
# que généré. Gratuit, sans clé API, safe à interroger depuis une démo.
_URLHAUS_HOSTFILE_URL = "https://urlhaus.abuse.ch/downloads/hostfile/"
_THREAT_CACHE_TTL = 600  # 10 min — évite de retélécharger tout le flux à chaque clic
_threat_cache: dict = {"domains": [], "fetched_at": 0.0}

# Domaines réels, stables, choisis pour résoudre de façon fiable sans
# dépendre d'un compte/API — juste une résolution A publique standard.
LEGIT_DOMAINS = [
    "google.com",
    "wikipedia.org",
    "github.com",
    "cloudflare.com",
    "microsoft.com",
    "amazon.fr",
    "office.com",
    "apple.com",
    "stackoverflow.com",
    "mozilla.org",
    "ovh.com",
    "orange.fr",
]

_DGA_TLDS = ["com", "net", "info", "xyz", "top", "online"]


def _random_dga_domain() -> str:
    """Génère un nom façon DGA : chaîne pseudo-aléatoire de longueur variable
    + un vrai TLD. But : haute entropie/longueur, comme un vrai algorithme de
    génération de domaines utilisé par des malwares (ex: familles Conficker,
    Necurs) pour échapper aux listes noires statiques."""
    length = random.randint(12, 24)
    label = "".join(random.choices(string.ascii_lowercase + string.digits, k=length))
    tld = random.choice(_DGA_TLDS)
    return f"{label}.{tld}"


def _fetch_real_threat_domains(timeout: float = 4.0) -> list[str]:
    """
    Télécharge la liste de domaines malveillants ACTIFS en ce moment (URLhaus)
    et la met en cache 10 minutes. En cas d'échec (pas d'internet, flux
    indisponible, timeout...), retombe sur le dernier cache connu (ou une
    liste vide si aucun) — ne lève jamais d'exception, exactement le même
    principe de dégradation propre que extract_dns_response_features()
    (live_features.py) : NetScope continue de fonctionner, juste avec moins
    de signal "réel" dans ce cas précis.
    """
    now = time.time()
    if _threat_cache["domains"] and (now - _threat_cache["fetched_at"] < _THREAT_CACHE_TTL):
        return _threat_cache["domains"]

    try:
        req = urllib.request.Request(_URLHAUS_HOSTFILE_URL, headers={"User-Agent": "NetScope-Demo/1.0"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            text = resp.read().decode("utf-8", errors="ignore")

        domains = []
        for line in text.splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split()
            # Format hosts file : "0.0.0.0 domaine-malveillant.com"
            if len(parts) == 2 and parts[0] in ("0.0.0.0", "127.0.0.1"):
                domains.append(parts[1])

        if domains:
            _threat_cache["domains"] = domains
            _threat_cache["fetched_at"] = now
        return _threat_cache["domains"]
    except Exception as e:
        print(f"[NetScope][live_feed] Flux URLhaus injoignable ({e}) — "
              f"repli sur légitime/DGA pour ce tirage.")
        return _threat_cache["domains"]


def _pick_filler_domain() -> str:
    """Un domaine 'de remplissage', sans forcer de domaine malveillant réel —
    moitié légitime connu, moitié généré façon DGA."""
    if random.random() < 0.5:
        return random.choice(LEGIT_DOMAINS)
    return _random_dga_domain()


def pick_live_domains(n: int = 4) -> list[str]:
    """
    Retourne n noms de domaine réels à interroger. Si le flux URLhaus est
    joignable, AU MOINS UN des n domaines est un vrai domaine malveillant
    actif (pas généré) — le reste complète avec un mélange de domaines
    légitimes connus et de domaines façon DGA. Jamais deux fois exactement
    le même tirage, contrairement à un CSV figé.
    """
    n = max(1, n)
    threat_domains = _fetch_real_threat_domains()

    chosen = []
    if threat_domains:
        chosen.append(random.choice(threat_domains))

    while len(chosen) < n:
        chosen.append(_pick_filler_domain())

    random.shuffle(chosen)
    return chosen[:n]


def pick_one_live_domain() -> str:
    """
    Un seul domaine — utilisé par auto_scan.py (une itération = un domaine
    toutes les ~25s). Tire un VRAI domaine malveillant environ 1 fois sur 3
    quand le flux est joignable (assez souvent pour voir l'auto-isolement se
    déclencher pendant une démo, sans que CHAQUE tour soit suspect).
    """
    threat_domains = _fetch_real_threat_domains()
    if threat_domains and random.random() < 0.33:
        return random.choice(threat_domains)
    return _pick_filler_domain()
