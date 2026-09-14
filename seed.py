from datetime import datetime, timezone

from bson import Decimal128
from pymongo import UpdateOne

from db import get_db

db = get_db()

now = datetime.now(timezone.utc)

catalogue = [
    # --- Claviers ---
    {
        "sku": "KBD-0011", "nom": "Clavier TKL silencieux", "categorie": "clavier",
        "prix": Decimal128("119.00"), "stock": 18,
        "switch": "linéaire silencieux", "retroeclairage": True, "sans_fil": False,
    },
    {
        "sku": "KBD-0012", "nom": "Clavier compact 60%", "categorie": "clavier",
        "prix": Decimal128("89.90"), "stock": 25,
        "switch": "mécanique clicky", "retroeclairage": True, "sans_fil": True,
    },
    # --- Écrans ---
    {
        "sku": "SCR-0013", "nom": "Écran 27 pouces 144Hz", "categorie": "ecran",
        "prix": Decimal128("249.00"), "stock": 7,
        "pouces": 27, "resolution": "2560x1440", "hz": 144,
    },
    {
        "sku": "SCR-0014", "nom": "Écran 34 pouces incurvé", "categorie": "ecran",
        "prix": Decimal128("449.00"), "stock": 3,
        "pouces": 34, "resolution": "3440x1440", "hz": 100,
    },
    # --- Livre ---
    {
        "sku": "LIV-0015", "nom": "MongoDB en pratique", "categorie": "livre",
        "prix": Decimal128("39.90"), "stock": 50,
        "auteur": "J. Dupont", "isbn": "978-2-1234-5678-9", "pages": 312,
    },
    # --- Abonnement (service, pas de stock) ---
    {
        "sku": "ABO-0016", "nom": "Support Pro 1 an", "categorie": "abonnement",
        "prix": Decimal128("190.00"),
        "periodicite": "annuelle", "renouvellement_auto": True,
    },
]

def peupler() -> None:
    db = get_db()
    operations = [
        UpdateOne(
            {"sku": produit["sku"]},                                    # filtre : cherche un document existant avec ce sku
            {"$set": produit,                                           # si trouvé (ou créé) : (re)définit tous les champs de "produit"
            "$setOnInsert": {"cree_le": now}},                          # mais "cree_le" n'est écrit QUE lors de la création (upsert) — jamais réécrit sur une mise à jour
            upsert=True,                                                # si aucun document ne correspond au filtre, en créer un nouveau plutôt que ne rien faire
        )
        for produit in catalogue
    ]
    resultat = db.produits.bulk_write(operations, ordered=False)        # ordered=False - plus rapide, et n'abandonne pas au premier échec.
    print(f"créés : {resultat.upserted_count} - mis à jour : {resultat.modified_count}")
    print("total en base :", db.produits.count_documents({}))           # combien de documents maintenant?


if __name__ == "__main__":
    peupler()