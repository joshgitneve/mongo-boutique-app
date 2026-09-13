from pymongo import ASCENDING, DESCENDING, IndexModel
from db import get_db

NOYAU_COMMUN = {
    "$jsonSchema": {
        "bsonType": "object",
        "title": "product",
        "required": ["sku", "nom", "categorie", "prix", "schema_version", "cree_le"],
        "properties": {
            "sku": {"bsonType": "string", "pattern": "^[A-Z]{3}-[0-9]{4}$"},
            "nom": {"bsonType": "string", "minLength": 2, "maxLength": 200},
            "categorie": {"enum": ["clavier", "ecran", "souris", "livre", "abonnement"]},
            "prix": {"bsonType": "decimal", "description": "Decimal128, en euros"},
            "stock": {"bsonType": "int", "minimum": 0},
            "tags": {"bsonType": "array", "items": {"bsonType": "string"}},
            "cree_le": {"bsonType": "date"},
            "schema_version": {"bsonType": "int", "minimum": 1},
        },
        "additionalProperties": True,      # still flexible
    }
}

# constraints specific per family
REGLES_ECRAN = {
    "$or": [
        {"categorie": {"$ne": "ecran"}},
        {"$and": [{"pouces": {"$type": "int"}}, {"resolution": {"$type": "string"}}]},
    ]
}

VALIDATOR = {"$and": [NOYAU_COMMUN, REGLES_ECRAN]}


def provisionner() -> None:
    db = get_db()
    if "products" not in db.list_collection_names():
        db.create_collection("products", validator=VALIDATOR)
        print("collection créée")
    else:
        db.command("collMod", "products", validator=VALIDATOR,
                   validationLevel="moderate", validationAction="warn")
        print("validation mise à jour (moderate/warn)")




if __name__ == "__main__":
    provisionner()