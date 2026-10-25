"""Vérifie la lecture des comptes de la SEC et la correction des divisions d'actions."""
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from retro_us import _corriger_divisions, comptes_annuels  # noqa: E402


def fait(debut, fin, val, publie, forme="10-K"):
    f = {"end": fin, "val": val, "filed": publie, "form": forme, "fy": int(fin[:4]), "fp": "FY"}
    if debut:
        f["start"] = debut
    return f


FAITS = {"facts": {"us-gaap": {
    # Changement de poste en 2018 (norme ASC 606), et chiffres repris l'année suivante
    "SalesRevenueNet": {"units": {"USD": [
        fait("2016-01-01", "2016-12-31", 100.0, "2017-02-20"),
        fait("2016-01-01", "2016-12-31", 101.0, "2018-02-20"),   # repris plus tard : ignoré
        fait("2017-10-01", "2017-12-31", 30.0, "2018-02-20"),    # trimestre : ignoré
        fait("2017-01-01", "2017-12-31", 120.0, "2018-02-20"),
    ]}},
    "RevenueFromContractWithCustomerExcludingAssessedTax": {"units": {"USD": [
        fait("2018-01-01", "2018-12-31", 150.0, "2019-02-25"),
    ]}},
    "NetIncomeLoss": {"units": {"USD": [
        fait("2016-01-01", "2016-12-31", 10.0, "2017-02-20"),
        fait("2017-01-01", "2017-12-31", 12.0, "2018-02-20"),
        fait("2018-01-01", "2018-12-31", 15.0, "2019-02-25"),
        fait("2018-01-01", "2018-06-30", 7.0, "2018-08-01", "10-Q"),  # rapport trimestriel
    ]}},
    "OperatingIncomeLoss": {"units": {"USD": [fait("2018-01-01", "2018-12-31", 20.0, "2019-02-25")]}},
    "DepreciationDepletionAndAmortization": {"units": {"USD": [
        fait("2018-01-01", "2018-12-31", 5.0, "2019-02-25")]}},
    "WeightedAverageNumberOfDilutedSharesOutstanding": {"units": {"shares": [
        fait("2018-01-01", "2018-12-31", 1000.0, "2019-02-25")]}},
    "CashAndCashEquivalentsAtCarryingValue": {"units": {"USD": [fait(None, "2018-12-31", 40.0, "2019-02-25")]}},
    "ShortTermInvestments": {"units": {"USD": [fait(None, "2018-12-31", 10.0, "2019-02-25")]}},
    "LongTermDebtNoncurrent": {"units": {"USD": [fait(None, "2018-12-31", 30.0, "2019-02-25")]}},
    "LongTermDebtCurrent": {"units": {"USD": [fait(None, "2018-12-31", 5.0, "2019-02-25")]}},
    "StockholdersEquity": {"units": {"USD": [fait(None, "2018-12-29", 80.0, "2019-02-25")]}},
}}}


def test_comptes():
    l = {r["fin"]: r for r in comptes_annuels("TEST", FAITS)}
    assert set(l) == {"2016-12-31", "2017-12-31", "2018-12-31"}, l.keys()
    assert l["2016-12-31"]["ca"] == 100.0 and l["2016-12-31"]["publie"] == "2017-02-20"
    a = l["2018-12-31"]
    assert a["ca"] == 150.0 and a["resultat_net"] == 15.0 and a["ebitda"] == 25.0
    assert a["tresorerie"] == 50.0 and a["dette"] == 35.0 and a["fonds_propres"] == 80.0
    assert a["actions"] == 1000.0 and a["publie"] == "2019-02-25"


def test_divisions():
    c = pd.DataFrame([{"symbole": "TEST", "publie": "2019-02-25", "actions": 1000.0},
                      {"symbole": "TEST", "publie": "2021-03-01", "actions": 1100.0},
                      {"symbole": "AUTRE", "publie": "2019-02-25", "actions": 50.0}])
    d = pd.DataFrame([{"symbole": "TEST", "date": "2020-08-31", "ratio": 4.0},
                      {"symbole": "TEST", "date": "2024-06-10", "ratio": 10.0}])
    r = _corriger_divisions(c, d)
    assert list(r["actions"]) == [40000.0, 11000.0, 50.0], list(r["actions"])


if __name__ == "__main__":
    test_comptes()
    test_divisions()
    print("OK")


def test_contact_masque():
    import importlib
    import os
    os.environ["SEC_CONTACT"] = "Jeanne Dupré \njeanne.dupre@exemple.fr"
    import retro_us
    importlib.reload(retro_us)
    assert retro_us.AGENT == "screener-actions Jeanne Dupre jeanne.dupre@exemple.fr"
    texte = retro_us._masquer("Invalid header value b'screener-actions Jeanne Dupr\\xe9 \\njeanne.dupre@exemple.fr'")
    assert "jeanne" not in texte.lower() and "exemple" not in texte.lower(), texte
    del os.environ["SEC_CONTACT"]


if __name__ == "__main__":
    test_contact_masque()
    print("OK masquage")
