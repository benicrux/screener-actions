"""Vérifie les règles des deux listes de l'accueil (radar, « Rallye 5 ans »), le plafond par
pays et la mesure de la dilution."""
import sys
import tempfile
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import listes  # noqa: E402
import notes  # noqa: E402


def S(valeurs):
    return pd.Series(valeurs, dtype=float)


def test_radar():
    note = S([80, 80, 80, 80, 70])
    val = S([70, 60, 70, 70, 70])
    sit = S([50, 50, None, 20, 50])       # non notée (banque) : acceptée ; 20 : fragile
    capi = S([2e8] * 5)
    assert list(listes.radar(note, val, sit, capi)) == [True, False, True, False, False]


def test_rallye():
    # 20 sociétés de 150 M€ à 2 Md€ ; 0 à 4 et 15 très bon marché sur les deux mesures
    n = 20
    capi = S([(i + 1.5) * 1e8 for i in range(n)])
    pas_cher = [0, 1, 2, 3, 4, 15]
    ebitda_ve = S([0.30 if i in pas_cher else 0.05 for i in range(n)])
    actif_prix = S([1.5 if i in pas_cher else 0.5 for i in range(n)])
    benef = pd.Series([i != 1 for i in range(n)])                 # 1 : en perte
    fin = pd.Series([False] * n)
    dil = S([0.25 if i == 2 else 0.0 for i in range(n)])           # 2 : trop diluée
    tres = pd.Series([False if i == 3 else (None if i == 4 else True) for i in range(n)])  # 3 : FCF < 0
    m = listes.rallye(capi, ebitda_ve, actif_prix, benef, fin, dil, tres)
    # 15 est trop grande ; 4 (trésorerie inconnue) est gardée
    assert list(m[m].index) == [0, 4], list(m[m].index)

    # Les sociétés financières ne comptent pas, ni dans la liste ni dans les parts
    fin2 = pd.Series([i == 0 for i in range(n)])
    m2 = listes.rallye(capi, ebitda_ve, actif_prix, benef, fin2, dil, tres)
    assert list(m2[m2].index) == [4]

    # Par date (tests sur le passé) : les parts se calculent date par date
    groupe = pd.Series(["a"] * n)
    m3 = listes.rallye(capi, ebitda_ve, actif_prix, benef, fin, dil, tres, groupe=groupe)
    assert list(m3[m3].index) == [0, 4]


def test_plafond_pays():
    # 10 sociétés japonaises et 8 pays avec une seule : le Japon garde ses 2 meilleures
    pays = pd.Series(["JP"] * 10 + [f"P{i}" for i in range(8)])
    masque = pd.Series([True] * 18)
    rang = S(list(range(10)) + [50] * 8)          # au Japon, les mieux classées : 9 et 8
    r = listes.plafond_pays(pays, masque, rang)
    japon = [i for i in r[r].index if pays[i] == "JP"]
    assert sorted(japon) == [8, 9] and r.sum() == 10
    assert (pays[r].value_counts() / r.sum()).max() <= 0.25
    # Une société hors liste le reste
    masque2 = masque.copy(); masque2[17] = False
    assert not listes.plafond_pays(pays, masque2, rang)[17]
    # Liste vide : rien ne change
    vide = pd.Series([False] * 18)
    assert listes.plafond_pays(pays, vide, rang).sum() == 0


def test_dilution():
    lignes = []
    def ajoute(s, actions):
        for k, a in enumerate(actions):
            lignes.append({"symbole": s, "fin": f"{2021 + k}-12-31", "actions": a})
    ajoute("STABLE", [100, 100, 100, 100])
    ajoute("DILUEE", [100, 110, 121, 133.1])
    ajoute("DIVISION", [100, 200, 200, 210])      # division 2 pour 1, puis +5 %
    ajoute("RACHAT", [100, 95, 90])
    ajoute("SEULE", [100])
    ajoute("VIEILLE", [50, 100, 100, 100, 100])   # seuls les 4 derniers exercices comptent
    with tempfile.TemporaryDirectory() as d:
        chemin = Path(d) / "comptes.csv"
        pd.DataFrame(lignes).to_csv(chemin, index=False)
        r = notes.dilution_3a(chemin)
    assert abs(r["STABLE"]) < 1e-9
    assert abs(r["DILUEE"] - 0.331) < 1e-6
    assert abs(r["DIVISION"] - 0.05) < 1e-6
    assert abs(r["RACHAT"] + 0.10) < 1e-6
    assert "SEULE" not in r
    assert abs(r["VIEILLE"]) < 1e-9
    assert notes.dilution_3a(Path("/nexiste/pas.csv")).empty


if __name__ == "__main__":
    test_radar()
    test_rallye()
    test_plafond_pays()
    test_dilution()
    print("OK")
