"""Contrôle de santé, sans intervention humaine.

Fait échouer le lancement GitHub, ce qui envoie un e-mail au propriétaire du dépôt, quand
quelque chose ne va pas. Deux moments :

    python sante.py avant-publication   # données du jour anormales : le site n'est pas republié
    python sante.py plusieurs-nuits     # Yahoo bloque depuis plusieurs nuits : alerte seulement
    python sante.py tests-trimestriels Monde   # (ou États-Unis) la note s'est-elle dégradée ?

N'utilise que la bibliothèque standard de Python.
"""
import csv
import json
import os
import sys
from pathlib import Path

import config

STATUT = Path("data/statut.json")
HISTORIQUE = Path("data/retro_historique.csv")


def degradation(lignes: list[dict], zone: str) -> list[str]:
    """Compare le dernier test sur le passé d'une zone au précédent."""
    tests = [l for l in lignes if l.get("zone", "").startswith(zone)]
    if not tests:
        return [f"Aucun résultat de test sur le passé pour « {zone} » : le test n'a pas abouti."]
    dernier = tests[-1]
    ecart = float(dernier["ecart_mieux_moins_bien"])
    gagnantes, dates = int(dernier["dates_gagnantes"]), int(dernier["dates"])
    p = []
    if ecart <= 0:
        p.append(f"{dernier['zone']} : les sociétés les mieux notées ne font plus mieux que les "
                 f"moins bien notées (écart de {ecart * 100:+.1f} points). La note est à revoir.")
    elif len(tests) >= 2:
        avant = float(tests[-2]["ecart_mieux_moins_bien"])
        if avant > 0 and ecart < avant / 2:
            p.append(f"{dernier['zone']} : l'avantage des mieux notées a été plus que divisé par "
                     f"deux depuis le test précédent ({avant * 100:+.1f} puis {ecart * 100:+.1f} "
                     "points). À surveiller, et à discuter si cela se confirme.")
    if dates and gagnantes / dates < 0.5:
        p.append(f"{dernier['zone']} : les mieux notées n'ont fait mieux qu'à {gagnantes} dates "
                 f"sur {dates}.")
    return p


def problemes(statut: dict, moment: str, collecte_faite: bool) -> list[str]:
    p = []
    if moment == "avant-publication":
        cours = statut.get("cours_du_jour") or 0
        if collecte_faite and cours < config.SANTE_COURS_MIN:
            p.append(f"Yahoo n'a renvoyé que {cours} cours du jour (environ 26 000 normalement). "
                     "Le site garde sa version précédente.")
        notees = statut.get("notees") or 0
        if notees < config.SANTE_NOTEES_MIN:
            p.append(f"Seulement {notees} sociétés notées (environ 24 000 normalement). "
                     "Le site garde sa version précédente.")
        graves = (statut.get("anomalies") or {}).get("graves") or 0
        if graves > config.SANTE_GRAVES_MAX:
            p.append(f"{graves} sociétés retirées par les contrôles (quelques centaines "
                     "normalement) : les données de Yahoo semblent dérangées. "
                     "Le site garde sa version précédente.")
    else:
        nuits = statut.get("nuits_difficiles") or 0
        if nuits >= config.SANTE_NUITS_MAX:
            p.append(f"Depuis {nuits} nuits, Yahoo bloque les requêtes ou ne renvoie rien. "
                     "Les cours du jour peuvent encore arriver, mais les comptes et prévisions "
                     "ne sont plus relus. Si cela dure, Yahoo a sans doute changé son "
                     "fonctionnement : le programme est à adapter.")
    return p


def main() -> None:
    moment = sys.argv[1] if len(sys.argv) > 1 else "avant-publication"
    if moment == "tests-trimestriels":
        zone = sys.argv[2] if len(sys.argv) > 2 else "Monde"
        lignes = list(csv.DictReader(HISTORIQUE.open())) if HISTORIQUE.exists() else []
        signaler(degradation(lignes, zone))
        return
    if not STATUT.exists():
        print("::error::Fichier data/statut.json absent : le calcul n'a pas abouti.")
        sys.exit(1)
    statut = json.loads(STATUT.read_text())
    signaler(problemes(statut, moment, collecte_faite=not os.environ.get("SANS_COLLECTE")))


def signaler(liste: list[str]) -> None:
    resume = os.environ.get("GITHUB_STEP_SUMMARY")
    if not liste:
        print("Contrôle de santé : tout est normal.")
        return
    for texte in liste:
        print(f"::error::{texte}")
    if resume:
        with open(resume, "a") as f:
            f.write("## Contrôle de santé : un problème à regarder\n\n")
            f.write("".join(f"- {t}\n" for t in liste))
    sys.exit(1)


if __name__ == "__main__":
    main()
