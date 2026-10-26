"""Vérifie le contrôle de santé qui déclenche les e-mails d'alerte de GitHub."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sante import problemes  # noqa: E402

NORMAL = {"cours_du_jour": 26_300, "notees": 24_000, "anomalies": {"graves": 400},
          "nuits_difficiles": 0}


def test_normal():
    assert problemes(NORMAL, "avant-publication", True) == []
    assert problemes(NORMAL, "plusieurs-nuits", True) == []


def test_cours_manquants_bloquent_la_publication():
    p = problemes({**NORMAL, "cours_du_jour": 300}, "avant-publication", True)
    assert len(p) == 1 and "300 cours" in p[0]
    # Republication sans relecture des données (après un changement du site) : pas de cours lus
    assert problemes({**NORMAL, "cours_du_jour": 0}, "avant-publication", False) == []


def test_notes_et_anomalies():
    assert len(problemes({**NORMAL, "notees": 5_000}, "avant-publication", True)) == 1
    assert len(problemes({**NORMAL, "anomalies": {"graves": 9_000}}, "avant-publication", True)) == 1


def test_plusieurs_nuits():
    assert problemes({**NORMAL, "nuits_difficiles": 2}, "plusieurs-nuits", True) == []
    assert len(problemes({**NORMAL, "nuits_difficiles": 3}, "plusieurs-nuits", True)) == 1


def test_indicateurs_economiques():
    import datetime as dt
    frais = {"maj": dt.date.today().isoformat(), "indicateurs": [{}] * 17}
    assert problemes(NORMAL, "plusieurs-nuits", True, macro=frais) == []
    vieux = {"maj": "2026-01-01", "indicateurs": [{}] * 17}
    assert len(problemes(NORMAL, "plusieurs-nuits", True, macro=vieux)) == 1
    maigre = {"maj": dt.date.today().isoformat(), "indicateurs": [{}] * 4}
    assert len(problemes(NORMAL, "plusieurs-nuits", True, macro=maigre)) == 1


def test_grands_indices():
    import datetime as dt
    jour = lambda n: (dt.date.today() - dt.timedelta(days=n)).isoformat()
    ok = {"indices": {"cac40": {"nom": "CAC 40", "lu": jour(5), "echec_depuis": None}}}
    assert problemes(NORMAL, "plusieurs-nuits", True, indices=ok) == []
    recent = {"indices": {"cac40": {"nom": "CAC 40", "echec_depuis": jour(1)}}}
    assert problemes(NORMAL, "plusieurs-nuits", True, indices=recent) == []   # passager
    panne = {"indices": {"cac40": {"nom": "CAC 40", "echec_depuis": jour(3)},
                         "dax": {"nom": "DAX", "echec_depuis": jour(10)}}}
    p = problemes(NORMAL, "plusieurs-nuits", True, indices=panne)
    assert len(p) == 1 and "CAC 40, DAX" in p[0]


def test_tests_trimestriels():
    from sante import degradation
    l = lambda e, g=5, n=5: {"zone": "Monde (depuis fin 2023)", "ecart_mieux_moins_bien": str(e),
                              "dates_gagnantes": str(g), "dates": str(n)}
    assert degradation([l(0.065), l(0.06)], "Monde") == []
    assert len(degradation([l(0.065), l(0.02)], "Monde")) == 1        # divisé par plus de deux
    assert len(degradation([l(0.065), l(-0.01)], "Monde")) == 1       # devenu négatif
    assert len(degradation([l(0.065), l(0.05, 2, 6)], "Monde")) == 1  # moins d'une date sur deux
    assert len(degradation([], "États-Unis")) == 1                     # pas de résultat


if __name__ == "__main__":
    test_normal()
    test_cours_manquants_bloquent_la_publication()
    test_notes_et_anomalies()
    test_plusieurs_nuits()
    test_tests_trimestriels()
    test_indicateurs_economiques()
    test_grands_indices()
    print("OK")
