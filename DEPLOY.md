# Déploiement sur Railway — MCP Trello

Une fois déployé, toute ton équipe pointe vers la même URL. Personne n'a rien à installer.

---

## Étapes

### 1. Créer un compte Railway
→ https://railway.app (gratuit jusqu'à 500h/mois)

### 2. Pousser le code sur GitHub

Crée un repo GitHub avec les 3 fichiers :
- `server.py`
- `requirements.txt`
- (ce fichier DEPLOY.md optionnel)

```bash
git init
git add server.py requirements.txt
git commit -m "Trello MCP server"
gh repo create trello-mcp --public --push --source=.
```

> Si tu n'as pas `gh` installé, fais-le manuellement sur github.com.

### 3. Déployer sur Railway

1. Sur Railway → **New Project** → **Deploy from GitHub repo**
2. Sélectionne ton repo `trello-mcp`
3. Railway détecte Python automatiquement via `requirements.txt`
4. Onglet **Variables** → ajoute :
   - `TRELLO_API_KEY` = ta clé API
   - `TRELLO_TOKEN` = ton token
5. Railway définit `PORT` automatiquement → le serveur démarre en mode HTTP

### 4. Récupérer ton URL

Dans Railway → onglet **Settings** → **Domains** → génère un domaine public.

L'URL MCP sera : `https://ton-projet.up.railway.app/mcp`

---

## Configurer Cowork pour chaque collègue

Dans **Cowork → Settings → MCP Servers → Add Server** :

```json
{
  "url": "https://ton-projet.up.railway.app/mcp"
}
```

C'est tout. Pas de Python, pas de clé API à partager, pas d'installation locale.

---

## Sécurité (optionnel mais recommandé)

Pour éviter que n'importe qui utilise ton serveur, ajoute un token d'authentification :

Dans Railway → Variables → ajoute `MCP_AUTH_TOKEN=un_secret_fort`

Puis dans la config Cowork de chaque collègue :
```json
{
  "url": "https://ton-projet.up.railway.app/mcp",
  "headers": {
    "Authorization": "Bearer un_secret_fort"
  }
}
```

> Note : l'implémentation du check côté serveur nécessite quelques lignes supplémentaires — demande si tu veux l'activer.
