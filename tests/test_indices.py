"""Vérifie la lecture de la composition des grands indices (sans réseau, pages imitées)."""
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import indices  # noqa: E402

UNIVERS = pd.DataFrame([
    ("AAPL", "Apple Inc.", "US0378331005"), ("BRK-B", "Berkshire Hathaway Inc.", "US0846707026"),
    ("GOOGL", "Alphabet Inc.", "US02079K3059"), ("0005.HK", "HSBC Holdings plc", "GB0005405286"),
    ("9988.HK", "Alibaba Group Holding Limited", "KYG017191142"), ("7267.T", "Honda Motor Co., Ltd.", ""),
    ("543A.T", "Archion Corp.", ""), ("BT-A.L", "BT Group plc", "GB0030913577"),
    ("RR.L", "Rolls-Royce Holdings plc", "GB00B63H8491"), ("MC.PA", "LVMH Moët Hennessy Louis Vuitton SE", "FR0000121014"),
    ("AIR.PA", "Airbus SE", "NL0000235190"), ("RCI-B.TO", "Rogers Communications Inc.", ""),
    ("BF-A", "Brown-Forman Corporation", ""), ("601318.SS", "Ping An Insurance (Group) Company of China, Ltd.", ""),
    ("601939.SS", "China Construction Bank Corporation", ""), ("C6TB.F", "China Construction Bank Corporation Class H", ""),
], columns=["symbole", "nom", "isin"]).assign(continent="Asie")


def tableau(entetes, lignes, double=None):
    tete = "".join(f"<th>{e}</th>" for e in entetes)
    if double:
        tete = "".join(f'<th colspan="{n}">{e}</th>' for e, n in double) + "</tr><tr>" + tete
    corps = "".join("<tr>" + "".join(f"<td>{c}</td>" for c in l) + "</tr>" for l in lignes)
    return f'<table class="wikitable"><tr>{tete}</tr>{corps}</table>'


def test_conversion_des_codes():
    assert indices.symbole_yahoo("BRK.B", "us") == "BRK-B"
    assert indices.symbole_yahoo("NYSE: MMM[3]", "us") == "MMM"
    assert indices.symbole_yahoo("SEHK: 5", "hk") == "0005.HK"
    assert indices.symbole_yahoo(388.0, "hk") == "0388.HK"
    assert indices.symbole_yahoo("BT.A", ".L") == "BT-A.L"
    assert indices.symbole_yahoo("RR.", ".L") == "RR.L"
    assert indices.symbole_yahoo("RCI.B", ".TO") == "RCI-B.TO"
    assert indices.symbole_yahoo("BIP.UN", ".TO") == "BIP-UN.TO"
    assert indices.symbole_yahoo("M&M", ".NS") == "M&M.NS"
    assert indices.symbole_yahoo("MC.PA", "tel") == "MC.PA"
    assert indices.symbole_yahoo("NDA-FI.HE", "tel") == "NDA-FI.HE"
    assert indices.symbole_yahoo("MC", "tel") is None          # suffixe manquant : par le nom
    assert indices.symbole_yahoo("NOVN", "tel:.SW") == "NOVN.SW"
    assert indices.symbole_yahoo("NOVN.SW", "tel:.SW") == "NOVN.SW"
    assert indices.symbole_yahoo("", "us") is None
    assert indices.nom_simple("Alphabet Inc. (Class A)") == indices.nom_simple("Alphabet Inc.") == "alphabet"
    assert indices.nom_simple("LVMH Moët Hennessy Louis Vuitton SE") == "lvmh moet hennessy louis vuitton"


def test_choix_du_bon_tableau():
    composition = tableau(["Symbol", "Security", "GICS Sector"],
                          [("AAPL", "Apple Inc.", "IT"), ("BRK.B", "Berkshire Hathaway", "Fin"),
                           ("GOOGL", "Alphabet Inc. (Class A)", "Com"), ("ZZZZ", "Inconnue", "x")])
    changements = tableau(["Ticker", "Security", "Ticker", "Security"], [("A", "a", "B", "b")],
                          double=[("Added", 2), ("Removed", 2)])
    lignes = indices.lire_tableau(composition + changements, ("Symbol",), "us", 4)
    assert [l["symbole"] for l in lignes] == ["AAPL", "BRK-B", "GOOGL", "ZZZZ"]
    assert lignes[2]["nom"] == "Alphabet Inc. (Class A)"


def test_titres_dans_la_premiere_ligne():
    # Page du SMI : la ligne de titres est une ligne ordinaire du tableau
    page = tableau(["0", "1", "2"], [("Rank", "Name", "Ticker"), ("1", "Novartis International AG", "NOVN.SW"),
                                     ("2", "Roche Holding AG", "ROG.SW")])
    lignes = indices.lire_tableau(page, ("Ticker",), "tel:.SW", 2)
    assert [l["symbole"] for l in lignes] == ["NOVN.SW", "ROG.SW"] and lignes[1]["nom"] == "Roche Holding AG"


def test_hong_kong_japon_et_correspondance():
    corr = indices.Correspondance(UNIVERS)
    hk = indices.lire_tableau(tableau(["Ticker", "Name", "Sub-index"],
                                      [("SEHK: 5", "HSBC Holdings plc", "Finance"),
                                       ("SEHK: 9988", "Alibaba", "Commerce")]), ("Ticker",), "hk", 2)
    assert [l["symbole"] for l in hk] == ["0005.HK", "9988.HK"]
    page = ("<p>Le plus gros poids : Tokyo Electron (<a>TYO</a>: <a>8035</a>).</p><ul>"
            "<li><a>Honda Motor Co., Ltd.</a> ( <a>TYO</a>: <a>7267</a>)</li>"
            "<li><a>Archion Corp.</a> (TYO:&nbsp;543A)</li>"
            "<li>Tokyo Electron Ltd. (TYO: 8035)</li></ul>")
    jp = indices.lire_liste_japon(page)
    assert [l["symbole"] for l in jp] == ["8035.T", "7267.T", "543A.T"]
    # Par le code ISIN, puis par le nom, quand le symbole ne correspond pas
    trouver = lambda sym, nom, isin="": corr.trouver({"symbole": sym, "isin": isin, "nom": nom}, "Asie")
    assert trouver("AIR.DE", "", "NL0000235190") == ["AIR.PA"]
    assert trouver("MC", "LVMH Moët Hennessy Louis Vuitton") == ["MC.PA"]
    assert trouver("BF-B", "Brown–Forman") == ["BF-A"]                      # tiret long
    assert trouver("2318.HK", "Ping An Insurance") == ["601318.SS"]          # nom abrégé
    assert sorted(trouver("0939.HK", "China Construction Bank")) == ["601939.SS", "C6TB.F"]
    assert trouver("XXX", "Inconnue SA") == []
    assert trouver("YYY", "China") == []                                     # un seul mot : pas d'abrégé


def test_mise_a_jour_garde_l_ancienne_liste():
    corr = indices.Correspondance(UNIVERS)
    sp = tableau(["Symbol", "Security"], [("AAPL", "Apple"), ("BRK.B", "Berkshire"), ("GOOGL", "Alphabet")])
    # Une seule page « réussit » ; les autres sont en panne
    def lire(page):
        if page == "List_of_S%26P_500_companies":
            return sp
        raise OSError("HTTP Error 503")

    vieux = {"indices": {"cac40": {"membres": ["MC.PA", "AIR.PA"], "lu": "2026-08-01", "lues": 40},
                         "dax": {"membres": ["SAP.DE"], "lu": "2026-10-20", "lues": 40}}}
    # Le S&P 500 imité ne compte que 3 sociétés
    liste = [indices.INDICES[0][:6] + (3,) + indices.INDICES[0][7:]] + indices.INDICES[1:]
    n = indices.mettre_a_jour(vieux, lire, corr, "2026-10-27", liste=liste)
    i = n["indices"]
    assert i["sp500"]["membres"] == ["AAPL", "BRK-B", "GOOGL"] and i["sp500"]["lu"] == "2026-10-27"
    # Relecture en échec : ancienne composition gardée, date de l'échec notée
    assert i["cac40"]["membres"] == ["MC.PA", "AIR.PA"] and i["cac40"]["echec_depuis"] == "2026-10-27"
    assert "503" in i["cac40"]["erreur"]
    # Lu il y a moins de 30 jours : pas relu
    assert i["dax"]["membres"] == ["SAP.DE"] and not i["dax"].get("erreur")
    # Jamais lu et en échec : liste vide, échec daté
    assert i["nikkei225"]["membres"] == [] and i["nikkei225"]["echec_depuis"] == "2026-10-27"
    # La nuit suivante, l'échec garde sa date de début
    n2 = indices.mettre_a_jour(n, lire, corr, "2026-10-28", liste=liste)
    assert n2["indices"]["cac40"]["echec_depuis"] == "2026-10-27"


def test_page_qui_ne_ressemble_pas_a_l_indice():
    corr = indices.Correspondance(UNIVERS)
    lignes = [{"code": "AAPL", "symbole": "AAPL", "nom": "Apple", "isin": ""}]
    try:
        indices.composer(lignes, corr, 500)
        assert False, "une page de 1 ligne pour 500 attendues doit être refusée"
    except ValueError as e:
        assert "500 attendues" in str(e)
    inconnues = [{"code": f"X{k}", "symbole": f"X{k}", "nom": f"Inconnue {k}", "isin": ""} for k in range(10)]
    try:
        indices.composer(inconnues, corr, 10)
        assert False, "des sociétés introuvables doivent faire refuser la page"
    except ValueError as e:
        assert "retrouvées" in str(e)


if __name__ == "__main__":
    for nom, f in list(globals().items()):
        if nom.startswith("test_"):
            f()
    print("Tests des grands indices : OK")
