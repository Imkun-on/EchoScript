/* I modelli delle due postazioni, «Locale» e «Cloud», e la chiave di Groq.
 *
 * E' la decisione piu' importante del programma — dove finisce l'audio, quanto
 * costa, quanto si aspetta — e non si prende con un interruttore: si prende
 * entrando in una delle due sezioni e lavorando li' dentro. Quale sia in uso lo
 * decide ``cambiaSezione`` in app.js; qui si riempiono i menu di ciascuna e si
 * tiene la targhetta della barra allineata.
 *
 * Le due terne di modelli fanno gli stessi tre mestieri — trascrizione,
 * riassunto e traduzione, analisi visiva — e non si mescolano mai: sotto
 * «Locale» solo modelli che girano su questo computer, sotto «Cloud» solo
 * modelli che girano sui server Groq, piu' la chiave che li paga. Non li mescola
 * nemmeno il codice qui sotto: due elenchi di menu, due pannelli distinti.
 *
 * I cataloghi li manda Python: e' Python a sapere quali modelli esistono e
 * quali sono gia' scaricati in Ollama. Qui si riempiono i menu e si ricorda a
 * Python cosa e' stato scelto.
 */

/* Menu -> scelta, divisi per mondo. Sono la stessa cosa per il codice che li
 * riempie, ma tenerli in due elenchi e' cio' che rende visibile — leggendo, non
 * ricordando — che nessun modello locale finisce nella sezione Cloud. */
const MENU_LOCALI = [['#m-whisper', 'whisper'], ['#m-ollama', 'ollama'],
                     ['#m-vision', 'vision']];
const MENU_GROQ = [['#m-groq', 'groq'], ['#m-groq-testo', 'groq_testo'],
                   ['#m-groq-vista', 'groq_vista']];
const MENU = MENU_LOCALI.concat(MENU_GROQ);

let MODELLI = {};
let CHIAVE = { presente: false, nome: '' };

function initMotore(dati) {
  MODELLI = dati.modelli || {};
  riempiMenu();
  mostraChiave(dati.chiave);

  sincronizzaMotore();

  // Ogni menu scrive la sua scelta e basta: la stima si aggiorna da se',
  // perche' salvaScelte() la richiede a Python e la rimette a schermo.
  MENU.forEach(([sel, chiave]) => {
    $(sel).addEventListener('change', (e) => salvaScelte({ [chiave]: e.target.value }));
  });

  $('#carica-chiave').addEventListener('click', caricaChiave);
  $('#ottieni-chiave').addEventListener('click',
    () => window.pywebview.api.apri_url('https://console.groq.com/keys'));
}

/* ── I menu dei modelli ───────────────────────────────────────────────────── */

/* Ogni voce arriva da Python come {valore, nome, chiave}: 'nome' e' la parte
 * che Python sa e la pagina no (il nome del modello, la RAM, il ✓ di gia'
 * scaricato), 'chiave' e' la descrizione da tradurre. Tenerle separate e'
 * quello che permette di cambiare lingua senza richiedere i cataloghi. */
function riempiMenu() {
  MENU.forEach(([sel, chiave]) => {
    const select = $(sel);
    const voci = MODELLI[chiave] || [];
    const scelto = scelte()[chiave];
    select.innerHTML = '';
    voci.forEach((v) => {
      const opzione = document.createElement('option');
      opzione.value = v.valore;
      opzione.textContent = etichetta(v);
      select.appendChild(opzione);
    });
    // Il valore scelto potrebbe non essere fra le voci (un modello tolto dal
    // catalogo, un .env cambiato): in quel caso vince la prima, che esiste.
    if (voci.some((v) => v.valore === scelto)) select.value = scelto;
    else if (voci.length) salvaScelte({ [chiave]: select.value });
  });
}

function etichetta(voce) {
  const desc = voce.chiave ? t(voce.chiave) : '';
  if (voce.nome && desc) return voce.nome + ' · ' + desc;
  return voce.nome || desc || voce.valore;
}

/* I ✓ dei modelli gia' scaricati arrivano in ritardo — Python interroga Ollama
 * in sottofondo e resta muto se e' spento — quindi i menu si riscrivono quando
 * arrivano, senza che nessuno debba aspettarli. */
window.aggiornaModelli = (modelli) => {
  MODELLI = modelli || MODELLI;
  riempiMenu();
};

/* ── Quale delle due sta lavorando ────────────────────────────────────────── */

/* Le targhette nella barra laterale dicono con quale motore si sta per partire
 * senza dover entrare da nessuna parte: e' l'informazione che si vuole piu'
 * spesso, e la si vuole mentre si sta guardando altro. Una sola delle due porta
 * il segno, cosi' l'occhio non deve confrontare due parole per sapere quale
 * conta. */
function sincronizzaMotore() {
  const motore = scelte().motore;
  targhetta('#targhetta-locale', motore === 'local', 'locale', 'eng.tag.offline');
  targhetta('#targhetta-cloud', motore === 'groq', 'cloud', 'eng.tag.cloud');
}

function targhetta(sel, acceso, tono, chiave) {
  const segno = $(sel);
  segno.className = 'targhetta-menu' + (acceso ? ' ' + tono : ' spenta');
  segno.textContent = acceso ? t(chiave) : '';
}

/* ── La chiave Groq ───────────────────────────────────────────────────────── */

async function caricaChiave() {
  const esito = await window.pywebview.api.scegli_chiave();
  if (!esito.ok) { errore(esito.errore); return; }
  mostraChiave(esito.chiave);
  if (window.aggiornaAvvio) window.aggiornaAvvio();
}

function mostraChiave(chiave) {
  CHIAVE = chiave || { presente: false, nome: '' };
  const riga = $('#stato-chiave');
  riga.className = 'stato-chiave' + (CHIAVE.presente ? ' presente' : '');
  riga.textContent = CHIAVE.presente
    ? t('eng.key.loaded', { nome: CHIAVE.nome })
    : t('eng.key.none');
}

/* ── Cambio lingua ────────────────────────────────────────────────────────── */

/* Le voci dei menu e la riga della chiave non hanno un data-t: sono composte
 * qui mettendo insieme un pezzo che viene da Python e uno tradotto. Vanno
 * quindi riscritte a mano, ed e' l'unico motivo per cui questa funzione esiste. */
function traduciMotore() {
  riempiMenu();
  mostraChiave(CHIAVE);
  sincronizzaMotore();
}

window.initMotore = initMotore;
window.traduciMotore = traduciMotore;
window.sincronizzaMotore = sincronizzaMotore;
window.chiaveCaricata = () => CHIAVE.presente;
