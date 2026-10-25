"""Prépare le site : données compactes pour le tableau, fiches détaillées, statut."""
from __future__ import annotations

import datetime as dt
import json
import math
import shutil
import zlib
from pathlib import Path

import numpy as np
import pandas as pd

from referentiels import TAILLES_FR

SITE = Path("site")
WEB = Path("web")
NB_PAQUETS = 256
DICTIONNAIRES = {"p", "c", "se", "i", "t", "g", "m", "dv"}

# Colonnes du tableau : (clé courte, colonne source, arrondi)
COLONNES = [
    ("s", "symbole", None), ("n", "nom", None), ("p", "pays", None), ("c", "continent", None),
    ("se", "secteur", None), ("i", "industrie", None), ("t", "taille_fr", None),
    ("cap", "capi_usd", "sig"), ("inv", "n_investisseur", 0), ("tra", "n_trading", 0),
    ("val", "n_valorisation", 0), ("cro", "n_croissance", 0), ("ren", "n_rentabilite", 0),
    ("sit", "n_situation_fi", 0), ("rlt", "n_revisions_lt", 0), ("rct", "n_revisions_ct", 0),
    ("pub", "n_publication", 0), ("vis", "n_visibilite", 0), ("nper", "n_per", 0),
    ("npot", "n_potentiel", 0), ("nrdt", "n_rendement", 0), ("con", "n_consensus", 0),
    ("per", "per", 1), ("pot", "potentiel", 3), ("rdt", "rendement_ref", 4),
    ("vc", "ve_ca", 2), ("mn", "marge_nette_ref", 3), ("cr", "croissance_ca", 3),
    ("dn", "dette_nette_ebitda", 1), ("p52", "perf_52s", 3), ("m", "maj", None),
    ("fin", "financiere", None), ("g", "groupe", None), ("cou", "n_couverture", 0),
    ("px", "cours", "sig"), ("dv", "devise_cours", None),
]


def _propre(x, arrondi=None):
    if x is None:
        return None
    if isinstance(x, (bool, np.bool_)):
        return 1 if x else 0
    if isinstance(x, (float, np.floating, int, np.integer)):
        x = float(x)
        if not math.isfinite(x):
            return None
        if arrondi == "sig":
            return float(f"{x:.3g}")
        if arrondi == 0:
            return int(round(x))
        if arrondi is not None:
            return round(x, arrondi)
        return float(f"{x:.6g}")
    if isinstance(x, str):
        return x if x and x != "nan" else None
    if pd.isna(x):
        return None
    return str(x)


def _resumes() -> dict[str, str]:
    try:
        import financedatabase as fd
        eq = fd.Equities().select()
        return eq["summary"].dropna().to_dict()
    except Exception as e:
        print(f"   Descriptions des sociétés indisponibles ({e}).")
        return {}


def paquet(symbole: str) -> str:
    return f"{zlib.crc32(symbole.encode()) % NB_PAQUETS:02x}"


def generer(table: pd.DataFrame, statut: dict) -> None:
    if SITE.exists():
        shutil.rmtree(SITE)
    shutil.copytree(WEB, SITE)
    # Numéro de version dans les adresses des fichiers : le navigateur ne mélange pas
    # une ancienne page gardée en mémoire avec les nouvelles données
    version = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%d%H%M")
    for nom in ("index.html", "app.js", "retro.html"):
        f = SITE / nom
        f.write_text(f.read_text().replace("__VERSION__", version))
    (SITE / "data" / "fiches").mkdir(parents=True, exist_ok=True)
    for nom in ("retro_resultats.json", "retro_us_resultats.json", "retro_historique.csv"):
        if (Path("data") / nom).exists():
            shutil.copy(Path("data") / nom, SITE / "data" / nom)

    t = table.copy()
    t["taille_fr"] = t["taille"].map(TAILLES_FR)
    visibles = t[t["statut"].eq("ok") & t["capi_usd"].notna()]

    lignes = [[_propre(r.get(src), arr) for _, src, arr in COLONNES]
              for r in visibles.to_dict("records")]
    # Les textes répétés (pays, secteur…) sont remplacés par un numéro dans un dictionnaire
    dicos = {}
    for j, (cle, _, _) in enumerate(COLONNES):
        if cle in DICTIONNAIRES:
            valeurs = sorted({l[j] for l in lignes if l[j] is not None})
            index = {v: k for k, v in enumerate(valeurs)}
            dicos[cle] = valeurs
            for l in lignes:
                l[j] = index.get(l[j]) if l[j] is not None else None
    tableau = {"maj": dt.date.today().isoformat(), "usd_par_eur": statut.get("usd_par_eur"),
               "champs": [c for c, _, _ in COLONNES], "dicos": dicos, "lignes": lignes}
    (SITE / "data" / "screener.json").write_text(
        json.dumps(tableau, ensure_ascii=False, separators=(",", ":")))

    resumes = _resumes()
    fiches: dict[str, dict] = {}
    for r in visibles.to_dict("records"):
        fiche = {k: _propre(v) for k, v in r.items() if _propre(v) is not None}
        if r["symbole"] in resumes:
            fiche["resume"] = resumes[r["symbole"]]
        fiches.setdefault(paquet(r["symbole"]), {})[r["symbole"]] = fiche
    for cle, contenu in fiches.items():
        (SITE / "data" / "fiches" / f"{cle}.json").write_text(
            json.dumps(contenu, ensure_ascii=False, separators=(",", ":")))

    (SITE / "data" / "statut.json").write_text(json.dumps(statut, ensure_ascii=False, indent=1))
    print(f"   Site généré : {len(lignes)} sociétés notées.")
