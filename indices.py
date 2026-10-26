"""Composition des grands indices boursiers, pour le filtre « Indice » du radar de l'accueil.

Une fois par mois, la tâche de nuit relit sur Wikipédia (en anglais) la liste des sociétés
de chaque indice, puis retrouve chacune dans la liste mondiale du screener
(data/univers.csv) : d'abord par son symbole Yahoo, puis par son code ISIN quand la page en
donne un, enfin par son nom. Le résultat est écrit dans data/indices.json.

    python indices.py            # relit les indices dont la composition a plus de 30 jours
    python indices.py --tout     # relit tous les indices

Si une page ne répond pas ou a changé de présentation, la composition précédente de cet
indice est gardée et l'erreur notée dans le fichier ; le contrôle de santé prévient par
e-mail si cela dure (voir sante.py).
"""
from __future__ import annotations

import bisect
import datetime as dt
import html as html_std
import io
import json
import re
import sys
import time
import unicodedata
import urllib.request
from pathlib import Path

import pandas as pd

FICHIER = Path("data/indices.json")
UNIVERS = Path("data/univers.csv")
WIKI = "https://en.wikipedia.org/wiki/"
# Wikipédia demande un nom d'outil et un moyen de contact (ici, le dépôt)
AGENT = "screener-actions/1.0 (https://github.com/benicrux/screener-actions)"
RELECTURE_JOURS = 30

# (identifiant, nom affiché, continent, page Wikipédia, colonnes du code, règle de conversion
#  en symbole Yahoo, nombre de sociétés attendu, description courte)
# Règles : "us" (BRK.B -> BRK-B), "tel" (le code a déjà son suffixe Yahoo : MC.PA ; « tel:.SW » :
# suffixe ajouté s'il manque),
# ".L", ".TO"… (suffixe ajouté, les points deviennent des tirets : BT.A -> BT-A.L),
# "hk" (SEHK: 5 -> 0005.HK), "jp" (texte « (TYO: 7203) » -> 7203.T)
INDICES = [
    ("sp500", "S&P 500", "Amérique du Nord", "List_of_S%26P_500_companies",
     ("Symbol",), "us", 503, "Les 500 plus grandes sociétés américaines"),
    ("nasdaq100", "Nasdaq-100", "Amérique du Nord", "List_of_NASDAQ-100_companies",
     ("Ticker", "Symbol"), "us", 101, "Les 100 plus grandes sociétés non financières du Nasdaq, surtout technologiques"),
    ("dow", "Dow Jones", "Amérique du Nord", "List_of_Dow_Jones_Industrial_Average_companies",
     ("Symbol", "Ticker"), "us", 30, "30 grandes sociétés américaines emblématiques"),
    ("tsx60", "S&P/TSX 60", "Amérique du Nord", "S%26P/TSX_60",
     ("Symbol", "Ticker"), ".TO", 60, "Les 60 plus grandes sociétés canadiennes"),
    ("eurostoxx50", "Euro Stoxx 50", "Europe", "EURO_STOXX_50",
     ("Ticker", "Symbol"), "tel", 50, "Les 50 plus grandes sociétés de la zone euro"),
    ("cac40", "CAC 40", "Europe", "CAC_40",
     ("Ticker", "Symbol"), "tel:.PA", 40, "Les 40 plus grandes sociétés de la Bourse de Paris"),
    ("dax", "DAX", "Europe", "DAX",
     ("Ticker", "Symbol"), "tel:.DE", 40, "Les 40 plus grandes sociétés allemandes"),
    ("ftse100", "FTSE 100", "Europe", "FTSE_100_Index",
     ("Ticker", "EPIC", "Symbol"), ".L", 100, "Les 100 plus grandes sociétés de la Bourse de Londres"),
    ("smi", "SMI", "Europe", "Swiss_Market_Index",
     ("Ticker", "Symbol"), "tel:.SW", 20, "Les 20 plus grandes sociétés suisses"),
    ("nikkei225", "Nikkei 225", "Asie", "Nikkei_225",
     (), "jp", 225, "225 grandes sociétés japonaises"),
    ("hangseng", "Hang Seng", "Asie", "Hang_Seng_Index",
     ("Ticker", "Code", "Symbol"), "hk", 85, "Les plus grandes sociétés de la Bourse de Hong Kong"),
    ("nifty50", "NIFTY 50", "Asie", "NIFTY_50",
     ("Symbol", "Ticker"), ".NS", 50, "Les 50 plus grandes sociétés indiennes"),
    ("asx50", "S&P/ASX 50", "Océanie", "S%26P/ASX_50",
     ("Symbol", "Code", "Ticker"), ".AX", 50, "Les 50 plus grandes sociétés australiennes"),
]

# Une page est acceptée si elle liste entre 75 % et 135 % du nombre de sociétés attendu,
# et si au moins 70 % d'entre elles sont retrouvées dans la liste mondiale du screener
LIGNES_MIN, LIGNES_MAX, TROUVEES_MIN = 0.75, 1.35, 0.70

MOTS_VIDES = {
    "inc", "incorporated", "corp", "corporation", "co", "company", "companies", "plc", "ltd",
    "limited", "sa", "se", "ag", "nv", "spa", "the", "holdings", "holding", "group", "groupe",
    "ab", "asa", "oyj", "kgaa", "and", "class", "shares", "share", "ordinary", "common", "de",
    "llc", "lp", "bhd", "tbk", "pcl", "kk", "reit", "trust", "of", "aktiengesellschaft",
    "societe", "anonyme", "cie", "hldg", "hldgs", "intl",
}


# --------------------------------------------------------------------------- #
# Lecture des pages
# --------------------------------------------------------------------------- #
def nom_simple(nom: str) -> str:
    """« Alphabet Inc. (Class A) » -> « alphabet » : pour retrouver une société par son nom."""
    s = re.sub(r"\[[^\]]*\]|\([^)]*\)", " ", str(nom))   # notes et parenthèses
    s = re.sub(r"(?i)\b(?:class|series)\s+[a-z]\b", " ", s)    # « Class H »
    s = re.sub(r"\b(?:[A-Za-z]\.){2,}", lambda m: m.group(0).replace(".", ""), s)  # N.V. -> NV
    s = "".join(" " if unicodedata.category(c)[0] in "PSZ" else c for c in s)  # « Brown–Forman »
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().lower()
    mots = [m for m in re.split(r"[^a-z0-9]+", s) if m and m not in MOTS_VIDES]
    return " ".join(mots)


def nettoyer_code(brut) -> str:
    """« SEHK: 5 » -> « 5 », « NYSE: MMM[1] » -> « MMM »."""
    if brut is None or (isinstance(brut, float) and pd.isna(brut)):
        return ""
    if isinstance(brut, float) and brut.is_integer():
        brut = int(brut)
    s = re.sub(r"\[[^\]]*\]", "", str(brut)).replace("\xa0", " ").strip()
    if ":" in s:
        s = s.rsplit(":", 1)[1]
    s = s.strip().split()[0] if s.strip() else ""
    return s.strip().upper()


def symbole_yahoo(brut, regle: str) -> str | None:
    code = nettoyer_code(brut)
    if not code or not re.fullmatch(r"[A-Z0-9.&\-]+", code):
        return None
    if regle == "us":
        return code.replace(".", "-")
    if regle.startswith("tel"):
        # Code avec son suffixe Yahoo (MC.PA) ; sinon, suffixe de la Bourse de l'indice s'il est donné
        if re.search(r"\.[A-Z]{1,3}$", code):
            return code
        return code.replace(".", "-") + regle[4:] if regle[4:] else None
    if regle == "hk":
        return f"{int(code):04d}.HK" if code.isdigit() else None
    if regle == "jp":
        return f"{code}.T" if re.fullmatch(r"[0-9][0-9A-Z]{3}", code) else None
    # Suffixe de la Bourse : BT.A -> BT-A.L, RR. -> RR.L, RCI.B -> RCI-B.TO
    return code.rstrip(".").replace(".", "-") + regle


def _colonnes(df: pd.DataFrame) -> list[str]:
    noms = []
    for c in df.columns:
        if isinstance(c, tuple):
            parties = [str(x) for x in c if not str(x).startswith("Unnamed")]
            c = " ".join(dict.fromkeys(parties))
        noms.append(re.sub(r"\[[^\]]*\]", "", str(c)).strip())
    return noms


def _trouver(noms: list[str], voulus: tuple, exclus=("isin", "gics", "sector", "cusip", "weight")) -> int | None:
    bas = [n.lower() for n in noms]
    for v in voulus:                       # nom exact d'abord
        if v.lower() in bas:
            return bas.index(v.lower())
    for v in voulus:                       # puis nom qui contient le mot
        for j, n in enumerate(bas):
            if v.lower() in n and not any(x in n for x in exclus):
                return j
    return None


def lire_tableau(page_html: str, colonnes: tuple, regle: str, attendu: int) -> list[dict]:
    """Lignes du tableau de la page qui ressemble le plus à la composition de l'indice."""
    tableaux = pd.read_html(io.StringIO(page_html))
    candidats = []
    for df in tableaux:
        noms = _colonnes(df)
        j = _trouver(noms, colonnes)
        if j is None and len(df) > 1:
            # Titres écrits comme une ligne ordinaire (page du SMI) : la 1re ligne devient l'en-tête
            df = df.iloc[1:].set_axis([str(x) for x in df.iloc[0]], axis=1)
            noms = _colonnes(df)
            j = _trouver(noms, colonnes)
        if j is None:
            continue
        jn = _trouver(noms, ("Company", "Security", "Name", "Constituent", "Company name"),
                      exclus=("ticker", "symbol", "code"))
        ji = next((k for k, n in enumerate(noms) if "isin" in n.lower()), None)
        lignes = []
        for _, r in df.iterrows():
            sym = symbole_yahoo(r.iloc[j], regle)
            if not sym:
                continue
            lignes.append({"code": nettoyer_code(r.iloc[j]), "symbole": sym,
                           "nom": "" if jn is None else str(r.iloc[jn]),
                           "isin": "" if ji is None else nettoyer_code(r.iloc[ji])})
        if lignes:
            candidats.append(lignes)
    if not candidats:
        raise ValueError("aucun tableau avec une colonne de codes")
    return min(candidats, key=lambda l: abs(len(l) - attendu))


def lire_liste_japon(page_html: str) -> list[dict]:
    """Nikkei 225 : liste à puces « Honda Motor Co., Ltd. (TYO: 7267) »."""
    texte = re.sub(r"(?is)<(script|style)\b.*?</\1>", "", page_html)
    texte = re.sub(r"(?i)<br\s*/?>|</li>|</p>|</tr>", "\n", texte)
    texte = html_std.unescape(re.sub(r"<[^>]+>", "", texte)).replace("\xa0", " ")
    vus, lignes = set(), []
    for m in re.finditer(r"([^\n()]*?)\s*\(\s*(?:TYO|TSE)\s*:\s*([0-9][0-9A-Z]{3})\s*\)", texte):
        nom, code = m.group(1).strip(" ,;·-"), m.group(2)
        if code not in vus:
            vus.add(code)
            lignes.append({"code": code, "symbole": f"{code}.T", "nom": nom, "isin": ""})
    if not lignes:
        raise ValueError("aucun code « TYO: … » trouvé")
    return lignes


def lire_page(page_html: str, colonnes: tuple, regle: str, attendu: int) -> list[dict]:
    if regle == "jp":
        return lire_liste_japon(page_html)
    return lire_tableau(page_html, colonnes, regle, attendu)


# --------------------------------------------------------------------------- #
# Correspondance avec la liste mondiale du screener
# --------------------------------------------------------------------------- #
class Correspondance:
    def __init__(self, univers: pd.DataFrame):
        self.symboles = set(univers["symbole"])
        self.continent = dict(zip(univers["symbole"], univers.get("continent", pd.Series(dtype=str))))
        self.par_isin = {i: s for i, s in zip(univers["isin"], univers["symbole"])
                         if isinstance(i, str) and len(i) == 12}
        self.par_nom: dict[str, list[str]] = {}
        for nom, s in zip(univers["nom"], univers["symbole"]):
            n = nom_simple(nom)
            if n:
                self.par_nom.setdefault(n, []).append(s)
        self.noms_tries = sorted(self.par_nom)

    def _choisir(self, candidats: list[str], continent: str | None) -> list[str]:
        """Plusieurs cotations du même nom (actions A et H d'une banque chinoise…) : celles du
        continent de l'indice d'abord ; au-delà de 3, le nom est trop commun pour conclure."""
        proches = [s for s in candidats if self.continent.get(s) == continent] or candidats
        return proches if len(proches) <= 3 else []

    def trouver(self, ligne: dict, continent: str | None = None) -> list[str]:
        s = ligne["symbole"]
        if s in self.symboles:
            return [s]
        if ligne.get("isin") in self.par_isin:
            return [self.par_isin[ligne["isin"]]]
        nom = nom_simple(ligne.get("nom", ""))
        if not nom:
            return []
        if nom in self.par_nom:
            return self._choisir(self.par_nom[nom], continent)
        # Nom abrégé sur Wikipédia : « Ping An Insurance » pour « Ping An Insurance (Group)
        # Company of China » ; seulement à partir de deux mots, et si un seul nom commence ainsi
        if " " in nom:
            k = bisect.bisect_left(self.noms_tries, nom + " ")
            suites = []
            while k < len(self.noms_tries) and self.noms_tries[k].startswith(nom + " "):
                suites.append(self.noms_tries[k])
                k += 1
            if len(suites) == 1:
                return self._choisir(self.par_nom[suites[0]], continent)
        return []


def composer(lignes: list[dict], corr: Correspondance, attendu: int, continent: str | None = None) -> dict:
    """Membres retrouvés ; lève une erreur si la page ne ressemble pas à l'indice."""
    if not LIGNES_MIN * attendu <= len(lignes) <= LIGNES_MAX * attendu:
        raise ValueError(f"{len(lignes)} sociétés lues, {attendu} attendues : la page a sans doute changé")
    membres, manquants = set(), []
    for l in lignes:
        trouves = corr.trouver(l, continent)
        if trouves:
            membres.update(trouves)
        else:
            manquants.append(f"{l['code']} {l['nom']}".strip())
    if len(lignes) - len(manquants) < TROUVEES_MIN * len(lignes):
        raise ValueError(f"seulement {len(lignes) - len(manquants)} sociétés sur {len(lignes)} "
                         "retrouvées dans la liste mondiale")
    return {"membres": sorted(membres), "lues": len(lignes), "manquantes": manquants[:30]}


# --------------------------------------------------------------------------- #
# Mise à jour du fichier
# --------------------------------------------------------------------------- #
def telecharger(page: str) -> str:
    req = urllib.request.Request(WIKI + page, headers={"User-Agent": AGENT})
    with urllib.request.urlopen(req, timeout=40) as r:
        return r.read().decode("utf-8", "replace")


def mettre_a_jour(ancien: dict, lire, corr: Correspondance, aujourd_hui: str,
                  tout: bool = False, liste: list | None = None) -> dict:
    """Relit les indices trop anciens ; garde la composition précédente en cas d'échec.

    `lire(page)` renvoie le HTML d'une page (le réseau, ou une fonction de test)."""
    anciens = ancien.get("indices", {})
    jour = dt.date.fromisoformat(aujourd_hui)
    resultat = {}
    for ident, nom, continent, page, colonnes, regle, attendu, description in liste or INDICES:
        avant = anciens.get(ident, {})
        info = {"nom": nom, "continent": continent, "description": description,
                "membres": avant.get("membres", []), "lu": avant.get("lu"),
                "lues": avant.get("lues"), "manquantes": avant.get("manquantes", [])}
        recent = info["lu"] and (jour - dt.date.fromisoformat(info["lu"])).days < RELECTURE_JOURS
        if recent and not tout:
            info["echec_depuis"] = avant.get("echec_depuis")
            resultat[ident] = info
            continue
        try:
            info.update(composer(lire_page(lire(page), colonnes, regle, attendu), corr, attendu, continent))
            info["lu"], info["echec_depuis"], info["erreur"] = aujourd_hui, None, None
            print(f"  {nom} : {len(info['membres'])} sociétés retrouvées sur {info['lues']}")
        except Exception as e:  # noqa: BLE001 - une page en échec ne bloque pas les autres
            info["erreur"] = f"{type(e).__name__}: {e}"[:300]
            info["echec_depuis"] = avant.get("echec_depuis") or aujourd_hui
            print(f"  {nom} : échec ({info['erreur']}) ; composition précédente gardée "
                  f"({len(info['membres'])} sociétés)")
        resultat[ident] = info
    return {"maj": aujourd_hui, "indices": resultat}


def main() -> None:
    tout = "--tout" in sys.argv
    ancien = json.loads(FICHIER.read_text()) if FICHIER.exists() else {}
    univers = pd.read_csv(UNIVERS, dtype=str, keep_default_na=False)
    corr = Correspondance(univers)

    def lire(page: str) -> str:
        time.sleep(1)  # politesse envers Wikipédia
        return telecharger(page)

    print("Composition des grands indices :")
    nouveau = mettre_a_jour(ancien, lire, corr, dt.date.today().isoformat(), tout)
    FICHIER.write_text(json.dumps(nouveau, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    try:
        main()
    except Exception as e:  # noqa: BLE001 - le calcul de la nuit continue sans les indices
        print(f"::warning::Composition des grands indices non relue : {e}")
