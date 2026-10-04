Projet « Boutique » · étape 13

# Aide-mémoire MongoDB

Les concepts, le pourquoi et le comment, avec les méthodes utilisées dans l'application : le dépôt `repository.py`, la validation `provision.py`, le CLI `app.py` et les tests.

[Le modèle](#modele) [Connexion](#connexion) [Schéma et validation](#schema) [Index](#index) [CRUD](#crud) [Agrégation](#agregation) [Pagination](#pagination) [Erreurs](#erreurs) [Python : CLI et tests](#python) [Pièges](#pieges) [Shell mongosh](#shell)

## Le modèle

Concepts de base

- **Base** → **collection** → **document**. Un document est un dict Python, stocké en BSON.
- **`_id`** : ajouté automatiquement (ObjectId), unique dans la collection.
- **Schéma souple** : deux documents d'une même collection peuvent avoir des champs différents. La validation est une option, pas une obligation.

### Types BSON qui comptent ici

- `Decimal128` pour les prix : pas de `float` pour l'argent.
- Dates en UTC « aware » (`tz_aware=True`, `datetime.now(timezone.utc)`).
- `ObjectId` pour les identifiants ; `ObjectId(str)` lève `InvalidId` si la chaîne est mal formée.

**Pourquoi :** on modélise pour les requêtes qu'on va faire, pas pour des entités abstraites.

## Connexion

db.py

- **`MongoClient`** : la vraie connexion (un pool de sockets). Une seule par processus.
- `@lru_cache(maxsize=1)` sur `get_client()` : le même objet est renvoyé à chaque appel.
- **Paresseux** : `MongoClient(...)` ne se connecte pas tout de suite. La première opération le fait. D'où le `ping` de test.
- `get_db()` = `client[nom]`. `db["products"]` = une référence légère, sans appel réseau.
- URI et nom de base dans `.env`, jamais en dur.

```
client = get_client()             # connexion unique
db = get_db()                     # base "boutique"
col = db["products"]              # collection (référence)
client.admin.command("ping")      # vérifie que le serveur répond
```

## Schéma et validation

provision.py

Le schéma vit sur le serveur, sous forme de validateur `$jsonSchema` attaché à la collection. Il s'applique à **toutes** les écritures, quel que soit le client.

```
db.create_collection("products", validator=VALIDATOR)   # 1re fois
db.command("collMod", "products", validator=VALIDATOR,   # ensuite
           validationLevel="moderate", validationAction="warn")
```

- `validationLevel` : `strict` (défaut de Mongo) ou `moderate` (seulement nouveaux documents et ceux déjà valides).
- `validationAction` : `error` (défaut, rejette) ou `warn` (accepte, journalise).
- Violation en `strict`/`error` → `WriteError` code 121, détail dans `exc.details["errInfo"]`.

**Piège :** notre branche `collMod` est en `moderate`/`warn`. Une violation passe alors sans erreur côté Python. Pour la voir, passer en `strict`/`error` dans mongosh.

## Index

repository.initialiser()

Un index est un B-arbre trié sur un champ : une recherche descend en quelques niveaux au lieu de parcourir tous les documents.

```
col.create_indexes([
    IndexModel([("sku", ASCENDING)], unique=True, name="unique_sku"),
    IndexModel([("categorie", ASCENDING), ("prix", DESCENDING)], name="cat_prix"),
    IndexModel("tags", name="tags_index"),
    IndexModel("supprime_le", expireAfterSeconds=30*24*3600,
               partialFilterExpression={"supprime_le": {"$type": "date"}},
               name="ttl_corbeille"),
])
```

- **`unique=True`** : la règle « un SKU par produit » est garantie par le serveur.
- **Partiel** : seuls les documents qui satisfont le filtre ont une entrée.
- **TTL** : `expireAfterSeconds` purge les documents automatiquement, environ toutes les 60 s.
- **Idempotent** si le nom et les options sont identiques. Changer une définition sans changer le nom suffit, sinon `IndexOptionsConflict`.

### ESR : ordre des champs d'un index composé

**E**quality d'abord, **S**ort ensuite, **R**ange en dernier. Un index `{a, b, c}` sert `{a}` et `{a, b}`, jamais `{b}` seul.

### Vérifier

```
col.find(filtre).explain("executionStats")
# IXSCAN = index utilisé   COLLSCAN = parcours complet
# totalDocsExamined proche de nReturned = bon index
```

## CRUD : quelle méthode, quel repository

repository.py

| Besoin | Méthode PyMongo | Méthode du dépôt | Points clés |
| --- | --- | --- | --- |
| Créer | `insert_one` | `creer()` | Décimal sur le prix, `stock` ajouté seulement s'il est fourni |
| Lire un | `find_one` | `par_sku()` | Renvoie `dict` ou `None`, on lève `ProduitIntrouvable` |
| Lire une page | `find` + `sort` + `limit` | `lister()` | Projection `{"sku": 1, ...}`, tri sur `_id` |
| Compter | `count_documents` | `compter()` | Filtre de base : exclut les supprimés |
| Modifier | `update_one` + `$set`, `$currentDate` | `modifier()` | `matched_count` pour « existe », `modified_count` pour « a changé » |
| Réserver | `find_one_and_update` + `$inc` | `reserver()` | Condition `stock ≥ n` *dans le filtre* : atomique, sans course |
| Supprimer (logique) | `update_one` + `$set supprime_le` | `supprimer()` | La purge TTL s'occupe du reste |
| Supprimer (définitif) | `find_one_and_delete` | `supprimer_definitivement()` | Renvoie le document supprimé, ou `None` |
| Importer en lot | `bulk_write([UpdateOne(..., upsert=True)], ordered=False)` | `importer()` | `$setOnInsert` pose `cree_le` à la création seulement |
| Agréger | `aggregate([...])` | `auditer()`, `statistiques()` | Curseur de résultats, pas une liste |

## Opérateurs à retenir

Syntaxe

### Filtres

```
{"sku": "KBD-0010"}                     # égalité
{"prix": {"$lte": Decimal128("130")}}   # plage
{"supprime_le": {"$exists": False}}     # champ absent
{"_id": {"$gt": dernier_id}}            # curseur
{"stock": {"$gte": 2}}                  # condition métier
```

### Mises à jour

```
{"$set": {"nom": "..."}}                 # pose / crée
{"$inc": {"stock": -2}}                 # incrémente
{"$currentDate": {"maj_le": True}}      # date serveur
{"$setOnInsert": {"cree_le": now}}      # seulement à l'insertion
```

## Agrégation

auditer() et statistiques()

Un pipeline est une liste d'étapes. Chaque étape reçoit les documents de la précédente.

### auditer() : quels champs, combien, quels types

```
{"$project": {"champs": {"$objectToArray": "$$ROOT"}}}   # doc → liste de paires k/v
{"$unwind": "$champs"}                                  # une ligne par champ
{"$group": {"_id": "$champs.k",                         # regroupe par nom de champ
            "presents": {"$sum": 1},
            "types": {"$addToSet": {"$type": "$champs.v"}}}}
{"$sort": {"presents": -1}}
```

### statistiques() : chiffres par catégorie

```
{"$match": {"supprime_le": {"$exists": False}}}   # filtrer en premier
{"$group": {
  "_id": "$categorie",
  "nombre": {"$sum": 1},
  "prix_moyen": {"$avg": {"$toDouble": "$prix"}},
  "stock_total": {"$sum": {"$ifNull": ["$stock", 0]}},
  "sans_stock": {"$sum": {"$cond": [
      {"$eq": [{"$type": "$stock"}, "missing"]}, 1, 0]}},
}}
```

**Lire `$type` :** il renvoie le type de la *valeur* sur ce document. Un champ absent donne la chaîne `"missing"`.

## Pagination

lister(taille, apres)

- **À éviter** : `skip(n)`. Mongo parcourt et jette n documents à chaque page : coût qui grandit avec la profondeur.
- **Curseur** : on retient le dernier `_id` vu, puis on demande ce qui suit.

```
page1 = depot.lister(taille=2)
page2 = depot.lister(apres=page1[-1]["_id"], taille=2)
# filtre : {"_id": {"$gt": apres}}, tri : _id ASC, limite : taille
```

**Pourquoi le tri est indispensable :** « après tel \_id » n'a de sens que si l'ordre est toujours le même.

## Erreurs : traduire et remonter

Exceptions

| Cause | Exception PyMongo | Exception métier |
| --- | --- | --- |
| SKU déjà pris | `DuplicateKeyError` | `ProduitDejaExistant` |
| Document invalide | `WriteError` | `DocumentInvalide` |
| Rien trouvé | `find_one` renvoie `None` | `ProduitIntrouvable` |
| Stock insuffisant | condition du filtre vide | `StockInsuffisant` |

- `class ErreurCatalogue(Exception): pass` : toutes les erreurs métier héritent de `Exception`, donc `except ErreurCatalogue` les attrape toutes.
- `raise X(...) from exc` garde l'erreur Mongo d'origine comme cause, visible dans le traceback.

## Python : CLI et tests

app.py et test_repository.py

### argparse : sous-commandes

```
parser = argparse.ArgumentParser()
sub = parser.add_subparsers(dest="command", required=True)
p = sub.add_parser("reserve")
p.add_argument("sku")
p.add_argument("n", type=int)
p = sub.add_parser("delete")
p.add_argument("--hard", action="store_true")
args = parser.parse_args()   # lit sys.argv[1:]
```

- Argument positionnel : sans `--`, rangé par ordre. Option : `--nom`, n'importe où.
- `store_true` : `True` si le flag est présent.
- `{args.champ: args.valeur}` : clé de dict calculée à partir d'une variable.

### Sortie et code de sortie

```
def main() -> int:
    ...
    except ErreurCatalogue as exc:
        print(f"erreur : {exc}", file=sys.stderr)
        return 1
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
```

0 = succès, autre = échec. Le shell le lit avec `$?`, `&&` et `||`.

### pytest

```
@pytest.fixture
def depot():
    client = get_client()
    d = CatalogueRepository(client["boutique_test"])
    d.initialiser()
    yield d                                   # le test s'exécute ici
    client.drop_database("boutique_test")     # nettoyage après le test

def test_sku_unique(depot):
    depot.creer("KBD-0001", "Clavier", "clavier", "99.00")
    with pytest.raises(ProduitDejaExistant):
        depot.creer("KBD-0001", "Autre", "clavier", "50.00")
```

- Le nom du paramètre de test (`depot`) doit être le nom de la fixture. Le nom de la variable interne n'a pas d'importance.
- `assert` : échec = `AssertionError` détaillée.

## Commandes CLI → méthodes

app.py

| Commande | Appelle |
| --- | --- |
| `init` | `provisionner()` puis `initialiser()` |
| `seed` | `importer(CATALOGUE_DEMO)` |
| `list [--categorie] [--max-prix]` | `lister()`, boucle « page suivante » |
| `show SKU` | `decouper(par_sku(sku))`, affichage commun puis spécifique |
| `add SKU NOM CAT PRIX [--stock]` | `creer()` |
| `set SKU CHAMP VALEUR` | `modifier(sku, {champ: valeur})` |
| `reserve SKU N` | `reserver()` |
| `delete SKU [--hard]` | `supprimer()` ou `supprimer_definitivement()` |
| `audit` | `compter(inclure_supprimes=True)` et `auditer()` |
| `stats` | `statistiques()` |

## Pièges à retenir

Ce qui surprend

- **Trouvé ≠ changé.** `matched_count` dit « existe ». `modified_count` dit « a changé ». Avec `$currentDate`, `maj_le` change toujours : `modifier()` renvoie donc presque toujours `True`.
- **`{"champ": None}`** matche les documents où le champ est `null` *et* ceux où il est absent.
- **Absent ≠ null ≠ 0.** Un abonnement n'a pas de `stock`. Un `stock` à `0` est une vraie valeur.
- **Types mélangés.** Une chaîne n'est jamais comparée à un nombre : `$lt: 100` ignore silencieusement un prix stocké en texte.
- **`replace_one`** efface les champs non fournis, et risque le *lost update*. Préférer `$set`.
- **Filtre vide** sur `update_many` ou `delete_many` = toute la collection.
- **`find_one` renvoie `None`** : toujours tester avant d'accéder à une clé.
- **`skip`** devient coûteux sur les grandes pages : curseur sur `_id`.

## Shell mongosh

Aide-mémoire

```
use boutique                       # base courante (sinon « test »)
db.getName()                       # vérifier la base
db.products.getIndexes()           # lister les index
db.products.dropIndex("uniq_sku")  # supprimer un index
db.runCommand({collMod: "products",
  validationLevel: "strict", validationAction: "error"})
db.grantRolesToUser("app",
  [{role: "dbAdmin", db: "boutique_test"}])   # depuis la base du compte
db.dropDatabase()                  # base courante, irréversible
```

**Rappel de permissions :** `readWrite` couvre les lectures, écritures et index. `collMod` et `dropDatabase` demandent `dbAdmin`. « ns does not exist » = mauvaise base sélectionnée.

Repère : tout le détail des méthodes est dans `repository.py`. Les tests de référence sont dans `test_repository.py`.