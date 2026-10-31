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

# --- Contrôle de santé après chaque calcul ----------------------------------------
# En dessous de ces seuils, le site n'est pas republié et GitHub envoie un e-mail d'échec
SANTE_COURS_MIN = 20_000      # cours du jour reçus de Yahoo (environ 26 000 normalement)
SANTE_NOTEES_MIN = 20_000     # sociétés notées (environ 24 000 normalement)
SANTE_GRAVES_MAX = 2_500      # sociétés retirées par les contrôles (quelques centaines normalement)
# Nuits de suite où Yahoo a bloqué ou n'a rien renvoyé, avant l'alerte par e-mail
SANTE_NUITS_MAX = 3
# Jours de suite où la composition d'un grand indice n'a pas pu être relue sur Wikipédia
SANTE_INDICES_JOURS = 3

# --- Radar de la page d'accueil -----------------------------------------------------
# Sociétés de qualité bon marché, sans risque de faillite apparent (voir le journal du
# projet, 26 octobre 2026, pour le choix de ces seuils)
RADAR_NOTE_MIN = 75            # note investisseur
RADAR_VALORISATION_MIN = 65    # parmi les 35 % les moins chères de leur secteur
RADAR_SITUATION_MIN = 30       # situation financière (non notée pour les banques : acceptée)
RADAR_CAPI_MIN_EUR = 100e6     # capitalisation minimale, en euros

# --- Liste « Rallye 5 ans » de l'accueil -----------------------------------------
# Petites sociétés bon marché à la fois sur leur excédent brut d'exploitation et sur leur
# actif net, bénéficiaires, qui ne diluent pas leurs actionnaires : la recette des actions
# multipliées par 10 (étude Yartseva, 2025). Testée à 5 ans sur les comptes de la SEC (voir
# le rapport d'analyse du 31 octobre 2026 et la page « Tests »).
RALLYE_CAPI_MIN_EUR = 100e6     # capitalisation minimale, en euros
RALLYE_TAILLE_PART = 0.5        # dans la moitié la plus petite des sociétés
RALLYE_BON_MARCHE_PART = 0.30   # parmi les 30 % les moins chères (EBITDA / VE et actif net / capitalisation)
RALLYE_DILUTION_MAX = 0.10      # au plus 10 % d'actions en plus sur 3 ans
RALLYE_TRESORERIE_POSITIVE = True  # trésorerie disponible positive (quand elle est connue)

# Radar et Rallye : au plus 25 % des sociétés d'un même pays (les mieux notées sont gardées),
# pour ne pas dépendre d'un seul marché. Sans effet mesurable sur le test sur le passé.
PAYS_PART_MAX = 0.25
