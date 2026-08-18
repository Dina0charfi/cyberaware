# Rendre le serious game dynamique — guide d'intégration

## Ce que ça change

| Avant | Après |
|---|---|
| 2 phrases fixes par vecteur, écrites à l'avance | Une phrase unique générée à chaque tentative |
| Résultat calculé dans le navigateur | Résultat calculé sur ton serveur (non trafiquable) |
| Aucun appel réseau | Un appel à `/api/attack` à chaque tentative |

## Étapes

### 1. Récupérer une clé API Anthropic
Sur [console.anthropic.com](https://console.anthropic.com), section API Keys.

### 2. Ajouter la clé sur Vercel
Dans ton projet Vercel : **Settings → Environment Variables**
```
ANTHROPIC_API_KEY = sk-ant-xxxxxxxxxxxx
```
Redéployer après ajout (Vercel te le proposera automatiquement).

### 3. Ajouter la route API
Copie `app-api-attack-route.js` dans ton projet à l'emplacement :
```
app/api/attack/route.js
```
(Si ton projet utilise le **Pages Router** au lieu de l'App Router, dis-le moi, la syntaxe est légèrement différente — `pages/api/attack.js` avec `export default function handler(req, res)`.)

### 4. Adapter le composant du jeu
Remplace la fonction `runAttack()` dans ta page/composant par la version de `client-runAttack-dynamique.js`, qui appelle `/api/attack` au lieu d'utiliser `v.success(t)` / `v.fail(t)`.

Ajuste `renderResult()` pour qu'elle affiche `data.narrative`, `data.module` et `data.agent` reçus de l'API, au lieu des valeurs codées en dur dans `VECTORS`.

### 5. Tester en local
```bash
npm run dev
```
Puis dans le navigateur, choisis une cible + un vecteur : la génération prendra 1 à 3 secondes (affiche un état de chargement pendant ce temps, prévu dans le code fourni).

## Points d'attention

- **Coût** : chaque tentative = un appel à l'API Claude. Pour un usage en formation interne (dizaines/centaines d'essais), le coût reste négligeable, mais évite de l'exposer en accès public illimité sans limite de fréquence.
- **Limite de fréquence (optionnel mais recommandé)** : si le jeu est accessible publiquement, ajoute un throttling (ex. via Vercel KV ou un simple compteur par IP) pour éviter les abus.
- **Fallback** : si l'appel à Claude échoue (réseau, quota), garde en réserve les 2 phrases pré-écrites par vecteur comme filet de sécurité plutôt que de bloquer le jeu.

## Et les données des cibles ?

Elles restent pour l'instant une liste en dur dans le code (comme avant). C'est un choix raisonnable tant que tu n'as pas de vraie source de scores de formation à brancher. Le jour où tu veux les rendre dynamiques aussi, la voie la plus simple avec Vercel est **Vercel Postgres** ou **Supabase** — dis-moi si tu veux ce guide-là aussi, une fois que celui-ci fonctionne.
