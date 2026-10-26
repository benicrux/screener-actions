"""Contrôles automatiques de cohérence des données, avant le calcul des notes.

- Anomalie grave (cours, capitalisation ou devise douteux) : la société garde sa fiche
  mais sort du classement jusqu'à sa prochaine lecture.
- Anomalie légère (un seul chiffre douteux) : ce chiffre est écarté, le reste est noté.

La liste du jour est enregistrée dans data/anomalies.csv.
"""
from __future__ import annotations

import datetime as dt
from pathlib import Path

import numpy as np
import pandas as pd

FICHIER = Path("data/anomalies.csv")

# Écart toléré avec les ratios calculés par Yahoo (facteur 2 dans les deux sens)
ECART_MAX = 2.0
# Bornes du rapport capitalisation Yahoo / (cours × nombre d'actions) : au-delà de 30,
# même plusieurs catégories d'actions (actions A et H chinoises…) ne l'expliquent plus
RAPPORT_CAPI = (1 / 3, 30)
RAPPORT_CENTIEMES = (0.004, 0.03)  # cours en pence, capitalisation en livres
RENDEMENT_MAX = 0.25
COTATION_MAX_JOURS = 15


def _num(d: pd.DataFrame, col: str) -> pd.Series:
    if col not in d:
        return pd.Series(np.nan, index=d.index)
    return pd.to_numeric(d[col], errors="coerce")


def _hors(a: pd.Series, b: pd.Series, facteur: float = ECART_MAX) -> pd.Series:
    """Vrai quand a et b sont positifs et diffèrent de plus d'un facteur donné."""
    r = a / b.where(b > 0)
    return (a > 0) & (b > 0) & ((r > facteur) | (r < 1 / facteur))


def _hors_yahoo(a: pd.Series, b: pd.Series, *facteurs: pd.Series) -> pd.Series:
    """Comme _hors, pour un ratio de Yahoo. Quand le cours et les comptes sont dans des devises
    différentes (ou le cours en centièmes : pence, agorot…), Yahoo divise souvent l'un par
    l'autre sans convertir : son ratio est alors faux d'un facteur égal au taux de change.
    On n'alerte que si notre chiffre s'écarte du ratio de Yahoo tel quel ET de chacune de
    ses versions converties."""
    hors = _hors(a, b)
    for k in facteurs:
        hors &= _hors(a, b * k.fillna(1.0))
    return hors


def _fmt(x: float) -> str:
    return f"{x:.1f}".replace(".", ",")


def controler(d: pd.DataFrame, aujourd_hui: dt.date | None = None) -> pd.DataFrame:
    d = d.copy()
    aujourd_hui = aujourd_hui or dt.date.today()
    lue = d["statut"].eq("ok") if "statut" in d else pd.Series(True, index=d.index)
    messages = pd.Series([[] for _ in range(len(d))], index=d.index, dtype=object)
    grave = pd.Series(False, index=d.index)

    def signaler(masque: pd.Series, texte, est_grave: bool, a_effacer=()):
        nonlocal grave
        masque = masque.fillna(False) & lue
        if not masque.any():
            return
        for i in d.index[masque]:
            messages[i].append(texte(i) if callable(texte) else texte)
        if est_grave:
            grave = grave | masque
        for col in a_effacer:
            if col in d:
                d.loc[masque, col] = np.nan

    cours, capi, actions = _num(d, "cours"), _num(d, "capi"), _num(d, "actions")

    # 1. Cours manquant ou nul
    signaler(~(cours > 0), "cours manquant", True)

    # 2. Capitalisation incohérente avec le cours et le nombre d'actions
    rapport = capi / (cours * actions)
    ok_capi = rapport.between(*RAPPORT_CAPI) | rapport.between(*RAPPORT_CENTIEMES)
    signaler(rapport.notna() & ~ok_capi,
             "capitalisation incohérente avec le cours et le nombre d'actions", True)

    # 3. Cours hors de sa fourchette sur un an (erreur d'unité, regroupement d'actions…)
    bas, haut = _num(d, "bas_52s"), _num(d, "haut_52s")
    signaler((cours < 0.8 * bas) | (cours > 1.25 * haut),
             "cours en dehors de sa fourchette sur un an", True)

    # 4. Pas de cotation récente (titre suspendu ou retiré)
    if "date_cours" in d:
        date_cours = pd.to_datetime(d["date_cours"], errors="coerce")
        limite = pd.Timestamp(aujourd_hui - dt.timedelta(days=COTATION_MAX_JOURS))
        signaler(date_cours < limite,
                 lambda i: f"pas de cotation depuis le {date_cours[i]:%d/%m/%Y}", True)

    # 5. Rapport capitalisation / chiffre d'affaires très différent de celui de Yahoo :
    #    signe d'une erreur de devise entre le cours et les comptes
    t_cours, t_princ = _num(d, "taux_cours"), _num(d, "taux_principale")
    t_comptes, t_bpa = _num(d, "taux_comptes"), _num(d, "taux_bpa")
    facteurs = (t_cours / t_comptes, t_princ / t_comptes, t_cours / t_bpa, t_princ / t_bpa)
    ps = _num(d, "capi_usd") / _num(d, "ca_usd").where(lambda s: s > 0)
    ps_yahoo = _num(d, "ps_yahoo")
    signaler(_hors_yahoo(ps, ps_yahoo, *facteurs[:2]),
             lambda i: (f"capitalisation / chiffre d'affaires de {_fmt(ps[i])} contre "
                        f"{_fmt(ps_yahoo[i])} chez Yahoo (erreur de devise probable)"),
             True, ("ve_ca", "ve_ebitda"))

    # 6. PER très différent de celui de Yahoo : bénéfice par action douteux (devise, unité).
    #    On compare notre PER avant correction des résultats exceptionnels, pour ne pas
    #    confondre cette correction volontaire avec une erreur. Le PER prévu de Yahoo
    #    (forwardPE) n'est pas utilisé : trop souvent faux, surtout en Asie.
    per12 = _num(d, "per_12m_brut").fillna(_num(d, "per_12m"))
    per_yahoo = _num(d, "per_yahoo")
    signaler(_hors_yahoo(per12, per_yahoo, *facteurs),
             lambda i: f"PER de {_fmt(per12[i])} contre {_fmt(per_yahoo[i])} chez Yahoo",
             False, ("per", "per_12m", "per_a1"))

    # 7. Rendement du dividende aberrant (souvent un dividende exceptionnel)
    rdt = _num(d, "rendement_ref")
    signaler(rdt > RENDEMENT_MAX,
             lambda i: f"rendement de {rdt[i] * 100:.0f} % jugé exceptionnel", False,
             ("rendement_ref",))

    d["anomalies"] = messages.map(lambda m: " ; ".join(m) if m else None)
    d["anomalie_grave"] = grave
    return d


def enregistrer(d: pd.DataFrame) -> dict:
    a = d[d["anomalies"].notna()]
    colonnes = [c for c in ("symbole", "nom", "pays", "anomalie_grave", "anomalies") if c in a]
    FICHIER.parent.mkdir(parents=True, exist_ok=True)
    a[colonnes].sort_values(["anomalie_grave", "symbole"], ascending=[False, True]).to_csv(
        FICHIER, index=False)
    return {"graves": int(a["anomalie_grave"].sum()), "legeres": int((~a["anomalie_grave"]).sum())}
