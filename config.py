"""Tous les réglages du screener, modifiables sans toucher au reste du code."""
import os

# --- Univers d'actions ------------------------------------------------------
# Tailles retenues (les « Nano Cap », sous ~50 M$, sont écartées : données trop pauvres)
TAILLES_RETENUES = ["Mega Cap", "Large Cap", "Mid Cap", "Small Cap", "Micro Cap"]
# Reconstruire la liste des actions tous les N jours
UNIVERS_MAJ_JOURS = 30

# --- Collecte Yahoo Finance --------------------------------------------------
# Durée maximale de collecte par lancement (le robot GitHub est limité à 6 h)
BUDGET_MINUTES = int(os.environ.get("BUDGET_MINUTES") or 300)
# Nombre maximal de sociétés interrogées par lancement
LOT_MAX = 6000
# Requêtes simultanées (plus = plus rapide, mais Yahoo bloque si on abuse)
PARALLELE = 3
# Une société introuvable chez Yahoo est retentée au bout de N jours
INTROUVABLE_RETENTE_JOURS = 30
# Après N blocages consécutifs de Yahoo, on arrête et on reprend au lancement suivant
BLOCAGES_MAX = 6

# --- Notes -------------------------------------------------------------------
# Pondérations de la note investisseur (en %). Inspirées de Zone Bourse, ajustées
# après le test sur Lion Finance et Afentra (valorisation renforcée).
POIDS_INVESTISSEUR = {
    "valorisation": 25,
    "croissance": 15,
    "rentabilite": 15,
    "situation_fi": 15,
    "revisions_lt": 15,
    "publication": 10,
    "visibilite": 5,
}
# Note trading (court terme) : moyenne simple de ces notes
COMPOSANTES_TRADING = ["valorisation", "revisions_ct", "visibilite"]
# Part minimale des pondérations disponibles pour calculer la note investisseur
COUVERTURE_MIN = 50
# Une note est calculée au sein du secteur s'il compte au moins N sociétés notables,
# sinon par rapport à toutes les actions
TAILLE_MIN_SECTEUR = 30

# --- Archives des prévisions (révisions sur 4 mois et 1 an) --------------------
ARCHIVE_MOIS_CONSERVES = 15
