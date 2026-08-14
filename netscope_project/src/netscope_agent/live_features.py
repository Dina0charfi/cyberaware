"""
live_features.py — calcule les 16 features NetScope EN DIRECT à partir d'un
simple nom de domaine, sans dépendre d'un CSV pré-calculé.

C'est la correction directe de la limite identifiée : "un vrai firewall ne
donnerait qu'un nom de domaine, pas les 16 statistiques déjà calculées".

Deux familles de features, traitées différemment :

1. Features "nom" — calculables à partir du texte du domaine seul, sans aucun
   accès réseau : entropy, len, FQDN_count, subdomain_length, subdomain,
   numeric, special, labels, labels_max, labels_average.

2. Features "réponse DNS" — nécessitent une VRAIE résolution DNS (une requête
   publique standard, aucun accès spécial requis) : rr_name_entropy,
   rr_name_length, rr_count, a_records, ttl_mean, ttl_variance.

⚠️ Limite honnête à connaître : le dataset d'entraînement (CIC-BellDNS-
Exfiltration 2021) ne fournit que les valeurs déjà calculées, pas le code qui
les a produites à l'origine. Cette implémentation est une reconstruction
raisonnable à partir de la définition usuelle de chaque statistique, pas une
copie certifiée de la méthode exacte des auteurs du dataset — à valider par
comparaison si une vraie intégration est faite un jour (voir la fonction
`extract_name_features`, qui reste la plus fiable puisqu'elle ne dépend que
de définitions mathématiques standards).
"""

import math
from collections import Counter

try:
    import dns.resolver
    _DNS_AVAILABLE = True
except ImportError:
    # dnspython n'est pas installé -> les features de réponse DNS retombent
    # sur des valeurs par défaut, NetScope continue de fonctionner (juste
    # avec moins de signal), au lieu de planter. Installer avec :
    #   pip install dnspython
    _DNS_AVAILABLE = False


def _shannon_entropy(s: str) -> float:
    """Entropie de Shannon d'une chaîne — plus élevé = plus 'aléatoire'."""
    if not s:
        return 0.0
    counts = Counter(s)
    length = len(s)
    return -sum((c / length) * math.log2(c / length) for c in counts.values())


def extract_name_features(domain: str) -> dict:
    """
    Features calculables à partir du texte du domaine seul — aucun réseau
    requis. C'est ce qu'un vrai firewall/proxy générique peut nous fournir
    (il connaît toujours le nom de domaine demandé).
    """
    domain = (domain or "").strip().lower()
    labels_list = [lbl for lbl in domain.split(".") if lbl]
    # Les 2 derniers labels = domaine + TLD (ex: "exemple.com") ; le reste = sous-domaines.
    subdomain_labels = labels_list[:-2] if len(labels_list) > 2 else []
    subdomain_str = ".".join(subdomain_labels)

    numeric_count = sum(c.isdigit() for c in domain)
    special_count = sum((not c.isalnum()) and c != "." for c in domain)
    label_lengths = [len(lbl) for lbl in labels_list] or [0]

    return {
        "entropy": _shannon_entropy(domain),
        "len": float(len(domain)),
        "FQDN_count": float(len(labels_list)),
        "subdomain_length": float(len(subdomain_str)),
        "subdomain": 1.0 if subdomain_labels else 0.0,
        "numeric": float(numeric_count),
        "special": float(special_count),
        "labels": float(len(labels_list)),
        "labels_max": float(max(label_lengths)),
        "labels_average": float(sum(label_lengths) / len(label_lengths)),
    }


def extract_dns_response_features(domain: str, timeout: float = 3.0) -> dict:
    """
    Features qui nécessitent une VRAIE résolution DNS (une requête publique
    standard vers un résolveur — pas un accès spécial). Se dégrade proprement
    vers des valeurs à 0 si dnspython n'est pas installé, si le domaine
    n'existe pas (NXDOMAIN), ou si la résolution échoue pour toute autre
    raison — NetScope continue de scorer, juste avec un signal en moins,
    plutôt que de planter.
    """
    defaults = {
        "rr_name_entropy": 0.0, "rr_name_length": 0.0,
        "rr_count": 0.0, "a_records": 0.0,
        "ttl_mean": 0.0, "ttl_variance": 0.0,
    }
    if not _DNS_AVAILABLE:
        return defaults

    try:
        resolver = dns.resolver.Resolver()
        resolver.timeout = timeout
        resolver.lifetime = timeout
        answer = resolver.resolve(domain, "A")

        a_records = len(answer)
        rr_count = len(answer.response.answer) if answer.response is not None else a_records
        ttl = float(answer.rrset.ttl) if answer.rrset is not None else 0.0
        rr_name = str(answer.qname).rstrip(".")

        return {
            "rr_name_entropy": _shannon_entropy(rr_name),
            "rr_name_length": float(len(rr_name)),
            "rr_count": float(rr_count),
            "a_records": float(a_records),
            "ttl_mean": ttl,
            # Une seule requête ne donne qu'un seul TTL -> pas de variance
            # observable ici (il en faudrait plusieurs dans le temps).
            "ttl_variance": 0.0,
        }
    except Exception:
        return defaults


def extract_all_features_live(domain: str) -> dict:
    """
    Point d'entrée unique : domaine brut -> les 16 features attendues par le
    modèle NetScope. C'est cette fonction qu'on appelle quand le webhook ne
    reçoit qu'un nom de domaine (comme le ferait un vrai firewall), au lieu
    d'exiger que l'appelant fournisse déjà toutes les statistiques.
    """
    features = {}
    features.update(extract_name_features(domain))
    features.update(extract_dns_response_features(domain))
    return features
