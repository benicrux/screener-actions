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


def test_constituer_et_suivre():
    # Cours simulés : chaque action gagne 10 % entre le départ (30/10) et le 6/11, l'indice 2 %
    def barres(symbole, params):
        if symbole == "MANQUE":
            return [], None
        if "range" in params:
            return [("2026-11-05", 99.0), ("2026-11-06", 110.0 if symbole != "IWDA.AS" else 102.0)], "EUR"
        return [("2026-10-29", 98.0), ("2026-10-30", 100.0)], "EUR"
    with tempfile.TemporaryDirectory() as d:
        d = Path(d)
        temoin.TEMOIN, temoin.SITE = d / "temoin.json", d / "site" / "temoin.json"
        temoin.ACCUEIL, temoin.TABLEAU = d / "accueil.json", d / "screener.json"
        temoin._barres = barres
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
        fx = {"EUR": 1.1, "USD": 1.0}
        etat = {"portefeuilles": []}
        assert temoin.constituer(etat, dt.date(2026, 10, 31), fx) == []   # avant le premier semestre
        crees = temoin.constituer(etat, dt.date(2026, 11, 1), fx)
        assert crees == ["2026-11-radar", "2026-11-rallye"]
        p = etat["portefeuilles"][0]
        # MANQUE (sans cours) remplacée ; 5 au plus par pays, donc 15 avec 3 pays
        assert len(p["lignes"]) == 15 and p["lignes"][0]["s"] == "R0"
        assert sum(l["pays"] == "Japon" for l in p["lignes"]) == 5
        assert p["lignes"][0]["depart"] == "2026-10-30" and p["reference"]["s"] == "IWDA.AS"
        assert temoin.constituer(etat, dt.date(2026, 11, 2), fx) == []    # déjà constitués
        assert temoin.suivre(etat, dt.date(2026, 11, 7), fx) == 30
        assert abs(temoin.valeur(p) - 1.10) < 1e-9 and abs(p["reference"]["r"] - 1.02) < 1e-9
        assert p["suivi"][-1] == ["2026-11-06", 1.1, 1.02]


if __name__ == "__main__":
    test_semestre()
    test_choisir()
    test_valeur_et_points()
    test_constituer_et_suivre()
    print("OK")
