"""Témoin large : toutes les sociétés des deux listes, chaque mois, face à l'ensemble.

Le portefeuille témoin (temoin.py) suit 20 sociétés par liste : le hasard y pèse lourd et
il faut des années pour conclure. Ici, chaque mois, on fige la composition complète des
deux listes de l'accueil et de l'ensemble des sociétés dont elles sont tirées (notées,
plus de 100 M€). Avec des centaines de sociétés, un avantage réel se voit en quelques mois.

- Départ : le cours de la nuit qui suit la constitution (on n'aurait pu acheter qu'après
  la publication de la liste).
- Chaque nuit : gain moyen de chaque groupe, à parts égales, en monnaie locale et hors
  dividendes (pareil pour tous les groupes : c'est l'écart entre eux qui compte). Une
  division d'actions est reconnue (le nombre d'actions est multiplié, le cours divisé
  d'autant) ; une société retirée de la cote garde son dernier cours connu.
- Chaque groupe est suivi 5 ans.

Fichiers : data/temoin_large/AAAA-MM.csv.gz (composition et cours de départ) et
data/temoin_large.json (résultats, un point par semaine). Lancé par la tâche de nuit.
"""
from __future__ import annotations

import datetime as dt
import json
import math
import shutil
from pathlib import Path

import numpy as np
import pandas as pd

import collecte
import config
from temoin import euros_par_unite, _plus_ans

DOSSIER = Path("data/temoin_large")
RESULTATS = Path("data/temoin_large.json")
SITE = Path("site/data/temoin_large.json")
ACCUEIL = Path("site/data/accueil.json")
TABLEAU = Path("site/data/screener.json")
DONNEES = Path("data/donnees.csv")
PREMIER_MOIS = "2026-11"
GROUPES = ("radar", "rallye", "ensemble")
DUREE_ANS = 5


# --------------------------------------------------------------------------- #
# Lecture de la nuit
# --------------------------------------------------------------------------- #
def lire_table() -> tuple[pd.DataFrame, dict]:
    """Toutes les sociétés du site : cours, devise, capitalisation (dollars), note, liquidité."""
    t = json.loads(TABLEAU.read_text())
    champs, dicos = t["champs"], t["dicos"]
    d = pd.DataFrame(t["lignes"], columns=champs)
    for k in ("dv",):
        if k in dicos:
            d[k] = d[k].map(lambda i: dicos[k][i] if isinstance(i, int) and i < len(dicos[k]) else None)
    d = d.set_index("s")
    acc = json.loads(ACCUEIL.read_text())
    return d, {"usd_par_eur": t.get("usd_par_eur") or 1.08,
               "radar": {x[0] for x in acc.get("radar") or []},
               "rallye": {x[0] for x in acc.get("rallye") or []}}


def _fx(devises: pd.Series, taux: dict[str, float]) -> pd.Series:
    """Dollars pour une unité de la devise du cours (pence comptés comme des livres : seuls
    les rapports servent)."""
    eur = taux.get("EUR")
    return devises.map(lambda dv: (euros_par_unite(dv, taux) or np.nan) * eur if eur else np.nan)


# --------------------------------------------------------------------------- #
# Constitution, départ, suivi
# --------------------------------------------------------------------------- #
def constituer(aujourd_hui: dt.date, table: pd.DataFrame, info: dict) -> Path | None:
    mois = aujourd_hui.strftime("%Y-%m")
    fichier = DOSSIER / f"{mois}.csv.gz"
    if mois < PREMIER_MOIS or fichier.exists():
        return None
    note = pd.to_numeric(table.get("inv"), errors="coerce")
    capi_eur = pd.to_numeric(table.get("cap"), errors="coerce") / info["usd_par_eur"]
    ensemble = note.notna() & (capi_eur >= config.RADAR_CAPI_MIN_EUR)
    membres = table.index[ensemble | table.index.isin(info["radar"] | info["rallye"])]
    if not len(info["radar"]) or not len(info["rallye"]):
        print("   Témoin large : listes de l'accueil vides, constitution remise à demain.")
        return None
    c = pd.DataFrame({"symbole": membres,
                      "radar": membres.isin(info["radar"]).astype(int),
                      "rallye": membres.isin(info["rallye"]).astype(int),
                      "ensemble": ensemble.reindex(membres).fillna(False).astype(int).to_numpy()})
    c["cree_le"] = aujourd_hui.isoformat()
    for col in ("depart", "px0", "cap0", "fx0", "dv"):
        c[col] = np.nan if col != "dv" else None
    DOSSIER.mkdir(parents=True, exist_ok=True)
    c.to_csv(fichier, index=False, compression="gzip")
    print(f"   Témoin large : groupe de {mois} constitué ({int(c['radar'].sum())} radar, "
          f"{int(c['rallye'].sum())} Rallye, {int(c['ensemble'].sum())} sociétés en tout).")
    return fichier


def ratios(c: pd.DataFrame, table: pd.DataFrame, taux: dict[str, float],
           secours: pd.Series | None = None) -> pd.Series:
    """Gain de chaque société depuis le départ (1,10 = +10 %), divisions d'actions comprises."""
    px = pd.to_numeric(table["px"], errors="coerce").reindex(c["symbole"]).to_numpy()
    cap = pd.to_numeric(table["cap"], errors="coerce").reindex(c["symbole"]).to_numpy()
    dv = table["dv"].reindex(c["symbole"])
    fx = _fx(dv.fillna(pd.Series(c["dv"].to_numpy(), index=dv.index)), taux).to_numpy()
    px0, cap0, fx0 = (c[k].to_numpy(dtype=float) for k in ("px0", "cap0", "fx0"))
    r = px / px0
    # Division (ou regroupement) d'actions : le nombre d'actions est multiplié par k et le
    # cours divisé d'autant ; on suit alors la valeur de la position, pas le cours
    actions = (cap / (px * fx)) / (cap0 / (px0 * fx0))
    division = ((actions >= 1.4) | (actions <= 0.7)) & (np.abs(np.log(r * actions)) < math.log(1.5))
    r = np.where(division, r * actions, r)
    # Retirée de la cote : dernier cours connu des données détaillées
    if secours is not None:
        manquant = np.isnan(r)
        r = np.where(manquant, secours.reindex(c["symbole"]).to_numpy() / px0, r)
    return pd.Series(np.clip(r, 0, 20), index=c.index)


def suivre(aujourd_hui: dt.date, table: pd.DataFrame, taux: dict[str, float],
           resultats: dict) -> int:
    """Remplit les départs en attente puis met à jour chaque groupe ; renvoie le nombre de
    groupes suivis."""
    if not DOSSIER.exists():
        return 0
    secours = None
    if DONNEES.exists():
        dd = pd.read_csv(DONNEES, usecols=["symbole", "cours"], dtype={"symbole": str})
        secours = pd.to_numeric(dd.drop_duplicates("symbole").set_index("symbole")["cours"], errors="coerce")
    jour = aujourd_hui.isoformat()
    par_id = {r["id"]: r for r in resultats.setdefault("cohortes", [])}
    suivis = 0
    for fichier in sorted(DOSSIER.glob("*.csv.gz")):
        c = pd.read_csv(fichier, dtype={"symbole": str, "dv": str})
        ident = fichier.name[:7]
        cree = c["cree_le"].iloc[0]
        if c["px0"].isna().all():
            if jour <= cree:
                continue  # départ : la nuit suivante
            px = pd.to_numeric(table["px"], errors="coerce")
            c["px0"] = px.reindex(c["symbole"]).to_numpy()
            c["cap0"] = pd.to_numeric(table["cap"], errors="coerce").reindex(c["symbole"]).to_numpy()
            c["dv"] = table["dv"].reindex(c["symbole"]).to_numpy()
            c["fx0"] = _fx(c["dv"], taux).to_numpy()
            c["depart"] = jour
            c = c[c["px0"] > 0]
            c.to_csv(fichier, index=False, compression="gzip")
            print(f"   Témoin large : départ du groupe de {ident} ({len(c)} sociétés).")
        depart = c["depart"].iloc[0]
        if jour >= _plus_ans(dt.date.fromisoformat(depart), DUREE_ANS).isoformat():
            continue
        r = ratios(c, table, taux, secours)
        moyennes = [round(float(r[c[g] == 1].mean()), 5) if (c[g] == 1).any() else None for g in GROUPES]
        res = par_id.get(ident)
        if res is None:
            res = {"id": ident, "cree_le": cree, "depart": depart,
                   "n": {g: int((c[g] == 1).sum()) for g in GROUPES}, "suivi": []}
            resultats["cohortes"].append(res)
        res["suivi"] = _point(res["suivi"], jour, moyennes)
        res["inconnus"] = int(r.isna().sum())
        suivis += 1
    resultats["cohortes"].sort(key=lambda x: x["id"])
    return suivis


def _point(suivi: list, jour: str, valeurs: list) -> list:
    """Un point par semaine : [date, radar, rallye, ensemble] (gain moyen, 1,10 = +10 %)."""
    point = [jour, *valeurs]
    if suivi:
        a = dt.date.fromisoformat(suivi[-1][0]).isocalendar()[:2]
        if a == dt.date.fromisoformat(jour).isocalendar()[:2]:
            return suivi[:-1] + [point]
    return suivi + [point]


def executer(aujourd_hui: dt.date | None = None) -> None:
    aujourd_hui = aujourd_hui or dt.date.today()
    if not TABLEAU.exists() or not ACCUEIL.exists():
        print("   Témoin large : tableau du site absent.")
        return
    table, info = lire_table()
    taux = dict(pd.read_csv(collecte.DEVISES).set_index("devise")["usd"]) if collecte.DEVISES.exists() else {}
    resultats = json.loads(RESULTATS.read_text()) if RESULTATS.exists() else {"cohortes": []}
    constituer(aujourd_hui, table, info)
    if suivre(aujourd_hui, table, taux, resultats):
        resultats["maj"] = aujourd_hui.isoformat()
    RESULTATS.write_text(json.dumps(resultats, ensure_ascii=False, separators=(",", ":")))
    if SITE.parent.exists():
        shutil.copy(RESULTATS, SITE)
    print(f"   Témoin large : {len(resultats['cohortes'])} groupe(s) suivi(s).")


if __name__ == "__main__":
    executer()
