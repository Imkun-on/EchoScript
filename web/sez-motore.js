/* Sezione «Motore»: chi fa il lavoro, e con quali modelli.
 *
 * E' la decisione piu' importante del programma — dove finisce l'audio, quanto
 * costa, quanto si aspetta — ed e' per questo che sta in una sezione sua invece
 * che in una riga della schermata principale: chi la prende la prende una volta
 * e poi non ci pensa piu', e chi vuole cambiarla vuole vedere le due opzioni
 * affiancate, non aprire una tendina.
 *
 * I cataloghi dei modelli li manda Python: e' Python a sapere quali esistono e
 * quali sono gia' scaricati in Ollama. Qui si riempiono i menu e si ricorda a
 * Python cosa e' stato scelto.
 */

let MODELLI = {};
let CHIAVE = { presente: false, nome: '' };

function initMotore(dati) {
  MODELLI = dati.modelli || {};
  riempiMenu();
  mostraChiave(dati.chiave);

  document.querySelectorAll('#scelta-motore .scelta').forEach((riquadro) => {
    riquadro.addEventListener('click', () => scegliMotore(riquadro.dataset.motore));
  });
  sincronizzaMotore();

  // Ogni menu scrive la sua scelta e basta: la stima si aggiorna da se',
  // perche' salvaScelte() la richiede a Python e la rimette a schermo.
  const menu = [['#m-whisper', 'whisper'], ['#m-ollama', 'ollama'],
                ['#m-vision', 'vision'], ['#m-groq', 'groq']];
  menu.forEach(([sel, chiave]) => {
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
  const menu = [['#m-whisper', 'whisper'], ['#m-ollama', 'ollama'],
                ['#m-vision', 'vision'], ['#m-groq', 'groq']];
  menu.forEach(([sel, chiave]) => {
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

/* ── La scelta del motore ─────────────────────────────────────────────────── */

function scegliMotore(quale) {
  salvaScelte({ motore: quale });
  sincronizzaMotore();
}

/* Un pannello per motore, e si vede solo quello che conta: con Groq i modelli
 * locali non servono, e senza chiave Groq non si va da nessuna parte. Mostrarli
 * entrambi sempre vorrebbe dire far leggere ogni volta meta' schermata che non
 * riguarda la scelta fatta. */
function sincronizzaMotore() {
  const motore = scelte().motore;
  document.querySelectorAll('#scelta-motore .scelta').forEach((riquadro) => {
    riquadro.classList.toggle('attiva', riquadro.dataset.motore === motore);
  });
  $('#pannello-locale').style.display = motore === 'local' ? '' : 'none';
  $('#pannello-groq').style.display = motore === 'groq' ? '' : 'none';

  // La targhetta nella barra laterale dice quale motore e' scelto senza dover
  // entrare qui: e' l'informazione che si vuole piu' spesso, e la si vuole
  // mentre si sta guardando altro.
  const targhetta = $('#targhetta-motore');
  targhetta.className = 'targhetta-menu ' + (motore === 'groq' ? 'cloud' : 'locale');
  targhetta.textContent = t(motore === 'groq' ? 'eng.tag.cloud' : 'eng.tag.offline');
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
window.chiaveCaricata = () => CHIAVE.presente;
