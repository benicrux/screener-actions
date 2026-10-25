"""Tous les réglages du screener, modifiables sans toucher au reste du code."""
import os

# --- Univers d'actions ------------------------------------------------------
# Tailles retenues (les « Nano Cap », sous ~50 M$, sont écartées : données trop pauvres)
TAILLES_RETENUES = ["Mega Cap", "Large Cap", "Mid Cap", "Small Cap", "Micro Cap"]
# Reconstruire la liste des actions tous les N jours
UNIVERS_MAJ_JOURS = 30
# Pays écartés (actions impossibles à acheter depuis la France)
PAYS_EXCLUS = ["Russia"]
# Écarter les fonds cotés (fonds fermés, « investment trusts ») et les certificats
# étrangers (ADR de gré à gré, BDR brésiliens), qui doublonnent les vraies sociétés
EXCLURE_FONDS = True

# --- Collecte Yahoo Finance --------------------------------------------------
# Durée maximale de collecte par lancement (le robot GitHub est limité à 6 h)
BUDGET_MINUTES = int(os.environ.get("BUDGET_MINUTES") or 300)
# Nombre maximal de sociétés interrogées par lancement
LOT_MAX = 12000
# Requêtes simultanées (plus = plus rapide, mais Yahoo bloque si on abuse)
PARALLELE = 3
# Une société introuvable ou illisible chez Yahoo est retentée au bout de N jours
INTROUVABLE_RETENTE_JOURS = 30
# Après N blocages consécutifs de Yahoo, on arrête et on reprend au lancement suivant
BLOCAGES_MAX = 6

# --- Notes -------------------------------------------------------------------
# Pondérations de la note investisseur (en %). Inspirées de Zone Bourse, ajustées
# par le test sur le passé (octobre 2026) : la valorisation est le critère qui
# annonce le mieux la performance ; la situation financière, le moins.
POIDS_INVESTISSEUR = {
    "valorisation": 30,
    "croissance": 15,
    "rentabilite": 15,
    "situation_fi": 10,
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
# Une société n'est archivée qu'une fois tous les N jours (suffisant pour les révisions)
ARCHIVE_INTERVALLE_JOURS = 7
