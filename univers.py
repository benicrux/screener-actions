"""Construit la liste mondiale des actions (data/univers.csv) à partir de FinanceDatabase.

Une société cotée sur plusieurs Bourses n'est gardée qu'une fois, sur sa cotation
principale (Bourse de son pays de préférence à une Bourse allemande secondaire ou au
marché de gré à gré américain).
"""
from __future__ import annotations

import datetime as dt
from pathlib import Path

import pandas as pd

import config
from referentiels import (INDUSTRIES, PAYS, SECTEURS, SUFFIXE_PAYS,
                          SUFFIXES_SECONDAIRES, TAILLES)

FICHIER = Path("data/univers.csv")


def _suffixe(symbole: str) -> str:
    if "." in symbole:
        return symbole.rsplit(".", 1)[1].upper()
    return ""


def _score_cotation(ligne: pd.Series) -> int:
    """Plus le score est élevé, plus la cotation a de chances d'être la principale."""
    suffixe = ligne["suffixe"]
    score = 0
    if SUFFIXE_PAYS.get(suffixe) == ligne["country"]:
        score += 8
    if suffixe not in SUFFIXES_SECONDAIRES:
        score += 4
    if "OTC" not in str(ligne["market"]):
        score += 2
    if suffixe == "DE":  # Xetra plutôt que les autres places allemandes
        score += 1
    return score


def construire() -> pd.DataFrame:
    import financedatabase as fd

    brut = fd.Equities().select().reset_index()
    brut = brut[brut["market_cap"].isin(config.TAILLES_RETENUES)].copy()
    if "delisted" in brut:
        brut = brut[brut["delisted"] != True]  # noqa: E712
    brut = brut[brut["country"].notna() & brut["sector"].notna()]
    brut = brut[~brut["country"].isin(config.PAYS_EXCLUS)]
    if config.EXCLURE_FONDS:
        fonds = brut["sector"].isin(["Financials", "Real Estate"]) & brut["name"].fillna("").str.contains(
            r"\bFunds?\b|Investment Trust|Trust (?:PLC|plc|Limited|Ltd)\b|Capital and Income|"
            r"Income Trust|Closed[- ]End|Municipal|Opportunit(?:y|ies) Trust", regex=True)
        adr_gre_a_gre = brut["market"].eq("OTC Markets") & brut["country"].ne("United States")
        bdr = brut["symbol"].str.match(r"^[A-Z0-9]{4}3[1-9]\.SA$")
        certificats = brut["name"].fillna("").str.contains(
            r"\b(?:GDR|ADR|ADS|CDR)\b|Depositary", regex=True)
        preferentielles = brut["symbol"].str.match(r"^[A-Z]+-P[A-Z]?$")  # actions de préférence US
        # Fonds d'investissement britanniques classés dans d'autres secteurs (énergie…)
        fonds |= brut["name"].fillna("").str.contains(
            r"(?:Income|Infrastructure|Investment|Renewables?) Trust (?:PLC|plc)\b", regex=True)
        brut = brut[~(fonds | adr_gre_a_gre | bdr | certificats | preferentielles)]

    brut["suffixe"] = brut["symbol"].map(_suffixe)
    brut["score"] = brut.apply(_score_cotation, axis=1)
    brut["longueur"] = brut["symbol"].str.len()
    brut = brut.sort_values(["score", "longueur"], ascending=[False, True])

    avec_isin = brut[brut["isin"].notna()].drop_duplicates("isin")
    sans_isin = brut[brut["isin"].isna() & ~brut["suffixe"].isin(SUFFIXES_SECONDAIRES)]
    sans_isin = sans_isin.drop_duplicates(["name", "country"])
    univ = pd.concat([avec_isin, sans_isin]).drop_duplicates(["name", "country"])

    rang_taille = {t: i for i, t in enumerate(TAILLES)}
    sortie = pd.DataFrame({
        "symbole": univ["symbol"],
        "nom": univ["name"].fillna(univ["symbol"]),
        "pays_en": univ["country"],
        "pays": univ["country"].map(lambda p: PAYS.get(p, (p, "Autres"))[0]),
        "continent": univ["country"].map(lambda p: PAYS.get(p, (p, "Autres"))[1]),
        "secteur": univ["sector"].map(lambda s: SECTEURS.get(s, s)),
        "industrie_en": univ["industry"],
        "industrie": univ["industry"].map(lambda i: INDUSTRIES.get(i, i)),
        "taille": univ["market_cap"],
        "rang_taille": univ["market_cap"].map(rang_taille),
        "isin": univ["isin"],
        "devise": univ["currency"],
        "bourse": univ["market"],
    })
    return sortie.sort_values("symbole").reset_index(drop=True)


def charger(forcer: bool = False) -> pd.DataFrame:
    """Charge la liste, en la reconstruisant si elle est absente ou trop ancienne."""
    if FICHIER.exists() and not forcer:
        age = dt.timedelta(days=0)
        existant = pd.read_csv(FICHIER, dtype=str)
        marqueur = Path("data/univers_date.txt")
        if marqueur.exists():
            date = dt.date.fromisoformat(marqueur.read_text().strip())
            age = dt.datetime.now() - dt.datetime.combine(date, dt.time())
        if age.days < config.UNIVERS_MAJ_JOURS:
            return existant
    try:
        univ = construire()
    except Exception as e:  # FinanceDatabase indisponible : on garde l'ancienne liste
        if FICHIER.exists():
            print(f"⚠️  Liste des actions non reconstruite ({e}), ancienne liste conservée.")
            return pd.read_csv(FICHIER, dtype=str)
        raise
    FICHIER.parent.mkdir(parents=True, exist_ok=True)
    univ.to_csv(FICHIER, index=False)
    Path("data/univers_date.txt").write_text(dt.date.today().isoformat())
    print(f"Liste des actions reconstruite : {len(univ)} sociétés.")
    return pd.read_csv(FICHIER, dtype=str)


if __name__ == "__main__":
    u = charger(forcer=True)
    print(u.groupby("continent").size())
