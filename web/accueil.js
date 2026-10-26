"use strict";

/* Page d'accueil : favoris, publications de la semaine, radar des pépites, contexte économique.
   Toutes les données sont préparées chaque nuit par GitHub ; cette page ne fait que les afficher. */

// Anciens liens vers une fiche (adresse#SYMBOLE) : ils s'ouvrent désormais dans le tableau
function versTableau() { if (location.hash.length > 1) location.replace("tableau.html" + location.hash); }
versTableau();
window.addEventListener("hashchange", versTableau);

const VERSION = "__VERSION__";
const PAR_PAGE = 15;
const IGNORE_JOURS = 90;
const NOUVEAU_JOURS = 7;
const CONTINENTS = ["Europe", "Amérique du Nord", "Asie", "Amérique latine", "Moyen-Orient", "Océanie", "Afrique"];
const CRITERES = [["val", "Valorisation"], ["cro", "Croissance"], ["ren", "Rentabilité"],
  ["sit", "Situation financière"], ["rlt", "Révisions des analystes"], ["pub", "Publications"], ["vis", "Visibilité"]];
const FORT = {
  val: "valorisation parmi les plus basses de son secteur",
  cro: "croissance parmi les plus fortes de son secteur",
  ren: "rentabilité parmi les meilleures de son secteur",
  sit: "situation financière parmi les plus solides de son secteur",
  rlt: "analystes qui relèvent leurs prévisions",
  pub: "résultats souvent meilleurs que prévu",
  vis: "analystes d'accord entre eux sur l'avenir",
};
const GROUPES = ["Taux des banques centrales", "Taux à 10 ans", "Inflation sur un an",
  "Matières premières", "Devises, marché et emploi"];
const COULEURS_PAYS = ["var(--accent)", "#5d8aa2", "#a9c3d1", "var(--filet)"];

let actions = [], parSymbole = new Map(), radar = [], filtre = {}, statut = {}, macro = null;
let favoris = lire("pepites.favoris", {});
let ignores = lire("pepites.ignores", {});
let etat = Object.assign({ continent: "", sansAnalystes: false }, lire("pepites.accueil", {}));
let affichees = PAR_PAGE;
let USD_PAR_EUR = 1.1;

/* ------------------------------------------------------------------ */
/* Outils                                                              */
/* ------------------------------------------------------------------ */
function lire(cle, defaut) {
  try { const v = localStorage.getItem(cle); return v ? JSON.parse(v) : defaut; } catch (e) { return defaut; }
}
function ecrire(cle, valeur) {
  try { localStorage.setItem(cle, JSON.stringify(valeur)); } catch (e) { /* stockage indisponible */ }
}
const nf = (d) => new Intl.NumberFormat("fr-FR", { minimumFractionDigits: d, maximumFractionDigits: d });
const F = [nf(0), nf(1), nf(2)];
function nombre(v, d = 1) { return v == null || !isFinite(v) ? "—" : F[d].format(v); }
function signe(v, d = 0) { return v == null || !isFinite(v) ? "—" : (v > 0 ? "+" : "") + F[d].format(v * 100) + " %"; }
function echapper(s) {
  return String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}
function date(iso) { if (!iso) return "—"; const [a, m, j] = iso.split("-"); return `${j}/${m}/${a}`; }
function aujourdhui() { return new Date().toISOString().slice(0, 10); }
function joursDepuis(iso) {
  if (!iso) return null;
  return Math.floor((Date.now() - Date.parse(`${iso.slice(0, 10)}T12:00:00Z`)) / 864e5);
}
function euros(usd) {
  if (usd == null || !isFinite(usd)) return "—";
  const e = usd / USD_PAR_EUR;
  return e >= 1e9 ? `${nombre(e / 1e9, e >= 1e11 ? 0 : 1)} Md€` : `${nombre(e / 1e6, 0)} M€`;
}
function classeNote(v, synthese) {
  if (v == null) return "n-vide";
  if (synthese && v >= 80) return "n-or";
  return v >= 70 ? "n-haut" : v >= 40 ? "n-moy" : "n-bas";
}
function couleurBarre(v) { return v >= 70 ? "var(--haut)" : v >= 40 ? "var(--moy)" : "var(--bas)"; }
function etoiles(v) { return v >= 80 ? 5 : v >= 60 ? 4 : v >= 40 ? 3 : v >= 20 ? 2 : 1; }
function lienFiche(s) { return `tableau.html#${encodeURIComponent(s)}`; }
function sansAnalystes(a) { return a.rlt == null && a.pub == null && a.vis == null; }
const el = (id) => document.getElementById(id);

/* ------------------------------------------------------------------ */
/* Chargement                                                          */
/* ------------------------------------------------------------------ */
async function charger() {
  const json = (url, defaut) => fetch(`${url}?v=${VERSION}`).then((r) => (r.ok ? r.json() : defaut)).catch(() => defaut);
  const [t, acc, m, s] = await Promise.all([
    json("data/screener.json", null), json("data/accueil.json", { radar: [] }),
    json("data/macro.json", null), json("data/statut.json", {}),
  ]);
  statut = s || {};
  macro = m;
  if (!t) {
    el("couverture").textContent = "Les données ne sont pas encore prêtes : elles arrivent après le premier passage de nuit.";
    rendreContexte();
    return;
  }
  if (t.usd_par_eur) USD_PAR_EUR = t.usd_par_eur;
  actions = t.lignes.map((l) => {
    const o = {};
    t.champs.forEach((c, j) => { const v = l[j]; o[c] = t.dicos[c] && v != null ? t.dicos[c][v] : v; });
    return o;
  });
  parSymbole = new Map(actions.map((a) => [a.s, a]));
  radar = (acc.radar || []).map(([sym, depuis]) => ({ a: parSymbole.get(sym), depuis })).filter((x) => x.a);
  filtre = acc.filtre || {};
  nettoyerIgnores();
  afficherEntete(t.maj);
  rendreFavoris();
  rendreSemaine();
  construireContinents();
  rendreRadar();
  rendreContexte();
}

function afficherEntete(maj) {
  const notees = actions.filter((a) => a.inv != null).length;
  const donneesDu = statut.passage_complet || maj;
  el("couverture").textContent = `${nombre(notees, 0)} actions notées dans le monde · données du ${date(donneesDu)}`;
  const jours = joursDepuis(donneesDu);
  const alerte = el("alerte-maj");
  alerte.hidden = !(jours > 3);
  if (!alerte.hidden) {
    alerte.textContent = `Attention : données non mises à jour depuis ${jours} jours. La tâche automatique de GitHub semble arrêtée. `;
    if (statut.depot) {
      const lien = document.createElement("a");
      lien.href = `https://github.com/${statut.depot}#si-quelque-chose-ne-va-pas`;
      lien.target = "_blank";
      lien.rel = "noopener";
      lien.textContent = "Que faire ?";
      alerte.append(lien);
    }
  }
}

/* ------------------------------------------------------------------ */
/* Favoris                                                             */
/* ------------------------------------------------------------------ */
/* Raisons de réexaminer un favori. Après un réexamen, seules les nouveautés comptent. */
function raisonsFavori(a, f) {
  const vu = f.vu || {};
  const r = [];
  const reference = vu.inv ?? f.inv;
  if (reference != null && a.inv != null && a.inv <= reference - 15) {
    r.push(`la note a perdu ${reference - a.inv} points ${f.vu ? "depuis le dernier réexamen" : "depuis l'ajout"}`);
  }
  if (a.val != null && a.val < 40 && !(vu.val != null && vu.val < 40)) r.push(`n'est plus bon marché (valorisation ${a.val})`);
  if (a.sit != null && a.sit < 30 && !(vu.sit != null && vu.sit < 30)) r.push(`situation financière fragile (${a.sit})`);
  const depuis = joursDepuis(vu.d || f.d);
  if (depuis != null && depuis >= 180) r.push(`pas réexaminée depuis ${Math.floor(depuis / 30)} mois`);
  return r;
}

function rendreFavoris() {
  const liste = Object.entries(favoris).map(([s, f]) => ({ s, f, a: parSymbole.get(s) }))
    .sort((x, y) => (x.a ? 0 : 1) - (y.a ? 0 : 1) || String(x.a?.n ?? x.s).localeCompare(String(y.a?.n ?? y.s), "fr"));
  if (!liste.length) {
    el("favoris-resume").textContent = "";
    el("favoris").innerHTML = `<p class="vide-texte">Aucun favori pour l'instant. Ajoute-en depuis le radar ci-dessous ou depuis le tableau, avec le bouton ☆ Favori.</p>`;
    return;
  }
  let aRevoir = 0;
  el("favoris").innerHTML = liste.map(({ s, f, a }) => {
    if (!a) {
      return `<div class="fav-ligne"><div class="fav-haut"><div><span class="fav-nom">${echapper(s)}</span>
        <span class="acc-ident">N'est plus suivie par le screener (retirée de la cote ou données indisponibles).</span></div></div></div>`;
    }
    const raisons = raisonsFavori(a, f);
    if (raisons.length) aRevoir += 1;
    const delta = f.inv != null && a.inv != null ? a.inv - f.inv : null;
    const coursDepuis = f.px && a.px && f.dv === a.dv ? `cours ${signe(a.px / f.px - 1)}` : "";
    const points = delta == null ? "" : `${delta > 0 ? "+" : delta < 0 ? "−" : "±"}${Math.abs(delta)} pt${Math.abs(delta) > 1 ? "s" : ""}`;
    const depuis = [points, coursDepuis]
      .filter(Boolean).join(" · ");
    return `<div class="fav-ligne">
      <div class="fav-haut">
        <div><a class="fav-nom" href="${lienFiche(s)}">${echapper(a.n)}</a>
          <span class="acc-ident">${echapper(a.p || "")} · ${echapper(a.se || "")}</span></div>
        <div class="fav-droite"><span class="n grande ${classeNote(a.inv, true)}">${a.inv ?? "—"}</span>
          <span>${depuis ? `${depuis} depuis l'ajout` : ""}</span><span>ajoutée le ${date(f.d)}</span></div>
      </div>
      <div class="fav-bas">
        ${raisons.length
          ? `<span class="signal revoir">À revoir : ${echapper(raisons.join(" ; "))}</span>
             <button type="button" class="bouton-contour" data-revu="${echapper(s)}">Marquer comme réexaminée</button>`
          : `<span class="signal ok">Rien à signaler</span>`}
      </div>
    </div>`;
  }).join("");
  el("favoris-resume").textContent = `${liste.length} suivi${liste.length > 1 ? "s" : ""}` +
    (aRevoir ? ` · ${aRevoir} à revoir` : "");
  el("favoris").querySelectorAll("[data-revu]").forEach((b) => {
    b.onclick = () => {
      const s = b.dataset.revu, a = parSymbole.get(s);
      favoris[s].vu = { d: aujourdhui(), inv: a.inv, val: a.val, sit: a.sit };
      ecrire("pepites.favoris", favoris);
      rendreFavoris();
    };
  });
}

function basculerFavori(s) {
  const a = parSymbole.get(s);
  if (favoris[s]) delete favoris[s];
  else favoris[s] = { d: aujourdhui(), px: a.px, dv: a.dv, inv: a.inv };
  ecrire("pepites.favoris", favoris);
  rendreFavoris();
  rendreSemaine();
}

/* ------------------------------------------------------------------ */
/* Publications de la semaine                                          */
/* ------------------------------------------------------------------ */
function rendreSemaine() {
  const debut = aujourdhui();
  const fin = new Date(Date.now() + 7 * 864e5).toISOString().slice(0, 10);
  const dansRadar = new Set(radar.map((r) => r.a.s));
  const symboles = new Set([...Object.keys(favoris), ...dansRadar]);
  const liste = [...symboles].map((s) => parSymbole.get(s))
    .filter((a) => a && a.pp && a.pp >= debut && a.pp <= fin)
    .sort((x, y) => x.pp.localeCompare(y.pp) || (favoris[y.s] ? 1 : 0) - (favoris[x.s] ? 1 : 0))
    .slice(0, 10);
  if (!liste.length) {
    el("semaine").innerHTML = `<p class="vide-texte">Aucune publication de résultats prévue d'ici 7 jours parmi tes favoris et le radar.</p>`;
    return;
  }
  el("semaine").innerHTML = liste.map((a) => {
    const j = new Date(`${a.pp}T12:00:00Z`);
    const jour = j.toLocaleDateString("fr-FR", { weekday: "short", timeZone: "UTC" }).replace(".", "");
    const fav = !!favoris[a.s];
    return `<div class="sem-ligne">
      <div class="sem-jour"><span>${echapper(jour)}</span><strong>${j.getUTCDate()}</strong></div>
      <div class="sem-texte"><a class="sem-nom" href="${lienFiche(a.s)}">${echapper(a.n)}</a>
        <span class="acc-ident">Résultats${a.ppe ? " (date estimée)" : ""}</span></div>
      <span class="tag ${fav ? "tag-favori" : "tag-radar"}">${fav ? "Favori" : "Radar"}</span>
    </div>`;
  }).join("");
}

/* ------------------------------------------------------------------ */
/* Radar                                                               */
/* ------------------------------------------------------------------ */
function nettoyerIgnores() {
  let change = false;
  for (const [s, d] of Object.entries(ignores)) {
    if (joursDepuis(d) >= IGNORE_JOURS) { delete ignores[s]; change = true; }
  }
  if (change) ecrire("pepites.ignores", ignores);
}

function construireContinents() {
  const presents = new Set(radar.map((r) => r.a.c));
  const liste = [["", "Monde"], ...CONTINENTS.filter((c) => presents.has(c)).map((c) => [c, c])];
  if (etat.continent && !presents.has(etat.continent)) etat.continent = "";
  el("radar-continents").innerHTML = liste.map(([c, nom]) =>
    `<button type="button" data-c="${echapper(c)}" aria-pressed="${etat.continent === c}">${echapper(nom)}</button>`).join("") +
    `<button type="button" class="bascule-puce" data-analystes aria-pressed="${etat.sansAnalystes}">Sans analystes seulement</button>`;
  el("radar-continents").onclick = (e) => {
    const b = e.target.closest("button");
    if (!b) return;
    if (b.hasAttribute("data-analystes")) etat.sansAnalystes = !etat.sansAnalystes;
    else etat.continent = b.dataset.c;
    ecrire("pepites.accueil", etat);
    affichees = PAR_PAGE;
    el("radar-continents").querySelectorAll("button[data-c]").forEach((x) =>
      x.setAttribute("aria-pressed", String(x.dataset.c === etat.continent)));
    el("radar-continents").querySelector("[data-analystes]").setAttribute("aria-pressed", String(etat.sansAnalystes));
    rendreRadar();
  };
}

function rendreConcentration(liste) {
  const boite = el("concentration");
  if (liste.length < 10) { boite.hidden = true; return; }
  const parPays = new Map();
  liste.forEach(({ a }) => parPays.set(a.p, (parPays.get(a.p) || 0) + 1));
  const tries = [...parPays].sort((x, y) => y[1] - x[1]);
  const premiers = tries.slice(0, 3);
  const autres = liste.length - premiers.reduce((t, [, n]) => t + n, 0);
  const parts = [...premiers, ...(autres ? [["Autres pays", autres]] : [])]
    .map(([p, n], i) => ({ p, part: Math.round((n / liste.length) * 100), couleur: COULEURS_PAYS[Math.min(i, 3)] }));
  // Poids du premier pays parmi les sociétés notées de la même zone
  const zone = actions.filter((a) => a.inv != null && (!etat.continent || a.c === etat.continent));
  const [paysTete] = premiers[0];
  const poids = Math.round((zone.filter((a) => a.p === paysTete).length / Math.max(zone.length, 1)) * 100);
  boite.hidden = false;
  boite.innerHTML = `<p><strong>${echapper(paysTete)} : ${parts[0].part} % du radar</strong>, alors que ce pays ne pèse que ${poids} % des sociétés notées${etat.continent ? ` de cette zone` : ""}.</p>
    <div class="barre-pays" aria-hidden="true">${parts.map((x) => `<span style="width:${x.part}%;background:${x.couleur}"></span>`).join("")}</div>
    <div class="legende-pays">${parts.map((x) => `<span><i style="background:${x.couleur}"></i>${echapper(x.p)} ${x.part} %</span>`).join("")}</div>`;
}

function ressortEtFaiblesse(a) {
  const notes = CRITERES.filter(([k]) => a[k] != null).map(([k, nom]) => ({ k, nom, v: a[k] }));
  if (!notes.length) return ["—", "—"];
  const fort = notes.reduce((x, y) => (y.v > x.v ? y : x));
  const faible = notes.reduce((x, y) => (y.v < x.v ? y : x));
  const ressort = `${FORT[fort.k]} (${fort.v})`;
  const point = faible.v >= 70
    ? `aucun marqué ; le moins bon : ${faible.nom.toLowerCase()} (${faible.v})`
    : `${faible.nom.toLowerCase()} (${faible.v}), nettement en retrait`;
  return [ressort, point];
}

function carteRadar({ a, depuis }) {
  const [ressort, faible] = ressortEtFaiblesse(a);
  const nouveau = joursDepuis(depuis) != null && joursDepuis(depuis) < NOUVEAU_JOURS;
  const fav = !!favoris[a.s];
  const mini = [["val", "Valorisation"], ["ren", "Rentabilité"], ["sit", "Situation financière"]].map(([k, nom]) => {
    const v = a[k];
    return `<div class="mini-note"><span>${nom}</span>
      <span class="piste-mini" aria-hidden="true"><span style="width:${v ?? 0}%;background:${couleurBarre(v)}"></span></span>
      <b>${v ?? "—"}</b></div>`;
  }).join("");
  const nbEtoiles = etoiles(a.inv);
  return `<article class="carte radar-carte">
    <div class="radar-haut">
      <div><a class="radar-nom" href="${lienFiche(a.s)}">${echapper(a.n)}</a>
        <span class="acc-ident">${echapper(a.p || "")} · ${echapper(a.i || a.se || "")} · ${euros(a.cap)}</span></div>
      <div class="radar-note"><span class="n ${classeNote(a.inv, true)}">${a.inv}</span>
        <span class="etoiles-mini" role="img" aria-label="${nbEtoiles} étoiles sur 5">${"★".repeat(nbEtoiles)}</span></div>
    </div>
    <div class="badges">
      ${nouveau ? `<span class="badge badge-nouveau">Nouveau cette semaine</span>` : ""}
      <span class="badge">${sansAnalystes(a) ? "Aucun analyste" : "Suivie par les analystes"}</span>
    </div>
    <div class="mini-notes">${mini}</div>
    <div class="raisons">
      <p><svg aria-hidden="true" width="16" height="16" viewBox="0 0 16 16" fill="none" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" class="trait-haut"><path d="M3 8.5l3 3 7-7"/></svg>
        <span><strong>Ressort pour :</strong> ${echapper(ressort)}</span></p>
      <p><svg aria-hidden="true" width="16" height="16" viewBox="0 0 16 16" fill="none" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" class="trait-bas"><path d="M8 2.5l6 11H2z"/><path d="M8 7v3"/><path d="M8 12h.01"/></svg>
        <span><strong>Point faible :</strong> ${echapper(faible)}</span></p>
    </div>
    <div class="actions-carte">
      <a class="bouton-plein" href="${lienFiche(a.s)}">Voir la fiche</a>
      <button type="button" class="bouton-contour" data-favori="${echapper(a.s)}" aria-pressed="${fav}">${fav ? "★ Dans mes favoris" : "☆ Favori"}</button>
      <button type="button" class="lien" data-ignorer="${echapper(a.s)}">Ignorer 90 jours</button>
    </div>
  </article>`;
}

function rendreRadar() {
  const f = filtre;
  el("radar-critere").textContent = f.note_min != null
    ? `Note d'au moins ${f.note_min}, parmi les ${100 - f.valorisation_min} % les moins chères de leur secteur, sans risque de faillite apparent (situation financière d'au moins ${f.situation_min}), plus de ${nombre(f.capi_min_eur / 1e6, 0)} M€ de capitalisation.`
    : "";
  const tous = radar.filter(({ a }) => (!etat.continent || a.c === etat.continent) && (!etat.sansAnalystes || sansAnalystes(a)));
  const liste = tous.filter(({ a }) => !ignores[a.s]);
  const nbIgnores = tous.length - liste.length;
  el("radar-compte").textContent = `${nombre(liste.length, 0)} société${liste.length > 1 ? "s" : ""}`;
  rendreConcentration(liste);
  el("radar").innerHTML = liste.length
    ? liste.slice(0, affichees).map(carteRadar).join("")
    : `<p class="vide-texte">Aucune société ne passe le filtre pour cette sélection.</p>`;
  const reste = liste.length - affichees;
  el("radar-plus").hidden = reste <= 0;
  el("radar-plus").textContent = `Voir les ${Math.min(reste, PAR_PAGE)} suivantes`;
  el("radar-ignores").hidden = !nbIgnores;
  el("radar-ignores").textContent = `${nbIgnores} société${nbIgnores > 1 ? "s" : ""} ignorée${nbIgnores > 1 ? "s" : ""} : les réafficher`;
}

el("radar").addEventListener("click", (e) => {
  const fav = e.target.closest("[data-favori]");
  if (fav) {
    basculerFavori(fav.dataset.favori);
    const actif = !!favoris[fav.dataset.favori];
    fav.setAttribute("aria-pressed", String(actif));
    fav.textContent = actif ? "★ Dans mes favoris" : "☆ Favori";
    return;
  }
  const ign = e.target.closest("[data-ignorer]");
  if (ign) {
    ignores[ign.dataset.ignorer] = aujourdhui();
    ecrire("pepites.ignores", ignores);
    rendreRadar();
  }
});
el("radar-plus").onclick = () => { affichees += PAR_PAGE; rendreRadar(); };
el("radar-ignores").onclick = () => { ignores = {}; ecrire("pepites.ignores", ignores); rendreRadar(); };

/* ------------------------------------------------------------------ */
/* Contexte économique                                                 */
/* ------------------------------------------------------------------ */
function valeurMacro(i) {
  const v = i.valeur;
  switch (i.id) {
    case "brent": case "cuivre": case "or": return `${nombre(v, 0)} $`;
    case "eurusd": return `${nombre(v, 2)} $`;
    case "eurjpy": return `${nombre(v, 0)} ¥`;
    case "vix": return nombre(v, 0);
    default: return `${nombre(v, i.id.startsWith("inf_") || i.id.startsWith("cho_") ? 1 : 2)} %`;
  }
}
function variationMacro(i) {
  const d = i.variation_1an;
  if (d == null) return "";
  const fleche = d > 0 ? "↑" : d < 0 ? "↓" : "→";
  return i.mode === "points"
    ? `${fleche} ${d > 0 ? "+" : ""}${nombre(d, Math.abs(d) < 1 ? 2 : 1)} pt sur 1 an`
    : `${fleche} ${d > 0 ? "+" : ""}${nombre(d, 0)} % sur 1 an`;
}
function mois(m) {
  return new Date(`${m.slice(0, 7)}-15T12:00:00Z`).toLocaleDateString("fr-FR", { month: "short", year: "numeric", timeZone: "UTC" });
}
function courbe(serie) {
  const v = serie.map(([, x]) => x);
  const min = Math.min(...v), max = Math.max(...v), e = max - min || 1;
  return v.map((y, i) => `${((i * 120) / Math.max(v.length - 1, 1)).toFixed(1)},${(33 - ((y - min) / e) * 30).toFixed(1)}`).join(" ");
}
const FLECHE_HAUT = `<svg aria-hidden="true" width="12" height="12" viewBox="0 0 12 12"><path d="M6 1.5l4.5 7.5h-9z" class="f-hausse"/></svg>`;
const FLECHE_BAS = `<svg aria-hidden="true" width="12" height="12" viewBox="0 0 12 12"><path d="M6 10.5L1.5 3h9z" class="f-baisse"/></svg>`;

function rendreContexte() {
  const boite = el("contexte");
  const liste = (macro && macro.indicateurs) || [];
  if (!liste.length) {
    boite.innerHTML = `<p class="vide-texte">Les indicateurs économiques arriveront après le prochain passage de nuit.</p>`;
    return;
  }
  boite.innerHTML = GROUPES.map((g) => {
    const tuiles = liste.filter((i) => i.groupe === g && (i.serie || []).length > 1);
    if (!tuiles.length) return "";
    return `<div class="groupe-macro"><h3>${echapper(g)}</h3><div class="tuiles">${tuiles.map((i) => `
      <div class="tuile">
        <span class="tuile-nom">${echapper(i.nom)}</span>
        <div class="tuile-valeur"><strong>${valeurMacro(i)}</strong><span>${variationMacro(i)}</span></div>
        <div>
          <svg class="courbe" role="img" aria-label="${echapper(i.nom)} : évolution de ${mois(i.serie[0][0])} à ${mois(i.serie[i.serie.length - 1][0])}" viewBox="0 0 120 36" preserveAspectRatio="none">
            <line x1="0" y1="35.5" x2="120" y2="35.5" vector-effect="non-scaling-stroke"/>
            <polyline points="${courbe(i.serie)}" vector-effect="non-scaling-stroke"/>
          </svg>
          <div class="axe"><span>${mois(i.serie[0][0])}</span><span>${mois(i.serie[i.serie.length - 1][0])}</span></div>
        </div>
        ${i.hausse || i.baisse ? `<div class="effets">
          ${i.hausse ? `<span>${FLECHE_HAUT}${echapper(i.hausse)}</span>` : ""}
          ${i.baisse ? `<span>${FLECHE_BAS}${echapper(i.baisse)}</span>` : ""}
        </div>` : ""}
      </div>`).join("")}</div></div>`;
  }).join("");
}

charger();
