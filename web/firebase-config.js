/* Réglages Firebase pour retrouver ses favoris sur tous ses appareils (synchro.js).
   null : pas de synchronisation, les favoris restent dans le navigateur.
   Ces clés ne sont pas secrètes (elles sont faites pour être publiques) : ce sont les règles
   Firestore qui protègent les données, chaque personne ne lit et n'écrit que son document.
   Projet Firebase « pepites-d0854 » (console.firebase.google.com). */
window.PEPITES_FIREBASE = {
  apiKey: "AIzaSyADOQPZmbl7VD6HiLSzyE-E-SSLroRth4E",
  authDomain: "pepites-d0854.firebaseapp.com",
  projectId: "pepites-d0854",
  storageBucket: "pepites-d0854.firebasestorage.app",
  messagingSenderId: "288791354364",
  appId: "1:288791354364:web:ae6bbe1fb75f7489787079",
};
