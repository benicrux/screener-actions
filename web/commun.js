"use strict";

/* Code commun à l'accueil et au screener : enregistrement des préférences, favoris (signaux
   de thèse, thèse écrite) et, si elle est configurée, synchronisation entre appareils. */
const Pepites = (() => {
  const auditeurs = [];

  /* ---------------------------------------------------------------- */
  /* Enregistrement dans le navigateur                                 */
  /* ---------------------------------------------------------------- */
  function lire(cle, defaut) {
    try { const v = localStorage.getItem(cle); return v ? JSON.parse(v) : defaut; } catch (e) { return defaut; }
  }
  // Favoris et sociétés ignorées : partagés entre appareils quand la synchronisation est
  // activée (synchro.js) ; les filtres et réglages d'affichage restent propres à l'appareil
  const PARTAGES = ["pepites.favoris", "pepites.ignores"];
  function ecrire(cle, valeur) {
    try { localStorage.setItem(cle, JSON.stringify(valeur)); } catch (e) { /* stockage indisponible */ }
    if (!PARTAGES.includes(cle)) return;
    try { localStorage.setItem("pepites.modifie", JSON.stringify(Date.now())); } catch (e) { /* idem */ }
    if (Pepites.synchro) Pepites.synchro.planifier();
  }
  // Une page qui affiche des favoris se fait prévenir quand ils changent ailleurs
  // (synchronisation, autre onglet)
  function surChangement(fonction) { auditeurs.push(fonction); }
  function prevenir() { auditeurs.forEach((f) => { try { f(); } catch (e) { console.error(e); } }); }
  window.addEventListener("storage", (e) => { if (e.key && e.key.startsWith("pepites.")) prevenir(); });

  /* ---------------------------------------------------------------- */
  /* Favoris : ce qui mérite un réexamen                               */
  /* ---------------------------------------------------------------- */
  // « Fondamentaux » : la note investisseur sans la valorisation. Une action qui monte
  // devient plus chère et perd des points de valorisation : ce n'est pas une raison de la
  // revoir. Une baisse des fondamentaux, si.
  const POIDS_FONDAMENTAUX = { cro: 15, ren: 15, sit: 10, rlt: 15, pub: 10, vis: 5 };

  function fondamentaux(a) {
    let somme = 0, poids = 0;
    for (const [k, w] of Object.entries(POIDS_FONDAMENTAUX)) {
      if (a[k] != null) { somme += a[k] * w; poids += w; }
    }
    return poids >= 25 ? Math.round(somme / poids) : null;
  }

  // Ce qu'on retient d'une société au moment de l'ajout ou d'un réexamen
  function photo(a) {
    return { fond: fondamentaux(a), ren: a.ren ?? null, sit: a.sit ?? null, rlt: a.rlt ?? null, dil: a.dil ?? null };
  }

  function nouveauFavori(a) {
    return { d: new Date().toISOString().slice(0, 10), px: a.px, dv: a.dv, inv: a.inv, ref: photo(a) };
  }

  const pct = (x) => new Intl.NumberFormat("fr-FR", { maximumFractionDigits: 0 }).format(x * 100) + " %";

  /* La thèse est-elle cassée ? Seuls les changements depuis l'ajout ou le dernier réexamen
     comptent ; une hausse du cours n'en est jamais un. */
  function raisonsFavori(a, f) {
    const ref = Object.assign({}, f.ref || {}, f.vu && f.vu.fond !== undefined ? f.vu : {});
    const r = [];
    const fond = fondamentaux(a);
    if (ref.fond != null && fond != null && fond <= ref.fond - 15) {
      r.push(`fondamentaux en baisse de ${ref.fond - fond} points (croissance, rentabilité, solidité, analystes)`);
    }
    if (ref.ren != null && a.ren != null && a.ren <= ref.ren - 20) r.push(`rentabilité en net recul (${ref.ren} → ${a.ren})`);
    if (a.sit != null && a.sit < 30 && !(ref.sit != null && ref.sit < 30)) r.push(`situation financière fragile (${a.sit})`);
    if (a.dil != null && a.dil > 0.10 && !(ref.dil != null && ref.dil > 0.10)) r.push(`dilution : ${pct(a.dil)} d'actions en plus en 3 ans`);
    if (a.rlt != null && a.rlt <= 25 && !(ref.rlt != null && ref.rlt <= 25)) r.push(`les analystes baissent leurs prévisions (révisions ${a.rlt})`);
    const depuis = joursDepuis((f.vu && f.vu.d) || f.d);
    if (depuis != null && depuis >= 180) r.push(`pas réexaminée depuis ${Math.floor(depuis / 30)} mois`);
    return r;
  }

  // Favoris enregistrés avant les signaux de thèse : la situation d'aujourd'hui sert de
  // point de départ (sinon tout ce qui a changé depuis l'ajout serait signalé d'un coup)
  function completerFavoris(favoris, parSymbole) {
    let change = false;
    for (const [s, f] of Object.entries(favoris)) {
      const a = parSymbole.get(s);
      if (a && !f.ref) { f.ref = photo(a); change = true; }
      if (a && f.vu && f.vu.fond === undefined) { Object.assign(f.vu, photo(a)); change = true; }
    }
    return change;
  }

  function joursDepuis(iso) {
    if (!iso) return null;
    return Math.floor((Date.now() - Date.parse(`${iso.slice(0, 10)}T12:00:00Z`)) / 864e5);
  }

  /* ---------------------------------------------------------------- */
  /* La thèse : pourquoi je l'ai choisie, ce qui me ferait vendre      */
  /* ---------------------------------------------------------------- */
  function echapper(s) {
    return String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  }

  function blocThese(s, f, ouvert = false) {
    const t = f.these || {};
    // Fermée, la thèse se résume à sa première ligne ; ouverte, elle se modifie
    const resume = t.pourquoi ? `<span class="these-resume">${echapper(t.pourquoi.length > 110 ? `${t.pourquoi.slice(0, 107)}…` : t.pourquoi)}</span>` : "";
    return `<details class="these"${ouvert ? " open" : ""} data-these="${echapper(s)}">
      <summary><span class="these-titre">${t.pourquoi || t.vendre ? "Ma thèse" : "Écrire ma thèse"}</span>${resume}</summary>
      <label>Pourquoi je l'ai choisie<textarea rows="2" data-champ="pourquoi" maxlength="600" placeholder="Ex. : très bon marché, trésorerie abondante, rachète ses actions">${echapper(t.pourquoi || "")}</textarea></label>
      <label>Ce qui me ferait vendre<textarea rows="2" data-champ="vendre" maxlength="600" placeholder="Ex. : la dette dépasse 2 fois l'EBITDA, la direction émet des actions">${echapper(t.vendre || "")}</textarea></label>
      <span class="these-etat" aria-live="polite"></span>
    </details>`;
  }

  // Enregistre la thèse au fil de la frappe (sans bouton à cliquer)
  function brancherTheses(conteneur, favoris, enregistrer) {
    const minuteurs = {};
    conteneur.querySelectorAll("details.these").forEach((d) => {
      d.addEventListener("input", (e) => {
        const champ = e.target.dataset.champ;
        if (!champ) return;
        const s = d.dataset.these;
        if (!favoris[s]) return;
        favoris[s].these = Object.assign({}, favoris[s].these, { [champ]: e.target.value.trim() });
        clearTimeout(minuteurs[s]);
        minuteurs[s] = setTimeout(() => {
          enregistrer();
          const etat = d.querySelector(".these-etat");
          if (etat) etat.textContent = "Enregistré";
        }, 400);
      });
    });
  }

  return { lire, ecrire, surChangement, prevenir, fondamentaux, photo, nouveauFavori, raisonsFavori,
           completerFavoris, blocThese, brancherTheses, synchro: null };
})();
