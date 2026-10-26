"""Vérifie la lecture des sources des indicateurs économiques (sans réseau)."""
import datetime as dt
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import macro  # noqa: E402


def test_formats():
    assert macro.lire_csv_fred("observation_date,DGS10\n2026-10-22,4.6\n2026-10-23,.\n") == [("2026-10-22", 4.6)]
    bce = "KEY,FREQ,TIME_PERIOD,OBS_VALUE\nICP.M,M,2026-08,3.6\nICP.M,M,2026-09,3.8\n"
    assert macro.lire_csv_bce(bce) == [("2026-08-01", 3.6), ("2026-09-01", 3.8)]
    js = {"dimension": {"time": {"category": {"index": {"2026-08": 0, "2026-09": 1}}}}, "value": {"0": 6.3, "1": 6.2}}
    assert macro.lire_eurostat(js) == [("2026-08-01", 6.3), ("2026-09-01", 6.2)]
    js_m = {"dimension": {"time": {"category": {"index": {"2026M09": 0}}}}, "value": [6.2]}
    assert macro.lire_eurostat(js_m) == [("2026-09-01", 6.2)]
    assert macro.lire_csv_boe("DATE,IUDBEDR\n18 Sep 2026,4.00\n") == [("2026-09-18", 4.0)]


def test_glissement_et_resume():
    indice = [(f"{a}-{m:02d}-01", 100 * (1.03 ** (a - 2020)) * (1 + m / 1000))
              for a in range(2020, 2027) for m in range(1, 13) if (a, m) <= (2026, 9)]
    g = macro.glissement(indice)
    assert g[-1][0] == "2026-09-01" and abs(g[-1][1] - 3.0) < 0.01
    r = macro.resumer(g, "points", "2021-10-26")
    assert r["date"] == "2026-09-01" and abs(r["variation_1an"]) < 0.01
    assert r["serie"][0][0] >= "2021-10" and len(r["serie"]) >= 24
    prix = [(f"{a}-{m:02d}-15", 50.0 + (a - 2021) * 10) for a in range(2021, 2027) for m in range(1, 13)]
    r = macro.resumer(prix, "pourcent", "2021-10-26")
    assert r["valeur"] == 100.0 and r["variation_1an"] == 11.11  # 90 → 100
    assert macro.resumer(prix[:10], "pourcent", "2021-10-26") is None  # trop peu de chiffres


def test_secours_et_chiffres_precedents(tmp_path=None):
    import json, tempfile
    with tempfile.TemporaryDirectory() as d:
        macro.FICHIER = Path(d) / "macro.json"
        macro.FICHIER.write_text(json.dumps({"indicateurs": [
            {"id": "fed", "valeur": 3.75, "date": "2026-10-20", "serie": [], "variation_1an": -0.5}]}))
        appels = []

        def faux(source, depuis):
            appels.append(source[1])
            if source[1] == "ECBDFR":
                raise OSError("panne")
            jours = [(dt.date(2021, 11, 1) + dt.timedelta(days=30 * i)).isoformat() for i in range(60)]
            return [(j, 2.25) for j in jours]

        original = macro.telecharger
        macro.telecharger = faux
        macro.INDICATEURS_ORIG = macro.INDICATEURS
        macro.INDICATEURS = [i for i in macro.INDICATEURS if i[0] in ("fed", "bce")]
        try:
            r = macro.collecter(dt.date(2026, 10, 26))
        finally:
            macro.telecharger, macro.INDICATEURS = original, macro.INDICATEURS_ORIG
        ids = {i["id"]: i for i in r["indicateurs"]}
        assert "ECBDFR" in appels and "FM" in appels   # source de secours (BCE) essayée
        assert ids["bce"]["source"].startswith("bce:")
        assert ids["fed"]["valeur"] == 2.25 and r["erreurs"] == {}


def test_sdmx_et_dbnomics():
    # Clé avec joker (BCE) : deux séries, on garde la plus récente
    bce = ("KEY,FREQ,TIME_PERIOD,OBS_VALUE\n"
           "HICP.M.U2.N.000000.4F0.ANR,M,2025-11,2.1\nHICP.M.U2.N.000000.4F0.ANR,M,2025-12,2.0\n"
           "HICP.M.U2.N.000000.4D0.ANR,M,2026-08,1.9\nHICP.M.U2.N.000000.4D0.ANR,M,2026-09,2.2\n")
    assert macro.lire_csv_bce(bce) == [("2026-08-01", 1.9), ("2026-09-01", 2.2)]
    # OCDE / BRI : CSV SDMX avec marque d'ordre des octets, valeurs manquantes
    ocde = "\ufeffSTRUCTURE,REF_AREA,TIME_PERIOD,OBS_VALUE\nDATAFLOW,JPN,2026-08,2.9\nDATAFLOW,JPN,2026-09,NaN\n"
    assert macro.lire_csv_bce(ocde) == [("2026-08-01", 2.9)]
    js = {"series": {"docs": [{"period": ["2026-08", "2026-09"], "period_start_day": ["2026-08-01", "2026-09-01"],
                               "value": [0.5, "NA"]}]}}
    assert macro.lire_dbnomics(js) == [("2026-08-01", 0.5)]


if __name__ == "__main__":
    test_formats()
    test_glissement_et_resume()
    test_secours_et_chiffres_precedents()
    test_sdmx_et_dbnomics()
    print("OK")
