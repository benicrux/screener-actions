"""Collecte des données Yahoo Finance.

Deux étapes à chaque lancement :
1. les cours du jour de toutes les sociétés, par paquets de 150 (rapide) ;
2. les données détaillées (comptes, prévisions des analystes, publications) d'un lot
   de sociétés, en commençant par celles jamais lues puis les plus anciennes. Tout
   l'univers est ainsi rafraîchi en une à deux semaines.

Les prévisions des analystes sont archivées à chaque lecture (data/estimations/) pour
pouvoir mesurer leurs révisions sur 4 mois et sur un an.
"""
from __future__ import annotations

import datetime as dt
import math
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import pandas as pd

import config

DONNEES = Path("data/donnees.csv")
ESTIMATIONS = Path("data/estimations")
DEVISES = Path("data/devises.csv")
MODULES = ["price", "summaryDetail", "defaultKeyStatistics", "financialData",
           "earningsTrend", "earningsHistory", "calendarEvents"]
URL_RESUME = "https://query2.finance.yahoo.com/v10/finance/quoteSummary/{}"
URL_COTES = "https://query1.finance.yahoo.com/v7/finance/quote"


# --------------------------------------------------------------------------- #
# Outils
# --------------------------------------------------------------------------- #
class Bloque(Exception):
    """Yahoo refuse temporairement nos requêtes (trop de demandes)."""


class Introuvable(Exception):
    """Yahoo ne connaît pas ce symbole."""


def _yahoo():
    from yfinance.data import YfData
    return YfData()


def _get_json(url: str, params: dict) -> dict:
    from yfinance.exceptions import YFRateLimitError
    try:
        reponse = _yahoo().get(url, params=params, timeout=30)
    except YFRateLimitError as e:
        raise Bloque() from e
    if reponse.status_code == 429:
        raise Bloque()
    if reponse.status_code == 404:
        raise Introuvable()
    if reponse.status_code >= 400:
        raise RuntimeError(f"HTTP {reponse.status_code}")
    return reponse.json()


def _v(x):
    """Valeur numérique brute d'un champ Yahoo ({'raw': 1.2, 'fmt': '1.2'} ou 1.2)."""
    if isinstance(x, dict):
        x = x.get("raw")
    if isinstance(x, bool):
        return None
    if isinstance(x, (int, float)) and math.isfinite(x):
        return float(x)
    return None


def _date(x):
    """Date Yahoo (horodatage, texte ou {'raw': …}) en AAAA-MM-JJ."""
    if isinstance(x, dict):
        x = x.get("fmt") or x.get("raw")
    if isinstance(x, str):
        return x[:10]
    if isinstance(x, (int, float)) and x > 0:
        return dt.datetime.fromtimestamp(x, dt.timezone.utc).date().isoformat()
    return None


# --------------------------------------------------------------------------- #
# 1. Cours du jour et taux de change
# --------------------------------------------------------------------------- #
def cours_du_jour(symboles: list[str]) -> pd.DataFrame:
    """Cours, devise et capitalisation de toutes les sociétés (paquets de 150)."""
    lignes, blocages = [], 0
    for i in range(0, len(symboles), 150):
        paquet = symboles[i:i + 150]
        try:
            js = _get_json(URL_COTES, {"symbols": ",".join(paquet), "formatted": "false"})
            blocages = 0
        except Bloque:
            blocages += 1
            if blocages >= 3:
                print("   Cours : Yahoo bloque, on garde les derniers cours connus pour le reste.")
                break
            time.sleep(60 * blocages)
            continue
        except Exception as e:  # paquet perdu, les autres continuent
            print(f"   Cours : paquet ignoré ({e})")
            continue
        for q in (js.get("quoteResponse") or {}).get("result") or []:
            lignes.append({
                "symbole": q.get("symbol"),
                "cours": _v(q.get("regularMarketPrice")),
                "devise_cours": q.get("currency"),
                "capi": _v(q.get("marketCap")),
                "actions": _v(q.get("sharesOutstanding")),
                "date_cours": _date(q.get("regularMarketTime")),
            })
        time.sleep(0.4)
    return pd.DataFrame(lignes, columns=["symbole", "cours", "devise_cours", "capi",
                                         "actions", "date_cours"])


def taux_de_change(devises: set[str]) -> dict[str, float]:
    """Valeur en dollars d'une unité de chaque devise. Garde les derniers taux connus."""
    connus = {}
    if DEVISES.exists():
        connus = dict(pd.read_csv(DEVISES).set_index("devise")["usd"])
    a_lire = sorted(d for d in devises if isinstance(d, str) and d != "USD" and len(d) == 3)
    symboles = [f"USD{d}=X" for d in a_lire]
    try:
        js = _get_json(URL_COTES, {"symbols": ",".join(symboles), "formatted": "false"})
        for q in (js.get("quoteResponse") or {}).get("result") or []:
            prix = _v(q.get("regularMarketPrice"))
            if prix:
                connus[q["symbol"][3:6]] = 1 / prix
    except Exception as e:
        print(f"   Taux de change non mis à jour ({e}), derniers taux conservés.")
    connus["USD"] = 1.0
    DEVISES.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(sorted(connus.items()), columns=["devise", "usd"]).to_csv(DEVISES, index=False)
    return connus


# --------------------------------------------------------------------------- #
# 2. Données détaillées d'une société
# --------------------------------------------------------------------------- #
def _extraire(symbole: str, js: dict) -> tuple[dict, list[dict]]:
    resultat = ((js.get("quoteSummary") or {}).get("result") or [None])[0]
    if not resultat:
        raise Introuvable()
    pr = resultat.get("price") or {}
    sd = resultat.get("summaryDetail") or {}
    ks = resultat.get("defaultKeyStatistics") or {}
    fd = resultat.get("financialData") or {}

    # dividendYield : dividende prévu / cours (0,05 = 5 %), fiable.
    # trailingAnnualDividendYield : 12 derniers mois, faux pour les cours en pence.
    rendement_prevu = _v(sd.get("dividendYield"))
    rendement_12m = _v(sd.get("trailingAnnualDividendYield"))
    l = {
        "symbole": symbole,
        "maj": dt.date.today().isoformat(),
        "statut": "ok",
        "version": 5,
        "nom_yahoo": pr.get("longName") or pr.get("shortName"),
        "devise_cours": pr.get("currency") or sd.get("currency"),
        "devise_comptes": fd.get("financialCurrency"),
        "cours": _v(pr.get("regularMarketPrice")) or _v(fd.get("currentPrice")),
        "date_cours": _date(pr.get("regularMarketTime")),
        # Ratios calculés par Yahoo, pour contrôler les nôtres
        "per_yahoo": _v(sd.get("trailingPE")),
        "per_prevu_yahoo": _v(sd.get("forwardPE")) or _v(ks.get("forwardPE")),
        "ps_yahoo": _v(sd.get("priceToSalesTrailing12Months")),
        "capi": _v(pr.get("marketCap")) or _v(sd.get("marketCap")),
        "actions": _v(ks.get("sharesOutstanding")) or _v(ks.get("impliedSharesOutstanding")),
        "ca": _v(fd.get("totalRevenue")),
        "ebitda": _v(fd.get("ebitda")),
        "tresorerie": _v(fd.get("totalCash")),
        "dette": _v(fd.get("totalDebt")),
        "fcf": _v(fd.get("freeCashflow")),
        "flux_exploitation": _v(fd.get("operatingCashflow")),
        "croiss_ca": _v(fd.get("revenueGrowth")),
        "croiss_bpa": _v(fd.get("earningsGrowth")),
        "marge_brute": _v(fd.get("grossMargins")),
        "marge_ebitda": _v(fd.get("ebitdaMargins")),
        "marge_op": _v(fd.get("operatingMargins")),
        "marge_nette": _v(fd.get("profitMargins")) or _v(ks.get("profitMargins")),
        "roe": _v(fd.get("returnOnEquity")),
        "roa": _v(fd.get("returnOnAssets")),
        "ratio_liquidite": _v(fd.get("currentRatio")),
        "dette_fp": _v(fd.get("debtToEquity")),
        "bpa_12m": _v(ks.get("trailingEps")),
        "actif_net_action": _v(ks.get("bookValue")),
        "pb": _v(ks.get("priceToBook")),
        "rendement": rendement_prevu,
        "rendement_12m": rendement_12m,
        "taux_distribution": _v(sd.get("payoutRatio")),
        "objectif": _v(fd.get("targetMeanPrice")),
        "objectif_haut": _v(fd.get("targetHighPrice")),
        "objectif_bas": _v(fd.get("targetLowPrice")),
        "reco": _v(fd.get("recommendationMean")),
        "nb_analystes": _v(fd.get("numberOfAnalystOpinions")),
        "beta": _v(sd.get("beta")) or _v(ks.get("beta")),
        "perf_52s": _v(ks.get("52WeekChange")),
        "haut_52s": _v(sd.get("fiftyTwoWeekHigh")),
        "bas_52s": _v(sd.get("fiftyTwoWeekLow")),
        "fin_exercice": _date(ks.get("lastFiscalYearEnd")),
    }

    archive = []
    tendances = {t.get("period"): t for t in
                 ((resultat.get("earningsTrend") or {}).get("trend") or [])}
    for periode, cle in (("0y", "a0"), ("+1y", "a1")):
        t = tendances.get(periode)
        if not t:
            continue
        ee = t.get("earningsEstimate") or {}
        re = t.get("revenueEstimate") or {}
        et = t.get("epsTrend") or {}
        l.update({
            f"ex_{cle}": _date(t.get("endDate")),
            f"bpa_{cle}_moy": _v(ee.get("avg")),
            f"bpa_{cle}_bas": _v(ee.get("low")),
            f"bpa_{cle}_haut": _v(ee.get("high")),
            f"bpa_{cle}_nb": _v(ee.get("numberOfAnalysts")),
            f"croiss_bpa_{cle}": _v(ee.get("growth")),
            f"ca_{cle}_moy": _v(re.get("avg")),
            f"ca_{cle}_bas": _v(re.get("low")),
            f"ca_{cle}_haut": _v(re.get("high")),
            f"ca_{cle}_nb": _v(re.get("numberOfAnalysts")),
            f"croiss_ca_{cle}": _v(re.get("growth")),
            f"bpa_{cle}_j7": _v(et.get("7daysAgo")),
            f"bpa_{cle}_j30": _v(et.get("30daysAgo")),
            f"bpa_{cle}_j90": _v(et.get("90daysAgo")),
        })
        l["devise_bpa"] = l.get("devise_bpa") or ee.get("earningsCurrency")
        l["devise_ca"] = l.get("devise_ca") or re.get("revenueCurrency")
        if l.get(f"ex_{cle}") and (l.get(f"bpa_{cle}_moy") is not None
                                   or l.get(f"ca_{cle}_moy") is not None):
            archive.append({"date": l["maj"], "symbole": symbole, "exercice": l[f"ex_{cle}"],
                            "bpa_moy": l.get(f"bpa_{cle}_moy"), "ca_moy": l.get(f"ca_{cle}_moy")})

    # Prochaine publication de résultats (date annoncée, ou estimée par Yahoo)
    publication = (resultat.get("calendarEvents") or {}).get("earnings") or {}
    dates = sorted(d for d in (_date(x) for x in (publication.get("earningsDate") or [])) if d)
    l["prochaine_publication"] = dates[0] if dates else None
    l["publication_estimee"] = bool(publication.get("isEarningsDateEstimate")) if dates else None

    surprises = []
    for h in ((resultat.get("earningsHistory") or {}).get("history") or []):
        s = _v(h.get("surprisePercent"))
        trimestre = _date(h.get("quarter"))
        if s is not None and trimestre:
            surprises.append((trimestre, s))
    surprises.sort()
    l["surprises"] = ";".join(f"{d}:{s:.4f}" for d, s in surprises[-4:]) or None
    return l, archive


MODULES_ESSENTIELS = ["price", "summaryDetail", "defaultKeyStatistics", "financialData"]


def lire_societe(symbole: str) -> tuple[dict, list[dict]]:
    def lire(modules):
        js = _get_json(URL_RESUME.format(symbole),
                       {"modules": ",".join(modules), "formatted": "false",
                        "corsDomain": "finance.yahoo.com", "symbol": symbole})
        return _extraire(symbole, js)
    try:
        return lire(MODULES)
    except (Introuvable, Bloque):
        raise
    except Exception:
        # Pour quelques sociétés, Yahoo échoue sur les prévisions ou l'historique des
        # publications : on relit sans ces modules plutôt que de ne rien avoir.
        return lire(MODULES_ESSENTIELS)


# --------------------------------------------------------------------------- #
# Choix du lot et boucle de collecte
# --------------------------------------------------------------------------- #
def charger_donnees() -> pd.DataFrame:
    if DONNEES.exists():
        return pd.read_csv(DONNEES, dtype={"symbole": str})
    return pd.DataFrame(columns=["symbole", "maj", "statut"])


def choisir_lot(univers: pd.DataFrame, donnees: pd.DataFrame, taille: int) -> list[str]:
    """Jamais lues d'abord (les plus grandes en premier), puis les plus anciennes."""
    u = univers[["symbole", "rang_taille"]].copy()
    u["rang_taille"] = pd.to_numeric(u["rang_taille"], errors="coerce").fillna(9)
    u = u.merge(donnees[["symbole", "maj", "statut"]], on="symbole", how="left")
    aujourd_hui = pd.Timestamp(dt.date.today())
    age = (aujourd_hui - pd.to_datetime(u["maj"], errors="coerce")).dt.days
    u["age"] = age.fillna(10_000)
    attente = u["statut"].isin(["introuvable", "illisible"]) & (u["age"] < config.INTROUVABLE_RETENTE_JOURS)
    u = u[~attente & (u["age"] >= 1)]
    u["jamais"] = u["maj"].isna()
    u = u.sort_values(["jamais", "rang_taille", "age"], ascending=[False, True, False])
    jamais = u[u["jamais"]]
    deja = u[~u["jamais"]].sort_values("age", ascending=False)
    return pd.concat([jamais, deja])["symbole"].head(taille).tolist()


def _sauver(donnees: pd.DataFrame, nouvelles: list[dict], archive: list[dict]) -> pd.DataFrame:
    if nouvelles:
        neuf = pd.DataFrame(nouvelles)
        donnees = pd.concat([donnees[~donnees["symbole"].isin(neuf["symbole"])], neuf],
                            ignore_index=True)
        donnees = donnees.sort_values("symbole").reset_index(drop=True)
        DONNEES.parent.mkdir(parents=True, exist_ok=True)
        donnees.to_csv(DONNEES, index=False, float_format="%.6g")
    if archive:
        ESTIMATIONS.mkdir(parents=True, exist_ok=True)
        fichier = ESTIMATIONS / f"{dt.date.today():%Y-%m}.csv"
        neuf = pd.DataFrame(archive)
        recents = _archives_recentes()
        neuf = neuf[~neuf["symbole"].isin(recents)]
        if not neuf.empty:
            neuf.to_csv(fichier, mode="a", header=not fichier.exists(),
                        index=False, float_format="%.5g")
            _ARCHIVEES.update(neuf["symbole"])
    return donnees


_ARCHIVEES: set[str] = set()
_ARCHIVEES_CHARGEES = False


def _archives_recentes() -> set[str]:
    """Sociétés déjà archivées ces derniers jours (on n'archive qu'une fois par semaine)."""
    global _ARCHIVEES_CHARGEES
    if not _ARCHIVEES_CHARGEES:
        limite = dt.date.today() - dt.timedelta(days=config.ARCHIVE_INTERVALLE_JOURS - 1)
        for f in sorted(ESTIMATIONS.glob("*.csv"))[-2:]:
            a = pd.read_csv(f, usecols=["date", "symbole"], dtype=str)
            _ARCHIVEES.update(a.loc[a["date"] >= limite.isoformat(), "symbole"])
        _ARCHIVEES_CHARGEES = True
    return _ARCHIVEES


def nettoyer_archives() -> None:
    limite = (dt.date.today().replace(day=1) - dt.timedelta(days=31 * config.ARCHIVE_MOIS_CONSERVES))
    for f in ESTIMATIONS.glob("*.csv"):
        try:
            if dt.date.fromisoformat(f.stem + "-01") < limite:
                f.unlink()
        except ValueError:
            pass


def collecter(univers: pd.DataFrame) -> dict:
    """Lit un lot de sociétés dans le temps imparti. Renvoie un bilan."""
    debut = time.monotonic()
    budget = config.BUDGET_MINUTES * 60
    donnees = charger_donnees()
    lot = choisir_lot(univers, donnees, config.LOT_MAX)
    connues = set(donnees["symbole"])
    print(f"   {len(lot)} sociétés à lire (jusqu'à {config.BUDGET_MINUTES} min).")

    verrou = threading.Lock()
    nouvelles, archive = [], []
    bilan = {"lues": 0, "introuvables": 0, "erreurs": 0, "blocages": 0, "arret": None,
             "detail_erreurs": {}}
    etat = {"pause_jusqu_a": 0.0, "blocages_suite": 0, "stop": False}

    def tache(symbole: str):
        while True:
            if etat["stop"] or time.monotonic() - debut > budget:
                return
            attente = etat["pause_jusqu_a"] - time.monotonic()
            if attente <= 0:
                break
            time.sleep(min(attente, 5))
        try:
            ligne, arch = lire_societe(symbole)
            with verrou:
                nouvelles.append(ligne)
                archive.extend(arch)
                bilan["lues"] += 1
                etat["blocages_suite"] = 0
        except Introuvable:
            with verrou:
                nouvelles.append({"symbole": symbole, "maj": dt.date.today().isoformat(),
                                  "statut": "introuvable"})
                bilan["introuvables"] += 1
        except Bloque:
            with verrou:
                bilan["blocages"] += 1
                etat["blocages_suite"] += 1
                n = etat["blocages_suite"]
                if n >= config.BLOCAGES_MAX:
                    etat["stop"] = True
                    bilan["arret"] = "Yahoo a bloqué les requêtes à répétition"
                etat["pause_jusqu_a"] = time.monotonic() + min(60 * 2 ** (n - 1), 900)
        except Exception as e:
            with verrou:
                bilan["erreurs"] += 1
                if len(bilan["detail_erreurs"]) < 20:  # pour comprendre ce qui coince
                    bilan["detail_erreurs"][symbole] = f"{type(e).__name__}: {e}"[:200]
                if symbole not in connues:
                    # Jamais lue et illisible même sans les prévisions : notée comme telle et
                    # retentée plus tard, plutôt que de rester indéfiniment « à lire ».
                    # Une société déjà lue garde ses données précédentes.
                    nouvelles.append({"symbole": symbole, "maj": dt.date.today().isoformat(),
                                      "statut": "illisible"})

    with ThreadPoolExecutor(max_workers=config.PARALLELE) as pool:
        futures = [pool.submit(tache, s) for s in lot]
        for i, _ in enumerate(as_completed(futures), 1):
            if i % 500 == 0:
                with verrou:
                    donnees = _sauver(donnees, nouvelles, archive)
                    nouvelles.clear()
                    archive.clear()
                minutes = (time.monotonic() - debut) / 60
                print(f"   … {i}/{len(lot)} ({bilan['lues']} lues) en {minutes:.0f} min")

    _sauver(donnees, nouvelles, archive)
    nettoyer_archives()
    if bilan["arret"] is None and time.monotonic() - debut > budget:
        bilan["arret"] = "temps imparti écoulé"
    bilan["minutes"] = round((time.monotonic() - debut) / 60, 1)
    return bilan
