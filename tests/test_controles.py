"""Vérifie que chaque contrôle repère bien le cas prévu, et seulement lui."""
import datetime as dt
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from controles import controler  # noqa: E402

AUJOURD_HUI = dt.date(2026, 10, 25)


def societe(**k):
    base = dict(symbole="X", statut="ok", cours=10.0, capi=1e9, actions=1e8, bas_52s=8.0,
                haut_52s=12.0, date_cours="2026-10-24", capi_usd=1e9, ca_usd=5e8,
                ps_yahoo=2.0, per_12m=15.0, per_yahoo=15.5, per_a1=12.0,
                per_prevu_yahoo=12.5, per=13.0, rendement_ref=0.03, ve_ca=2.1)
    base.update(k)
    return base


def test_controles():
    cas = {
        "saine": societe(),
        "pence": societe(capi=1e7),                        # capi en livres, cours en pence
        "classes": societe(capi=8e9, capi_usd=8e9, ps_yahoo=16.0),  # actions A et H
        "capi": societe(capi=1e12),
        "fourchette": societe(cours=2.0, capi=2e8),
        "ancien": societe(date_cours="2026-08-01"),
        "devise": societe(ps_yahoo=40.0),
        "per": societe(per_yahoo=60.0),
        "per_prevu": societe(per_prevu_yahoo=50.0),
        "rendement": societe(rendement_ref=0.6),
        "non_lue": societe(statut="introuvable", cours=np.nan),
    }
    d = controler(pd.DataFrame(cas.values(), index=cas.keys()), AUJOURD_HUI)
    graves = set(d.index[d["anomalie_grave"]])
    avec = set(d.index[d["anomalies"].notna()])
    assert graves == {"capi", "fourchette", "ancien", "devise"}, graves
    assert avec == graves | {"per", "per_prevu", "rendement"}, avec
    assert np.isnan(d.loc["per", "per"]) and np.isnan(d.loc["per", "per_12m"])
    assert np.isnan(d.loc["per_prevu", "per_a1"]) and d.loc["per_prevu", "per_12m"] == 15.0
    assert np.isnan(d.loc["rendement", "rendement_ref"])
    assert np.isnan(d.loc["devise", "ve_ca"])
    assert d.loc["saine", "ve_ca"] == 2.1
    assert "01/08/2026" in d.loc["ancien", "anomalies"]


if __name__ == "__main__":
    test_controles()
    print("OK")
