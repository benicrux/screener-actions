"""Vérifie le radar de la page d'accueil et le suivi des dates d'entrée."""
import json
import sys
import tempfile
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import rendu  # noqa: E402


def societe(s, **k):
    base = dict(symbole=s, n_investisseur=85, n_valorisation=80, n_situation_fi=60,
                capi_usd=5e8, ca_usd=2e8, pays=f"Pays {s}", financiere=False,
                fin_exercice="2025-12-31")
    base.update(k)
    return base


def test_radar():
    v = pd.DataFrame([
        societe("BON"),
        societe("MIEUX", n_investisseur=92),
        societe("BANQUE", n_situation_fi=None),            # banque : pas de note de situation fi.
        societe("CHERE", n_valorisation=50),
        societe("FRAGILE", n_situation_fi=20),
        societe("PETITE", capi_usd=5e7),
        societe("SANS_CA", ca_usd=None),                   # véhicule sans chiffre d'affaires
        societe("MOYENNE", n_investisseur=70),
        societe("MUETTE", fin_exercice="2023-12-31"),     # plus de comptes depuis 2023
    ])
    r = rendu.radar(v, usd_par_eur=1.1)
    assert list(r["symbole"]) == ["MIEUX", "BON", "BANQUE"], list(r["symbole"])


def test_rallye():
    # 20 sociétés ; 0 à 4 et 15 très bon marché ; 1 en perte, 2 trop diluée, 3 sans trésorerie
    lignes = []
    for i in range(20):
        pas_cher = i in (0, 1, 2, 3, 4, 15)
        lignes.append(societe(f"S{i}", capi_usd=(i + 1.5) * 1e8, n_investisseur=60 + i,
                              ebitda_ve=0.30 if pas_cher else 0.05,
                              actif_prix=1.5 if pas_cher else 0.5,
                              marge_nette_ajustee=-0.05 if i == 1 else (None if i == 4 else 0.08),
                              per_12m=9.0, dilution_3a=0.25 if i == 2 else 0.0,
                              rendement_tresorerie=-0.02 if i == 3 else 0.06))
    lignes.append(societe("BANQUE", capi_usd=2e8, financiere=True, ebitda_ve=0.5, actif_prix=3,
                          marge_nette_ajustee=0.2, rendement_tresorerie=0.1))
    r = rendu.rallye(pd.DataFrame(lignes), usd_par_eur=1.0)
    # 4 : marge inconnue mais PER positif, donc bénéficiaire ; la mieux notée d'abord
    assert list(r["symbole"]) == ["S4", "S0"], list(r["symbole"])


def test_dates_entree():
    with tempfile.TemporaryDirectory() as d:
        rendu.RADAR_ENTREES = Path(d) / "radar_entrees.json"
        # tout premier calcul : date inconnue (personne n'est « nouveau »)
        assert rendu.dates_entree(["A", "B"], "2026-10-26") == {"A": "", "B": ""}
        # le lendemain : A reste, B sort, C entre
        assert rendu.dates_entree(["A", "C"], "2026-10-27") == {"A": "", "C": "2026-10-27"}
        # B revient : nouvelle date d'entrée ; C garde la sienne
        r = rendu.dates_entree(["A", "B", "C"], "2026-10-28")
        assert r["B"] == "2026-10-28" and r["C"] == "2026-10-27"
        assert json.loads(rendu.RADAR_ENTREES.read_text())["C"] == "2026-10-27"


def test_grands_indices():
    with tempfile.TemporaryDirectory() as d:
        rendu.INDICES = Path(d) / "indices.json"
        assert rendu.grands_indices({"A"}) == []                    # pas encore lu
        rendu.INDICES.write_text(json.dumps({"indices": {
            "cac40": {"nom": "CAC 40", "continent": "Europe", "lu": "2026-10-27", "membres": ["A", "Z"]},
            "dax": {"nom": "DAX", "continent": "Europe", "lu": None, "membres": []}}}))
        i = rendu.grands_indices({"A", "B"})
        # seules les sociétés affichées sur le site ; un indice vide est masqué
        assert [x["id"] for x in i] == ["cac40"] and i[0]["membres"] == ["A"]


if __name__ == "__main__":
    test_radar()
    test_rallye()
    test_dates_entree()
    test_grands_indices()
    print("OK")
