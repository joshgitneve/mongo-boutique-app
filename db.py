"""Connexion unique à MongoDB, partagée par toute l'application.
    À retenir:    - MongoClient(...) est paresseux — il ne se connecte pas réellement à la création, 
                    seulement à la première vraie opération (ping, find, etc.).
                  - config externalisée dans .env.
                  - 'singleton' via lru_cache. MongoClient est créé une fois et mis en cache.
"""
import os
from functools import lru_cache

from dotenv import load_dotenv
from pymongo import MongoClient
from pymongo.database import Database

load_dotenv()


@lru_cache(maxsize=1)          # ← un seul client par processus
def get_client() -> MongoClient:
    return MongoClient(
        os.environ["MONGODB_URI"],
        serverSelectionTimeoutMS=5_000,   # échouer vite si le serveur est absent
        connectTimeoutMS=5_000,
        tz_aware=True,                    # renvoie des datetime "aware" (UTC)
        uuidRepresentation="standard",
        appname=os.getenv("APP_NAME", "boutique"),
    )


def get_db() -> Database:
    """ne crée aucune nouvelle connexion — un Database est juste un objet Python léger qui référence le client. 
    Donc appeler get_db() plusieurs fois ne coûte rien, grâce au cache sur get_client().

    Returns:
        Database: _description_
    """
    return get_client()[os.environ.get("MONGODB_DB", "boutique")]


if __name__ == "__main__":
    client = get_client()
    client.admin.command("ping")    # commande brut envoyé au serveur. Comme MongoClient est paresseux, 
                                    # c'est cette ligne précise qui force la premiere vraie connexion réseau au serveur - c'est donc elle 
                                    # qui planterait avec une erreur claire si mongo n'est pas lancé ou si l'URL est fausse.
    
    print("Connecté à MongoDB", client.server_info()["version"])
    print("Bases visibles :", client.list_database_names())