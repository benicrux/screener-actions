"""Indicateurs économiques de la page d'accueil, relus chaque nuit.

Taux des banques centrales, taux à 10 ans, inflation, matières premières, devises,
volatilité et chômage, sur 5 ans. Sources gratuites et sans inscription :
- la Réserve fédérale de Saint-Louis (FRED), pour la plupart des séries ;
- la BCE, Eurostat et la Banque d'Angleterre, pour l'Europe ;
- l'OCDE, la BRI (Banque des règlements internationaux) et DBnomics, pour le Japon et la Chine ;
- Yahoo Finance, pour les prix de marché.

Chaque indicateur a une ou plusieurs sources, essayées dans l'ordre. Si aucune ne répond,
on garde les chiffres de la veille ; un indicateur sans chiffre est simplement masqué sur
le site. Les échecs sont notés dans data/macro.json (« erreurs »).

    python macro.py
"""
from __future__ import annotations

import csv
import datetime as dt
import io
import json
import sys
import urllib.parse
import urllib.request
from pathlib import Path

FICHIER = Path("data/macro.json")
ANNEES = 5
AGENT = "screener-actions (https://github.com/benicrux/screener-actions)"
ANCIENNETE_MAX_JOURS = 150  # au-delà, une source est jugée arrêtée : on passe à la suivante

# (identifiant, groupe, nom, mode, sources, secteurs qui montent, secteurs qui baissent)
# mode « points » : variation en points (taux) ; « pourcent » : variation en % (prix).
# Sources : ("fred", série), ("fred_glissement", série d'indice → variation sur un an),
# ("bce", flux, clé), ("eurostat", jeu, paramètres), ("boe", série), ("yahoo", symbole, facteur),
# ("oecd", flux, clé), ("bri", flux, clé), ("dbnomics", fournisseur/jeu/série)
# Depuis 2026 : la zone euro compte 21 pays (Bulgarie) et l'inflation suit une nouvelle
# nomenclature (ECOICOP 2) ; l'OCDE n'alimente plus les séries japonaises et chinoises de FRED.
INDICATEURS = [
    ("fed", "Taux des banques centrales", "Fed (États-Unis)", "points",
     [("fred", "DFEDTARU")], "Banques", "Immobilier, sociétés endettées"),
    ("bce", "Taux des banques centrales", "BCE (zone euro)", "points",
     [("fred", "ECBDFR"), ("bce", "FM", "D.U2.EUR.4F.KR.DFR.LEV")], "Banques", "Immobilier, sociétés endettées"),
    ("boe", "Taux des banques centrales", "Banque d'Angleterre", "points",
     [("boe", "IUDBEDR")], "Banques", "Immobilier"),
    ("boj", "Taux des banques centrales", "Banque du Japon", "points",
     [("bri", "WS_CBPOL", "M.JP"), ("bri2", "WS_CBPOL", "M.JP"), ("dbnomics", "BIS/WS_CBPOL/M.JP"),
      ("fred", "IRSTCB01JPM156N")], "Banques japonaises", "Exportateurs japonais"),
    ("us10", "Taux à 10 ans", "États-Unis", "points",
     [("fred", "DGS10"), ("yahoo", "^TNX", 1.0)], "Assureurs", "Valeurs de croissance chères"),
    ("de10", "Taux à 10 ans", "Allemagne", "points",
     [("fred", "IRLTLT01DEM156N"), ("bce", "IRS", "M.DE.L.L40.CI.0000.EUR.N.Z")],
     "Assureurs", "Valeurs de croissance chères"),
    ("inf_us", "Inflation sur un an", "États-Unis", "points",
     [("fred_glissement", "CPIAUCSL")], "Énergie, matières premières", "Consommation"),
    ("inf_ze", "Inflation sur un an", "Zone euro", "points",
     [("bce", "HICP", "M.U2.N.000000..ANR"),
      ("eurostat", "prc_hicp_minr", {"geo": "EA", "unit": "RCH_A", "coicop18": "TOTAL"}),
      ("eurostat", "prc_hicp_minr", {"geo": "EA21", "unit": "RCH_A", "coicop18": "TOTAL"}),
      ("bce", "ICP", "M.U2.N.000000.4.ANR")], "Énergie, matières premières", "Consommation"),
    ("inf_jp", "Inflation sur un an", "Japon", "points",
     [("oecd", "OECD.SDD.TPS,DSD_PRICES@DF_PRICES_ALL,1.0", "JPN.M.N.CPI.PA._T.N.GY"),
      ("oecd", "OECD.SDD.TPS,DSD_PRICES_COICOP2018@DF_PRICES_C2018_ALL,1.0", "JPN.M.N.CPI.PA._T.N.GY"),
      ("dbnomics", "OECD/DSD_PRICES@DF_PRICES_ALL/JPN.M.N.CPI.PA._T.N.GY"),
      ("dbnomics", "IMF/CPI/M.JP.PCPI_PC_CP_A_PT")], "Banques japonaises", "Consommation"),
    ("inf_cn", "Inflation sur un an", "Chine", "points",
     [("oecd", "OECD.SDD.TPS,DSD_PRICES@DF_PRICES_ALL,1.0", "CHN.M.N.CPI.PA._T.N.GY"),
      ("oecd", "OECD.SDD.TPS,DSD_PRICES_COICOP2018@DF_PRICES_C2018_ALL,1.0", "CHN.M.N.CPI.PA._T.N.GY"),
      ("dbnomics", "OECD/DSD_PRICES@DF_PRICES_ALL/CHN.M.N.CPI.PA._T.N.GY"),
      ("dbnomics", "IMF/CPI/M.CN.PCPI_PC_CP_A_PT")], "Luxe, matières premières", ""),
    ("brent", "Matières premières", "Pétrole (Brent), en $", "pourcent",
     [("fred", "DCOILBRENTEU"), ("yahoo", "BZ=F", 1.0)], "Énergie", "Aérien, chimie, transport"),
    ("cuivre", "Matières premières", "Cuivre, en $ la tonne", "pourcent",
     [("fred", "PCOPPUSDM"), ("yahoo", "HG=F", 2204.62)], "Mines, industrie", ""),
    ("or", "Matières premières", "Or, en $ l'once", "pourcent",
     [("yahoo", "GC=F", 1.0)], "Mines d'or", ""),
    ("eurusd", "Devises, marché et emploi", "1 euro en dollars", "pourcent",
     [("fred", "DEXUSEU"), ("yahoo", "EURUSD=X", 1.0)], "", "Tes actions américaines, en euros"),
    ("eurjpy", "Devises, marché et emploi", "1 euro en yens", "pourcent",
     [("yahoo", "EURJPY=X", 1.0)], "Exportateurs japonais", "Tes actions japonaises, en euros"),
    ("vix", "Devises, marché et emploi", "Volatilité (VIX)", "pourcent",
     [("fred", "VIXCLS"), ("yahoo", "^VIX", 1.0)], "", "Petites sociétés"),
    ("cho_us", "Devises, marché et emploi", "Chômage États-Unis", "points",
     [("fred", "UNRATE")], "", "Consommation, banques"),
    ("cho_ze", "Devises, marché et emploi", "Chômage zone euro", "points",
     [("eurostat", "une_rt_m", {"geo": "EA21", "sex": "T", "age": "TOTAL", "unit": "PC_ACT", "s_adj": "SA"}),
      ("eurostat", "une_rt_m", {"geo": "EA", "sex": "T", "age": "TOTAL", "unit": "PC_ACT", "s_adj": "SA"}),
      ("eurostat", "une_rt_m", {"geo": "EA20", "sex": "T", "age": "TOTAL", "unit": "PC_ACT", "s_adj": "SA"}),
      ("fred", "LRHUTTTTEZM156S")], "", "Consommation, banques"),
]


# --------------------------------------------------------------------------- #
# Lecture des différents formats (fonctions pures, testées)
# --------------------------------------------------------------------------- #
def lire_csv_fred(texte: str) -> list[tuple[str, float]]:
    """CSV de FRED : date, valeur (« . » quand il n'y a pas de chiffre)."""
    points = []
    for ligne in list(csv.reader(io.StringIO(texte)))[1:]:
        if len(ligne) >= 2 and ligne[1] not in ("", "."):
            try:
                points.append((ligne[0][:10], float(ligne[1])))
            except ValueError:
                continue
    return points


def lire_csv_bce(texte: str) -> list[tuple[str, float]]:
    """CSV au format SDMX (BCE, OCDE, BRI) : colonnes TIME_PERIOD et OBS_VALUE.

    Si la clé demandée contient un joker et renvoie plusieurs séries, on garde la plus
    récente (puis la plus longue)."""
    series: dict[str, list[tuple[str, float]]] = {}
    for r in csv.DictReader(io.StringIO(texte.lstrip("\ufeff"))):
        periode, valeur = r.get("TIME_PERIOD") or "", r.get("OBS_VALUE") or ""
        if not periode or valeur in ("", "NaN", "NA"):
            continue
        try:
            v = float(valeur)
        except ValueError:
            continue
        jour = (periode + "-01")[:10] if len(periode) == 7 else periode[:10]
        series.setdefault(r.get("KEY") or r.get("SERIES_KEY") or "", []).append((jour, v))
    if not series:
        return []
    return max(series.values(), key=lambda pts: (max(pts)[0], len(pts)))


def lire_dbnomics(js: dict) -> list[tuple[str, float]]:
    """JSON de DBnomics (api.db.nomics.world, v22) : une série, dates et valeurs."""
    doc = js["series"]["docs"][0]
    dates = doc.get("period_start_day") or doc["period"]
    points = []
    for d, v in zip(dates, doc["value"]):
        if isinstance(v, (int, float)):
            points.append(((d + "-01")[:10] if len(d) == 7 else d[:10], float(v)))
    return points


def lire_eurostat(js: dict) -> list[tuple[str, float]]:
    """JSON-stat d'Eurostat, une seule série : la dimension « time » porte les dates."""
    temps = js["dimension"]["time"]["category"]["index"]  # {"2024-01": 0, …}
    valeurs = js.get("value") or {}
    par_index = {int(k): v for k, v in valeurs.items()} if isinstance(valeurs, dict) else dict(enumerate(valeurs))
    points = []
    for periode, i in sorted(temps.items(), key=lambda x: x[1]):
        v = par_index.get(i)
        if v is not None:
            points.append((periode.replace("M", "-") + "-01" if len(periode) == 7 else periode, float(v)))
    return points


def lire_csv_boe(texte: str) -> list[tuple[str, float]]:
    """CSV de la Banque d'Angleterre : « 02 Jan 2024,5.25 »."""
    points = []
    for ligne in list(csv.reader(io.StringIO(texte)))[1:]:
        if len(ligne) >= 2 and ligne[1].strip():
            try:
                jour = dt.datetime.strptime(ligne[0].strip(), "%d %b %Y").date().isoformat()
                points.append((jour, float(ligne[1])))
            except ValueError:
                continue
    return points


def mensuel(points: list[tuple[str, float]]) -> list[tuple[str, float]]:
    """Dernière valeur de chaque mois, dans l'ordre."""
    mois: dict[str, float] = {}
    for jour, v in sorted(points):
        mois[jour[:7]] = v
    return sorted(mois.items())


def glissement(points: list[tuple[str, float]]) -> list[tuple[str, float]]:
    """Indice de prix → variation sur un an, en %."""
    m = dict(mensuel(points))
    res = []
    for mois_, v in sorted(m.items()):
        a, mm = int(mois_[:4]), mois_[5:7]
        avant = m.get(f"{a - 1}-{mm}")
        if avant:
            res.append((mois_ + "-01", round((v / avant - 1) * 100, 2)))
    return res


def resumer(points: list[tuple[str, float]], mode: str, depuis: str) -> dict | None:
    """Dernière valeur, variation sur un an et série mensuelle sur la période."""
    if not points:
        return None
    points = sorted(points)
    dernier_jour, derniere = points[-1]
    serie = [(m, v) for m, v in mensuel(points) if m >= depuis[:7]]
    if len(serie) < 24:
        return None
    il_y_a_un_an = (dt.date.fromisoformat(dernier_jour[:10]) - dt.timedelta(days=365)).isoformat()
    avant = [v for j, v in points if j <= il_y_a_un_an]
    variation = None
    if avant:
        variation = (derniere - avant[-1]) if mode == "points" else (
            (derniere / avant[-1] - 1) * 100 if avant[-1] else None)
    return {"valeur": round(derniere, 4), "date": dernier_jour[:10],
            "variation_1an": None if variation is None else round(variation, 2),
            "serie": [[m, round(v, 4)] for m, v in serie]}


# --------------------------------------------------------------------------- #
# Téléchargement
# --------------------------------------------------------------------------- #
def _get(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": AGENT, "Accept": "*/*"})
    with urllib.request.urlopen(req, timeout=40) as r:
        return r.read().decode("utf-8", "replace")


def telecharger(source: tuple, depuis: str) -> list[tuple[str, float]]:
    genre = source[0]
    if genre in ("fred", "fred_glissement"):
        debut = depuis if genre == "fred" else f"{int(depuis[:4]) - 1}{depuis[4:]}"
        url = f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={source[1]}&cosd={debut}"
        points = lire_csv_fred(_get(url))
        return glissement(points) if genre == "fred_glissement" else points
    if genre == "bce":
        url = (f"https://data-api.ecb.europa.eu/service/data/{source[1]}/{source[2]}"
               f"?format=csvdata&startPeriod={depuis[:7]}")
        return lire_csv_bce(_get(url))
    if genre == "eurostat":
        params = dict(source[2], sinceTimePeriod=depuis[:7], format="JSON", lang="fr")
        url = (f"https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/{source[1]}?"
               + urllib.parse.urlencode(params))
        return lire_eurostat(json.loads(_get(url)))
    if genre == "boe":
        debut = dt.date.fromisoformat(depuis).strftime("%d/%b/%Y")
        url = ("https://www.bankofengland.co.uk/boeapps/database/_iadb-fromshowcolumns.asp?"
               f"csv.x=yes&Datefrom={debut}&Dateto=now&SeriesCodes={source[1]}"
               "&CSVF=TN&UsingCodes=Y&VPD=Y&VFD=N")
        return lire_csv_boe(_get(url))
    if genre == "oecd":
        url = (f"https://sdmx.oecd.org/public/rest/data/{source[1]}/{source[2]}?startPeriod={depuis[:7]}"
               "&dimensionAtObservation=AllDimensions&format=csvfile")
        return lire_csv_bce(_get(url))
    if genre == "bri":
        url = (f"https://stats.bis.org/api/v1/data/{source[1]}/{source[2]}/all?startPeriod={depuis[:7]}"
               "&detail=dataonly&format=csv")
        return lire_csv_bce(_get(url))
    if genre == "bri2":
        url = (f"https://stats.bis.org/api/v2/data/dataflow/BIS/{source[1]}/1.0/{source[2]}"
               f"?startPeriod={depuis[:7]}&format=csv")
        return lire_csv_bce(_get(url))
    if genre == "dbnomics":
        chemin = urllib.parse.quote(source[1], safe="/@._-")
        return lire_dbnomics(json.loads(_get(f"https://api.db.nomics.world/v22/series/{chemin}?observations=1&format=json")))
    if genre == "yahoo":
        import collecte
        js = collecte._get_json(f"https://query1.finance.yahoo.com/v8/finance/chart/{source[1]}",
                                {"range": f"{ANNEES}y", "interval": "1d"})
        res = js["chart"]["result"][0]
        dates = [dt.datetime.fromtimestamp(t, dt.timezone.utc).date().isoformat() for t in res["timestamp"]]
        fermetures = res["indicators"]["quote"][0]["close"]
        return [(d, c * source[2]) for d, c in zip(dates, fermetures) if c is not None]
    raise ValueError(f"source inconnue : {genre}")


def collecter(aujourd_hui: dt.date | None = None) -> dict:
    aujourd_hui = aujourd_hui or dt.date.today()
    depuis = aujourd_hui.replace(year=aujourd_hui.year - ANNEES).isoformat()
    precedent = json.loads(FICHIER.read_text()) if FICHIER.exists() else {}
    anciens = {i["id"]: i for i in precedent.get("indicateurs", [])}
    indicateurs, erreurs = [], {}
    for ident, groupe, nom, mode, sources, hausse, baisse in INDICATEURS:
        resume, origine, messages = None, None, []
        for source in sources:
            nom_source = " ".join([source[0], str(source[1])] + ([source[2]] if len(source) > 2 and isinstance(source[2], str) else [])
                                  + ([source[2].get("geo", "")] if len(source) > 2 and isinstance(source[2], dict) else []))
            try:
                r = resumer(telecharger(source, depuis), mode, depuis)
            except Exception as e:  # une source qui ne répond pas : on essaie la suivante
                messages.append(f"{nom_source} : {type(e).__name__} {str(e)[:80]}")
                continue
            if r is None:
                messages.append(f"{nom_source} : pas assez de chiffres")
                continue
            age = (aujourd_hui - dt.date.fromisoformat(r["date"])).days
            if age > ANCIENNETE_MAX_JOURS:
                messages.append(f"{nom_source} : dernier chiffre du {r['date']}")
                continue
            resume, origine = r, f"{source[0]}:{source[1]}"
            break
        base = {"id": ident, "groupe": groupe, "nom": nom, "mode": mode,
                "hausse": hausse, "baisse": baisse}
        if resume:
            indicateurs.append({**base, **resume, "source": origine})
        elif ident in anciens:  # rien de neuf : on garde les chiffres précédents
            indicateurs.append({**anciens[ident], **base})
            erreurs[ident] = " ; ".join(messages)
        else:
            erreurs[ident] = " ; ".join(messages)
    return {"maj": aujourd_hui.isoformat(), "indicateurs": indicateurs, "erreurs": erreurs}


if __name__ == "__main__":
    resultat = collecter()
    FICHIER.parent.mkdir(exist_ok=True)
    FICHIER.write_text(json.dumps(resultat, ensure_ascii=False, separators=(",", ":")))
    print(f"Indicateurs économiques : {len(resultat['indicateurs'])} sur {len(INDICATEURS)}.")
    for ident, message in resultat["erreurs"].items():
        print(f"   {ident} : {message}")
    sys.exit(0)
