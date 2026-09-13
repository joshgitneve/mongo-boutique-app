import argparse
import sys

from bson import Decimal128

from db import get_db
from repository import CatalogueRepository, ErreurCatalogue
from provision import provisionner

CATALOGUE_DEMO = [
    {"sku": "KBD-0010", "nom": "Clavier TKL silencieux", "categorie": "clavier",
     "prix": Decimal128("119.00"), "stock": 8, "tags": ["clavier"], "switches": "marron"},
    {"sku": "SCR-0011", "nom": "Ecran 24 pouces", "categorie": "ecran",
     "prix": Decimal128("179.00"), "stock": 15, "pouces": 24, "resolution": "1920x1080"},
    {"sku": "LIV-0014", "nom": "MongoDB en pratique", "categorie": "livre",
     "prix": Decimal128("42.00"), "stock": 30, "auteur": "K. Chodorow", "pages": 514},
    {"sku": "ABO-0013", "nom": "Support Pro mensuel", "categorie": "abonnement",
     "prix": Decimal128("19.00"), "periodicite": "mensuelle"},      # pas de stock
]


def main() -> int:
# ArgumentParser est une classe définie dans le module argparse. Cette ligne crée un nouvel objet, une instance de cette classe, et le stocke dans parser.
    parser = argparse.ArgumentParser(
                        prog='MongoDB catalogue interface',
                        description='Maps commands to repository.py functions',
                        )
    # pour l'instant parser est vide - on va progressivement lui apprendre quelles commandes et quels arguments sont valides
    # Plus tard, quand on appellera parseur.parse_args(), objet lira réellement ce que l'utilisateur a tapé dans le 
    # terminal (sys.argv), vérifiera que c'est valide selon les règles que l'on lui a données, et renverra un objet propre 
    # (args) avec chaque valeur accessible comme attribut (args.sku, args.categorie...).

    # add_subparsers(...) est une méthode appelée sur parseur qui gere les sous-commandes. Don't bloody ask why you need this to add parsers!
    # it's all about the fact that you get back an object that has just what you asked for each time (grosso modo @_@ ). Here we're adding 
    # the capacity to add parsers and setting up where they are arranged (command). required=True meaning just python app.py will error.
    sub = parser.add_subparsers(dest="command", required=True)

    #creates a parser that links the command "init" to the creation of the collection (provisionner()) and the index config (initialiser()). 
    sub.add_parser("init", help="create a catalog with useful indexing")
    #creates a parser that links the command "seed" to importer() - mass import of products
    sub.add_parser("seed", help="Add products using a pre-cleaned list of dictionaries, each representing a product")

    sub.add_parser("audit", help="Take a look at the collection and what fields each product has")
    sub.add_parser("stats")

    p = sub.add_parser("list")
    p.add_argument("--categorie")
    p.add_argument("--max-prix")

    p = sub.add_parser("show")
    p.add_argument("sku")

    p = sub.add_parser("add")
    p.add_argument("sku")
    p.add_argument("nom")
    p.add_argument("categorie")
    p.add_argument("prix")
    p.add_argument("--stock", type=int)
    p.add_argument("specifiques", nargs="*", help="champs additionnels sou forme cle=valeur")

    p = sub.add_parser("set")
    p.add_argument("sku")
    p.add_argument("champ")
    p.add_argument("valeur")

    p = sub.add_parser("reserve")
    p.add_argument("sku")
    p.add_argument("n", type=int)

    p = sub.add_parser("delete")
    p.add_argument("sku")
    p.add_argument("--hard", action="store_true")

    args = parser.parse_args() # lit sys.arv[1:] - donc cette ligne sauveguarde les args entrées en CLI à la variable args.  
    # argparse découpe cette liste de mots selon les règles que l'on a définies avec add_argument(...) (position, ou noms --xxx),
    #  et renvoie un objet args bien structuré, avec des attributs nommés
    depot = CatalogueRepository(get_db())

# The dispatch
    try:
        if args.command == "init":
            provisionner()
            depot.initialiser()
            print("collection initialisée")

        elif args.command == "seed":
            depot.importer(CATALOGUE_DEMO)
            print("products imported with success")

        elif args.command == "audit":
            total = depot.compter(inclure_supprimes=True)
            for ligne in depot.auditer():
                taux = 100 * ligne["presents"] / total
                alerte = "  ⚠️ plusieurs types" if len(ligne["types"]) > 1 else ""
                print(f"{ligne['_id']:<22}{taux}%  {', '.join(sorted(ligne['types']))}{alerte}")

        elif args.command == "stats":
            for ligne in depot.statistiques():
                print(f"{ligne['_id']:<22}{ligne['nombre']:>2}  prix moyen: {ligne['prix_moyen']}  stock: {ligne['stock_total']}   sans stock: {ligne['sans_stock']} ")

        elif args.command == "list":
            apres = None
            while True:
                page = depot.lister(args.categorie, args.max_prix, apres=apres)
                if not page:
                    break
                for produit in page:
                    print(f"{produit['sku']:<12}{produit['nom']:<32}{str(produit['prix']):>9} €")
                apres = page[-1]["_id"]
                if len(page) < 20:          # moins que la taille de page = dernière page
                    break
                if input("Page suivante ? (o/n) ").strip().lower() != "o":
                    break

        elif args.command == "show":
            commun, specifique = depot.decouper(depot.par_sku(args.sku))
            for cle, valeur in commun.items():
                print(f"{cle:<16}: {valeur}")

            if specifique:
                print("--- spécifique à la famille ---")
                for cle, valeur in specifique.items():
                    print(f"{cle:<16}: {valeur}")

        elif args.command == "add":
            specifiques = dict(item.split("=", 1) for item in args.specifiques)
            depot.creer(args.sku, args.nom, args.categorie, args.prix, args.stock, **specifiques)
            print("créé")

        elif args.commend == "set":
            depot.modifier(args.sku, {args.champ: args.valeur})
            print("champ ajouté")

        elif args.command == "reserve":
            depot.reserver(args.sku, args.n)
            print("Articles résérvés")

        elif args.command == "delete":
            if args.hard:
                depot.supprimer_definitivement(args.sku)
            else:
                depot.supprimer(args.sku)
        
    except ErreurCatalogue as exc:
        print(f"erreur : {exc}", file=sys.stderr)
        return 1
    return 0

if __name__=="__main__":
    raise SystemExit(main())