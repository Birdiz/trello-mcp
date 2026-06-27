# MCP Trello — Guide d'installation

Ce serveur MCP expose les outils Trello à Claude (Cowork / Claude Code).

---

## 1. Obtenir une clé API et un token Trello

1. Ouvre **https://trello.com/power-ups/admin**
2. Clique sur **New Power-Up** → donne un nom quelconque → **Create**
3. Onglet **API Key** → copie ta **API Key**
4. Sur la même page, clique **Generate a Token** → autorise l'accès → copie le **Token**

---

## 2. Installer les dépendances Python

```bash
pip install "mcp[cli]" httpx pydantic
```

> Python 3.10+ requis.

---

## 3. Configurer les variables d'environnement

```bash
export TRELLO_API_KEY="ta_clé_api"
export TRELLO_TOKEN="ton_token"
```

Pour les rendre permanentes, ajoute-les dans `~/.zshrc` ou `~/.bashrc`.

---

## 4. Connecter le serveur MCP à Cowork

Dans les **Paramètres Cowork → MCP Servers → Add Server**, saisir :

```json
{
  "command": "python",
  "args": ["/chemin/absolu/vers/trello_mcp/server.py"],
  "env": {
    "TRELLO_API_KEY": "ta_clé_api",
    "TRELLO_TOKEN": "ton_token"
  }
}
```

> Remplace le chemin par le chemin réel vers `server.py` sur ton ordinateur.

---

## 5. Outils disponibles

| Outil | Description |
|---|---|
| `trello_get_me` | Profil de l'utilisateur connecté |
| `trello_list_boards` | Lister tous les boards |
| `trello_get_board` | Détails d'un board (listes + labels) |
| `trello_create_board` | Créer un board |
| `trello_list_lists` | Lister les colonnes d'un board |
| `trello_create_list` | Créer une colonne |
| `trello_list_cards` | Lister les cartes (par liste ou board) |
| `trello_get_card` | Détails d'une carte |
| `trello_create_card` | Créer une carte (avec labels, due date…) |
| `trello_update_card` | Modifier une carte (titre, liste, due…) |
| `trello_delete_card` | Supprimer une carte définitivement |
| `trello_list_labels` | Lister les labels d'un board |
| `trello_create_label` | Créer un label |
| `trello_update_label` | Modifier un label |
| `trello_delete_label` | Supprimer un label |
| `trello_add_label_to_card` | Ajouter un label à une carte |
| `trello_remove_label_from_card` | Retirer un label d'une carte |
| `trello_assign_member_to_card` | Assigner un membre à une carte |
| `trello_search` | Rechercher cartes/boards |

### Couleurs de labels disponibles
`yellow`, `purple`, `blue`, `red`, `green`, `orange`, `black`, `sky`, `pink`, `lime`

---

## 6. Exemples d'usage avec Claude

> "Liste mes boards Trello"
> "Crée un label 'Bug' en rouge sur mon board Sprint"
> "Ajoute une carte 'Fix login flow' dans la liste To Do avec le label Bug"
> "Déplace la carte X dans la liste Done"
> "Recherche toutes les cartes avec 'API' dans le titre"
