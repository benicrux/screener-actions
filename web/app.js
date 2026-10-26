"use strict";

/* ------------------------------------------------------------------ */
/* Réglages d'affichage                                                */
/* ------------------------------------------------------------------ */
const COLONNES_NOTES = [
  { k: "inv", t: "Note", titre: "Note investisseur", synthese: true },
  { k: "val", t: "Valo.", titre: "Valorisation" },
  { k: "cro", t: "Crois.", titre: "Croissance" },
  { k: "ren", t: "Renta.", titre: "Rentabilité" },
  { k: "sit", t: "Fin.", titre: "Situation financière" },
  { k: "rlt", t: "Révis.", titre: "Révisions BNA long terme" },
  { k: "pub", t: "Publi.", titre: "Publication" },
  { k: "vis", t: "Visib.", titre: "Visibilité" },
  { k: "tra", t: "Trading", titre: "Note trading", synthese: true },
];
const COLONNES_CHIFFRES = [
  { k: "per", t: "PER", titre: "Cours / bénéfice par action (passé et prévu)", f: (v) => per(v) },
  { k: "pot", t: "Potentiel", titre: "Objectif de cours moyen des analystes / cours", f: (v) => pct(v, 0, true) },
  { k: "rdt", t: "Rdt", titre: "Rendement du dividende", f: (v) => (v ? pct(v, 1) : "—") },
  { k: "cap", t: "Capi.", titre: "Capitalisation boursière", f: (v) => capi(v) },
];
const NOTES_FICHE = [
  ["val", "Valorisation"], ["cro", "Croissance"], ["ren", "Rentabilité"],
  ["sit", "Situation financière"], ["rlt", "Révisions BNA long terme"],
  ["rct", "Révisions BNA court terme"], ["pub", "Publication"], ["vis", "Visibilité"],
  ["nper", "PER"], ["npot", "Potentiel"], ["nrdt", "Rendement"], ["con", "Consensus"],
];
const CONTINENTS = ["Europe", "Amérique du Nord", "Amérique latine", "Asie", "Moyen-Orient", "Afrique", "Océanie"];
const PAR_PAGE = 100;
// Remplacé à chaque publication : évite qu'un téléphone mélange une ancienne et une nouvelle version
const VERSION = "__VERSION__";

/* ------------------------------------------------------------------ */
/* État                                                                */
/* ------------------------------------------------------------------ */
const ECHELLES = [
  { k: "inv", nom: "Note investisseur" },
];
// Paliers du curseur de capitalisation, en euros
const PALIERS_CAPI = [0, 25e6, 50e6, 100e6, 250e6, 500e6, 1e9, 2e9, 5e9, 10e9, 50e9, 100e9, 500e9, Infinity];
const DERNIER_PALIER = PALIERS_CAPI.length - 1;
// Part de la note investisseur qui repose sur des chiffres disponibles (en % de ses pondérations)
const PALIERS_INFO = [0, 70, 85, 100];
const CRITERES_INV = [["valorisation", "val", "valorisation"], ["croissance", "cro", "croissance"],
  ["rentabilite", "ren", "rentabilité"], ["situation_fi", "sit", "situation financière"],
  ["revisions_lt", "rlt", "révisions des analystes sur 1 an"], ["publication", "pub", "publications"],
  ["visibilite", "vis", "visibilité"]];
const ETAT_DEFAUT = {
  continents: [], paysExclus: [], secteur: "", industrie: "",
  favoris: false, q: "", tri: "inv", sens: -1, etoiles: {}, capi: [0, DERNIER_PALIER], info: 0,
};
const SAUVE = lire("pepites.filtres", {}) || {};
let etat = Object.assign({}, ETAT_DEFAUT, SAUVE);
// Anciennes préférences : un seul continent et un seul pays
if (!Array.isArray(SAUVE.continents)) etat.continents = SAUVE.continent ? [SAUVE.continent] : [];
if (!Array.isArray(SAUVE.paysExclus)) etat.paysExclus = [];
delete etat.continent;
delete etat.pays;
etat.etoiles = { inv: (etat.etoiles || {}).inv || 0 };
if (!Array.isArray(etat.capi) || etat.capi.length !== 2) etat.capi = [0, DERNIER_PALIER];
if (!PALIERS_INFO.includes(etat.info)) etat.info = 0;
delete etat.note;
delete etat.taille;
let USD_PAR_EUR = 1.08;

/* Échelle d'étoiles : 1 = toutes les sociétés notées, puis 20, 40, 60, 80 et plus */
function seuilEtoiles(n) { return n ? Math.max(1, (n - 1) * 20) : 0; }
function texteEtoiles(n) {
  if (!n) return "Toutes";
  return n === 1 ? "Toutes les notées" : `${(n - 1) * 20} et plus`;
}
let affichees = PAR_PAGE;
let actions = [];
let parSymbole = new Map();
let statut = {};
let favoris = lire("pepites.favoris", {});

function lire(cle, defaut) {
  try { const v = localStorage.getItem(cle); return v ? JSON.parse(v) : defaut; }
  catch (e) { return defaut; }
}
function ecrire(cle, valeur) {
  try { localStorage.setItem(cle, JSON.stringify(valeur)); } catch (e) { /* stockage indisponible */ }
}

/* ------------------------------------------------------------------ */
/* Formats                                                             */
/* ------------------------------------------------------------------ */
const nf = (dec) => new Intl.NumberFormat("fr-FR", { minimumFractionDigits: dec, maximumFractionDigits: dec });
const F = [nf(0), nf(1), nf(2)];
function nombre(v, dec = 1) { return v == null || !isFinite(v) ? "—" : F[dec].format(v); }
function pct(v, dec = 1, signe = false) {
  if (v == null || !isFinite(v)) return "—";
  const s = F[dec].format(v * 100) + " %";
  return signe && v > 0 ? "+" + s : s;
}
function per(v) {
  if (v == null || !isFinite(v)) return "—";
  if (v <= 0 || v > 999) return "n.s.";
  return nombre(v, 1);
}
function euros(e) {
  if (e >= 1e9) {
    const md = e / 1e9;
    return nombre(md, md >= 100 || Number.isInteger(md) ? 0 : 1) + " Md€";
  }
  return nombre(e / 1e6, 0) + " M€";
}
function capi(v) {  // v en dollars, affiché en euros
  if (v == null || !isFinite(v)) return "—";
  return euros(v / USD_PAR_EUR);
}
function texteCapi([min, max]) {
  if (min === 0 && max === DERNIER_PALIER) return "Toutes";
  if (max === DERNIER_PALIER) return `Plus de ${euros(PALIERS_CAPI[min])}`;
  if (min === 0) return `Moins de ${euros(PALIERS_CAPI[max])}`;
  return `De ${euros(PALIERS_CAPI[min])} à ${euros(PALIERS_CAPI[max])}`;
}
function montant(v, devise) {
  if (v == null || !isFinite(v)) return "—";
  const d = devise ? " " + devise : "";
  const a = Math.abs(v);
  if (a >= 1e9) return nombre(v / 1e9, 2) + " Md" + d;
  if (a >= 1e6) return nombre(v / 1e6, 1) + " M" + d;
  return nombre(v, 0) + d;
}
function prix(v, devise) {
  if (v == null || !isFinite(v)) return "—";
  return nombre(v, v >= 100 ? 0 : 2) + " " + (devise || "");
}
function date(iso) {
  if (!iso) return "—";
  const [a, m, j] = iso.split("-");
  return `${j}/${m}/${a}`;
}
function joursDepuis(iso) {
  if (!iso) return null;
  return Math.round((Date.now() - new Date(iso + "T12:00:00").getTime()) / 864e5);
}
function echapper(s) {
  return String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}
function classeNote(v, synthese) {
  if (v == null) return "n-vide";
  if (synthese && v >= 80) return "n-or";
  if (v >= 70) return "n-haut";
  if (v >= 40) return "n-moy";
  return "n-bas";
}
function pastille(v, synthese = false, grande = false) {
  return `<span class="n ${classeNote(v, synthese)}${grande ? " grande" : ""}">${v == null ? "—" : v}</span>`;
}
function couleurBarre(v) {
  return v >= 70 ? "var(--haut)" : v >= 40 ? "var(--moy)" : "var(--bas)";
}
function consensusTexte(r) {
  if (r == null) return "—";
  const t = r <= 1.5 ? "Achat fort" : r <= 2.5 ? "Achat" : r <= 3.5 ? "Conserver" : r <= 4.5 ? "Vente" : "Vente forte";
  return `${t} (${nombre(r, 1)} sur 5)`;
}

/* ------------------------------------------------------------------ */
/* Chargement                                                          */
/* ------------------------------------------------------------------ */
async function charger() {
  try {
    const [t, s] = await Promise.all([
      fetch(`data/screener.json?v=${VERSION}`).then((r) => {
        if (!r.ok) throw new Error("donnees-absentes");
        return r.json();
      }),
      fetch(`data/statut.json?v=${VERSION}`).then((r) => r.json()).catch(() => ({})),
    ]);
    statut = s;
    if (t.usd_par_eur) USD_PAR_EUR = t.usd_par_eur;
    const champs = t.champs;
    actions = t.lignes.map((l) => {
      const o = {};
      champs.forEach((c, j) => {
        const v = l[j];
        o[c] = t.dicos[c] && v != null ? t.dicos[c][v] : v;
      });
      return o;
    });
    parSymbole = new Map(actions.map((a) => [a.s, a]));
    afficherCouverture(t.maj);
    construireFiltres();
    afficher();
    ouvrirDepuisAdresse();
  } catch (e) {
    document.getElementById("couverture").textContent = e && e.message === "donnees-absentes"
      ? "Les données ne sont pas encore prêtes. Le premier calcul est peut-être en cours : revenez dans quelques minutes."
      : "La page n'a pas pu s'afficher. Rechargez-la ; si le problème continue, une mise à jour est peut-être en cours.";
    console.error(e);
  }
}

/* Bandeau si les données n'ont pas été relues depuis plus de 3 jours : la tâche programmée
   de GitHub s'est peut-être arrêtée */
function alerteDonneesAnciennes(jour) {
  const el = document.getElementById("alerte-maj");
  const t = Date.parse(`${String(jour).slice(0, 10)}T12:00:00Z`);
  const jours = isFinite(t) ? Math.floor((Date.now() - t) / 864e5) : 0;
  el.hidden = jours <= 3;
  if (el.hidden) return;
  el.textContent = `Attention : données non mises à jour depuis ${jours} jours. ` +
    "La tâche automatique de GitHub semble arrêtée.";
  if (statut.depot) {
    const lien = document.createElement("a");
    lien.href = `https://github.com/${statut.depot}#si-quelque-chose-ne-va-pas`;
    lien.target = "_blank";
    lien.rel = "noopener";
    lien.textContent = "Que faire ?";
    el.append(" ", lien);
  }
}

function afficherCouverture(maj) {
  const el = document.getElementById("couverture");
  const notees = actions.filter((a) => a.inv != null).length;
  if (!actions.length) {
    el.textContent = "Le robot n'a encore récupéré aucune donnée. Les premières sociétés apparaissent après son premier passage.";
    return;
  }
  // Date des données : dernier passage complet de nuit (une simple republication du site
  // ne relit pas les données)
  const donneesDu = statut.passage_complet || maj;
  let texte = `${nombre(notees, 0)} actions notées dans le monde, mise à jour du ${date(donneesDu)}.`;
  alerteDonneesAnciennes(donneesDu);
  if (statut.jamais_lues > 0) {
    texte += statut.jamais_lues > 1
      ? ` ${nombre(statut.jamais_lues, 0)} sociétés restent à lire`
      : " 1 société reste à lire";
    texte += statut.jours_restants ? ` (environ ${statut.jours_restants} jours).` : ".";
  }
  el.textContent = texte;
  const aideMaj = document.getElementById("aide-maj");
  aideMaj.textContent = statut.date ? `Dernier calcul : ${statut.date}. ` : "";
  if (statut.depot) {
    const lien = document.createElement("a");
    lien.href = `https://github.com/${statut.depot}/actions/workflows/screener.yml`;
    lien.target = "_blank";
    lien.rel = "noopener";
    lien.textContent = "Relancer un calcul maintenant";
    aideMaj.append(lien, " (sur GitHub : « Run workflow », puis le bouton vert).");
  }
}

/* ------------------------------------------------------------------ */
/* Filtres                                                             */
/* ------------------------------------------------------------------ */
function options(select, valeurs, tous, choisie) {
  select.innerHTML = `<option value="">${tous}</option>` +
    valeurs.map((v) => `<option value="${echapper(v)}"${v === choisie ? " selected" : ""}>${echapper(v)}</option>`).join("");
}
function uniques(liste, cle) {
  return [...new Set(liste.map((a) => a[cle]).filter(Boolean))].sort((a, b) => a.localeCompare(b, "fr"));
}

function construireFiltres() {
  const zone = document.getElementById("continents");
  zone.innerHTML = ["", ...CONTINENTS].map((c) =>
    `<button type="button" data-c="${c}">${c || "Monde"}</button>`).join("");
  zone.onclick = (e) => {
    const b = e.target.closest("button");
    if (!b) return;
    const c = b.dataset.c;
    if (!c) etat.continents = [];
    else if (etat.continents.includes(c)) etat.continents = etat.continents.filter((x) => x !== c);
    else etat.continents = [...etat.continents, c];
    majFiltres();
  };
  const liste = document.getElementById("liste-pays");
  document.getElementById("btn-pays").onclick = (e) => {
    liste.hidden = !liste.hidden;
    e.currentTarget.setAttribute("aria-expanded", String(!liste.hidden));
    if (!liste.hidden) rendreListePays();
  };
  liste.onchange = (e) => {
    const caseP = e.target.closest("input[data-p]");
    if (!caseP) return;
    const p = caseP.dataset.p;
    etat.paysExclus = caseP.checked ? etat.paysExclus.filter((x) => x !== p) : [...etat.paysExclus, p];
    majFiltres();
  };
  liste.onclick = (e) => {
    const b = e.target.closest("button[data-tous]");
    if (!b) return;
    const duContinent = paysParContinent().get(b.dataset.c).map(([p]) => p);
    const exclus = new Set(etat.paysExclus);
    duContinent.forEach((p) => (b.dataset.tous === "1" ? exclus.delete(p) : exclus.add(p)));
    etat.paysExclus = [...exclus];
    majFiltres();
  };
  document.getElementById("f-secteur").onchange = (e) => { etat.secteur = e.target.value; etat.industrie = ""; majFiltres(); };
  document.getElementById("f-industrie").onchange = (e) => { etat.industrie = e.target.value; majFiltres(); };
  const echelles = document.getElementById("echelles");
  echelles.innerHTML = ECHELLES.map(({ k, nom }) => `
    <div class="echelle-filtre" role="group" aria-label="${nom} minimale">
      <span class="echelle-nom">${nom}</span>
      <span class="etoiles">${[1, 2, 3, 4, 5].map((n) =>
        `<button type="button" data-k="${k}" data-n="${n}" aria-label="${n} étoile${n > 1 ? "s" : ""} et plus : ${texteEtoiles(n).toLowerCase()}">★</button>`).join("")}</span>
      <span class="echelle-seuil" data-seuil="${k}"></span>
    </div>`).join("") + `
    <div class="echelle-filtre capi-filtre" role="group" aria-label="Capitalisation boursière">
      <span class="echelle-nom">Capitalisation</span>
      <span class="double-curseur">
        <input type="range" id="capi-min" min="0" max="${DERNIER_PALIER}" step="1" aria-label="Capitalisation minimale">
        <input type="range" id="capi-max" min="0" max="${DERNIER_PALIER}" step="1" aria-label="Capitalisation maximale">
      </span>
      <span class="echelle-seuil" id="capi-texte"></span>
    </div>
    <div class="echelle-filtre info-filtre" role="group" aria-label="Informations disponibles">
      <span class="echelle-nom">Informations</span>
      <span class="paliers">${PALIERS_INFO.map((p) =>
        `<button type="button" data-info="${p}" aria-label="${p ? `Au moins ${p} % des informations` : "Toutes les sociétés"}">${p ? `${p} %${p < 100 ? " +" : ""}` : "Toutes"}</button>`).join("")}</span>
    </div>`;
  const curseurMin = document.getElementById("capi-min");
  const curseurMax = document.getElementById("capi-max");
  const bougerCapi = (e) => {
    let min = +curseurMin.value, max = +curseurMax.value;
    if (min >= max) {
      if (e.target === curseurMin) min = max - 1; else max = min + 1;
    }
    etat.capi = [min, max];
    majFiltres();
  };
  curseurMin.oninput = bougerCapi;
  curseurMax.oninput = bougerCapi;
  echelles.onclick = (e) => {
    const bi = e.target.closest("button[data-info]");
    if (bi) { etat.info = +bi.dataset.info; majFiltres(); return; }
    const b = e.target.closest("button[data-n]");
    if (!b) return;
    const k = b.dataset.k, n = +b.dataset.n;
    etat.etoiles[k] = etat.etoiles[k] === n ? 0 : n;
    majFiltres();
  };
  document.getElementById("f-favoris").onchange = (e) => { etat.favoris = e.target.checked; majFiltres(); };
  let minuterie;
  document.getElementById("recherche").oninput = (e) => {
    clearTimeout(minuterie);
    minuterie = setTimeout(() => { etat.q = e.target.value; majFiltres(false); }, 150);
  };
  document.getElementById("btn-reinit").onclick = () => {
    etat = Object.assign({}, ETAT_DEFAUT, { tri: etat.tri, sens: etat.sens, etoiles: {},
      capi: [0, DERNIER_PALIER], continents: [], paysExclus: [] });
    document.getElementById("recherche").value = "";
    majFiltres();
  };
  document.getElementById("btn-plus").onclick = () => { affichees += PAR_PAGE; afficher(false); };
  document.getElementById("btn-filtres").onclick = (e) => {
    const zone = document.getElementById("selecteurs");
    const ouvert = zone.classList.toggle("ouvert");
    e.currentTarget.setAttribute("aria-expanded", String(ouvert));
    libelleFiltres();
  };
  majFiltres();
}

/* Pays des continents choisis (tous si aucun), avec le nombre d'actions de chacun */
function paysParContinent() {
  const groupes = new Map();
  const comptes = new Map();
  actions.forEach((a) => {
    if (!a.p || (etat.continents.length && !etat.continents.includes(a.c))) return;
    comptes.set(a.p, (comptes.get(a.p) || 0) + 1);
    if (!groupes.has(a.c)) groupes.set(a.c, new Set());
    groupes.get(a.c).add(a.p);
  });
  const ordre = [...CONTINENTS, ...[...groupes.keys()].filter((c) => !CONTINENTS.includes(c))];
  const resultat = new Map();
  ordre.forEach((c) => {
    if (!groupes.has(c)) return;
    resultat.set(c, [...groupes.get(c)].sort((x, y) => x.localeCompare(y, "fr")).map((p) => [p, comptes.get(p)]));
  });
  return resultat;
}

function libellePays() {
  const tous = [...paysParContinent().values()].flat().map(([p]) => p);
  const exclus = tous.filter((p) => etat.paysExclus.includes(p));
  if (!exclus.length) return "Pays : tous";
  if (exclus.length === tous.length) return "Pays : aucun";
  if (exclus.length <= 3) return `Pays : tous sauf ${exclus.join(", ")}`;
  return `Pays : ${tous.length - exclus.length} sur ${tous.length}`;
}

function rendreListePays() {
  const liste = document.getElementById("liste-pays");
  const exclus = new Set(etat.paysExclus);
  liste.innerHTML = [...paysParContinent()].map(([c, pays]) => `
    <div class="groupe-pays">
      <div class="groupe-tete"><strong>${echapper(c)}</strong>
        <span><button type="button" class="lien" data-c="${echapper(c)}" data-tous="1">Tout cocher</button>
        <button type="button" class="lien" data-c="${echapper(c)}" data-tous="0">Tout décocher</button></span></div>
      <div class="cases">${pays.map(([p, n]) => `
        <label class="case"><input type="checkbox" data-p="${echapper(p)}"${exclus.has(p) ? "" : " checked"}>
          <span>${echapper(p)}</span><span class="nb">${nombre(n, 0)}</span></label>`).join("")}</div>
    </div>`).join("");
}

function majFiltres(remettre = true) {
  document.querySelectorAll("#continents button").forEach((b) => b.setAttribute("aria-pressed",
    String(b.dataset.c ? etat.continents.includes(b.dataset.c) : !etat.continents.length)));
  document.getElementById("btn-pays").textContent = libellePays();
  if (!document.getElementById("liste-pays").hidden) rendreListePays();
  options(document.getElementById("f-secteur"), uniques(actions, "se"), "Tous", etat.secteur);
  const dansSecteur = etat.secteur ? actions.filter((a) => a.se === etat.secteur) : actions;
  options(document.getElementById("f-industrie"), uniques(dansSecteur, "i"), "Toutes", etat.industrie);
  const [cmin, cmax] = etat.capi;
  document.getElementById("capi-min").value = String(cmin);
  document.getElementById("capi-max").value = String(cmax);
  document.querySelector(".double-curseur").style.setProperty("--debut", `${(cmin / DERNIER_PALIER) * 100}%`);
  document.querySelector(".double-curseur").style.setProperty("--fin", `${(cmax / DERNIER_PALIER) * 100}%`);
  document.getElementById("capi-texte").textContent = texteCapi(etat.capi);
  document.querySelectorAll("#echelles button[data-n]").forEach((b) => {
    const choisi = etat.etoiles[b.dataset.k] || 0;
    b.classList.toggle("pleine", +b.dataset.n <= choisi);
    b.setAttribute("aria-pressed", String(+b.dataset.n === choisi));
  });
  document.querySelectorAll("#echelles button[data-info]").forEach((b) =>
    b.setAttribute("aria-pressed", String(+b.dataset.info === etat.info)));
  document.querySelectorAll("#echelles [data-seuil]").forEach((el) => {
    el.textContent = texteEtoiles(etat.etoiles[el.dataset.seuil] || 0);
  });
  document.getElementById("f-favoris").checked = etat.favoris;
  if (document.getElementById("recherche").value !== etat.q) document.getElementById("recherche").value = etat.q;
  ecrire("pepites.filtres", Object.assign({}, etat, { q: "" }));
  if (remettre) affichees = PAR_PAGE;
  libelleFiltres();
  afficher();
}

function libelleFiltres() {
  const actifs = ["secteur", "industrie", "favoris"].filter((k) => etat[k]).length;
  const ouvert = document.getElementById("selecteurs").classList.contains("ouvert");
  document.getElementById("btn-filtres").textContent =
    (ouvert ? "Masquer les filtres" : "Plus de filtres") + (actifs ? ` (${actifs} actif${actifs > 1 ? "s" : ""})` : "");
}

function normaliser(s) {
  return String(s || "").normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase();
}

function filtrer() {
  const q = normaliser(etat.q.trim());
  const exclus = new Set(etat.paysExclus);
  return actions.filter((a) =>
    (!etat.continents.length || etat.continents.includes(a.c)) &&
    !exclus.has(a.p) &&
    (!etat.secteur || a.se === etat.secteur) &&
    (!etat.industrie || a.i === etat.industrie) &&
    (a.cap != null && a.cap / USD_PAR_EUR >= PALIERS_CAPI[etat.capi[0]] &&
      a.cap / USD_PAR_EUR < PALIERS_CAPI[etat.capi[1]]) &&
    ECHELLES.every(({ k }) => !etat.etoiles[k] || (a[k] != null && a[k] >= seuilEtoiles(etat.etoiles[k]))) &&
    (!etat.info || (a.cou != null && a.cou >= etat.info)) &&
    (!etat.favoris || favoris[a.s]) &&
    (!q || normaliser(a.n).includes(q) || normaliser(a.s).startsWith(q)));
}

function trier(liste) {
  const k = etat.tri, s = etat.sens;
  return liste.sort((a, b) => {
    const x = a[k], y = b[k];
    if (x == null && y == null) return 0;
    if (x == null) return 1;
    if (y == null) return -1;
    if (typeof x === "string") return s * x.localeCompare(y, "fr");
    return s * (x - y);
  });
}

/* ------------------------------------------------------------------ */
/* Tableau                                                             */
/* ------------------------------------------------------------------ */
function entetes() {
  const cols = [{ k: "n", t: "Société", titre: "Nom" }, ...COLONNES_NOTES, ...COLONNES_CHIFFRES];
  document.getElementById("entetes").innerHTML = cols.map((c) => {
    const tri = etat.tri === c.k ? ` aria-sort="${etat.sens < 0 ? "descending" : "ascending"}"` : "";
    return `<th scope="col" data-k="${c.k}" title="${echapper(c.titre)}"${tri}${c.k === "n" ? ' class="col-nom"' : ""}>${c.t}</th>`;
  }).join("");
  document.getElementById("entetes").onclick = (e) => {
    const th = e.target.closest("th");
    if (!th) return;
    const k = th.dataset.k;
    if (etat.tri === k) etat.sens = -etat.sens;
    else { etat.tri = k; etat.sens = k === "n" || k === "per" ? 1 : -1; }
    ecrire("pepites.filtres", Object.assign({}, etat, { q: "" }));
    afficher();
  };
}

function afficher(remettreDefilement = true) {
  entetes();
  const liste = trier(filtrer());
  const visibles = liste.slice(0, affichees);
  document.getElementById("compte").textContent =
    `${nombre(liste.length, 0)} action${liste.length > 1 ? "s" : ""}`;
  document.getElementById("vide").hidden = liste.length > 0;
  document.getElementById("btn-plus").hidden = liste.length <= affichees;
  document.getElementById("lignes").innerHTML = visibles.map((a) => {
    const etoile = favoris[a.s] ? `<span class="etoile" aria-label="Favori">★</span>` : "";
    const notes = COLONNES_NOTES.map((c) => `<td>${pastille(a[c.k], c.synthese, c.k === "inv")}</td>`).join("");
    const chiffres = COLONNES_CHIFFRES.map((c) => `<td class="num${c.k === "cap" ? " droite" : ""}">${c.f(a[c.k])}</td>`).join("");
    return `<tr data-s="${echapper(a.s)}"><td class="col-nom"><span class="nom-societe">${etoile}${echapper(a.n)}</span>` +
      `<span class="sous">${echapper(a.p || "")}, ${echapper(a.i || a.se || "")}</span></td>${notes}${chiffres}</tr>`;
  }).join("");
  document.getElementById("lignes").onclick = (e) => {
    const tr = e.target.closest("tr");
    if (tr) ouvrir(tr.dataset.s);
  };
  if (remettreDefilement && affichees === PAR_PAGE) { /* rien : on garde la position */ }
}

/* ------------------------------------------------------------------ */
/* Fiche d'une action                                                   */
/* ------------------------------------------------------------------ */
const TABLE_CRC = (() => {
  const t = new Uint32Array(256);
  for (let n = 0; n < 256; n++) {
    let c = n;
    for (let k = 0; k < 8; k++) c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1;
    t[n] = c >>> 0;
  }
  return t;
})();
function crc32(texte) {
  const octets = new TextEncoder().encode(texte);
  let c = 0xffffffff;
  for (const o of octets) c = TABLE_CRC[(c ^ o) & 0xff] ^ (c >>> 8);
  return (c ^ 0xffffffff) >>> 0;
}
const paquets = new Map();
async function chargerFiche(s) {
  const cle = (crc32(s) % 256).toString(16).padStart(2, "0");
  if (!paquets.has(cle)) {
    paquets.set(cle, fetch(`data/fiches/${cle}.json?v=${VERSION}`).then((r) => r.json()));
  }
  const p = await paquets.get(cle);
  return p[s];
}

let derniereFocalisation = null;
async function ouvrir(s, pousser = true) {
  const a = parSymbole.get(s);
  if (!a) return;
  derniereFocalisation = document.activeElement;
  if (pousser) history.replaceState(null, "", "#" + encodeURIComponent(s));
  const corps = document.getElementById("fiche-corps");
  corps.innerHTML = `<h2 id="fiche-nom">${echapper(a.n)}</h2><p class="ident">Chargement de la fiche…</p>`;
  montrer("fiche");
  let f;
  try { f = await chargerFiche(s); } catch (e) { f = null; }
  corps.innerHTML = rendreFiche(a, f || {});
  corps.querySelector("[data-favori]").onclick = (e) => basculerFavori(a, f || {}, e.currentTarget);
  corps.querySelectorAll("[data-pair]").forEach((tr) => { tr.onclick = () => ouvrir(tr.dataset.pair); });
  document.getElementById("fiche").scrollTop = 0;
}

function montrer(id) {
  document.getElementById("voile").hidden = false;
  const el = document.getElementById(id);
  el.hidden = false;
  el.querySelector(".fermer").focus();
  document.body.style.overflow = "hidden";
}
function fermer() {
  ["fiche", "aide"].forEach((id) => { document.getElementById(id).hidden = true; });
  document.getElementById("voile").hidden = true;
  document.body.style.overflow = "";
  if (location.hash) history.replaceState(null, "", location.pathname + location.search);
  if (derniereFocalisation) derniereFocalisation.focus();
}

function basculerFavori(a, f, bouton) {
  if (favoris[a.s]) delete favoris[a.s];
  else favoris[a.s] = { d: new Date().toISOString().slice(0, 10), px: a.px, dv: a.dv, inv: a.inv };
  ecrire("pepites.favoris", favoris);
  const actif = !!favoris[a.s];
  bouton.setAttribute("aria-pressed", String(actif));
  bouton.textContent = actif ? "★ Dans mes favoris" : "☆ Ajouter aux favoris";
  afficher(false);
}

function ligne(libelle, valeur, aide) {
  return `<tr><th scope="row"${aide ? ` title="${echapper(aide)}"` : ""}>${libelle}</th><td>${valeur}</td></tr>`;
}
/* Dettes moins trésorerie ; si la trésorerie l'emporte, on affiche la trésorerie nette */
function ligneDetteNette(f, devise) {
  if (f.dette == null && f.tresorerie == null) return "";
  const nette = (f.dette || 0) - (f.tresorerie || 0);
  return nette > 0
    ? ligne("Dette nette", montant(nette, devise), "Dettes financières moins trésorerie")
    : ligne("Trésorerie nette", montant(-nette, devise), "Trésorerie moins dettes financières : la société a plus d'argent que de dettes");
}
function tableau(lignes) {
  const l = lignes.filter(Boolean);
  return l.length ? `<table class="chiffres">${l.join("")}</table>` : `<p class="note-bas">Pas de données.</p>`;
}
function signe(v, dec = 1) {
  if (v == null || !isFinite(v)) return "—";
  const cls = v > 0 ? "positif" : v < 0 ? "negatif" : "";
  return `<span class="${cls}">${pct(v, dec, true)}</span>`;
}

function minuscule(t) {
  return t.length > 1 && t[1] === t[1].toUpperCase() && t[1] !== t[1].toLowerCase() ? t : t[0].toLowerCase() + t.slice(1);
}

function pointsSaillants(a, f) {
  if (f.anomalie_grave) {
    return [`Retirée du classement jusqu'à sa prochaine lecture : ${echapper(f.anomalies)}. Les chiffres ci-dessous sont à vérifier.`];
  }
  const forts = [], faibles = [];
  NOTES_FICHE.forEach(([k, lib]) => {
    if (a[k] == null) return;
    if (a[k] >= 75) forts.push(`${minuscule(lib)} (${a[k]})`);
    else if (a[k] <= 25) faibles.push(`${minuscule(lib)} (${a[k]})`);
  });
  const l = [];
  if (forts.length) l.push(`Points forts : ${forts.join(", ")}.`);
  if (faibles.length) l.push(`Points faibles : ${faibles.join(", ")}.`);
  if (f.nb_analystes == null || f.nb_analystes < 3) {
    l.push("Peu ou pas suivie par les analystes : les notes de révisions, de publication et de visibilité manquent souvent.");
  }
  if (a.fin) l.push("Banque ou société financière : jugée sur le PER, le cours / actif net et la rentabilité des fonds propres.");
  if (f.anomalies) l.push(`Chiffre écarté du calcul des notes : ${echapper(f.anomalies)}.`);
  const age = joursDepuis(f.maj || a.m);
  if (age != null && age > 10) l.push(`Données détaillées lues il y a ${age} jours.`);
  return l;
}

function pairs(a) {
  const cap0 = Math.log(a.cap || 1);
  const candidats = actions.filter((b) => b.s !== a.s && b.i === a.i && b.inv != null);
  candidats.sort((x, y) => Math.abs(Math.log(x.cap || 1) - cap0) - Math.abs(Math.log(y.cap || 1) - cap0));
  return candidats.slice(0, 5);
}

function rendrePairs(a) {
  const p = pairs(a);
  if (!p.length) return `<p class="note-bas">Pas d'autre société notée dans cette industrie.</p>`;
  const groupe = [a, ...p].sort((x, y) => (y.inv ?? -1) - (x.inv ?? -1));
  const cols = [["inv", "Note"], ["val", "Valo."], ["cro", "Crois."], ["ren", "Renta."], ["sit", "Fin."], ["rlt", "Révis."], ["npot", "Pot."]];
  const meilleurs = {};
  cols.forEach(([k]) => { meilleurs[k] = Math.max(...groupe.map((b) => b[k] ?? -1)); });
  const tete = `<tr><th>Société</th>${cols.map(([, t]) => `<th>${t}</th>`).join("")}</tr>`;
  const corps = groupe.map((b) => {
    const cellules = cols.map(([k]) =>
      `<td class="${b[k] != null && b[k] === meilleurs[k] ? "meilleur" : ""}">${pastille(b[k], k === "inv")}</td>`).join("");
    const attrs = b.s === a.s ? ' class="soi"' : ` data-pair="${echapper(b.s)}" style="cursor:pointer"`;
    return `<tr${attrs}><td class="societe" title="${echapper(b.n)}">${echapper(b.n)}<br><span class="note-bas">${echapper(b.p || "")}</span></td>${cellules}</tr>`;
  }).join("");
  const phrases = [];
  [["val", "en valorisation"], ["cro", "en croissance"], ["ren", "en rentabilité"], ["sit", "en situation financière"]].forEach(([k, lib]) => {
    if (a[k] == null) return;
    const mieux = p.filter((b) => b[k] != null && b[k] - a[k] >= 15).sort((x, y) => y[k] - x[k])[0];
    if (mieux) phrases.push(`${echapper(mieux.n)} fait mieux ${lib} (${mieux[k]} contre ${a[k]}).`);
  });
  return `<div class="tableau-cadre"><table class="chiffres large pairs">${tete}${corps}</table></div>` +
    (phrases.length ? `<ul class="ressort">${phrases.slice(0, 3).map((x) => `<li>${x}</li>`).join("")}</ul>` : "") +
    `<p class="note-bas">Sociétés de la même industrie, de taille proche. Encadré : la meilleure note de chaque colonne. Touchez une ligne pour ouvrir sa fiche.</p>`;
}

/* Part des informations disponibles pour la note investisseur, et ce qui manque */
function texteInformations(a) {
  if (a.cou == null) return "";
  const manque = CRITERES_INV.filter(([, k]) => a[k] == null).map(([, , lib]) => lib);
  return `<p class="note-bas">Informations disponibles : ${nombre(a.cou, 0)} % de la note investisseur` +
    (manque.length ? `. Manque : ${manque.join(", ")}.` : ", rien ne manque.") + "</p>";
}

function rendreFiche(a, f) {
  const dc = f.devise_comptes || "";
  const dcours = f.devise_cours || a.dv || "";
  const fav = !!favoris[a.s];
  const synthInv = a.inv != null && a.inv >= 80 ? " or" : "";
  const lienNom = encodeURIComponent(a.n);
  const sansSuffixe = a.s.split(".")[0];

  let suivi = "";
  if (favoris[a.s] && favoris[a.s].px && a.px && favoris[a.s].dv === a.dv) {
    const s = favoris[a.s];
    suivi = `<p class="cours">Depuis l'ajout aux favoris le ${date(s.d)} : cours ${signe(a.px / s.px - 1)}` +
      (s.inv != null && a.inv != null ? `, note investisseur ${s.inv} → ${a.inv}` : "") + ".</p>";
  }

  const barres = NOTES_FICHE.map(([k, lib]) => {
    const v = a[k];
    if (v == null) return `<div class="barre absente"><span>${lib}</span><span class="piste"></span><span class="valeur">—</span></div>`;
    return `<div class="barre"><span>${lib}</span><span class="piste"><span class="remplissage" style="width:${v}%;background:${couleurBarre(v)}"></span></span><span class="valeur">${v}</span></div>`;
  }).join("");

  const surprises = (f.surprises || "").split(";").filter(Boolean).map((x) => {
    const [d, s] = x.split(":");
    return ligne(`Trimestre clos le ${date(d)}`, signe(+s));
  });

  const prev = (cle) => {
    if (f[`ex_${cle}`] == null) return "";
    const fourchette = (m, b, h, dev) => `${montant(f[m], dev)}${f[b] != null && f[h] != null ? `<br><span class="note-bas">${montant(f[b], "")} à ${montant(f[h], "")}</span>` : ""}`;
    const fbpa = (m, b, h) => `${nombre(f[m], 2)}${f[b] != null && f[h] != null ? `<br><span class="note-bas">${nombre(f[b], 2)} à ${nombre(f[h], 2)}</span>` : ""}`;
    return `<tr><td>${date(f[`ex_${cle}`]).slice(3)}</td><td>${fourchette(`ca_${cle}_moy`, `ca_${cle}_bas`, `ca_${cle}_haut`, f.devise_ca || dc)}</td>` +
      `<td>${fbpa(`bpa_${cle}_moy`, `bpa_${cle}_bas`, `bpa_${cle}_haut`)}</td><td>${f[`bpa_${cle}_nb`] != null ? nombre(f[`bpa_${cle}_nb`], 0) : "—"}</td></tr>`;
  };
  const tablePrev = f.ex_a0 || f.ex_a1
    ? `<div class="tableau-cadre"><table class="chiffres large"><tr><th>Exercice clos</th><th>Chiffre d'affaires</th><th>BPA (${echapper(f.devise_bpa || dc)})</th><th>Analystes</th></tr>${prev("a0")}${prev("a1")}</table></div>`
    : `<p class="note-bas">Aucune prévision d'analyste disponible.</p>`;

  return `
  <h2 id="fiche-nom">${echapper(a.n)}</h2>
  <p class="ident">${echapper(a.s)}, ${echapper(a.p || "")}, ${echapper(a.i || a.se || "")}. Taille : ${echapper((a.t || "").toLowerCase())}.</p>
  <p class="cours"><strong>${prix(a.px, dcours)}</strong> &nbsp;capitalisation ${capi(a.cap)}, sur un an ${signe(a.p52, 0)}</p>
  ${suivi}
  <div class="actions-fiche">
    <button type="button" class="bouton" data-favori aria-pressed="${fav}">${fav ? "★ Dans mes favoris" : "☆ Ajouter aux favoris"}</button>
  </div>

  <div class="synthese">
    <div class="bloc${synthInv}"><span>Note investisseur</span>${pastille(a.inv, true, true)}</div>
    <div class="bloc"><span>Note trading</span>${pastille(a.tra, true, true)}</div>
  </div>
  <ul class="ressort">${pointsSaillants(a, f).map((x) => `<li>${x}</li>`).join("")}</ul>

  <h3>Les notes</h3>
  <div class="barres">${barres}</div>
  <p class="note-bas">Comparée à son groupe : ${echapper(a.g || a.se || "")}.</p>
  ${texteInformations(a)}

  <h3>Comparaison avec le secteur</h3>
  ${rendrePairs(a)}

  <h3>Valorisation</h3>
  ${tableau([
    !a.fin && ligne("Valeur d'entreprise / CA", nombre(f.ve_ca, 2), "Passé et prévu"),
    !a.fin && ligne("Valeur d'entreprise / EBITDA", nombre(f.ve_ebitda, 1)),
    ligne("PER (passé et prévu)", per(f.per)),
    ligne("PER sur 12 mois", per(f.per_12m)),
    ligne("PER du prochain exercice", per(f.per_a1)),
    ligne("Cours / actif net", nombre(f.pb, 2)),
    !a.fin && ligne("Valeur d'entreprise", capi(f.ve_usd)),
  ])}

  <h3>Situation financière</h3>
  ${a.fin ? `<p class="note-bas">Pour une banque, la dette fait partie du métier : on regarde plutôt les fonds propres (ratio CET1), non fourni gratuitement par Yahoo.</p>` : ""}
  ${tableau([
    ligne("Trésorerie", montant(f.tresorerie, dc)),
    ligne("Dettes financières", montant(f.dette, dc)),
    !a.fin && ligneDetteNette(f, dc),
    !a.fin && ligne("Dette nette / EBITDA", f.dette_nette_ebitda === -1 ? "Aucune dette nette" : f.dette_nette_ebitda === 99 ? "Dettes, mais EBITDA négatif" : nombre(f.dette_nette_ebitda, 1),
      "Nombre d'années d'EBITDA qu'il faudrait pour rembourser la dette nette"),
    !a.fin && ligne("Trésorerie nette / CA", pct(f.treso_nette_ca, 0)),
    ligne("Liquidité générale", nombre(f.ratio_liquidite, 2), "Actif circulant / passif circulant"),
    ligne("Dettes / fonds propres", f.dette_fp != null ? pct(f.dette_fp / 100, 0) : "—"),
    ligne("Flux de trésorerie libre", montant(f.fcf, dc)),
  ])}

  <h3>Rentabilité et croissance</h3>
  ${tableau([
    ligne("Chiffre d'affaires sur 12 mois", montant(f.ca, dc)),
    ligne("Croissance du CA (dernier trimestre sur un an)", signe(f.croiss_ca)),
    ligne("Croissance prévue cet exercice", signe(f.croiss_ca_a0)),
    ligne("Croissance prévue l'exercice suivant", signe(f.croiss_ca_a1)),
    !(a.fin && !f.marge_brute) && ligne("Marge brute", pct(f.marge_brute)),
    !(a.fin && !f.marge_ebitda) && ligne("Marge d'EBITDA", pct(f.marge_ebitda)),
    !(a.fin && !f.marge_op) && ligne("Marge opérationnelle", pct(f.marge_op)),
    ligne("Marge nette sur 12 mois", pct(f.marge_nette)),
    ligne("Rentabilité des fonds propres (ROE)", pct(f.roe)),
    ligne("Rentabilité des actifs (ROA)", pct(f.roa)),
  ])}

  <h3>Prévisions des analystes</h3>
  ${tablePrev}
  ${tableau([
    ligne("Consensus", consensusTexte(f.reco)),
    ligne("Analystes", f.nb_analystes != null ? nombre(f.nb_analystes, 0) : "—"),
    ligne("Objectif de cours moyen", f.objectif != null ? `${prix(f.objectif, dcours)}${f.objectif_bas != null ? `<br><span class="note-bas">${prix(f.objectif_bas, "")} à ${prix(f.objectif_haut, dcours)}</span>` : ""}` : "—"),
    ligne("Potentiel", signe(f.potentiel, 0)),
    ligne("Révision du BPA sur 7 jours", signe(f.rev_bpa_7j)),
    ligne("Révision du BPA sur 90 jours", signe(f.rev_bpa_90j)),
    ligne("Révision du BPA sur 4 mois", signe(f.rev_bpa_4m)),
    ligne("Révision du BPA sur 1 an", signe(f.rev_bpa_1a)),
    ligne("Révision du CA sur 4 mois", signe(f.rev_ca_4m)),
    ligne("Révision du CA sur 1 an", signe(f.rev_ca_1a)),
  ])}
  <p class="note-bas">Les révisions sur 4 mois et 1 an se remplissent au fil des semaines : le screener archive les prévisions à chaque lecture.</p>

  <h3>Publications</h3>
  ${surprises.length ? tableau(surprises) + `<p class="note-bas">Écart entre le bénéfice par action publié et la prévision des analystes.</p>` : `<p class="note-bas">Pas d'historique de publications.</p>`}

  <h3>Dividende</h3>
  ${tableau([
    ligne("Rendement", f.rendement_ref ? pct(f.rendement_ref, 1) : "Pas de dividende connu"),
    ligne("Part du bénéfice distribuée", pct(f.taux_distribution, 0)),
  ])}

  <h3>Actualités</h3>
  <div class="liens">
    <a class="bouton" href="https://news.google.com/search?q=${lienNom}&hl=fr&gl=FR&ceid=FR:fr" target="_blank" rel="noopener">Google Actualités</a>
    <a class="bouton" href="https://finance.yahoo.com/quote/${encodeURIComponent(a.s)}/news" target="_blank" rel="noopener">Yahoo Finance</a>
    <a class="bouton" href="https://www.zonebourse.com/recherche/?q=${encodeURIComponent(sansSuffixe)}" target="_blank" rel="noopener">Zone Bourse</a>
  </div>

  ${f.resume ? `<h3>Activité</h3><details><summary>Lire la description (en anglais)</summary><p class="resume-anglais">${echapper(f.resume)}</p></details>` : ""}

  <p class="note-bas" style="margin-top:28px">Données détaillées lues le ${date(f.maj || a.m)}, cours du jour quand il est disponible. Source : Yahoo Finance. ${f.isin ? `ISIN ${echapper(f.isin)}.` : ""}</p>`;
}

/* ------------------------------------------------------------------ */
/* Navigation                                                          */
/* ------------------------------------------------------------------ */
function ouvrirDepuisAdresse() {
  const s = decodeURIComponent(location.hash.slice(1));
  if (s && parSymbole.has(s)) ouvrir(s, false);
}
document.getElementById("btn-fermer").onclick = fermer;
document.getElementById("btn-fermer-aide").onclick = fermer;
document.getElementById("voile").onclick = fermer;
document.getElementById("btn-aide").onclick = () => { derniereFocalisation = document.activeElement; montrer("aide"); };
document.addEventListener("keydown", (e) => { if (e.key === "Escape") fermer(); });
window.addEventListener("hashchange", ouvrirDepuisAdresse);

charger();
