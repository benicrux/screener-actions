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

import config
import listes
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
    ("pp", "prochaine_publication", None), ("ppe", "publication_estimee", None),
    ("na", "analystes", 0),
    # Liste « Rallye 5 ans », contrôle express et signaux des favoris
    ("vee", "ve_ebitda", 1), ("pb", "pb", 2), ("tdr", "rendement_tresorerie", 3),
    ("dil", "dilution_3a", 3), ("dir", "dirigeants", 3),
]
RADAR_ENTREES = Path("data/radar_entrees.json")
RALLYE_ENTREES = Path("data/rallye_entrees.json")
INDICES = Path("data/indices.json")


def _capi_eur(visibles: pd.DataFrame, usd_par_eur: float | None) -> pd.Series:
    return pd.to_numeric(visibles.get("capi_usd"), errors="coerce") / (usd_par_eur or 1.0)


def _comptes_recents(visibles: pd.DataFrame) -> pd.Series:
    """Derniers comptes annuels de moins de 18 mois (ou date inconnue) : une société qui ne
    publie plus n'a rien à faire dans les listes de l'accueil."""
    if "fin_exercice" not in visibles:
        return pd.Series(True, index=visibles.index)
    fin = pd.to_datetime(visibles["fin_exercice"], errors="coerce")
    return fin.isna() | (fin >= pd.Timestamp(dt.date.today()) - pd.Timedelta(days=548))


def radar(visibles: pd.DataFrame, usd_par_eur: float | None) -> pd.DataFrame:
    """Les sociétés du radar de la page d'accueil, les mieux notées d'abord (25 % au plus
    d'un même pays)."""
    n = lambda c: pd.to_numeric(visibles.get(c), errors="coerce")
    garde = (listes.radar(n("n_investisseur"), n("n_valorisation"), n("n_situation_fi"),
                          _capi_eur(visibles, usd_par_eur))
             & n("ca_usd").gt(0)  # un chiffre d'affaires publié : écarte les véhicules sans activité
             & _comptes_recents(visibles))
    garde = listes.plafond_pays(visibles["pays"], garde, n("n_investisseur") + n("n_valorisation") / 1000)
    r = visibles[garde].assign(_note=n("n_investisseur"), _val=n("n_valorisation"))
    return r.sort_values(["_note", "_val"], ascending=False)


def rallye(visibles: pd.DataFrame, usd_par_eur: float | None) -> pd.DataFrame:
    """La liste « Rallye 5 ans » : petites, bon marché sur l'EBITDA et sur l'actif net,
    bénéficiaires, sans forte dilution (25 % au plus d'un même pays), les mieux notées d'abord."""
    n = lambda c: pd.to_numeric(visibles.get(c), errors="coerce")
    benefice = n("marge_nette_ajustee").gt(0) | (n("marge_nette_ajustee").isna() & n("per_12m").gt(0))
    garde = listes.rallye(_capi_eur(visibles, usd_par_eur), n("ebitda_ve"), n("actif_prix"),
                          benefice, visibles["financiere"].fillna(False).astype(bool),
                          n("dilution_3a"),
                          n("rendement_tresorerie").gt(0).where(n("rendement_tresorerie").notna()))
    garde &= n("ca_usd").gt(0) & _comptes_recents(visibles)
    garde = listes.plafond_pays(visibles["pays"], garde, n("n_investisseur").fillna(0))
    r = visibles[garde].assign(_note=n("n_investisseur"), _val=n("n_valorisation"))
    return r.sort_values(["_note", "_val"], ascending=False, na_position="last")


def grands_indices(symboles_visibles: set[str]) -> list[dict]:
    """Grands indices pour le filtre du radar (composition relue chaque mois par indices.py) ;
    un indice jamais lu est absent."""
    if not INDICES.exists():
        return []
    try:
        donnees = json.loads(INDICES.read_text()).get("indices", {})
    except ValueError:
        return []
    sortie = []
    for ident, i in donnees.items():
        membres = sorted(set(i.get("membres") or []) & symboles_visibles)
        if membres:
            sortie.append({"id": ident, "nom": i["nom"], "continent": i.get("continent"),
                           "description": i.get("description"), "lu": i.get("lu"),
                           "membres": membres})
    return sortie


def dates_entree(symboles: list[str], aujourd_hui: str, fichier: Path | None = None) -> dict[str, str]:
    """Date d'entrée dans la liste de chaque société ; une société qui en sort l'oublie."""
    fichier = fichier or RADAR_ENTREES
    if fichier.exists():
        anciennes = json.loads(fichier.read_text())
        entrees = {s: anciennes.get(s, aujourd_hui) for s in symboles}
    else:  # tout premier calcul : date inconnue, personne n'est marqué « nouveau »
        entrees = {s: "" for s in symboles}
    fichier.parent.mkdir(exist_ok=True)
    fichier.write_text(json.dumps(entrees, ensure_ascii=False, indent=0, sort_keys=True))
    return entrees


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
    for nom in ("index.html", "tableau.html", "app.js", "accueil.js", "commun.js", "retro.html"):
        f = SITE / nom
        f.write_text(f.read_text().replace("__VERSION__", version))
    (SITE / "data" / "fiches").mkdir(parents=True, exist_ok=True)
    for nom in ("retro_resultats.json", "retro_us_resultats.json", "retro_historique.csv", "macro.json"):
        if (Path("data") / nom).exists():
            shutil.copy(Path("data") / nom, SITE / "data" / nom)

    t = table.copy()
    t["taille_fr"] = t["taille"].map(TAILLES_FR)
    # Nombre d'analystes qui publient une prévision (à défaut, qui donnent un avis)
    nb = lambda c: pd.to_numeric(t[c], errors="coerce") if c in t else pd.Series(np.nan, index=t.index)
    t["analystes"] = nb("bpa_a1_nb").fillna(nb("nb_analystes")).fillna(nb("bpa_a0_nb"))
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

    # Page d'accueil : le radar (avec la date d'entrée de chaque société)
    r = radar(visibles, statut.get("usd_par_eur"))
    entrees = dates_entree(r["symbole"].tolist(), dt.date.today().isoformat())
    ry = rallye(visibles, statut.get("usd_par_eur"))
    entrees_ry = dates_entree(ry["symbole"].tolist(), dt.date.today().isoformat(), RALLYE_ENTREES)
    accueil = {"maj": dt.date.today().isoformat(),
               "filtre": {"note_min": config.RADAR_NOTE_MIN,
                          "valorisation_min": config.RADAR_VALORISATION_MIN,
                          "situation_min": config.RADAR_SITUATION_MIN,
                          "capi_min_eur": config.RADAR_CAPI_MIN_EUR},
               "radar": [[s, entrees[s]] for s in r["symbole"]],
               "rallye": [[s, entrees_ry[s]] for s in ry["symbole"]],
               "regles_rallye": {"capi_min_eur": config.RALLYE_CAPI_MIN_EUR,
                                 "taille_part": config.RALLYE_TAILLE_PART,
                                 "bon_marche_part": config.RALLYE_BON_MARCHE_PART,
                                 "dilution_max": config.RALLYE_DILUTION_MAX,
                                 "tresorerie_positive": config.RALLYE_TRESORERIE_POSITIVE},
               "pays_part_max": config.PAYS_PART_MAX,
               "indices": grands_indices(set(visibles["symbole"]))}
    (SITE / "data" / "accueil.json").write_text(
        json.dumps(accueil, ensure_ascii=False, separators=(",", ":")))

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
