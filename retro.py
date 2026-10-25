"""Test sur le passé : les sociétés bien notées ont-elles ensuite fait mieux que les autres ?

On se replace à plusieurs dates passées. À chaque date, on recalcule les notes avec les
seuls comptes publiés à ce moment-là (exercices clos au moins 4 mois avant) et le cours
du jour, puis on mesure la performance de l'action sur les 12 mois suivants, en euros,
dividendes compris.

Limites, à garder en tête en lisant les résultats :
- Yahoo ne fournit gratuitement que 4 exercices de comptes : on ne peut pas remonter
  au-delà de fin 2023, et les prévisions passées des analystes ne sont pas disponibles.
  Le test porte donc sur la partie « comptes » de la note investisseur : valorisation,
  croissance, rentabilité, situation financière (70 % des pondérations).
- Les sociétés disparues depuis (faillites, rachats) ne sont plus dans la liste : les
  rendements des moins bien notées sont sans doute un peu flattés.

    python retro.py collecte   # lit Yahoo (sur le robot GitHub)
    python retro.py analyse    # calcule les résultats
    python retro.py            # les deux
"""
from __future__ import annotations

import datetime as dt
import json
import random
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np
import pandas as pd

import collecte
import config
import notes as module_notes
import univers as module_univers
from referentiels import INDUSTRIES_FINANCIERES, SOUS_UNITES

DOSSIER = Path("data/retro")
# v2 : colonnes dans un ordre fixe (la v1 mélangeait l'ordre d'un paquet à l'autre)
COMPTES = DOSSIER / "comptes_v2.csv"
COURS = DOSSIER / "cours.csv"
CHANGES = DOSSIER / "changes.csv"
TRAITES = DOSSIER / "traites_v2.txt"
COURS_LUS = DOSSIER / "traites.txt"  # sociétés dont les cours sont déjà dans cours.csv
RESULTATS = Path("data/retro_resultats.json")

URL_SERIES = ("https://query2.finance.yahoo.com/ws/fundamentals-timeseries/v1/finance/"
              "timeseries/{s}")
URL_GRAPHE = "https://query2.finance.yahoo.com/v8/finance/chart/{s}"
POSTES = {
    "TotalRevenue": "ca", "NetIncomeCommonStockholders": "resultat_net",
    "OperatingIncome": "resultat_op", "EBITDA": "ebitda",
    "CashCashEquivalentsAndShortTermInvestments": "tresorerie", "TotalDebt": "dette",
    "OrdinarySharesNumber": "actions", "StockholdersEquity": "fonds_propres",
}
# Dates du test (début de mois) : on dispose ensuite de 12 mois de cours
COLONNES_COMPTES = ["symbole", "fin", "devise", *POSTES.values()]
COLONNES_COURS = ["symbole", "mois", "cours", "ajuste", "devise"]
DATES = ["2023-11-01", "2024-05-01", "2024-11-01", "2025-05-01", "2025-10-01"]
DELAI_PUBLICATION_MOIS = 4
CAPI_MIN_EUR = 50e6
POIDS = {k: v for k, v in config.POIDS_INVESTISSEUR.items()
         if k in ("valorisation", "croissance", "rentabilite", "situation_fi")}


# --------------------------------------------------------------------------- #
# Collecte (sur le robot GitHub)
# --------------------------------------------------------------------------- #
def _comptes(symbole: str) -> list[dict]:
    debut = int(dt.datetime(2016, 12, 31).timestamp())
    fin = int(time.time()) + 86400
    js = collecte._get_json(URL_SERIES.format(s=symbole), {
        "symbol": symbole, "type": ",".join("annual" + k for k in POSTES),
        "period1": debut, "period2": fin})
    lignes: dict[str, dict] = {}
    for serie in (js.get("timeseries") or {}).get("result") or []:
        for cle, valeurs in serie.items():
            if not cle.startswith("annual") or not isinstance(valeurs, list):
                continue
            poste = POSTES.get(cle[len("annual"):])
            for v in valeurs:
                if not v or not v.get("asOfDate"):
                    continue
                l = lignes.setdefault(v["asOfDate"], {"symbole": symbole, "fin": v["asOfDate"]})
                l[poste] = collecte._v(v.get("reportedValue"))
                l["devise"] = l.get("devise") or v.get("currencyCode")
    return list(lignes.values())


def _cours(symbole: str) -> list[dict]:
    js = collecte._get_json(URL_GRAPHE.format(s=symbole), {
        "range": "5y", "interval": "1mo", "events": "div,split", "includeAdjustedClose": "true"})
    r = ((js.get("chart") or {}).get("result") or [None])[0]
    if not r or not r.get("timestamp"):
        return []
    devise = (r.get("meta") or {}).get("currency")
    decalage = (r.get("meta") or {}).get("gmtoffset") or 0  # heure locale de la Bourse
    fermeture = ((r.get("indicators") or {}).get("quote") or [{}])[0].get("close") or []
    ajuste = ((r.get("indicators") or {}).get("adjclose") or [{}])[0].get("adjclose") or fermeture
    lignes = []
    for t, c, a in zip(r["timestamp"], fermeture, ajuste):
        if c is None or a is None:
            continue
        mois = dt.datetime.fromtimestamp(t + decalage, dt.timezone.utc).strftime("%Y-%m")
        lignes.append({"symbole": symbole, "mois": mois, "cours": c, "ajuste": a, "devise": devise})
    return lignes


def _changes(devises: set[str]) -> None:
    lignes = []
    for d in sorted(devises | {"EUR"}):
        if not isinstance(d, str) or d == "USD" or len(d) != 3:
            continue
        try:
            for l in _cours(f"USD{d}=X"):
                lignes.append({"devise": d, "mois": l["mois"], "par_usd": l["cours"]})
        except Exception as e:
            print(f"   Change {d} indisponible ({e})")
        time.sleep(0.3)
    pd.DataFrame(lignes).to_csv(CHANGES, index=False)


def _ajouter(fichier: Path, lignes: list[dict], colonnes: list[str]) -> None:
    if lignes:
        pd.DataFrame(lignes, columns=colonnes).to_csv(
            fichier, mode="a", header=not fichier.exists(), index=False, float_format="%.6g")


def collecter(budget_minutes: float) -> None:
    DOSSIER.mkdir(parents=True, exist_ok=True)
    (DOSSIER / "comptes.csv").unlink(missing_ok=True)  # ancienne version aux colonnes mélangées
    univ = module_univers.charger()
    deja = set(TRAITES.read_text().split()) if TRAITES.exists() else set()
    cours_lus = set(COURS_LUS.read_text().split()) if COURS_LUS.exists() else set()
    a_lire = [s for s in univ["symbole"] if s not in deja]
    random.Random(1).shuffle(a_lire)  # ordre aléatoire : un échantillon équilibré si on s'arrête
    print(f"   {len(a_lire)} sociétés à lire, {len(deja)} déjà lues.")
    debut, budget = time.monotonic(), budget_minutes * 60
    verrou = threading.Lock()
    tampon = {"comptes": [], "cours": [], "traites": []}
    etat = {"pause": 0.0, "suite": 0, "stop": False, "lues": 0, "blocages": 0}

    def vider():
        _ajouter(COMPTES, tampon["comptes"], COLONNES_COMPTES)
        _ajouter(COURS, tampon["cours"], COLONNES_COURS)
        with open(TRAITES, "a") as f:
            f.write("".join(s + "\n" for s in tampon["traites"]))
        for v in tampon.values():
            v.clear()

    def tache(s):
        while time.monotonic() < etat["pause"]:
            time.sleep(2)
        if etat["stop"] or time.monotonic() - debut > budget:
            return
        try:
            c = _comptes(s)
            p = [] if s in cours_lus else _cours(s)
            with verrou:
                tampon["comptes"].extend(c)
                tampon["cours"].extend(p)
                tampon["traites"].append(s)
                etat["lues"] += 1
                etat["suite"] = 0
                if etat["lues"] % 1000 == 0:
                    vider()
                    print(f"   … {etat['lues']} lues en {(time.monotonic() - debut) / 60:.0f} min")
        except collecte.Introuvable:
            with verrou:
                tampon["traites"].append(s)
        except collecte.Bloque:
            with verrou:
                etat["blocages"] += 1
                etat["suite"] += 1
                if etat["suite"] >= config.BLOCAGES_MAX:
                    etat["stop"] = True
                etat["pause"] = time.monotonic() + min(60 * 2 ** (etat["suite"] - 1), 900)
        except Exception:
            pass

    with ThreadPoolExecutor(max_workers=config.PARALLELE) as pool:
        list(pool.map(tache, a_lire))
    with verrou:
        vider()
    devises = set(pd.read_csv(COURS, usecols=["devise"])["devise"].dropna()) if COURS.exists() else set()
    devises = {SOUS_UNITES.get(d, (d, 1))[0] for d in devises}
    if COMPTES.exists():
        devises |= set(pd.read_csv(COMPTES, usecols=["devise"])["devise"].dropna())
    _changes(devises)
    print(f"   Collecte : {etat['lues']} sociétés lues, {etat['blocages']} blocages, "
          f"{(time.monotonic() - debut) / 60:.0f} min.")


# --------------------------------------------------------------------------- #
# Analyse
# --------------------------------------------------------------------------- #
def _taux(changes: pd.DataFrame):
    """Fonction (devise, mois) -> unités de devise pour 1 euro."""
    table = changes.pivot_table(index="mois", columns="devise", values="par_usd", aggfunc="last")
    table = table.sort_index().ffill()
    table["USD"] = 1.0

    def par_euro(devise: str, mois: str) -> float:
        principale, diviseur = SOUS_UNITES.get(devise, (devise, 1))
        if principale not in table or "EUR" not in table or mois not in table.index:
            return np.nan
        return table.at[mois, principale] / table.at[mois, "EUR"] * diviseur
    return par_euro


def _notes_a_la_date(date: str, univ: pd.DataFrame, comptes: pd.DataFrame,
                     cours: pd.DataFrame, par_euro) -> pd.DataFrame:
    t0 = pd.Timestamp(date)
    mois0 = t0.strftime("%Y-%m")
    mois1 = (t0 + pd.DateOffset(months=12)).strftime("%Y-%m")
    limite = t0 - pd.DateOffset(months=DELAI_PUBLICATION_MOIS)

    c = comptes[comptes["fin_date"] <= limite].sort_values("fin_date")
    dernier = c.groupby("symbole").tail(1).set_index("symbole")
    precedent = c.groupby("symbole").nth(-2).set_index("symbole")

    p0 = cours[cours["mois"] == mois0].drop_duplicates("symbole").set_index("symbole")
    p1 = cours[cours["mois"] == mois1].drop_duplicates("symbole").set_index("symbole")

    d = univ[["symbole", "nom", "secteur", "industrie_en", "continent"]].set_index("symbole")
    d = d.join(dernier.drop(columns=["fin_date"], errors="ignore"), how="inner")
    d = d.join(precedent[["ca"]].rename(columns={"ca": "ca_prec"}), how="left")
    d = d.join(p0[["cours", "ajuste", "devise"]].rename(columns={"devise": "devise_cours"}),
               how="inner")
    d = d.join(p1[["ajuste"]].rename(columns={"ajuste": "ajuste_fin"}), how="left")
    if d.empty:
        return d

    # Tout en euros, au change de la date
    d["eur_cours"] = [1 / par_euro(dv, mois0) if isinstance(dv, str) else np.nan
                      for dv in d["devise_cours"]]
    d["eur_comptes"] = [1 / par_euro(dv, mois0) if isinstance(dv, str) else np.nan
                        for dv in d["devise"]]
    capi = d["cours"] * d["actions"] * d["eur_cours"]
    for poste in ("ca", "resultat_net", "resultat_op", "ebitda", "tresorerie", "dette",
                  "fonds_propres", "ca_prec"):
        d[poste + "_eur"] = d[poste] * d["eur_comptes"]
    d["capi_eur"] = capi
    d = d[d["capi_eur"] >= CAPI_MIN_EUR]

    fin = d["industrie_en"].isin(INDUSTRIES_FINANCIERES)
    ca = d["ca_eur"].where(d["ca_eur"] > 0)
    ve = d["capi_eur"] + d["dette_eur"].fillna(0) - d["tresorerie_eur"].fillna(0)
    marge_op = d["resultat_op_eur"] / ca
    marge_nette = d["resultat_net_eur"] / ca
    plafond = (marge_op + 0.15).fillna(0.6)
    marge = marge_nette.where(fin | (marge_nette <= plafond), plafond)
    vehicule = d["industrie_en"].eq("Capital Markets") & (marge_nette >= 0.6)

    m = pd.DataFrame(index=d.index)
    m["ve_ca"] = (ve / ca).where(~fin)
    benef = d["resultat_net_eur"].where(d["resultat_net_eur"] > 0)
    m["per"] = (d["capi_eur"] / benef).fillna(10_000).where(d["resultat_net_eur"].notna())
    m["pb"] = d["capi_eur"] / d["fonds_propres_eur"].where(d["fonds_propres_eur"] > 0)
    m["croissance"] = (d["ca_eur"] / d["ca_prec_eur"].where(d["ca_prec_eur"] > 0) - 1).clip(-0.9, 5)
    m["marge"] = marge.clip(-2, 1)
    m["roe"] = (d["resultat_net_eur"] / d["fonds_propres_eur"].where(d["fonds_propres_eur"] > 0)).clip(-2, 2)
    m["treso_ca"] = ((d["tresorerie_eur"] - d["dette_eur"]) / ca).clip(-10, 10).where(~fin)
    ebitda = d["ebitda_eur"]
    levier = (d["dette_eur"] - d["tresorerie_eur"]) / ebitda.where(ebitda > 0)
    levier = levier.mask(levier < 0, -1.0).mask(ebitda.le(0) & (d["dette_eur"] - d["tresorerie_eur"]).gt(0), 99.0)
    m["levier"] = levier.where(~fin)

    groupe = d["secteur"].where(~fin, "Finance : " + d["industrie_en"].fillna(""))
    groupe = groupe.where(groupe.map(groupe.value_counts()) >= config.TAILLE_MIN_SECTEUR, d["secteur"])
    cl = module_notes._classement
    n = pd.DataFrame(index=d.index)
    n["valorisation"] = cl(m["ve_ca"], groupe, -1)
    valo_fin = pd.concat([cl(m["per"], groupe, -1), cl(m["pb"], groupe, -1)], axis=1).mean(axis=1)
    n["valorisation"] = n["valorisation"].where(~fin, valo_fin.round())
    n["croissance"] = cl(m["croissance"], groupe, +1)
    rent = cl(m["marge"], groupe, +1)
    n["rentabilite"] = rent.where(~fin, pd.concat([rent, cl(m["roe"], groupe, +1)], axis=1).mean(axis=1).round())
    n["situation_fi"] = pd.concat([cl(m["treso_ca"], groupe, +1), cl(m["levier"], groupe, -1)],
                                  axis=1).mean(axis=1).round()
    poids = pd.Series(POIDS, dtype=float)
    dispo = n[poids.index].notna().mul(poids, axis=1).sum(axis=1)
    somme = n[poids.index].fillna(0).mul(poids, axis=1).sum(axis=1)
    n["note"] = (somme / dispo.where(dispo > 0)).round().where(
        (dispo >= poids.sum() / 2) & n["valorisation"].notna())

    # Performance sur 12 mois en euros, dividendes compris
    change0 = np.array([par_euro(dv, mois0) for dv in d["devise_cours"]])
    change1 = np.array([par_euro(dv, mois1) for dv in d["devise_cours"]])
    perf = d["ajuste_fin"] / d["ajuste"] * change0 / change1 - 1
    n["perf"] = perf.clip(-0.99, 10)
    n["secteur"] = d["secteur"]
    n["continent"] = d["continent"]
    n["nom"] = d["nom"]
    n["date"] = date
    n["capi_eur"] = d["capi_eur"]
    return n[~vehicule & n["note"].notna() & n["perf"].notna()]


def _tranches(df: pd.DataFrame, cle: str) -> list[dict]:
    """Performance par cinquième de note (1 = les moins bien notées, 5 = les mieux notées)."""
    resultats = []
    df = df[df[cle].notna()].copy()
    df["mediane_date"] = df.groupby("date")["perf"].transform("median")
    df["bat"] = df["perf"] > df["mediane_date"]
    df["tranche"] = df.groupby("date")[cle].transform(
        lambda s: pd.qcut(s.rank(method="first"), 5, labels=False) + 1)
    for q, g in df.groupby("tranche"):
        resultats.append({
            "tranche": int(q), "nombre": int(len(g)),
            "perf_mediane": round(float(g["perf"].median()), 4),
            "perf_moyenne": round(float(g["perf"].clip(-0.95, 3).mean()), 4),
            "part_bat_mediane": round(float(g["bat"].mean()), 4),
        })
    return resultats


def analyser() -> dict:
    univ = module_univers.charger()
    comptes = pd.read_csv(COMPTES, dtype={"symbole": str})
    comptes["fin_date"] = pd.to_datetime(comptes["fin"], errors="coerce")
    comptes = comptes.sort_values("fin_date").drop_duplicates(["symbole", "fin"], keep="last")
    cours = pd.read_csv(COURS, dtype={"symbole": str})
    par_euro = _taux(pd.read_csv(CHANGES))

    tout = pd.concat([_notes_a_la_date(d, univ, comptes, cours, par_euro) for d in DATES])
    res = {"genere_le": dt.date.today().isoformat(), "dates": DATES,
           "societes": int(tout.index.nunique()), "observations": int(len(tout)),
           "par_date": {}, "par_note": {}, "par_critere": {}, "par_continent": {},
           "meilleures": {}, "cas": {}}
    for date, g in tout.groupby("date"):
        rang = g["note"].rank()
        res["par_date"][date] = {
            "nombre": int(len(g)),
            "correlation_rang": round(float(rang.corr(g["perf"].rank())), 4),
            "perf_mediane_toutes": round(float(g["perf"].median()), 4),
            "perf_mediane_top_100": round(float(g.nlargest(100, "note")["perf"].median()), 4),
            "perf_mediane_note_80": round(float(g[g["note"] >= 80]["perf"].median()), 4),
            "nombre_note_80": int((g["note"] >= 80).sum()),
        }
    res["par_note"] = _tranches(tout, "note")
    for critere in POIDS:
        res["par_critere"][critere] = _tranches(tout, critere)
    for continent, g in tout.groupby("continent"):
        if len(g) >= 500:
            res["par_continent"][continent] = _tranches(g, "note")
    for symbole in ("BGEO.L", "AET.L"):
        if symbole in tout.index:
            l = tout.loc[[symbole]]
            res["cas"][symbole] = [
                {k: (round(float(v), 3) if isinstance(v, (float, np.floating)) else v)
                 for k, v in r.items() if k in ("date", "note", "valorisation", "croissance",
                                                 "rentabilite", "situation_fi", "perf")}
                for r in l.reset_index(drop=True).to_dict("records")]
    derniere = tout[tout["date"] == DATES[-1]].nlargest(20, "note")
    res["meilleures"] = [{"symbole": s, "nom": r["nom"], "note": int(r["note"]),
                          "perf": round(float(r["perf"]), 3)} for s, r in derniere.iterrows()]
    def propre(x):
        if isinstance(x, dict):
            return {k: propre(v) for k, v in x.items()}
        if isinstance(x, list):
            return [propre(v) for v in x]
        if isinstance(x, (float, np.floating)):
            return None if not np.isfinite(x) else float(x)
        if isinstance(x, np.integer):
            return int(x)
        return x
    res = propre(res)
    RESULTATS.write_text(json.dumps(res, ensure_ascii=False, indent=1))
    return res


if __name__ == "__main__":
    etape = sys.argv[1] if len(sys.argv) > 1 else "tout"
    if etape in ("collecte", "tout"):
        print("Collecte des comptes et cours passés")
        collecter(float(config.BUDGET_MINUTES))
    if etape in ("analyse", "tout"):
        print("Analyse")
        r = analyser()
        print(json.dumps({k: r[k] for k in ("societes", "observations", "par_date", "par_note")},
                         ensure_ascii=False, indent=1))
