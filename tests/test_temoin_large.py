"""Vérifie le témoin large : constitution, départ la nuit suivante, divisions d'actions."""
import datetime as dt
import json
import sys
import tempfile
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import temoin_large as T  # noqa: E402


def _table(px, cap):
    """Tableau du site : A, B dans le radar, C dans Rallye, D et E seulement dans l'ensemble."""
    lignes = [[s, px[s], 0, cap[s], 80] for s in px]
    return {"usd_par_eur": 1.0, "champs": ["s", "px", "dv", "cap", "inv"], "dicos": {"dv": ["EUR"]},
            "lignes": lignes}


def test_temoin_large():
    with tempfile.TemporaryDirectory() as d:
        d = Path(d)
        T.DOSSIER, T.RESULTATS, T.SITE = d / "cohortes", d / "res.json", d / "site.json"
        T.ACCUEIL, T.TABLEAU, T.DONNEES = d / "acc.json", d / "tab.json", d / "donnees.csv"
        T.collecte.DEVISES = d / "devises.csv"
        pd.DataFrame({"devise": ["EUR"], "usd": [1.0]}).to_csv(T.collecte.DEVISES, index=False)
        T.ACCUEIL.write_text(json.dumps({"radar": [["A", ""], ["B", ""]], "rallye": [["C", ""]]}))
        cap = {"A": 2e8, "B": 2e8, "C": 2e8, "D": 2e8, "E": 5e7}       # E trop petite : hors ensemble
        T.TABLEAU.write_text(json.dumps(_table({"A": 10, "B": 10, "C": 10, "D": 10, "E": 10}, cap)))
        T.executer(dt.date(2026, 11, 8))                               # constitution, pas de départ
        c = pd.read_csv(T.DOSSIER / "2026-11.csv.gz")
        assert set(c["symbole"]) == {"A", "B", "C", "D"} and c["px0"].isna().all()
        # Nuit suivante : départ au cours du jour
        T.TABLEAU.write_text(json.dumps(_table({"A": 20, "B": 20, "C": 30, "D": 10}, cap)))
        T.executer(dt.date(2026, 11, 9))
        res = json.loads(T.RESULTATS.read_text())["cohortes"][0]
        assert res["suivi"][-1] == ["2026-11-09", 1.0, 1.0, 1.0]
        # Une semaine plus tard : A +10 %, B divisée par 2 (deux fois plus d'actions), C +20 %,
        # D retirée de la cote (dernier cours 12 dans les données détaillées)
        pd.DataFrame({"symbole": ["D"], "cours": [12.0]}).to_csv(T.DONNEES, index=False)
        T.TABLEAU.write_text(json.dumps(_table({"A": 22, "B": 10, "C": 36}, {"A": 2.2e8, "B": 2e8, "C": 2.4e8})))
        T.executer(dt.date(2026, 11, 16))
        res = json.loads(T.RESULTATS.read_text())["cohortes"][0]
        jour, radar, rallye, ensemble = res["suivi"][-1]
        assert jour == "2026-11-16" and abs(radar - 1.05) < 1e-9 and abs(rallye - 1.2) < 1e-9
        assert abs(ensemble - (1.1 + 1.0 + 1.2 + 1.2) / 4) < 1e-9
        assert res["n"] == {"radar": 2, "rallye": 1, "ensemble": 4}
        # Un seul groupe par mois
        T.executer(dt.date(2026, 11, 20))
        assert len(list(T.DOSSIER.glob("*.csv.gz"))) == 1


if __name__ == "__main__":
    test_temoin_large()
    print("OK")
