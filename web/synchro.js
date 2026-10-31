/* Synchronisation des favoris (thèses comprises) et des sociétés ignorées entre appareils,
   avec un compte Google.

   Firebase (gratuit) : connexion Google et base Firestore, un document par personne,
   utilisateurs/{identifiant}, que seule la personne connectée peut lire et écrire (règles
   Firestore). Rien d'autre n'est envoyé : ni les filtres, ni l'adresse e-mail.

   Sans réglages Firebase (firebase-config.js vide), ce fichier ne fait rien : les favoris
   restent dans le navigateur, comme avant. */
const CONFIG = window.PEPITES_FIREBASE;
const SDK = window.PEPITES_FIREBASE_SDK || "https://www.gstatic.com/firebasejs/12.19.0";
const CLES = ["pepites.favoris", "pepites.ignores"];
const MODIFIE = "pepites.modifie";   // dernière modification faite sur cet appareil (ms)
const LIE = "pepites.synchro";       // compte déjà réuni avec cet appareil

const etat = { actif: Boolean(CONFIG), pret: false, connecte: false, prenom: "", erreur: "" };
const vues = [];

function lireBrut(cle, defaut) {
  try { const v = localStorage.getItem(cle); return v ? JSON.parse(v) : defaut; } catch (e) { return defaut; }
}
function ecrireBrut(cle, valeur) {
  try { localStorage.setItem(cle, JSON.stringify(valeur)); } catch (e) { /* stockage indisponible */ }
}
function montrer() {
  vues.forEach((f) => { try { f(etat); } catch (e) { console.error(e); } });
  rendreLigne();
}

// Sous les favoris de l'accueil : où sont gardés les favoris, et le bouton pour se connecter
const MESSAGES = {
  fenetre: "La fenêtre de connexion a été bloquée : autorise les fenêtres pour ce site, puis réessaie.",
  connexion: "La connexion n'a pas abouti, réessaie plus tard.",
  lecture: "Synchronisation impossible pour le moment : tes favoris restent sur cet appareil.",
  envoi: "Le dernier changement n'a pas pu être envoyé : il le sera au prochain.",
  chargement: "Synchronisation indisponible (Google ne répond pas) : tes favoris restent sur cet appareil.",
};
function rendreLigne() {
  const el = document.getElementById("synchro");
  if (!el || !etat.actif) return;
  el.hidden = !etat.pret;
  const bouton = (action, texte) => `<button type="button" class="lien" data-compte="${action}">${texte}</button>`;
  let html = etat.connecte
    ? `Favoris synchronisés sur tous tes appareils${etat.prenom ? ` (compte de ${echapper(etat.prenom)})` : ""}. ${bouton("deconnecter", "Se déconnecter")}`
    : `Favoris gardés sur cet appareil. ${bouton("connecter", "Les retrouver sur tous mes appareils")} (compte Google)`;
  if (etat.erreur) html += `<br><span class="synchro-erreur">${MESSAGES[etat.erreur] || MESSAGES.lecture}</span>`;
  el.innerHTML = html;
}
function echapper(s) {
  return String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}
document.addEventListener("click", (e) => {
  const b = e.target.closest("[data-compte]");
  if (!b) return;
  if (b.dataset.compte === "connecter") window.PepitesCompte.connecter();
  else window.PepitesCompte.deconnecter();
});

window.PepitesCompte = {
  etat,
  // Une page affiche l'état de la synchronisation (accueil : sous les favoris)
  surEtat(f) { vues.push(f); f(etat); },
  connecter() {}, deconnecter() {},
};

async function demarrer() {
  const [app, A, F] = await Promise.all([
    import(`${SDK}/firebase-app.js`), import(`${SDK}/firebase-auth.js`), import(`${SDK}/firebase-firestore.js`)]);
  const appli = app.initializeApp(CONFIG);
  const auth = A.getAuth(appli);
  const db = F.getFirestore(appli);
  let arreter = null, minuteur = null, envoyee = 0;

  const local = () => ({ favoris: lireBrut(CLES[0], {}), ignores: lireBrut(CLES[1], {}) });
  // Écrit sur cet appareil ce qui vient d'ailleurs, sans le renvoyer, et prévient la page
  function appliquer(d) {
    ecrireBrut(CLES[0], d.favoris || {});
    ecrireBrut(CLES[1], d.ignores || {});
    ecrireBrut(MODIFIE, d.maj || Date.now());
    Pepites.prevenir();
  }
  async function envoyer(ref) {
    envoyee = Math.max(Date.now(), lireBrut(MODIFIE, 0));
    ecrireBrut(MODIFIE, envoyee);
    await F.setDoc(ref, { ...local(), maj: envoyee });
  }

  A.onAuthStateChanged(auth, async (personne) => {
    if (arreter) { arreter(); arreter = null; }
    Pepites.synchro = null;
    etat.pret = true;
    etat.connecte = Boolean(personne);
    etat.prenom = personne ? String(personne.displayName || "").split(" ")[0] : "";
    etat.erreur = "";
    if (!personne) { montrer(); return; }
    const ref = F.doc(db, "utilisateurs", personne.uid);
    try {
      const lu = await F.getDoc(ref);
      const distant = lu.exists() ? lu.data() : {};
      if (lireBrut(LIE, null) !== personne.uid) {
        // Première connexion sur cet appareil : on réunit les deux listes (en cas de doublon,
        // la version de cet appareil l'emporte)
        const l = local();
        appliquer({ favoris: { ...(distant.favoris || {}), ...l.favoris },
                    ignores: { ...(distant.ignores || {}), ...l.ignores }, maj: Date.now() });
        ecrireBrut(LIE, personne.uid);
        await envoyer(ref);
      } else if ((distant.maj || 0) > lireBrut(MODIFIE, 0)) {
        appliquer(distant);            // modifié ailleurs depuis : l'autre appareil fait foi
      } else if ((distant.maj || 0) < lireBrut(MODIFIE, 0)) {
        await envoyer(ref);            // modifié ici sans être envoyé (hors connexion)
      }
      Pepites.synchro = {
        planifier() {
          clearTimeout(minuteur);
          minuteur = setTimeout(() => envoyer(ref).catch((e) => { console.error(e); etat.erreur = "envoi"; montrer(); }), 1200);
        },
      };
      // Un changement fait sur un autre appareil arrive tout seul
      arreter = F.onSnapshot(ref, (s) => {
        if (s.metadata.hasPendingWrites || !s.exists()) return;
        const d = s.data();
        if (d.maj && d.maj !== envoyee && d.maj > lireBrut(MODIFIE, 0)) appliquer(d);
      });
    } catch (e) {
      console.error(e);
      etat.erreur = "lecture";
    }
    montrer();
  });

  window.PepitesCompte.connecter = () => A.signInWithPopup(auth, new A.GoogleAuthProvider()).catch((e) => {
    if (e && (e.code === "auth/popup-closed-by-user" || e.code === "auth/cancelled-popup-request")) return;
    console.error(e);
    etat.erreur = e && e.code === "auth/popup-blocked" ? "fenetre" : "connexion";
    montrer();
  });
  window.PepitesCompte.deconnecter = () => A.signOut(auth);
}

if (CONFIG) {
  demarrer().catch((e) => { console.error(e); etat.pret = true; etat.erreur = "chargement"; montrer(); });
}
