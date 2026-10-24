"""Calcul des indicateurs et des notes sur 100, inspirés de Zone Bourse.

Chaque note est un classement : 80 veut dire que la société fait mieux que 80 % des
sociétés de son secteur sur ce critère. Les banques et assureurs sont comparés entre eux,
sur des critères adaptés (PER, cours / actif net, rentabilité des fonds propres).
"""
from __future__ import annotations

import datetime as dt
from pathlib import Path

import numpy as np
import pandas as pd

import config
from referentiels import INDUSTRIES_FINANCIERES, SOUS_UNITES

# (clé, libellé, sens) : sens = +1 si une valeur haute est meilleure, -1 sinon
NOTES = {
    "valorisation": "Valorisation",
    "croissance": "Croissance",
    "rentabilite": "Rentabilité",
    "situation_fi": "Situation financière",
    "revisions_lt": "Révisions BNA long terme",
    "revisions_ct": "Révisions BNA court terme",
    "publication": "Publication",
    "visibilite": "Visibilité",
    "per": "PER",
    "potentiel": "Potentiel",
    "rendement": "Rendement",
    "consensus": "Consensus",
}


# --------------------------------------------------------------------------- #
# Devises
# --------------------------------------------------------------------------- #
def _convertisseur(fx: dict[str, float]):
    def taux(devise) -> float:
        if not isinstance(devise, str):
            return np.nan
        if devise in SOUS_UNITES:
            principale, diviseur = SOUS_UNITES[devise]
            return fx.get(principale, np.nan) / diviseur
        return fx.get(devise.upper(), np.nan)
    return taux


def _num(df: pd.DataFrame, col: str) -> pd.Series:
    if col not in df:
        return pd.Series(np.nan, index=df.index)
    return pd.to_numeric(df[col], errors="coerce")


def _moyenne(*series: pd.Series) -> pd.Series:
    return pd.concat(series, axis=1).mean(axis=1, skipna=True)


def _moyenne_ponderee(series_poids: list[tuple[pd.Series, float]]) -> pd.Series:
    """Moyenne des valeurs disponibles, chacune avec son poids."""
    valeurs = pd.concat([s for s, _ in series_poids], axis=1)
    poids = np.array([p for _, p in series_poids], dtype=float)
    presents = valeurs.notna().to_numpy() * poids
    somme = np.nansum(valeurs.to_numpy() * poids, axis=1)
    total = presents.sum(axis=1)
    return pd.Series(np.where(total > 0, somme / np.where(total > 0, total, 1), np.nan),
                     index=valeurs.index)


def _ratio(a: pd.Series, b: pd.Series) -> pd.Series:
    r = a / b.where(b != 0)
    return r.replace([np.inf, -np.inf], np.nan)


# --------------------------------------------------------------------------- #
# Révisions issues de nos archives (4 mois, 1 an)
# --------------------------------------------------------------------------- #
def _revisions_archive(d: pd.DataFrame, jours: int, tolerance: int) -> tuple[pd.Series, pd.Series]:
    """Évolution des prévisions de BPA et de CA depuis ~`jours` jours, même exercice."""
    fichiers = sorted(Path("data/estimations").glob("*.csv"))
    vide = pd.Series(np.nan, index=d.index)
    if not fichiers:
        return vide, vide
    arch = pd.concat([pd.read_csv(f, dtype={"symbole": str}) for f in fichiers], ignore_index=True)
    arch["date"] = pd.to_datetime(arch["date"], errors="coerce")
    cible = pd.Timestamp(dt.date.today() - dt.timedelta(days=jours))
    arch["ecart"] = (arch["date"] - cible).abs().dt.days
    arch = arch[arch["ecart"] <= tolerance].sort_values("ecart")
    passe = arch.drop_duplicates(["symbole", "exercice"]).set_index(["symbole", "exercice"])
    if passe.empty:
        return vide, vide

    evol_bpa, evol_ca = [], []
    for cle in ("a0", "a1"):
        cle_ex = list(zip(d["symbole"], d.get(f"ex_{cle}", pd.Series(index=d.index))))
        ancien = passe.reindex(cle_ex)
        ancien.index = d.index
        bpa_avant = pd.to_numeric(ancien["bpa_moy"], errors="coerce")
        ca_avant = pd.to_numeric(ancien["ca_moy"], errors="coerce")
        evol_bpa.append(_ratio(_num(d, f"bpa_{cle}_moy") - bpa_avant, bpa_avant.abs()))
        evol_ca.append(_ratio(_num(d, f"ca_{cle}_moy") - ca_avant, ca_avant.abs()))
    return _moyenne(*evol_bpa).clip(-2, 2), _moyenne(*evol_ca).clip(-2, 2)


# --------------------------------------------------------------------------- #
# Indicateurs bruts
# --------------------------------------------------------------------------- #
def indicateurs(base: pd.DataFrame, fx: dict[str, float]) -> pd.DataFrame:
    d = base.copy()
    taux = _convertisseur(fx)
    t_cours = d["devise_cours"].map(taux)
    principale = d["devise_cours"].map(lambda x: SOUS_UNITES.get(x, (x, 1))[0]
                                       if isinstance(x, str) else x)
    t_principale = principale.map(taux)
    t_comptes = d["devise_comptes"].fillna(principale).map(taux)
    t_bpa = d.get("devise_bpa", pd.Series(index=d.index)).fillna(d["devise_comptes"]).fillna(principale).map(taux)
    t_ca = d.get("devise_ca", pd.Series(index=d.index)).fillna(d["devise_comptes"]).fillna(principale).map(taux)

    cours, capi, actions = _num(d, "cours"), _num(d, "capi"), _num(d, "actions")
    d["financiere"] = d["industrie_en"].isin(INDUSTRIES_FINANCIERES)

    # Capitalisation en dollars (Yahoo l'exprime parfois en livres pour un cours en pence)
    calc = cours * actions
    r = capi / calc
    d["capi_usd"] = np.where(r.between(0.5, 3), capi * t_cours,
                    np.where(r.between(0.004, 0.03), capi * t_principale,
                    np.where(calc.notna(), calc * t_cours, capi * t_principale)))
    d["prix_usd"] = cours * t_cours

    ca = _num(d, "ca") * t_comptes
    ca_a0 = _num(d, "ca_a0_moy") * t_ca
    ca_a1 = _num(d, "ca_a1_moy") * t_ca
    ebitda = _num(d, "ebitda") * t_comptes
    treso = _num(d, "tresorerie") * t_comptes
    dette = _num(d, "dette") * t_comptes
    d["ca_usd"], d["ebitda_usd"] = ca, ebitda
    d["dette_nette_usd"] = dette - treso
    d["ve_usd"] = np.where(d["financiere"], np.nan, d["capi_usd"] + dette.fillna(0) - treso.fillna(0))
    ca_ref = _moyenne(ca, ca_a0, ca_a1).where(lambda s: s > 0)

    # Valorisation : VE / CA (passé et prévu) ; PER et cours / actif net pour la finance
    d["ve_ca"] = _ratio(d["ve_usd"], ca_ref)
    d["ve_ebitda"] = _ratio(d["ve_usd"], ebitda.where(ebitda > 0))
    bpa_12m = _num(d, "bpa_12m") * t_comptes
    bpa_a0 = _num(d, "bpa_a0_moy") * t_bpa
    bpa_a1 = _num(d, "bpa_a1_moy") * t_bpa
    bpa_ref = _moyenne(bpa_12m, bpa_a0, bpa_a1)
    d["per"] = _ratio(d["prix_usd"], bpa_ref)
    d["per_12m"] = _ratio(d["prix_usd"], bpa_12m.where(bpa_12m > 0))
    d["per_a1"] = _ratio(d["prix_usd"], bpa_a1.where(bpa_a1 > 0))
    d["pb"] = _ratio(d["prix_usd"], (_num(d, "actif_net_action") * t_comptes).where(lambda s: s > 0))

    # Croissance du chiffre d'affaires : dernier trimestre sur un an + prévisions.
    # Les prévisions pèsent plus que le passé (leçon du test sur Afentra).
    d["croissance_ca"] = _moyenne_ponderee([
        (_num(d, "croiss_ca"), 1), (_num(d, "croiss_ca_a0"), 1),
        (_num(d, "croiss_ca_a1"), 2)]).clip(-0.9, 5)

    # Rentabilité : marge nette passée et prévue (bénéfice prévu / CA prévu)
    marge_a0 = _ratio(bpa_a0 * actions, ca_a0)
    marge_a1 = _ratio(bpa_a1 * actions, ca_a1)
    d["marge_nette_ref"] = _moyenne_ponderee([
        (_num(d, "marge_nette"), 1), (marge_a0, 1), (marge_a1, 2)]).clip(-2, 1)
    d["roe"] = _num(d, "roe").clip(-2, 2)

    # Situation financière : trésorerie nette / CA et dette nette / EBITDA
    d["treso_nette_ca"] = _ratio(treso - dette, ca_ref).clip(-10, 10)
    levier = _ratio(dette - treso, ebitda.where(ebitda > 0))
    levier = levier.mask(levier < 0, -1.0)  # plus de trésorerie que de dettes : excellent
    levier = levier.mask(ebitda.le(0) & (dette - treso).gt(0), 99.0)  # dettes sans EBITDA
    d["dette_nette_ebitda"] = levier.where(~d["financiere"])
    d["treso_nette_ca"] = d["treso_nette_ca"].where(~d["financiere"])

    # Révisions des prévisions de BPA par les analystes
    rev = {}
    for cle in ("a0", "a1"):
        moy = _num(d, f"bpa_{cle}_moy")
        for j in (7, 90):
            avant = _num(d, f"bpa_{cle}_j{j}")
            rev[(cle, j)] = _ratio(moy - avant, avant.abs())
    d["rev_bpa_7j"] = _moyenne(rev[("a0", 7)], rev[("a1", 7)]).clip(-1, 1)
    d["rev_bpa_90j"] = _moyenne(rev[("a0", 90)], rev[("a1", 90)]).clip(-2, 2)
    d["rev_bpa_4m"], d["rev_ca_4m"] = _revisions_archive(d, 120, 20)
    d["rev_bpa_1a"], d["rev_ca_1a"] = _revisions_archive(d, 365, 30)
    d["revisions_lt_brut"] = _moyenne(d["rev_bpa_90j"].where(d["rev_bpa_4m"].isna()),
                                      d["rev_bpa_4m"], d["rev_bpa_1a"])

    # Publications : écart moyen des derniers résultats par rapport aux attentes
    def surprise(txt):
        if not isinstance(txt, str):
            return np.nan
        vals = [float(x.split(":")[1]) for x in txt.split(";") if ":" in x]
        return float(np.clip(np.mean(vals), -1, 1)) if vals else np.nan
    d["surprise_moy"] = d.get("surprises", pd.Series(index=d.index)).map(surprise)

    # Visibilité : dispersion des prévisions des analystes
    disp = []
    for x in ("ca_a0", "ca_a1", "bpa_a0", "bpa_a1"):
        nb = _num(d, f"{x}_nb")
        e = _ratio(_num(d, f"{x}_haut") - _num(d, f"{x}_bas"), _num(d, f"{x}_moy").abs())
        disp.append(e.where(nb >= 2))
    d["dispersion"] = _moyenne(*disp).clip(0, 5)

    # Potentiel : objectif de cours moyen des analystes / cours
    obj = _ratio(_num(d, "objectif"), cours)
    obj = obj.mask(obj.between(40, 250), obj / 100).mask(obj.between(0.004, 0.025), obj * 100)
    d["potentiel"] = (obj - 1).where((obj > 0.05) & (obj < 20) & (_num(d, "nb_analystes") >= 1))

    # Rendement : dividende prévu (fiable) ; à défaut, dividende des 12 derniers mois,
    # corrigé pour les cours exprimés en centièmes (pence…)
    rdt_12m = _num(d, "rendement_12m")
    centiemes = d["devise_cours"].isin(SOUS_UNITES.keys())
    rdt_12m = rdt_12m.where(~centiemes, rdt_12m * 100)
    rdt = _num(d, "rendement")
    ancien = _num(d, "version").isna()  # premières lectures : « rendement » = sur 12 mois
    rdt = rdt.where(~(ancien & centiemes), rdt * 100)
    rdt = rdt.fillna(rdt_12m)
    d["rendement_ref"] = rdt.where(rdt < 0.3).fillna(0).where(d["prix_usd"].notna())
    d["reco"] = _num(d, "reco").where(_num(d, "nb_analystes") >= 1)
    d["perf_52s"] = _num(d, "perf_52s")
    return d


# --------------------------------------------------------------------------- #
# Notes sur 100
# --------------------------------------------------------------------------- #
def _classement(valeurs: pd.Series, groupes: pd.Series, sens: int) -> pd.Series:
    """Note 1 à 100 : part des sociétés du groupe que la société dépasse."""
    v = valeurs * sens
    effectif = v.groupby(groupes).transform("count")
    dans_groupe = v.groupby(groupes).rank(pct=True)
    global_ = v.rank(pct=True)
    pct = dans_groupe.where(effectif >= config.TAILLE_MIN_SECTEUR, global_)
    return (pct * 100).round().clip(1, 100)


def noter(d: pd.DataFrame) -> pd.DataFrame:
    n = pd.DataFrame(index=d.index)
    fin = d["financiere"]
    groupe = d["secteur"].where(~fin, "Finance : " + d["industrie_en"].fillna(""))
    groupe = groupe.where(
        groupe.map(groupe.value_counts()) >= config.TAILLE_MIN_SECTEUR,
        d["secteur"])
    d["groupe"] = groupe

    # PER négatif (pertes) = le moins bon
    per = d["per"].where(d["per"] > 0, 10_000)
    per = per.where(d["per"].notna())

    n["valorisation"] = _classement(d["ve_ca"], groupe, -1)
    valo_fin = _moyenne(_classement(per, groupe, -1), _classement(d["pb"], groupe, -1))
    n["valorisation"] = n["valorisation"].where(~fin, valo_fin.round())
    n["croissance"] = _classement(d["croissance_ca"], groupe, +1)
    rent = _classement(d["marge_nette_ref"], groupe, +1)
    rent_fin = _moyenne(rent, _classement(d["roe"], groupe, +1))
    n["rentabilite"] = rent.where(~fin, rent_fin.round())
    n["situation_fi"] = _moyenne(_classement(d["treso_nette_ca"], groupe, +1),
                                 _classement(d["dette_nette_ebitda"], groupe, -1)).round()
    n["revisions_lt"] = _classement(d["revisions_lt_brut"], groupe, +1)
    n["revisions_ct"] = _classement(d["rev_bpa_7j"], groupe, +1)
    n["publication"] = _classement(d["surprise_moy"], groupe, +1)
    n["visibilite"] = _classement(d["dispersion"], groupe, -1)
    n["per"] = _classement(per, groupe, -1)
    n["potentiel"] = _classement(d["potentiel"], groupe, +1)
    n["rendement"] = _classement(d["rendement_ref"], groupe, +1)
    n["consensus"] = _classement(d["reco"], groupe, -1)

    poids = pd.Series(config.POIDS_INVESTISSEUR, dtype=float)
    notes = n[poids.index]
    dispo = notes.notna().mul(poids, axis=1).sum(axis=1)
    somme = notes.fillna(0).mul(poids, axis=1).sum(axis=1)
    inv = (somme / dispo.where(dispo > 0)).round()
    n["investisseur"] = inv.where((dispo >= config.COUVERTURE_MIN) & n["valorisation"].notna())
    n["couverture"] = dispo

    tr = n[config.COMPOSANTES_TRADING]
    n["trading"] = tr.mean(axis=1).round().where(
        n["valorisation"].notna() & (tr.notna().sum(axis=1) >= 2))
    return n
