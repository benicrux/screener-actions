"""Test sur le passé long : sociétés américaines, de 2011 à 2025.

Les comptes viennent de la SEC (l'autorité boursière américaine), qui publie gratuitement
tous les chiffres déposés par les sociétés depuis 2009, avec leur date de publication :
à chaque date du test, on n'utilise que ce qui était réellement publié ce jour-là.
Les cours (corrigés des divisions d'actions) viennent de Yahoo.

Ce test sert surtout à vérifier, sur une longue période et des marchés différents
(2015-2016, 2018, 2020, 2022…), que la note ne marche pas seulement sur les deux
dernières années, et que les pondérations choisies ne sont pas un hasard.

    python retro_us.py collecte | analyse | (rien : les deux)
"""
from __future__ import annotations

import datetime as dt
import gzip
import json
import os
import re
import sys
import threading
import unicodedata
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np
import pandas as pd

import collecte
import config
import retro
import univers as module_univers

DOSSIER = Path("data/retro_us")
COMPTES = DOSSIER / "comptes.csv"
COURS = DOSSIER / "cours.csv"
DIVISIONS = DOSSIER / "divisions.csv"
CHANGES = DOSSIER / "changes.csv"
TRAITES = DOSSIER / "traites.txt"
RESULTATS = Path("data/retro_us_resultats.json")

# La SEC exige dans chaque requête un nom et une adresse e-mail de contact. On la lit dans
# le secret GitHub « SEC_CONTACT » (Settings → Secrets and variables → Actions), pour
# qu'elle n'apparaisse pas dans le code public.
def _nettoyer_contact(brut: str) -> str:
    """Une seule ligne, sans accents : un en-tête de requête n'accepte rien d'autre."""
    ascii_ = unicodedata.normalize("NFKD", brut).encode("ascii", "ignore").decode()
    return " ".join(ascii_.split())


CONTACT_BRUT = os.environ.get("SEC_CONTACT", "")
CONTACT = _nettoyer_contact(CONTACT_BRUT)
AGENT = f"screener-actions {CONTACT}"


def _masquer(texte: str) -> str:
    """Retire le contact (nom et adresse) de tout texte enregistré ou affiché."""
    texte = re.sub(r"[\w.+-]+@[\w-]+(\.[\w-]+)+", "[adresse masquée]", texte)
    for morceau in set((CONTACT_BRUT + " " + CONTACT).replace("\n", " ").split()):
        if len(morceau) > 2:
            texte = texte.replace(morceau, "[masqué]")
            texte = texte.replace(morceau.encode("unicode_escape").decode(), "[masqué]")
    return texte
STATUT = Path("data/retro_us_statut.json")
URL_TICKERS = "https://www.sec.gov/files/company_tickers.json"
URL_FAITS = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik:010d}.json"

DATES = retro.dates_test("2011-05-01")
PERIODES = {"2011 à 2018": ("2011", "2019"), "depuis 2019": ("2019", "2100")}
OBSERVATIONS_MIN = 1000

# Postes comptables américains (US GAAP), par ordre de préférence
FLUX = {
    "ca": ["Revenues", "RevenueFromContractWithCustomerExcludingAssessedTax", "SalesRevenueNet",
           "RevenueFromContractWithCustomerIncludingAssessedTax", "RevenuesNetOfInterestExpense",
           "SalesRevenueGoodsNet", "SalesRevenueServicesNet"],
    "resultat_net": ["NetIncomeLoss", "NetIncomeLossAvailableToCommonStockholdersBasic", "ProfitLoss"],
    "resultat_op": ["OperatingIncomeLoss"],
    "amortissements": ["DepreciationDepletionAndAmortization", "DepreciationAndAmortization",
                       "DepreciationAmortizationAndAccretionNet", "Depreciation"],
    "actions": ["WeightedAverageNumberOfDilutedSharesOutstanding",
                "WeightedAverageNumberOfSharesOutstandingBasic"],
}
STOCKS = {
    "tresorerie": ["CashAndCashEquivalentsAtCarryingValue",
                   "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents", "Cash"],
    "placements": ["ShortTermInvestments", "MarketableSecuritiesCurrent",
                   "AvailableForSaleSecuritiesDebtSecuritiesCurrent"],
    "dette_lt": ["LongTermDebt", "LongTermDebtAndCapitalLeaseObligations"],
    "dette_lt_nc": ["LongTermDebtNoncurrent", "LongTermDebtAndCapitalLeaseObligationsNoncurrent"],
    "dette_lt_c": ["LongTermDebtCurrent", "LongTermDebtAndCapitalLeaseObligationsCurrent"],
    "dette_ct": ["ShortTermBorrowings", "CommercialPaper", "DebtCurrent"],
    "fonds_propres": ["StockholdersEquity",
                      "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest"],
}


# --------------------------------------------------------------------------- #
# Lecture des comptes de la SEC
# --------------------------------------------------------------------------- #
def _sec(url: str) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": AGENT, "Accept-Encoding": "gzip"})
    with urllib.request.urlopen(req, timeout=60) as r:
        brut = r.read()
        if r.headers.get("Content-Encoding") == "gzip":
            brut = gzip.decompress(brut)
    return json.loads(brut)


def _premiers(faits: dict, concept: str, duree: bool) -> dict[str, tuple[float, str]]:
    """{date de fin: (valeur, date de première publication)} pour un poste, tel que publié
    à l'origine dans un rapport annuel (10-K)."""
    poste = (faits.get("us-gaap") or {}).get(concept) or {}
    res: dict[str, tuple[float, str]] = {}
    for unite, valeurs in (poste.get("units") or {}).items():
        if unite not in ("USD", "shares"):
            continue
        for v in valeurs:
            if not str(v.get("form", "")).startswith("10-K") or v.get("val") is None:
                continue
            fin, publie = v.get("end"), v.get("filed")
            if not fin or not publie:
                continue
            if duree:
                if not v.get("start"):
                    continue
                jours = (dt.date.fromisoformat(fin) - dt.date.fromisoformat(v["start"])).days
                if not 330 <= jours <= 400:
                    continue
            elif v.get("start"):
                continue
            if fin not in res or publie < res[fin][1]:
                res[fin] = (float(v["val"]), publie)
    return res


def _proche(serie: dict[str, tuple[float, str]], fin: str, jours: int = 10):
    if fin in serie:
        return serie[fin]
    f = dt.date.fromisoformat(fin)
    for cle, val in serie.items():
        if abs((dt.date.fromisoformat(cle) - f).days) <= jours:
            return val
    return None


def comptes_annuels(symbole: str, js: dict) -> list[dict]:
    faits = js.get("facts") or {}
    flux = {k: [_premiers(faits, c, True) for c in concepts] for k, concepts in FLUX.items()}
    stocks = {k: [_premiers(faits, c, False) for c in concepts] for k, concepts in STOCKS.items()}

    def choisir(series, fin):
        for s in series:
            v = _proche(s, fin)
            if v is not None:
                return v
        return None

    # Les exercices : dates de fin des chiffres d'affaires ou résultats annuels
    fins = sorted({f for s in flux["ca"] + flux["resultat_net"] for f in s})
    lignes = []
    for fin in fins:
        ca, rn = choisir(flux["ca"], fin), choisir(flux["resultat_net"], fin)
        if ca is None and rn is None:
            continue
        valeurs = {k: choisir(v, fin) for k, v in {**flux, **stocks}.items()}
        publie = max(x[1] for x in (ca, rn) if x is not None)
        n = {k: (v[0] if v else None) for k, v in valeurs.items()}
        dette = n["dette_lt"]
        if dette is None and (n["dette_lt_nc"] is not None or n["dette_lt_c"] is not None):
            dette = (n["dette_lt_nc"] or 0) + (n["dette_lt_c"] or 0)
        if dette is not None or n["dette_ct"] is not None:
            dette = (dette or 0) + (n["dette_ct"] or 0)
        treso = None
        if n["tresorerie"] is not None:
            treso = n["tresorerie"] + (n["placements"] or 0)
        ebitda = None
        if n["resultat_op"] is not None and n["amortissements"] is not None:
            ebitda = n["resultat_op"] + n["amortissements"]
        lignes.append({
            "symbole": symbole, "fin": fin, "publie": publie, "devise": "USD",
            "ca": n["ca"], "resultat_net": n["resultat_net"], "resultat_op": n["resultat_op"],
            "ebitda": ebitda, "tresorerie": treso, "dette": dette, "actions": n["actions"],
            "fonds_propres": n["fonds_propres"],
        })
    return lignes


def _corriger_divisions(comptes: pd.DataFrame, divisions: pd.DataFrame) -> pd.DataFrame:
    """Exprime le nombre d'actions dans les unités d'aujourd'hui, comme les cours de Yahoo :
    une division d'actions postérieure à la publication multiplie le nombre d'actions."""
    if divisions.empty:
        return comptes
    c = comptes.copy()
    facteur = np.ones(len(c))
    par_societe = {s: g for s, g in divisions.groupby("symbole")}
    for i, (s, publie) in enumerate(zip(c["symbole"], c["publie"])):
        g = par_societe.get(s)
        if g is not None:
            facteur[i] = float(np.prod(g.loc[g["date"] > publie, "ratio"])) or 1.0
    c["actions"] = c["actions"] * facteur
    return c


# --------------------------------------------------------------------------- #
# Collecte
# --------------------------------------------------------------------------- #
def collecter(budget_minutes: float) -> None:
    DOSSIER.mkdir(parents=True, exist_ok=True)
    if os.environ.get("RAFRAICHIR"):
        retro.rafraichir(DOSSIER)
    univ = module_univers.charger()
    us = univ[univ["pays_en"].eq("United States") & ~univ["symbole"].str.contains(r"\.")]
    tickers = {v["ticker"].upper(): int(v["cik_str"]) for v in _sec(URL_TICKERS).values()}
    a_lire = [s for s in us["symbole"] if s.upper() in tickers]
    deja = set(TRAITES.read_text().split()) if TRAITES.exists() else set()
    a_lire = [s for s in a_lire if s not in deja]
    print(f"   {len(us)} sociétés américaines, {len(a_lire)} à lire ({len(deja)} déjà lues).")

    debut, budget = time.monotonic(), budget_minutes * 60
    verrou = threading.Lock()
    tampon = {"comptes": [], "cours": [], "divisions": [], "traites": []}
    etat = {"lues": 0, "erreurs": 0, "pause": 0.0, "suite": 0, "stop": False}

    def vider():
        retro._ajouter(COMPTES, tampon["comptes"], ["symbole", "fin", "publie", "devise", "ca",
                       "resultat_net", "resultat_op", "ebitda", "tresorerie", "dette",
                       "actions", "fonds_propres"])
        retro._ajouter(COURS, tampon["cours"], retro.COLONNES_COURS)
        retro._ajouter(DIVISIONS, tampon["divisions"], ["symbole", "date", "ratio"])
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
            js = _sec(URL_FAITS.format(cik=tickers[s.upper()]))
            time.sleep(0.25)  # la SEC limite à 10 requêtes par seconde
            c = comptes_annuels(s, js)
            p, dv = retro._historique(s, "20y") if c else ([], [])
            with verrou:
                tampon["comptes"].extend(c)
                tampon["cours"].extend(p)
                tampon["divisions"].extend(dv)
                tampon["traites"].append(s)
                etat["lues"] += 1
                etat["suite"] = 0
                if etat["lues"] % 250 == 0:
                    vider()
                    print(f"   … {etat['lues']} lues en {(time.monotonic() - debut) / 60:.0f} min")
        except collecte.Bloque:
            with verrou:
                etat["suite"] += 1
                if etat["suite"] >= config.BLOCAGES_MAX:
                    etat["stop"] = True
                etat["pause"] = time.monotonic() + min(60 * 2 ** (etat["suite"] - 1), 900)
        except urllib.error.HTTPError as e:
            with verrou:
                if e.code == 404:
                    tampon["traites"].append(s)
                elif e.code in (403, 429):
                    etat["suite"] += 1
                    etat["pause"] = time.monotonic() + 30 * etat["suite"]
                    if etat["suite"] >= config.BLOCAGES_MAX:
                        etat["stop"] = True
                        print(f"   La SEC refuse les requêtes (HTTP {e.code}).")
                etat["erreurs"] += 1
        except Exception:
            with verrou:
                etat["erreurs"] += 1

    with ThreadPoolExecutor(max_workers=3) as pool:
        list(pool.map(tache, a_lire))
    with verrou:
        vider()
    retro._changes({"EUR"}, "20y", CHANGES)
    print(f"   Collecte : {etat['lues']} sociétés, {etat['erreurs']} erreurs, "
          f"{(time.monotonic() - debut) / 60:.0f} min.")


# --------------------------------------------------------------------------- #
# Analyse
# --------------------------------------------------------------------------- #
VARIANTES = {
    "actuelle (30/15/15/10)": [30, 15, 15, 10],
    "première version (25/15/15/15)": [25, 15, 15, 15],
    "poids égaux": [1, 1, 1, 1],
    "valorisation seule": [1, 0, 0, 0],
}
CRITERES = ["valorisation", "croissance", "rentabilite", "situation_fi"]


def _note(df: pd.DataFrame, poids: list[float]) -> pd.Series:
    w = pd.Series(poids, index=CRITERES, dtype=float)
    dispo = df[CRITERES].notna().mul(w, axis=1).sum(axis=1)
    somme = df[CRITERES].fillna(0).mul(w, axis=1).sum(axis=1)
    return (somme / dispo.where(dispo > 0)).where((dispo >= w.sum() / 2) & df["valorisation"].notna())


def _resume(df: pd.DataFrame, cle: str) -> dict:
    df = df[df[cle].notna()].copy()
    if df.empty:
        return {}
    df["med"] = df.groupby("date")["perf"].transform("median")
    df["bat"] = df["perf"] > df["med"]
    df["q"] = df.groupby("date")[cle].transform(lambda s: pd.qcut(s.rank(method="first"), 5, labels=False) + 1)
    q = df.groupby("q").agg(perf=("perf", "median"), bat=("bat", "mean"), n=("perf", "size"))
    par_date = df.groupby("date").apply(
        lambda g: g.loc[g["q"] == 5, "perf"].median() - g.loc[g["q"] == 1, "perf"].median())
    return {
        "tranches": [{"tranche": int(i), "perf_mediane": round(float(r.perf), 4),
                      "part_bat_mediane": round(float(r.bat), 4), "nombre": int(r.n)}
                     for i, r in q.iterrows()],
        "ecart_moyen": round(float(par_date.mean()), 4),
        "dates_gagnantes": int((par_date > 0).sum()), "dates": int(len(par_date)),
    }


def analyser() -> dict:
    univ = module_univers.charger()
    comptes = pd.read_csv(COMPTES, dtype={"symbole": str})
    comptes = comptes.sort_values("publie").drop_duplicates(["symbole", "fin"], keep="first")
    divisions = pd.read_csv(DIVISIONS, dtype={"symbole": str}) if DIVISIONS.exists() else pd.DataFrame()
    comptes = _corriger_divisions(comptes, divisions)
    comptes["fin_date"] = pd.to_datetime(comptes["fin"], errors="coerce")
    cours = pd.read_csv(COURS, dtype={"symbole": str})
    par_euro = retro._taux(pd.read_csv(CHANGES))

    tout = pd.concat([n for n in (retro._notes_a_la_date(d, univ, comptes, cours, par_euro)
                                  for d in DATES) if len(n) >= OBSERVATIONS_MIN])
    tout = tout.reset_index().rename(columns={"index": "symbole"})
    res = {"genere_le": dt.date.today().isoformat(), "dates": sorted(tout["date"].unique()),
           "societes": int(tout["symbole"].nunique()), "observations": int(len(tout)),
           "ensemble": _resume(tout, "note"), "periodes": {}, "variantes": {}, "criteres": {},
           "par_date": {}}
    for nom, (a, b) in PERIODES.items():
        res["periodes"][nom] = _resume(tout[(tout["date"] >= a) & (tout["date"] < b)], "note")
    for nom, poids in VARIANTES.items():
        tout["alt"] = _note(tout, poids)
        res["variantes"][nom] = {p: _resume(tout[(tout["date"] >= a) & (tout["date"] < b)], "alt")
                                 .get("ecart_moyen") for p, (a, b) in PERIODES.items()}
        res["variantes"][nom]["ensemble"] = _resume(tout, "alt").get("ecart_moyen")
    for c in CRITERES:
        res["criteres"][c] = _resume(tout, c)
    for date, g in tout.groupby("date"):
        top = g.nlargest(100, "note")
        res["par_date"][date] = {
            "nombre": int(len(g)),
            "perf_mediane_toutes": round(float(g["perf"].median()), 4),
            "perf_mediane_top_100": round(float(top["perf"].median()), 4),
        }
    RESULTATS.write_text(json.dumps(res, ensure_ascii=False, indent=1))
    e = res["ensemble"]
    retro.noter_historique("États-Unis (depuis 2011)",
                           e["tranches"][4]["perf_mediane"] - e["tranches"][0]["perf_mediane"],
                           e["tranches"][4]["part_bat_mediane"], e["dates_gagnantes"], e["dates"])
    return res


def _statut(**infos) -> None:
    STATUT.write_text(json.dumps({"date": dt.datetime.now(dt.timezone.utc).isoformat(timespec="minutes"),
                                  **infos}, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    etape = sys.argv[1] if len(sys.argv) > 1 else "tout"
    try:
        if etape in ("collecte", "tout"):
            if "@" not in CONTACT:
                _statut(etat="en attente", message="Secret SEC_CONTACT absent : la SEC exige une "
                        "adresse e-mail de contact. Test américain non lancé.")
                print("Secret SEC_CONTACT absent : test américain non lancé.")
                sys.exit(0)
            print("Collecte des comptes américains (SEC) et des cours sur 20 ans")
            collecter(float(config.BUDGET_MINUTES))
        if etape in ("analyse", "tout"):
            print("Analyse")
            r = analyser()
            _statut(etat="terminé", societes=r["societes"], observations=r["observations"])
            print(json.dumps({k: r[k] for k in ("societes", "observations", "ensemble", "periodes",
                                                "variantes")}, ensure_ascii=False, indent=1))
    except Exception as e:
        import traceback
        message = _masquer(f"{type(e).__name__}: {e}")
        _statut(etat="erreur", message=message, detail=_masquer(traceback.format_exc()[-2000:]))
        print(f"Erreur : {message}")  # jamais la trace brute : elle pourrait contenir le contact
        sys.exit(1)
