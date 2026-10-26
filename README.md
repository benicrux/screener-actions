# Pépites : screener d'actions mondial

Un screener gratuit inspiré de Zone Bourse : environ 27 000 sociétés cotées dans le monde, classées par continent, pays, secteur et industrie, avec des notes sur 100 (valorisation, croissance, rentabilité, situation financière, révisions des analystes, publications, visibilité) et une note investisseur qui les résume.

**Mission :** faire ressortir les entreprises de qualité que le marché sous-évalue encore.

**Coût : 0 €.** GitHub Actions et GitHub Pages sont gratuits pour un dépôt public.

---

## Mise en place (une seule fois)

1. **Settings → Pages** : dans *Build and deployment*, *Source*, choisissez **GitHub Actions**.
2. Onglet **Actions** → **Screener** → **Run workflow** → **Run workflow**.
3. Le site est à l'adresse `https://benicrux.github.io/screener-actions/`. Sur téléphone, « Ajouter à l'écran d'accueil » pour l'avoir comme une appli.

Ensuite tout est automatique : le calcul tourne **chaque nuit**. GitHub retarde parfois les tâches programmées de plusieurs heures, voire les saute : un créneau de rattrapage, en milieu de matinée, relance le calcul seulement si la nuit n'a rien donné.

## Les pages du site

- **Accueil** : tes favoris (avec un signal « à revoir » quand la note a perdu 15 points, que la société n'est plus bon marché, que sa situation financière devient fragile ou après 6 mois sans réexamen), les publications de résultats des 7 jours, le **radar des pépites** et le **contexte économique**.
- **Screener** (`tableau.html`) : toutes les sociétés, avec les filtres et les fiches.
- **Test sur le passé** (`retro.html`) : ce que la note aurait donné ces dernières années.

Le radar garde les sociétés notées au moins 75, parmi les 35 % les moins chères de leur secteur, avec une situation financière d'au moins 30 (sans risque de faillite apparent) et plus de 100 M€ de capitalisation. Ces seuils se règlent dans `config.py` (rubrique « Radar »). « Ignorer 90 jours » et les favoris sont gardés dans le navigateur.

Le filtre **Indice** du radar sépare les sociétés des grands indices (S&P 500, Nasdaq-100, Dow Jones, S&P/TSX 60, Euro Stoxx 50, CAC 40, DAX, FTSE 100, SMI, Nikkei 225, Hang Seng, NIFTY 50, S&P/ASX 50) de toutes les autres ; il ne montre que les indices des continents choisis, avec le nombre de sociétés du radar dans chacun. La composition des indices est relue une fois par mois sur Wikipédia par `indices.py` : si une page ne répond pas ou a changé, la composition précédente est gardée.

Le contexte économique (taux, inflation, matières premières, devises, chômage) vient de la Réserve fédérale de Saint-Louis, de la BCE, d'Eurostat, de la Banque d'Angleterre et de Yahoo Finance, relus chaque nuit par `macro.py`. La plupart des indicateurs ont une source de secours. Si aucune ne répond, les chiffres de la veille sont gardés ; un indicateur jamais lu est simplement masqué. Le contrôle de santé prévient par e-mail si plus de la moitié manquent ou si les chiffres ont plus de 7 jours.

## Comment ça marche

- **Chaque nuit**, le robot récupère les cours du jour de toutes les sociétés, puis les données détaillées (comptes, prévisions des analystes, publications) d'un lot de quelques milliers de sociétés. Le monde entier est relu en une à deux semaines. Les premiers jours, les grandes sociétés arrivent d'abord, les petites ensuite.
- **Les notes** sont des classements : 80 veut dire que la société fait mieux que 80 % des sociétés de son secteur. Les banques et assureurs sont comparés entre eux, sur le PER, le cours / actif net et la rentabilité des fonds propres.
- **La note investisseur** pondère : valorisation 30 %, croissance 15 %, rentabilité 15 %, situation financière 10 %, révisions 15 %, publications 10 %, visibilité 5 %. Les prévisions des analystes comptent plus que le passé pour la croissance et la rentabilité.
- **Les révisions sur 4 mois et 1 an** se remplissent avec le temps : le screener archive les prévisions des analystes à chaque lecture (`data/estimations/`).
- **Les favoris** sont gardés dans le navigateur (téléphone ou ordinateur). La fiche montre l'évolution du cours et de la note depuis l'ajout.

## Tests de fiabilité, refaits automatiquement

| Quoi | Quand | Où voir le résultat |
|---|---|---|
| Tests du programme (lecture des données, contrôles) | Chaque nuit, avant le calcul ; s'ils échouent, rien n'est publié | Onglet **Actions** |
| Contrôles de cohérence des chiffres | Chaque nuit | Fiche de la société, `data/anomalies.csv` |
| Test sur le passé, monde (depuis fin 2023) | Chaque trimestre, le 2 janvier, avril, juillet et octobre | Page « Test sur le passé » |
| Test sur le passé, États-Unis (depuis 2012, comptes de la SEC) | Chaque trimestre, le 9 janvier, avril, juillet et octobre | Page « Test sur le passé » |

Les tests trimestriels relisent toutes les données et ajoutent les dates qui ont désormais 12 mois de recul. Chaque résultat est ajouté à `data/retro_historique.csv`, affiché sur la page : si l'écart entre les mieux et les moins bien notées s'effondre d'un trimestre à l'autre, c'est le signe qu'il faut revoir la note. Les pondérations, elles, ne changent jamais toutes seules.

## Fonctionnement autonome

Le screener n'a besoin de personne pour tourner : tout se fait sur GitHub, gratuitement.

| Quand | Ce qui se passe |
|---|---|
| Chaque nuit à 4 h 13 (heure d'hiver ; 5 h 13 en été) | Cours du jour, lecture d'un lot de comptes et de prévisions, contrôles, notes, contrôle de santé, publication du site |
| Chaque matin à 10 h 13 (11 h 13 en été) | Rattrapage, seulement si GitHub n'a pas lancé la tâche de nuit (cela arrive) |
| Tous les 30 jours | Mise à jour de la liste mondiale des sociétés (entrées et sorties de la cote) et de la composition des grands indices |
| Chaque trimestre | Les deux tests sur le passé, puis la vérification que la note tient encore |

La bibliothèque qui lit Yahoo (yfinance) se met à jour toute seule à chaque lancement, dans sa version 1.x : quand Yahoo change son fonctionnement, le correctif publié par ses auteurs est en général repris sans rien faire.

### Les alertes

GitHub envoie un **e-mail** au propriétaire du dépôt chaque fois qu'un lancement échoue. Vérifiez une fois que c'est bien réglé : sur GitHub, photo de profil → **Settings** → **Notifications** → rubrique **Actions** : cocher **Email** et « Only notify for failed workflows ».

Un lancement échoue, et vous recevez donc un e-mail, dans ces cas :

- **Les tests du programme échouent** : rien n'est calculé ni publié, le site garde sa version précédente.
- **Le contrôle de santé trouve des données anormales** (trop peu de cours reçus, trop peu de sociétés notées, trop de sociétés retirées par les contrôles) : le site garde sa version précédente.
- **Yahoo bloque ou ne renvoie rien depuis 3 nuits de suite.**
- **Une source de la page d'accueil est en panne** : indicateurs économiques trop anciens ou trop peu nombreux, ou composition d'un grand indice impossible à relire sur Wikipédia depuis 3 jours (le site reste publié, avec les derniers chiffres connus).
- **Un test trimestriel se dégrade** : les mieux notées ne font plus mieux que les moins bien notées, ou leur avantage a été divisé par deux.

Les seuils sont réglables dans `config.py` (rubrique « Contrôle de santé »). Enfin, le site affiche un **bandeau rouge** si les données n'ont pas été mises à jour depuis plus de 3 jours, par exemple si GitHub a cessé de lancer les tâches.

### Si quelque chose ne va pas

1. **Lire le message** : onglet **Actions** du dépôt → cliquer sur le lancement marqué d'une croix rouge. Le résumé en haut de la page explique le problème en français.
2. **Selon le cas** :
   - *Yahoo bloque ou renvoie peu de cours* : c'est souvent passager. Attendre deux ou trois nuits. Si cela dure plus d'une semaine, Yahoo a sans doute changé son fonctionnement et le programme est à adapter (voir point 3).
   - *Les tâches programmées sont désactivées* (GitHub le fait après 60 jours sans activité, et prévient par e-mail) : onglet **Actions** → choisir le workflow à gauche → bouton **Enable workflow**.
   - *Un test trimestriel s'est dégradé* : rien n'est cassé, c'est une information. La page « Test sur le passé » montre l'historique ; c'est le moment de se demander s'il faut revoir les pondérations dans `config.py`.
   - *Relancer un calcul sans attendre la nuit* : onglet **Actions** → **Screener** → **Run workflow** → bouton vert.
   - *Changer l'adresse de contact exigée par la SEC* (test américain) : **Settings** → **Secrets and variables** → **Actions** → `SEC_CONTACT` → modifier. Format : `Prénom Nom adresse@exemple.fr`.
3. **Pour une vraie panne**, confiez le dépôt à quelqu'un qui code, ou à un assistant IA : ce fichier, le tableau « Organisation du code » ci-dessous et les commentaires du code suffisent pour s'y retrouver. L'historique des choix (pourquoi chaque règle existe) est dans le journal du projet ; gardez-en une copie téléchargée (PDF ou Word).

## Régler le screener

Tout est dans `config.py` : pondérations de la note investisseur, durée de collecte, taille des lots. Pour modifier : ouvrez le fichier sur GitHub, cliquez le crayon ✏️, changez la valeur, puis **Commit changes**. Le changement s'applique au calcul suivant.

## Ce qu'il faut savoir

- Les données viennent de **Yahoo Finance** (source non officielle) et de **FinanceDatabase** (liste des sociétés). Elles peuvent comporter des erreurs, surtout pour les petites sociétés et les cotations en devises différentes des comptes. Vérifiez toujours avant d'investir.
- **Contrôles automatiques** : chaque nuit, les chiffres de chaque société sont vérifiés (cours présent et récent, capitalisation cohérente avec le cours, cours dans sa fourchette annuelle, PER et rapport capitalisation / chiffre d'affaires proches de ceux calculés par Yahoo, rendement plausible). Une anomalie grave retire la société du classement jusqu'à sa prochaine lecture ; une anomalie légère écarte seulement le chiffre douteux. La fiche indique la raison, et la liste du jour est dans `data/anomalies.csv`.
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
| `controles.py` | Contrôles de cohérence des chiffres avant le calcul des notes |
| `macro.py` | Indicateurs économiques de la page d'accueil |
| `indices.py` | Composition des grands indices (filtre « Indice » du radar), relue chaque mois sur Wikipédia |
| `sante.py` | Contrôle de santé après chaque calcul et chaque test trimestriel : déclenche les e-mails d'alerte |
| `retro.py`, `retro_us.py` | Tests sur le passé (monde ; États-Unis avec les comptes de la SEC) |
| `tests/` | Tests automatiques du programme |
| `rendu.py`, `web/` | Le site : accueil (`index.html`, `accueil.js`), tableau et fiches (`tableau.html`, `app.js`) |
| `data/` | Liste des sociétés, composition des grands indices, taux de change, archive des prévisions, statut |
| branche `donnees` | Les données détaillées de chaque société, remplacées à chaque passage |
| branches `retro`, `retro-us` | L'historique de comptes et de cours des tests sur le passé |
| `.github/workflows/screener.yml` | Le planning de nuit et la publication |

Pour tester sur un ordinateur : `pip install -r requirements.txt`, `python main.py`, puis ouvrez `site/` avec un petit serveur (`python -m http.server -d site`).
