"""Portefeuille témoin : ce que les listes de l'accueil donnent vraiment, en direct.

Chaque semestre (1er mai, 1er novembre), on fige les 20 premières sociétés de chaque liste
de l'accueil (radar des pépites, « Rallye 5 ans ») telles que le site les montre, 5 au plus
par pays, à parts égales. On n'y touche plus pendant 5 ans. Chaque nuit, on mesure leur
gain en euros, dividendes réinvestis, et on le compare à l'indice mondial (ETF iShares Core
MSCI World, capitalisant, coté en euros).

Lancé par la tâche de nuit après main.py (jamais par les lancements courts). Une panne de
Yahoo n'efface rien : les derniers chiffres connus sont gardés.
"""
from __future__ import annotations

import datetime as dt
import json
import shutil
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pandas as pd

import collecte
from referentiels import SOUS_UNITES

TEMOIN = Path("data/temoin.json")
ACCUEIL = Path("site/data/accueil.json")
TABLEAU = Path("site/data/screener.json")
SITE = Path("site/data/temoin.json")
URL_GRAPHE = "https://query2.finance.yahoo.com/v8/finance/chart/{s}"

PREMIER_SEMESTRE = "2026-11"  # le premier portefeuille date du 1er novembre 2026
TAILLE = 20          # sociétés par portefeuille
PAR_PAYS_MAX = 5     # au plus par pays
DUREE_ANS = 5
LISTES = {"radar": "Radar des pépites", "rallye": "Rallye 5 ans"}
# Indice mondial : ETF capitalisant (dividendes réinvestis), coté en euros ; le second si
# Yahoo ne connaît plus le premier
REFERENCES = ["IWDA.AS", "EUNL.DE"]
NOM_REFERENCE = "Indice mondial (MSCI World, dividendes réinvestis)"


# --------------------------------------------------------------------------- #
# Règles (sans réseau, testées)
# --------------------------------------------------------------------------- #
def semestre(jour: dt.date) -> str:
    """Semestre en cours : « 2026-11 » du 1er novembre au 30 avril, « 2027-05 » ensuite."""
    if jour.month >= 11:
        return f"{jour.year}-11"
    if jour.month >= 5:
        return f"{jour.year}-05"
    return f"{jour.year - 1}-11"


def choisir(symboles: list[str], pays: dict[str, str], taille: int = TAILLE,
            par_pays: int = PAR_PAYS_MAX, valide=lambda s: True) -> list[str]:
    """Les premières de la liste, dans l'ordre de l'accueil, 5 au plus par pays ; une société
    dont Yahoo ne donne pas le cours de départ est remplacée par la suivante."""
    retenues, compte = [], {}
    for s in symboles:
        p = pays.get(s) or "?"
        if compte.get(p, 0) >= par_pays:
            continue
        if not valide(s):
            continue
        retenues.append(s)
        compte[p] = compte.get(p, 0) + 1
        if len(retenues) >= taille:
            break
    return retenues


def valeur(portefeuille: dict) -> float | None:
    """Valeur d'un euro placé au départ, à parts égales, sans rééquilibrage."""
    ratios = [l["r"] * l["eur"] / l["eur0"] for l in portefeuille["lignes"]
              if l.get("r") and l.get("eur") and l.get("eur0")]
    return sum(ratios) / len(ratios) if ratios else None


def noter_point(suivi: list, jour: str, v: float, ref: float) -> list:
    """Un point par semaine (le dernier jour connu de la semaine) : l'historique reste léger."""
    point = [jour, round(v, 5), round(ref, 5)]
    if suivi:
        a = dt.date.fromisoformat(suivi[-1][0]).isocalendar()[:2]
        b = dt.date.fromisoformat(jour).isocalendar()[:2]
        if a == b:
            return suivi[:-1] + [point]
    return suivi + [point]


def euros_par_unite(devise: str | None, fx: dict[str, float]) -> float | None:
    """Euros pour une unité de la devise (les pence comptent comme des livres : seuls les
    rapports de change servent)."""
    if not isinstance(devise, str) or not fx.get("EUR"):
        return None
    principale = SOUS_UNITES.get(devise, (devise.upper(), 1))[0]
    usd = 1.0 if principale == "USD" else fx.get(principale)
    return usd / fx["EUR"] if usd else None


# --------------------------------------------------------------------------- #
# Cours (Yahoo, dividendes réinvestis)
# --------------------------------------------------------------------------- #
def _barres(symbole: str, params: dict) -> tuple[list[tuple[str, float]], str | None]:
    """[(date locale, cours ajusté)] et devise. Les deux appels d'une même nuit (départ et
    dernier cours) sont ajustés sur la même base : leur rapport inclut les dividendes."""
    js = collecte._get_json(URL_GRAPHE.format(s=symbole), {
        **params, "interval": "1d", "includeAdjustedClose": "true", "events": "div,split"})
    r = ((js.get("chart") or {}).get("result") or [None])[0]
    if not r or not r.get("timestamp"):
        return [], None
    meta = r.get("meta") or {}
    decalage = meta.get("gmtoffset") or 0
    ajuste = ((r.get("indicators") or {}).get("adjclose") or [{}])[0].get("adjclose") or []
    barres = []
    for t, a in zip(r["timestamp"], ajuste):
        if a:
            jour = dt.datetime.fromtimestamp(t + decalage, dt.timezone.utc).date().isoformat()
            barres.append((jour, float(a)))
    return barres, meta.get("currency")


def _depart(symbole: str, avant: str) -> tuple[str, float, str | None] | None:
    """Dernier cours ajusté strictement avant la date (la liste a été choisie sur ces cours)."""
    d = dt.date.fromisoformat(avant)
    p1 = int(dt.datetime(d.year, d.month, d.day, tzinfo=dt.timezone.utc).timestamp())
    barres, devise = _barres(symbole, {"period1": p1 - 12 * 86400, "period2": p1 + 86400})
    barres = [b for b in barres if b[0] < avant]
    return (barres[-1][0], barres[-1][1], devise) if barres else None


def _dernier(symbole: str) -> tuple[str, float] | None:
    barres, _ = _barres(symbole, {"range": "5d"})
    return barres[-1] if barres else None


def _ratio(symbole: str, depart: str) -> tuple[str, float] | None:
    """(date du dernier cours, gain depuis le départ dividendes réinvestis, en devise locale)."""
    a = _barres(symbole, {"period1": _ts(depart) - 4 * 86400, "period2": _ts(depart) + 86400})[0]
    a = [b for b in a if b[0] <= depart]
    b = _dernier(symbole)
    if not a or not b:
        return None
    return b[0], b[1] / a[-1][1]


def _plus_ans(jour: dt.date, n: int) -> dt.date:
    try:
        return jour.replace(year=jour.year + n)
    except ValueError:  # 29 février
        return jour.replace(year=jour.year + n, day=28)


def _ts(jour: str) -> int:
    d = dt.date.fromisoformat(jour)
    return int(dt.datetime(d.year, d.month, d.day, tzinfo=dt.timezone.utc).timestamp())


# --------------------------------------------------------------------------- #
# Constitution et suivi
# --------------------------------------------------------------------------- #
def charger() -> dict:
    if TEMOIN.exists():
        return json.loads(TEMOIN.read_text())
    return {"reference": NOM_REFERENCE, "portefeuilles": []}


def _taux() -> dict[str, float]:
    if not collecte.DEVISES.exists():
        return {}
    return dict(pd.read_csv(collecte.DEVISES).set_index("devise")["usd"])


def _lire_site() -> tuple[dict, dict]:
    """Les deux listes de l'accueil (dans l'ordre affiché) et, par société, nom/pays/devise."""
    accueil = json.loads(ACCUEIL.read_text())
    tab = json.loads(TABLEAU.read_text())
    champs, dicos = tab["champs"], tab["dicos"]
    i = {c: champs.index(c) for c in ("s", "n", "p", "dv")}
    infos = {}
    for l in tab["lignes"]:
        pays, devise = l[i["p"]], l[i["dv"]]
        infos[l[i["s"]]] = {"nom": l[i["n"]],
                            "pays": dicos["p"][pays] if pays is not None else None,
                            "devise": dicos["dv"][devise] if devise is not None else None}
    listes = {cle: [x[0] for x in accueil.get(cle) or []] for cle in LISTES}
    return listes, infos


def constituer(etat: dict, aujourd_hui: dt.date, fx: dict[str, float]) -> list[str]:
    """Fige les portefeuilles du semestre s'ils n'existent pas encore."""
    sem = semestre(aujourd_hui)
    if sem < PREMIER_SEMESTRE:
        return []
    deja = {p["id"] for p in etat["portefeuilles"]}
    a_faire = [cle for cle in LISTES if f"{sem}-{cle}" not in deja]
    if not a_faire:
        return []
    listes, infos = _lire_site()
    jour = aujourd_hui.isoformat()
    ref = None
    for symbole in REFERENCES:
        try:
            ref = _depart(symbole, jour)
        except Exception as e:
            print(f"   Témoin : indice {symbole} indisponible ({e})")
        if ref:
            ref = (symbole, *ref)
            break
    if not ref:
        print("   Témoin : indice mondial indisponible, constitution remise à demain.")
        return []
    crees = []
    for cle in a_faire:
        departs = {}

        def valide(s):
            try:
                d = _depart(s, jour)
            except collecte.Bloque:
                raise
            except Exception:
                d = None
            eur = euros_par_unite((d[2] if d else None) or infos.get(s, {}).get("devise"), fx)
            if d and eur:
                departs[s] = (d, eur)
                time.sleep(0.2)
                return True
            return False

        try:
            choix = choisir(listes.get(cle, []), {s: infos.get(s, {}).get("pays") for s in listes.get(cle, [])},
                            valide=valide)
        except collecte.Bloque:
            print(f"   Témoin : Yahoo bloque, constitution « {LISTES[cle]} » remise à demain.")
            continue
        if len(choix) < TAILLE // 2:
            print(f"   Témoin : seulement {len(choix)} cours de départ pour « {LISTES[cle]} », remis à demain.")
            continue
        lignes = []
        for s in choix:
            (jour_depart, _, devise), eur = departs[s]
            lignes.append({"s": s, "nom": infos.get(s, {}).get("nom") or s,
                           "pays": infos.get(s, {}).get("pays"),
                           "devise": devise or infos.get(s, {}).get("devise"),
                           "depart": jour_depart, "eur0": eur, "eur": eur, "r": 1.0, "maj": jour_depart})
        etat["portefeuilles"].append({
            "id": f"{sem}-{cle}", "semestre": sem, "liste": cle, "nom_liste": LISTES[cle],
            "cree_le": jour, "fin": _plus_ans(aujourd_hui, DUREE_ANS).isoformat(),
            "reference": {"s": ref[0], "depart": ref[1], "r": 1.0, "maj": ref[1]},
            "lignes": lignes, "suivi": [[ref[1], 1.0, 1.0]]})
        crees.append(f"{sem}-{cle}")
        print(f"   Témoin : portefeuille « {LISTES[cle]} » du {jour} constitué ({len(lignes)} sociétés).")
    return crees


def suivre(etat: dict, aujourd_hui: dt.date, fx: dict[str, float]) -> int:
    """Met à jour chaque portefeuille en cours ; renvoie le nombre de cours relus."""
    actifs = [p for p in etat["portefeuilles"] if p["fin"] > aujourd_hui.isoformat()]
    if not actifs:
        return 0
    taches = {}
    for p in actifs:
        for l in p["lignes"]:
            taches[(l["s"], l["depart"])] = None
        taches[(p["reference"]["s"], p["reference"]["depart"])] = None
    bloque = {"oui": False}

    def lire(cle):
        if bloque["oui"]:
            return cle, None
        try:
            r = _ratio(*cle)
            time.sleep(0.2)
            return cle, r
        except collecte.Bloque:
            bloque["oui"] = True
        except Exception as e:
            print(f"   Témoin : {cle[0]} non relu ({e})")
        return cle, None

    with ThreadPoolExecutor(max_workers=3) as pool:
        for cle, r in pool.map(lire, list(taches)):
            taches[cle] = r
    if bloque["oui"]:
        print("   Témoin : Yahoo bloque, derniers chiffres connus gardés pour le reste.")
    relus = 0
    for p in actifs:
        for l in p["lignes"]:
            r = taches.get((l["s"], l["depart"]))
            if r:
                l["maj"], l["r"] = r[0], round(r[1], 6)
                eur = euros_par_unite(l.get("devise"), fx)
                if eur:
                    l["eur"] = eur
                relus += 1
        ref = p["reference"]
        r = taches.get((ref["s"], ref["depart"]))
        if r:
            ref["maj"], ref["r"] = r[0], round(r[1], 6)
        v = valeur(p)
        if v is not None:
            jour = max([l["maj"] for l in p["lignes"]] + [ref["maj"]])
            p["suivi"] = noter_point(p.get("suivi") or [], jour, v, ref["r"])
    return relus


def executer(aujourd_hui: dt.date | None = None) -> None:
    aujourd_hui = aujourd_hui or dt.date.today()
    etat = charger()
    fx = _taux()
    try:
        constituer(etat, aujourd_hui, fx)
    except FileNotFoundError as e:
        print(f"   Témoin : listes de l'accueil absentes ({e}), constitution remise à demain.")
    relus = suivre(etat, aujourd_hui, fx)
    if relus:
        etat["maj"] = aujourd_hui.isoformat()
    TEMOIN.parent.mkdir(exist_ok=True)
    TEMOIN.write_text(json.dumps(etat, ensure_ascii=False, indent=0))
    if SITE.parent.exists():
        shutil.copy(TEMOIN, SITE)
    print(f"   Témoin : {len(etat['portefeuilles'])} portefeuilles, {relus} cours relus.")


def verifier() -> None:
    """Vérifie que Yahoo donne bien les cours de départ et les derniers cours (sans rien écrire)."""
    hier = (dt.date.today() - dt.timedelta(days=7)).isoformat()
    ok = 0
    for s in REFERENCES + ["AAPL", "7203.T", "BARC.L"]:
        try:
            d, r = _depart(s, hier), _ratio(s, hier)
            print(f"   {s} : départ {d}, dernier cours et gain {r}")
            ok += bool(d and r)
        except Exception as e:
            print(f"   {s} : échec ({e})")
    if ok < 4:
        sys.exit(1)


if __name__ == "__main__":
    if sys.argv[1:] == ["--verifier"]:
        verifier()
    else:
        executer(dt.date.fromisoformat(sys.argv[1]) if len(sys.argv) > 1 else None)
