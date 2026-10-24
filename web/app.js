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
const ORDRE_TAILLES = ["Géante", "Grande", "Moyenne", "Petite", "Très petite"];
const CONTINENTS = ["Europe", "Amérique du Nord", "Amérique latine", "Asie", "Moyen-Orient", "Afrique", "Océanie"];
const PAR_PAGE = 100;

/* ------------------------------------------------------------------ */
/* État                                                                */
/* ------------------------------------------------------------------ */
const ETAT_DEFAUT = {
  continent: "", pays: "", secteur: "", industrie: "", taille: "", note: 0,
  favoris: false, q: "", tri: "inv", sens: -1,
};
let etat = Object.assign({}, ETAT_DEFAUT, lire("pepites.filtres", {}));
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
function capi(v) {
  if (v == null || !isFinite(v)) return "—";
  if (v >= 1e9) return nombre(v / 1e9, v >= 1e11 ? 0 : 1) + " Md$";
  return nombre(v / 1e6, 0) + " M$";
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
      fetch("data/screener.json").then((r) => r.json()),
      fetch("data/statut.json").then((r) => r.json()).catch(() => ({})),
    ]);
    statut = s;
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
    document.getElementById("couverture").textContent =
      "Les données ne sont pas encore prêtes. Le premier calcul est peut-être en cours : revenez dans quelques minutes.";
  }
}

function afficherCouverture(maj) {
  const el = document.getElementById("couverture");
  const notees = actions.filter((a) => a.inv != null).length;
  if (!actions.length) {
    el.textContent = "Le robot n'a encore récupéré aucune donnée. Les premières sociétés apparaissent après son premier passage.";
    return;
  }
  let texte = `${nombre(notees, 0)} actions notées dans le monde, mise à jour du ${date(maj)}.`;
  if (statut.jamais_lues > 0) {
    texte += ` ${nombre(statut.jamais_lues, 0)} sociétés restent à lire`;
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
    `<button type="button" data-c="${c}" aria-pressed="${etat.continent === c}">${c || "Monde"}</button>`).join("");
  zone.onclick = (e) => {
    const b = e.target.closest("button");
    if (!b) return;
    etat.continent = b.dataset.c;
    etat.pays = "";
    majFiltres();
  };
  document.getElementById("f-pays").onchange = (e) => { etat.pays = e.target.value; majFiltres(); };
  document.getElementById("f-secteur").onchange = (e) => { etat.secteur = e.target.value; etat.industrie = ""; majFiltres(); };
  document.getElementById("f-industrie").onchange = (e) => { etat.industrie = e.target.value; majFiltres(); };
  document.getElementById("f-taille").onchange = (e) => { etat.taille = e.target.value; majFiltres(); };
  document.getElementById("f-note").onchange = (e) => { etat.note = +e.target.value; majFiltres(); };
  document.getElementById("f-favoris").onchange = (e) => { etat.favoris = e.target.checked; majFiltres(); };
  let minuterie;
  document.getElementById("recherche").oninput = (e) => {
    clearTimeout(minuterie);
    minuterie = setTimeout(() => { etat.q = e.target.value; majFiltres(false); }, 150);
  };
  document.getElementById("btn-reinit").onclick = () => {
    etat = Object.assign({}, ETAT_DEFAUT, { tri: etat.tri, sens: etat.sens });
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

function majFiltres(remettre = true) {
  document.querySelectorAll("#continents button").forEach((b) =>
    b.setAttribute("aria-pressed", String(b.dataset.c === etat.continent)));
  const dansContinent = etat.continent ? actions.filter((a) => a.c === etat.continent) : actions;
  options(document.getElementById("f-pays"), uniques(dansContinent, "p"), "Tous", etat.pays);
  options(document.getElementById("f-secteur"), uniques(actions, "se"), "Tous", etat.secteur);
  const dansSecteur = etat.secteur ? actions.filter((a) => a.se === etat.secteur) : actions;
  options(document.getElementById("f-industrie"), uniques(dansSecteur, "i"), "Toutes", etat.industrie);
  const tailles = ORDRE_TAILLES.filter((t) => actions.some((a) => a.t === t));
  options(document.getElementById("f-taille"), tailles, "Toutes", etat.taille);
  document.getElementById("f-note").value = String(etat.note);
  document.getElementById("f-favoris").checked = etat.favoris;
  if (document.getElementById("recherche").value !== etat.q) document.getElementById("recherche").value = etat.q;
  ecrire("pepites.filtres", Object.assign({}, etat, { q: "" }));
  if (remettre) affichees = PAR_PAGE;
  libelleFiltres();
  afficher();
}

function libelleFiltres() {
  const actifs = ["pays", "secteur", "industrie", "taille", "note", "favoris"].filter((k) => etat[k]).length;
  const ouvert = document.getElementById("selecteurs").classList.contains("ouvert");
  document.getElementById("btn-filtres").textContent =
    (ouvert ? "Masquer les filtres" : "Plus de filtres") + (actifs ? ` (${actifs} actif${actifs > 1 ? "s" : ""})` : "");
}

function normaliser(s) {
  return String(s || "").normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase();
}

function filtrer() {
  const q = normaliser(etat.q.trim());
  return actions.filter((a) =>
    (!etat.continent || a.c === etat.continent) &&
    (!etat.pays || a.p === etat.pays) &&
    (!etat.secteur || a.se === etat.secteur) &&
    (!etat.industrie || a.i === etat.industrie) &&
    (!etat.taille || a.t === etat.taille) &&
    (!etat.note || (a.inv != null && a.inv >= etat.note)) &&
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
    paquets.set(cle, fetch(`data/fiches/${cle}.json`).then((r) => r.json()));
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
    !a.fin && ligne("Dette nette / EBITDA", f.dette_nette_ebitda === -1 ? "Trésorerie nette" : f.dette_nette_ebitda === 99 ? "Dettes sans EBITDA positif" : nombre(f.dette_nette_ebitda, 1)),
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
    ligne("Rentabilité des fonds propres", pct(f.roe)),
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
