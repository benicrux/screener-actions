"""Vérifie le portefeuille témoin : semestres, choix des sociétés, valeur, suivi (sans réseau)."""
import datetime as dt
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import temoin  # noqa: E402


def test_semestre():
    assert temoin.semestre(dt.date(2026, 11, 1)) == "2026-11"
    assert temoin.semestre(dt.date(2027, 3, 15)) == "2026-11"
    assert temoin.semestre(dt.date(2027, 5, 1)) == "2027-05"
    assert temoin.semestre(dt.date(2027, 10, 31)) == "2027-05"


def test_choisir():
    symboles = [f"J{i}" for i in range(8)] + ["A", "B", "C"]
    pays = {**{f"J{i}": "Japon" for i in range(8)}, "A": "France", "B": "Inde", "C": "Inde"}
    # 5 au plus par pays, dans l'ordre de la liste ; une société sans cours est remplacée
    assert temoin.choisir(symboles, pays, taille=7, valide=lambda s: s != "J1") == \
        ["J0", "J2", "J3", "J4", "J5", "A", "B"]


def test_valeur_et_points():
    p = {"lignes": [{"r": 1.2, "eur": 1.0, "eur0": 1.0},      # +20 %
                    {"r": 1.0, "eur": 0.9, "eur0": 1.0}]}     # devise en baisse de 10 %
    assert abs(temoin.valeur(p) - 1.05) < 1e-12
    s = temoin.noter_point([], "2026-11-02", 1.0, 1.0)
    s = temoin.noter_point(s, "2026-11-04", 1.01, 1.0)        # même semaine : remplacé
    s = temoin.noter_point(s, "2026-11-09", 1.02, 1.01)       # semaine suivante : ajouté
    assert [x[0] for x in s] == ["2026-11-04", "2026-11-09"]
    fx = {"EUR": 1.10, "GBP": 1.30, "JPY": 0.0066}
    assert abs(temoin.euros_par_unite("GBp", fx) - 1.30 / 1.10) < 1e-12   # pence : la livre
    assert abs(temoin.euros_par_unite("USD", fx) - 1 / 1.10) < 1e-12
    assert temoin.euros_par_unite("XYZ", fx) is None


def _faux_yahoo(cours_indice=102.0):
    """Cours simulés : départ (premier jour après le 1er novembre) à 100, 110 le 6 novembre ;
    l'indice finit à 102. MANQUE n'a aucun cours."""
    def ts(j):
        return temoin._ts(j)
    serie = [("2026-10-29", 98.0), ("2026-10-30", 100.0), ("2026-11-02", 100.0), ("2026-11-03", 101.0)]

    def barres(symbole, params):
        if symbole == "MANQUE":
            return [], None
        fin = 110.0 if symbole != "IWDA.AS" else cours_indice
        if "range" in params:
            return [("2026-11-05", 99.0), ("2026-11-06", fin)], "EUR"
        p1, p2 = params["period1"], params["period2"]
        return [b for b in serie + [("2026-11-06", fin)] if p1 <= ts(b[0]) <= p2], "EUR"
    return barres


def _preparer(d):
    temoin.TEMOIN, temoin.SITE = d / "temoin.json", d / "site" / "temoin.json"
    temoin.ACCUEIL, temoin.TABLEAU = d / "accueil.json", d / "screener.json"
    temoin._barres = _faux_yahoo()
    temoin.time.sleep = lambda s: None
    temoin.ACCUEIL.write_text(json.dumps({
        "radar": [["MANQUE", ""]] + [[f"R{i}", ""] for i in range(25)],
        "rallye": [[f"Y{i}", ""] for i in range(25)]}))
    # Pays : 8 sociétés sur 25 au Japon (0, 3, 6…), les autres réparties sur 2 pays
    symboles = ["MANQUE"] + [f"R{i}" for i in range(25)] + [f"Y{i}" for i in range(25)]
    pays = lambda s: 0 if s == "MANQUE" else (0 if int(s[1:]) % 3 == 0 else int(s[1:]) % 3)
    temoin.TABLEAU.write_text(json.dumps({"champs": ["s", "n", "p", "dv"],
                                          "dicos": {"p": ["Japon", "France", "Inde"], "dv": ["EUR"]},
                                          "lignes": [[s, f"Société {s}", pays(s), 0] for s in symboles]}))


def test_constituer_et_suivre():
    with tempfile.TemporaryDirectory() as d:
        _preparer(Path(d))
        fx = {"EUR": 1.1, "USD": 1.0}
        etat = {"portefeuilles": []}
        assert temoin.constituer(etat, dt.date(2026, 10, 31), fx) == []   # avant le premier semestre
        crees = temoin.constituer(etat, dt.date(2026, 11, 1), fx)
        assert crees == ["2026-11-radar", "2026-11-rallye"]
        p = etat["portefeuilles"][0]
        # MANQUE (sans cours) remplacée ; 5 au plus par pays, donc 15 avec 3 pays
        assert len(p["lignes"]) == 15 and p["lignes"][0]["s"] == "R0"
        assert sum(l["pays"] == "Japon" for l in p["lignes"]) == 5
        assert p["lignes"][0]["depart"] is None and p["reference"]["s"] == "IWDA.AS"
        assert temoin.constituer(etat, dt.date(2026, 11, 2), fx) == []    # déjà constitués
        assert temoin.suivre(etat, dt.date(2026, 11, 7), fx) == 30
        # Départ : premier cours après la constitution (2 novembre), pas celui de la veille
        assert p["lignes"][0]["depart"] == "2026-11-02" and p["reference"]["depart"] == "2026-11-02"
        assert abs(temoin.valeur(p) - 1.10) < 1e-9 and abs(p["reference"]["r"] - 1.02) < 1e-9
        assert p["suivi"][-1] == ["2026-11-06", 1.1, 1.02]


def test_ancien_depart_corrige():
    with tempfile.TemporaryDirectory() as d:
        _preparer(Path(d))
        ancien = {"portefeuilles": [{
            "id": "2026-11-radar", "semestre": "2026-11", "liste": "radar", "nom_liste": "Radar des pépites",
            "cree_le": "2026-11-01", "fin": "2031-11-01",
            "reference": {"s": "IWDA.AS", "depart": "2026-10-30", "r": 1.0, "maj": "2026-10-30"},
            "lignes": [{"s": "R1", "nom": "R1", "pays": "France", "devise": "EUR", "depart": "2026-10-30",
                        "eur0": 0.9, "eur": 0.9, "r": 1.0, "maj": "2026-10-30"}],
            "suivi": [["2026-10-30", 1.0, 1.0]]}]}
        temoin.TEMOIN.write_text(json.dumps(ancien))
        etat = temoin.charger()
        p = etat["portefeuilles"][0]
        assert p["depart_apres_constitution"] and p["lignes"][0]["depart"] is None and p["suivi"] == []
        temoin.suivre(etat, dt.date(2026, 11, 7), {"EUR": 1.1})
        assert p["lignes"][0]["depart"] == "2026-11-02" and p["suivi"][-1][1] == 1.1


if __name__ == "__main__":
    test_semestre()
    test_choisir()
    test_valeur_et_points()
    test_constituer_et_suivre()
    test_ancien_depart_corrige()
    print("OK")
