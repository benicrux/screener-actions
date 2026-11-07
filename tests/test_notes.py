"""Vérifie quelques calculs de notes.py : liquidité, sociétés qui brûlent leur trésorerie,
bénéfice par action sans analystes."""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import notes  # noqa: E402


def societe(s, **k):
    base = dict(symbole=s, nom=s, industrie_en="Software—Application", devise_cours="USD",
                devise_comptes="USD", cours=10.0, capi=1e9, actions=1e8, ca=5e8, ebitda=1e8,
                tresorerie=2e8, dette=1e8, fcf=5e7, marge_nette=0.1, marge_op=0.15,
                bpa_12m=0.5, volume_moyen=20_000)
    base.update(k)
    return base


def test_indicateurs():
    d = pd.DataFrame([
        societe("SAINE"),
        # Brûle sa trésorerie : 40 M de pertes d'exploitation et 45 M consommés par an,
        # 30 M de trésorerie et 5 M de dettes : à peine plus de 6 mois de réserves
        societe("BRULE", ca=5e6, ebitda=-4e7, fcf=-4.5e7, tresorerie=3e7, dette=5e6, marge_nette=-9.0),
        # Même chose avec 10 ans de réserves
        societe("RESERVES", ca=5e6, ebitda=-4e7, fcf=-4e7, tresorerie=4.05e8, dette=5e6, marge_nette=-9.0),
        # Sans analystes, cours en livres et comptes en dollars : le BPA de Yahoo peut être
        # en livres (0,4 £ = 0,5 $) ou en dollars (0,5 $). Le bénéfice tiré des comptes
        # (5e8 × 10 % / 1e8 actions = 0,5 $) tranche dans les deux cas
        societe("EN_LIVRES", devise_cours="GBP", devise_comptes="USD", bpa_12m=0.4),
        societe("EN_DOLLARS", devise_cours="GBP", devise_comptes="USD", bpa_12m=0.5),
    ])
    r = notes.indicateurs(d, {"USD": 1.0, "GBP": 1.25, "EUR": 1.1}).set_index("symbole")
    # Liquidité : 20 000 actions × 10 $
    assert abs(r.loc["SAINE", "volume_usd"] - 200_000) < 1e-6
    # La société saine ne brûle rien ; les deux autres oui
    assert not r.loc["SAINE", "brule_tresorerie"]
    assert r.loc["BRULE", "brule_tresorerie"] and r.loc["RESERVES", "brule_tresorerie"]
    assert abs(r.loc["BRULE", "autonomie_ans"] - 25 / 45) < 1e-9
    # Pour la note : moins de 3 ans de réserves = comme une société endettée sans EBITDA ;
    # la trésorerie / CA (énorme, puisque le CA est minuscule) ne compte plus
    assert r.loc["BRULE", "levier_note"] == 99 and r.loc["RESERVES", "levier_note"] == 5
    assert np.isnan(r.loc["BRULE", "treso_note"]) and r.loc["SAINE", "treso_note"] == r.loc["SAINE", "treso_nette_ca"]
    # Les chiffres affichés, eux, ne changent pas
    assert r.loc["BRULE", "treso_nette_ca"] > 4
    # BPA : 0,5 $ dans les deux cas, donc un PER de 25 (cours 10 £ = 12,5 $). Avant, sans
    # analystes, le second était lu en livres (0,625 $) : PER de 20, faux
    assert abs(r.loc["EN_LIVRES", "per_12m_brut"] - 25) < 1e-9
    assert abs(r.loc["EN_DOLLARS", "per_12m_brut"] - 25) < 1e-9


if __name__ == "__main__":
    test_indicateurs()
    print("OK")
