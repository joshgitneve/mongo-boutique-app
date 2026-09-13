# On commence par la squelette: la classe + les exceptions métier, avant les méthodes CRUD une par une

from datetime import datetime, timezone # pour les dates UTC aware
from typing import Any, Iterator # pour les annotations de type sur des dicts/paramètres flexibles
from bson import Decimal128, ObjectId # pour les prix et les identifiants
from bson.errors import InvalidId # pour capturer un ObjectId mal formé
from pymongo import ASCENDING, DESCENDING, IndexModel, ReturnDocument, UpdateOne 
from pymongo.database import Database # pour typer le paramètre du constructeur (facultatif)
from pymongo.errors import DuplicateKeyError, WriteError # les erreurs Mongo à intercepter

class ErreurCatalogue(Exception):
    pass
class ProduitIntrouvable(ErreurCatalogue):
    pass
class ProduitDejaExistant(ErreurCatalogue):
    pass
class DocumentInvalide(ErreurCatalogue):
    pass
class StockInsuffisant(ErreurCatalogue):
    pass

VERSION_SCHEMA = 1

CHAMPS_COMMUNS = {"_id", "sku", "nom", "categorie", "prix", "stock", "tags", "cree_le", "maj_le", "supprime_le", "schema_version"}

class CatalogueRepository:
    def __init__(self, db: Database) -> None:
        self.db = db
        self.col = db["products"]

    # create the indexes
    def initialiser(self) -> None:
        self.col.create_indexes([
            IndexModel("sku", unique=True, name="unique_sku"), # ASCENDING par default; if DESCENDING is needed alors [("sku", DESCENDING)] - sq bracks needed with tuple inside
            IndexModel([("categorie", ASCENDING), ("prix", DESCENDING)], name="cat_prix"),
            IndexModel("tags", name="tags_index"),
            IndexModel("supprime_le", expireAfterSeconds=30 * 24 * 3600, partialFilterExpression={"supprime_le": {"$type": "date"}}, name="ttl_corbeille")
        ])


    def importer(self, catalogue: list[dict[str, Any]]) -> tuple[int, int]:
        maintenant = datetime.now(timezone.utc)
        resultat = self.col.bulk_write([
            UpdateOne(
                {"sku": produit["sku"]},
                {"$set": {**produit, "schema_version": VERSION_SCHEMA},
                "$setOnInsert": {"cree_le": maintenant}},
                upsert=True,
            )
            for produit in catalogue
        ], ordered=False)
        return (resultat.upserted_count, resultat.modified_count)

    def creer(self, sku: str, nom: str, categorie: str, prix: str, stock: int | None = None, **specifique: Any) -> ObjectId:
        """exemple call: getdb_object.creer("MON-0120", "Super Monitor 2", "ecrans", "210", stock=10, pouces=24, resolution='1920x1080')

        Raises:
            ProduitDejaExistant: (f"le SKU {sku} existe déjà")
            DocumentInvalide: (exc.details.get("errInfo", exc))

        Returns:
            ObjectId: _id
        """
        document = {
                    "sku": sku,
                    "nom": nom,
                    "categorie": categorie,
                    "prix": Decimal128(prix),
                    "schema_version": VERSION_SCHEMA,
                    "cree_le": datetime.now(timezone.utc),
                    **specifique,
                }
        if stock is not None:
            document["stock"] = stock

        try:
            resultat = self.col.insert_one(document)
        except DuplicateKeyError as exc:
            raise ProduitDejaExistant(f"le SKU {sku} existe déjà") from exc
        except WriteError as exc:
            raise DocumentInvalide(str(exc.details.get("errInfo", exc))) from exc
        return resultat.inserted_id


    def par_sku(self, sku: str, inclure_supprimes: bool = False) -> dict[str, Any]:

        filtre:dict[str, Any]  = {"sku": sku}

        if not inclure_supprimes:
            filtre["supprime_le"] = {"$exists": False}

        resultat = self.col.find_one(filtre)

        if resultat is None:
            raise ProduitIntrouvable(sku)
        return resultat

    def compter(self, categorie: str | None = None, inclure_supprimes: bool = False) -> int:

        filtre:dict[str, Any] = {}
        if not inclure_supprimes:
            filtre["supprime_le"] = {"$exists": False}
        if categorie is not None:
            filtre["categorie"] = categorie
        return self.col.count_documents(filtre)


    def lister(self, categorie: str | None = None, prix_max: str | None = None, taille: int = 20, apres: ObjectId | None = None) -> list[dict[str, Any]]:

        filtre:dict[str, Any] = {"supprime_le": {"$exists": False}}

        if categorie is not None:
            filtre["categorie"] = categorie
        if prix_max is not None:
            filtre["prix"] = {"$lte": Decimal128(prix_max)}
        if apres:
            filtre["_id"] = {"$gt": apres}

        return list(
            self.col.find(filtre, {"sku": 1, "nom": 1, "prix": 1, "stock": 1, "categorie": 1})
                    .sort("_id", ASCENDING)
                    .limit(taille)
        )

    def modifier(self, sku: str, champs: dict[str, Any]) -> bool:

        disallowed = [key for key in champs if key.startswith("$") or "." in key or key =="_id"]

        if disallowed:
            raise DocumentInvalide(f"champs interdits : {disallowed} - Les champs ne peuvent ni commencer par '$', ni contenir '.', ni être '_id'")
        
        resultat = self.col.update_one(
            {"sku": sku, "supprime_le": {"$exists": False}}, 
            {"$set": champs, "$currentDate": {"maj_le": True}})
        
        if resultat.matched_count == 0:
            raise ProduitIntrouvable(sku)
        return resultat.modified_count == 1

    def reserver(self, sku: str, quantite: int) -> dict[str, Any]:

        produit = self.col.find_one_and_update(
                {"sku": sku, "stock": {"$gte": quantite}, "supprime_le": {"$exists": False}},    # 👈 la condition est DANS le filtre
                {"$inc": {"stock": -quantite}, "$currentDate": {"maj_le": True}},
        return_document = ReturnDocument.AFTER,
            )
        if produit is None:
            self.par_sku(sku)
            raise StockInsuffisant(f"{sku} : stock insuffisant ou non géré en stock")
        return produit
        

    def supprimer(self, sku: str) -> None:

        deleted = self.col.update_one(
                {"sku": sku, "supprime_le": {"$exists": False}},
                {"$set": {"supprime_le": datetime.now(timezone.utc)}},
            )
        if deleted.matched_count == 0:
            raise ProduitIntrouvable(sku)
        

    def supprimer_definitivement(self, sku: str) -> None:
        doc = self.col.find_one_and_delete({"sku": sku})
        if doc is None:
            raise ProduitIntrouvable(sku)


    @staticmethod
    def decouper(document: dict[str, Any]) -> tuple[dict, dict]:

        commun = {k: v for k,v in document.items() if k in CHAMPS_COMMUNS}

        specifique = {k: v for k,v in document.items() if k not in CHAMPS_COMMUNS}

        return (commun, specifique)


    def auditer(self) -> Iterator[dict[str, Any]]:
        
        return self.col.aggregate([
            {"$project": {"champs": {"$objectToArray": "$$ROOT"}}},
            {"$unwind": "$champs"},
            {"$group": {
                "_id": "$champs.k",
                "presents": {"$sum": 1},
                "types": {"$addToSet": {"$type": "$champs.v"}}}},
            {"$sort": {"presents": -1}},
        ])

    def statistiques(self) -> Iterator[dict[str, Any]]:
        return self.col.aggregate([
            {"$match": {"supprime_le": {"$exists": False}}},
        {"$group": {
            "_id": "$categorie",
            "nombre": {"$sum": 1},
            "prix_moyen": {"$avg": {"$toDouble": "$prix"}},
            "stock_total": {"$sum": {"$ifNull": ["$stock", 0]}},
            "sans_stock": {"$sum": {"$cond": [{"$eq": [{"$type": "$stock"}, "missing"]}, 1, 0]}},
        }},
        {"$sort": {"nombre": -1}},
        ])

    
       


if __name__ == "__main__": # "main gaurd" ou "garde d'execution"
    from db import get_db
    CatalogueRepository(get_db()).initialiser()
    d = CatalogueRepository(get_db())
    