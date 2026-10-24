# Pépites : screener d'actions mondial

Un screener gratuit inspiré de Zone Bourse : environ 27 000 sociétés cotées dans le monde, classées par continent, pays, secteur et industrie, avec des notes sur 100 (valorisation, croissance, rentabilité, situation financière, révisions des analystes, publications, visibilité) et une note investisseur qui les résume.

**Mission :** faire ressortir les entreprises de qualité que le marché sous-évalue encore.

**Coût : 0 €.** GitHub Actions et GitHub Pages sont gratuits pour un dépôt public.

---

## Mise en place (une seule fois)

1. **Settings → Pages** : dans *Build and deployment*, *Source*, choisissez **GitHub Actions**.
2. Onglet **Actions** → **Screener** → **Run workflow** → **Run workflow**.
3. Le site est à l'adresse `https://benicrux.github.io/screener-actions/`. Sur téléphone, « Ajouter à l'écran d'accueil » pour l'avoir comme une appli.

Ensuite tout est automatique : le calcul tourne **chaque nuit**.

## Comment ça marche

- **Chaque nuit**, le robot récupère les cours du jour de toutes les sociétés, puis les données détaillées (comptes, prévisions des analystes, publications) d'un lot de quelques milliers de sociétés. Le monde entier est relu en une à deux semaines. Les premiers jours, les grandes sociétés arrivent d'abord, les petites ensuite.
- **Les notes** sont des classements : 80 veut dire que la société fait mieux que 80 % des sociétés de son secteur. Les banques et assureurs sont comparés entre eux, sur le PER, le cours / actif net et la rentabilité des fonds propres.
- **La note investisseur** pondère : valorisation 25 %, croissance 15 %, rentabilité 15 %, situation financière 15 %, révisions 15 %, publications 10 %, visibilité 5 %. Les prévisions des analystes comptent plus que le passé pour la croissance et la rentabilité.
- **Les révisions sur 4 mois et 1 an** se remplissent avec le temps : le screener archive les prévisions des analystes à chaque lecture (`data/estimations/`).
- **Les favoris** sont gardés dans le navigateur (téléphone ou ordinateur). La fiche montre l'évolution du cours et de la note depuis l'ajout.

## Régler le screener

Tout est dans `config.py` : pondérations de la note investisseur, durée de collecte, taille des lots. Pour modifier : ouvrez le fichier sur GitHub, cliquez le crayon ✏️, changez la valeur, puis **Commit changes**. Le changement s'applique au calcul suivant.

## Ce qu'il faut savoir

- Les données viennent de **Yahoo Finance** (source non officielle) et de **FinanceDatabase** (liste des sociétés). Elles peuvent comporter des erreurs, surtout pour les petites sociétés et les cotations en devises différentes des comptes. Vérifiez toujours avant d'investir.
- Si Yahoo bloque temporairement les requêtes, le robot s'arrête proprement et reprend la nuit suivante.
- Sont écartés : les sociétés russes (impossibles à acheter depuis la France), les fonds cotés et les certificats étrangers (ADR, GDR, BDR), qui doublonnent les vraies sociétés. Réglable dans `config.py`.
- Ce screener est un outil de repérage, pas un conseil en investissement.

## Organisation du code

| Fichier | Rôle |
|---|---|
| `config.py` | Tous les réglages |
| `referentiels.py` | Pays, continents, secteurs et industries en français |
| `univers.py` | Liste mondiale des sociétés (une seule cotation par société) |
| `collecte.py` | Lecture des données Yahoo Finance et archive des prévisions |
| `notes.py` | Calcul des indicateurs et des notes sur 100 |
| `rendu.py`, `web/` | Le site (tableau, filtres, fiches, favoris) |
| `data/` | Liste des sociétés, taux de change, archive des prévisions, statut |
| branche `donnees` | Les données détaillées de chaque société, remplacées à chaque passage |
| `.github/workflows/screener.yml` | Le planning de nuit et la publication |

Pour tester sur un ordinateur : `pip install -r requirements.txt`, `python main.py`, puis ouvrez `site/` avec un petit serveur (`python -m http.server -d site`).
