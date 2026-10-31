"""Les deux listes de l'accueil : le radar des pépites et la liste « Rallye 5 ans ».

Les mêmes règles servent au site (rendu.py) et aux tests sur le passé (retro_us.py), pour
que la page « Tests » mesure exactement ce que le site affiche. Réglages dans config.py.
"""
from __future__ import annotations

import math

import pandas as pd

import config


def radar(note: pd.Series, valorisation: pd.Series, situation: pd.Series,
          capi_eur: pd.Series) -> pd.Series:
    """Note d'au moins 75, parmi les 35 % les moins chères du secteur, sans risque de faillite
    apparent (situation financière d'au moins 30, ou non notée comme pour les banques)."""
    sit_ok = situation.isna() | (situation >= config.RADAR_SITUATION_MIN)
    return ((note >= config.RADAR_NOTE_MIN) & (valorisation >= config.RADAR_VALORISATION_MIN)
            & sit_ok & (capi_eur >= config.RADAR_CAPI_MIN_EUR)).fillna(False)


def rallye(capi_eur: pd.Series, ebitda_ve: pd.Series, actif_prix: pd.Series,
           beneficiaire: pd.Series, financiere: pd.Series, dilution_3a: pd.Series,
           tresorerie_positive: pd.Series | None = None, groupe: pd.Series | None = None) -> pd.Series:
    """Petites, bon marché sur l'EBITDA ET sur l'actif net, bénéficiaires, sans forte dilution.

    Les parts (moitié la plus petite, 30 % les moins chères) se calculent parmi les sociétés
    non financières de plus de 100 M€ ; `groupe` = la date, dans les tests sur le passé."""
    base = (capi_eur >= config.RALLYE_CAPI_MIN_EUR) & ~financiere.fillna(False).astype(bool)

    def part(s: pd.Series) -> pd.Series:
        s = s.where(base)
        return s.groupby(groupe).rank(pct=True) if groupe is not None else s.rank(pct=True)

    seuil = 1 - config.RALLYE_BON_MARCHE_PART
    m = (base & (part(capi_eur) <= config.RALLYE_TAILLE_PART)
         & (part(ebitda_ve) > seuil) & (part(actif_prix) > seuil)
         & beneficiaire.fillna(False).astype(bool)
         & (dilution_3a.fillna(0) <= config.RALLYE_DILUTION_MAX))
    if config.RALLYE_TRESORERIE_POSITIVE and tresorerie_positive is not None:
        m &= tresorerie_positive.fillna(True).astype(bool)  # inconnue : non bloquante
    return m.fillna(False)


def plafond_pays(pays: pd.Series, masque: pd.Series, rang: pd.Series,
                 part_max: float | None = None) -> pd.Series:
    """Garde au plus `part_max` des sociétés retenues dans un même pays : les mieux classées
    selon `rang` (le plus grand d'abord). Les autres restent visibles dans le screener."""
    part_max = config.PAYS_PART_MAX if part_max is None else part_max
    retenues = masque[masque].index
    if not len(retenues):
        return masque
    plafond = max(1, math.ceil(part_max * len(retenues)))
    ordre = rang.loc[retenues].sort_values(ascending=False, kind="stable").index
    gardes = (pd.DataFrame({"pays": pays.loc[ordre].fillna("?").values}, index=ordre)
              .groupby("pays", sort=False).cumcount() < plafond)
    resultat = pd.Series(False, index=masque.index)
    resultat.loc[gardes[gardes].index] = True
    return resultat
