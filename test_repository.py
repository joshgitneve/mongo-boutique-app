import pytest
from bson import Decimal128

from db import get_client
from repository import (CatalogueRepository, DocumentInvalide, ProduitDejaExistant,
                        ProduitIntrouvable, StockInsuffisant)
@pytest.fixture
def depot():
    client = get_client()
    base = client['boutique_test']
    dep = CatalogueRepository(base) # the collection 'products' is created here -> see this class in repository.py
    dep.initialiser()
    yield dep
    client.drop_database('boutique_test')

def test_creer_puis_lire(depot):
    depot.creer("MON-0001", "Big Monitor", "ecran", "299.00", 5)
    product = depot.par_sku("MON-0001")
    assert product["sku"] == "MON-0001"
    assert product["nom"] == "Big Monitor"
    assert product["categorie"] == "ecran"
    assert product["stock"] == 5
    assert product["schema_version"] == 1

def test_sku_unique(depot):
    depot.creer("MON-0001", "Monitor", "ecran", "99.00")
    with pytest.raises(ProduitDejaExistant):
        depot.creer("MON-0001", "Another monitor", "ecran", "288.00")

def test_champs_specifiques_conserves(depot):
    depot.creer("SCR-0001", "Ecran", "ecran", "199.00", stock=3,
                pouces=27, resolution="2560x1440")
    produit = depot.par_sku("SCR-0001")
    assert produit["pouces"] == 27
    commun, specifique = depot.decouper(produit)
    assert set(specifique) == {"pouces", "resolution"}
    assert "prix" in commun


# ----------------------------------------------------------------- read
def test_produit_sans_stock(depot):
    """Un abonnement n'a pas de champ stock : rien ne doit casser."""
    depot.creer("ABO-0001", "Support", "abonnement", "19.00", periodicite="mensuelle")
    produit = depot.par_sku("ABO-0001")
    assert "stock" not in produit          # champ ABSENT, pas à zéro
    assert produit.get("stock") is None
    with pytest.raises(StockInsuffisant):
        depot.reserver("ABO-0001", 1)


def test_lister_filtre_et_pagination(depot):
    for i in range(5):
        depot.creer(f"KBD-000{i}", f"Clavier {i}", "clavier", "99.00", stock=1)
    depot.creer("LIV-0001", "Livre", "livre", "20.00", stock=1)

    assert len(depot.lister(categorie="clavier")) == 5
    assert len(depot.lister(taille=2)) == 2

    page1 = depot.lister(taille=2)
    page2 = depot.lister(apres=page1[-1]["_id"], taille=2)
    assert {p["sku"] for p in page1} & {p["sku"] for p in page2} == set()


def test_produit_introuvable(depot):
    with pytest.raises(ProduitIntrouvable):
        depot.par_sku("INEXISTANT")
    # with pytest.raises(ProduitIntrouvable): # need to to develop par_id for this test
    #     depot.par_id("pas-un-objectid")


# --------------------------------------------------------------- update
def test_modifier(depot):
    depot.creer("KBD-0001", "Clavier", "clavier", "99.00", stock=5)
    assert depot.modifier("KBD-0001", {"nom": "Clavier v2"}) is True
    assert depot.modifier("KBD-0001", {"nom": "Clavier v2"}) is False   # test va toujours échouer avec l'implementation tel quel car "maj_le" change à chaque modif.
    assert depot.par_sku("KBD-0001")["nom"] == "Clavier v2"
    assert "maj_le" in depot.par_sku("KBD-0001")


def test_modifier_refuse_les_operateurs(depot):
    """Protection contre l'injection d'opérateurs venue d'un formulaire."""
    depot.creer("KBD-0001", "Clavier", "clavier", "99.00")
    with pytest.raises(DocumentInvalide):
        depot.modifier("KBD-0001", {"$set": {"prix": 0}})


def test_reservation_atomique(depot):
    depot.creer("KBD-0001", "Clavier", "clavier", "99.00", stock=3)
    assert depot.reserver("KBD-0001", 2)["stock"] == 1
    with pytest.raises(StockInsuffisant):
        depot.reserver("KBD-0001", 2)              # il n'en reste qu'un
    assert depot.par_sku("KBD-0001")["stock"] == 1  # rien n'a été décrémenté


# --------------------------------------------------------------- delete
def test_suppression_logique(depot):
    depot.creer("KBD-0001", "Clavier", "clavier", "99.00")
    depot.supprimer("KBD-0001")
    with pytest.raises(ProduitIntrouvable):
        depot.par_sku("KBD-0001")
    assert depot.par_sku("KBD-0001", inclure_supprimes=True)["sku"] == "KBD-0001"


def test_suppression_definitive(depot):
    depot.creer("KBD-0001", "Clavier", "clavier", "99.00")
    depot.supprimer_definitivement("KBD-0001")
    with pytest.raises(ProduitIntrouvable):
        depot.par_sku("KBD-0001", inclure_supprimes=True)


# ---------------------------------------------------------------- import
def test_import_reexecutable(depot):
    catalogue = [{"sku": "A-0001", "nom": "A", "categorie": "livre",
                  "prix": Decimal128("10.00")}]
    assert depot.importer(catalogue) == (1, 0)      # créé
    depot.importer(catalogue)                        # relancé : pas de doublon
    assert depot.compter() == 1

    cree_le = depot.par_sku("A-0001")["cree_le"]
    depot.importer([{**catalogue[0], "nom": "A modifié"}])
    produit = depot.par_sku("A-0001")
    assert produit["nom"] == "A modifié"
    assert produit["cree_le"] == cree_le             # $setOnInsert : date préservée


def test_statistiques_tolerent_les_champs_absents(depot):
    depot.creer("KBD-0001", "Clavier", "clavier", "99.00", stock=5)
    depot.creer("ABO-0001", "Support", "abonnement", "19.00")     # sans stock
    stats = {ligne["_id"]: ligne for ligne in depot.statistiques()}
    assert stats["clavier"]["stock_total"] == 5
    assert stats["abonnement"]["stock_total"] == 0
    assert stats["abonnement"]["sans_stock"] == 1
