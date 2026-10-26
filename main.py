"""Lancement complet : liste des actions, collecte, notes, site.

    python main.py              # tout
    python main.py --sans-collecte   # recalcule les notes et le site avec les données déjà là
"""
from __future__ import annotations

import datetime as dt
import json
import os
import sys
from pathlib import Path

import pandas as pd

import collecte
import config
import controles
import notes
import rendu
import univers as module_univers


COLONNES_TEXTE = ["maj", "statut", "devise_cours", "devise_comptes", "devise_bpa", "devise_ca",
                  "surprises", "ex_a0", "ex_a1", "fin_exercice"]


def assembler(univ: pd.DataFrame, donnees: pd.DataFrame, cours: pd.DataFrame) -> pd.DataFrame:
    table = univ.merge(donnees.drop(columns=["nom"], errors="ignore"), on="symbole", how="left")
    for col in COLONNES_TEXTE + ["cours", "capi", "actions", "date_cours"]:
        if col not in table:
            table[col] = pd.Series(index=table.index, dtype=object)
    if not cours.empty:
        c = cours.dropna(subset=["cours"]).drop_duplicates("symbole").set_index("symbole")
        idx = table["symbole"]
        for col in ("cours", "devise_cours", "capi", "actions", "date_cours"):
            frais = idx.map(c[col]) if col in c else pd.Series(index=table.index, dtype=object)
            if col in table:
                table[col] = frais.where(frais.notna(), table[col])
            else:
                table[col] = frais
    return table


def main() -> None:
    sans_collecte = "--sans-collecte" in sys.argv or os.environ.get("SANS_COLLECTE")
    print("1. Liste mondiale des actions")
    univ = module_univers.charger()
    print(f"   {len(univ)} sociétés.")

    bilan, cours = {}, pd.DataFrame(columns=["symbole"])
    if not sans_collecte:
        print("2. Cours du jour")
        cours = collecte.cours_du_jour(univ["symbole"].tolist())
        print(f"   {len(cours)} cours récupérés.")
        print("3. Données détaillées (lot du jour)")
        bilan = collecte.collecter(univ)
        print(f"   Bilan : {bilan}")

    donnees = collecte.charger_donnees()
    devises = set(univ["devise"].dropna())
    for col in ("devise_cours", "devise_comptes", "devise_bpa", "devise_ca"):
        if col in donnees:
            devises |= set(donnees[col].dropna())
    if not cours.empty:
        devises |= set(cours["devise_cours"].dropna())
    devises = {d if d not in ("GBp", "GBX") else "GBP" for d in devises}
    devises |= {"GBP", "ZAR", "ILS"}
    if sans_collecte and collecte.DEVISES.exists():
        fx = dict(pd.read_csv(collecte.DEVISES).set_index("devise")["usd"])
    else:
        fx = collecte.taux_de_change(devises)

    print("4. Notes")
    table = assembler(univ, donnees, cours)
    table = notes.indicateurs(table, fx)
    vehicules = int((table["vehicule"] & table["statut"].eq("ok")).sum())
    table = table[~table["vehicule"]].copy()
    table = controles.controler(table)
    anomalies = controles.enregistrer(table)
    print(f"   Contrôles : {anomalies['graves']} sociétés retirées du classement, "
          f"{anomalies['legeres']} avec un chiffre écarté.")
    classees = table[~table["anomalie_grave"]].copy()
    n = notes.noter(classees)
    table["groupe"] = classees["groupe"]
    table = table.join(n.add_prefix("n_"))

    lues = (table["statut"] == "ok").sum()
    jamais = table["statut"].isna().sum()
    rythme = bilan.get("lues", 0) + bilan.get("introuvables", 0)
    statut = {
        "date": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "univers": int(len(univ)),
        "avec_donnees": int(lues),
        "notees": int(table["n_investisseur"].notna().sum()),
        "jamais_lues": int(jamais),
        "introuvables": int((table["statut"] == "introuvable").sum()),
        "illisibles": int((table["statut"] == "illisible").sum()),
        "vehicules_ecartes": vehicules,
        "anomalies": anomalies,
        "jours_restants": (int(-(-jamais // rythme)) if rythme and jamais else 0),
        "cours_du_jour": int(len(cours)),
        "collecte": bilan,
        "poids": config.POIDS_INVESTISSEUR,
        "usd_par_eur": fx.get("EUR"),
        "depot": os.environ.get("GITHUB_REPOSITORY"),
    }
    # Date du dernier passage complet (collecte de nuit), gardée par les lancements courts :
    # sert au créneau de rattrapage du matin, qui ne tourne que si la nuit n'a rien donné
    ancien = Path("data/statut.json")
    precedent = json.loads(ancien.read_text()).get("passage_complet") if ancien.exists() else None
    complet = not sans_collecte and config.BUDGET_MINUTES >= 60
    statut["passage_complet"] = (dt.datetime.now(dt.timezone.utc).date().isoformat()
                                 if complet else precedent)
    Path("data").mkdir(exist_ok=True)
    Path("data/statut.json").write_text(json.dumps(statut, ensure_ascii=False, indent=1))

    print("5. Site")
    rendu.generer(table, statut)
    print("Terminé.")


if __name__ == "__main__":
    main()
