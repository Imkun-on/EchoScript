/* I modelli di una postazione, e la chiave di Groq.
 *
 * Quale sia la decisione che si prende qui
 *     E' la piu' importante del programma: dove finisce l'audio, quanto costa,
 *     quanto si aspetta. E non si prende con un interruttore, si prende
 *     entrando in una delle due stanze e lavorando li' dentro. In «Locale»
 *     girano solo modelli che stanno su questo computer, in «Cloud» solo
 *     modelli che stanno sui server Groq, piu' la chiave che li paga.
 *
 * Perche' le due terne non si possono mescolare nemmeno per sbaglio
 *     Non e' piu' una promessa scritta nei commenti: e' come e' fatta la
 *     pagina. La postazione «Locale» contiene soltanto i tre menu locali,
 *     perche' gli altri tre le vengono tolti nel momento in cui viene
 *     costruita, e viceversa. Un modello di Groq dentro «Locale» non e'
 *     sconsigliato, non c'e' proprio.
 *
 * I cataloghi li manda Python: e' Python a sapere quali modelli esistono e
 * quali sono gia' scaricati in Ollama. Qui si riempiono i menu e si ricorda a
 * Python cosa e' stato scelto.
 */

/* Quali menu vivono in quale stanza. I nomi sono nudi, senza il prefisso della
 * postazione: ce lo mette p.q(), e chi scrive qui non deve pensarci. */
const MENU_DI = {
  locale: [['m-whisper', 'whisper'], ['m-ollama', 'ollama'], ['m-vision', 'vision']],
  cloud:  [['m-groq', 'groq'], ['m-groq-testo', 'groq_testo'],
           ['m-groq-vista', 'groq_vista']],
};

/* I cataloghi e la chiave sono del programma, non della postazione.
 *
 * I cataloghi perche' sono l'elenco di cosa esiste al mondo, ed e' lo stesso
 * elenco da qualunque stanza lo si guardi. La chiave perche' e' una sola
 * chiave: averne due copie vorrebbe dire solo poterle far divergere, e
 * scoprirlo nel momento in cui una delle due smette di pagare. */
let MODELLI = {};
let CHIAVE = { presente: false, nome: '' };

function initMotore(p, dati) {
  MODELLI = dati.modelli || MODELLI;
  riempiMenu(p);

  // Ogni menu scrive la sua scelta e basta: la stima si aggiorna da se',
  // perche' salvaScelte() la richiede a Python e la rimette a schermo.
  MENU_DI[p.dove].forEach(([nome, chiave]) => {
    p.q(nome).addEventListener('change',
      (e) => salvaScelte({ [chiave]: e.target.value }, p));
  });

  // La chiave esiste soltanto in «Cloud»: in «Locale» quei tre pezzi sono
  // stati tolti insieme al riquadro che li conteneva, e cercarli tornerebbe a
  // mani vuote. Si chiede se ci sono invece di dare per scontato in quale
  // stanza siamo, cosi' la riga resta vera anche il giorno in cui la chiave
  // dovesse servire altrove.
  if (p.q('carica-chiave')) {
    mostraChiave(p, dati.chiave);
    p.q('carica-chiave').addEventListener('click', () => caricaChiave(p));
    p.q('ottieni-chiave').addEventListener('click',
      () => window.pywebview.api.apri_url('https://console.groq.com/keys'));
  }
}

/* ── I menu dei modelli ───────────────────────────────────────────────────── */

/* Ogni voce arriva da Python come {valore, nome, chiave}: 'nome' e' la parte
 * che Python sa e la pagina no (il nome del modello, la RAM, il ✓ di gia'
 * scaricato), 'chiave' e' la descrizione da tradurre. */
function riempiMenu(p) {
  MENU_DI[p.dove].forEach(([nome, chiave]) => {
    const select = p.q(nome);
    if (!select) return;
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
    else if (voci.length) salvaScelte({ [chiave]: select.value }, p);
  });
}

function etichetta(voce) {
  const desc = voce.chiave ? t(voce.chiave) : '';
  if (voce.nome && desc) return voce.nome + ' · ' + desc;
  return voce.nome || desc || voce.valore;
}

/* I ✓ dei modelli gia' scaricati arrivano in ritardo, perche' Python interroga
 * Ollama in sottofondo e resta muto se e' spento. Quando arrivano, i menu si
 * riscrivono da soli, e li riscrivono tutte e due le postazioni: il catalogo e'
 * uno solo ma i menu che lo mostrano sono sei, divisi in due stanze.
 *
 * Questa non passa dallo smistamento perche' non appartiene a nessun lavoro:
 * e' una cosa che il programma viene a sapere, non una cosa che succede a una
 * trascrizione. */
window.aggiornaModelli = (modelli) => {
  MODELLI = modelli || MODELLI;
  Object.values(POSTI).forEach(riempiMenu);
  Object.values(POSTI).forEach((p) => { if (window.aggiornaCarte) window.aggiornaCarte(p); });
};

/* ── La chiave Groq ───────────────────────────────────────────────────────── */

async function caricaChiave(p) {
  const esito = await window.pywebview.api.scegli_chiave();
  if (!esito.ok) { erroreDi(p, esito.errore); return; }
  mostraChiave(p, esito.chiave);
  if (window.aggiornaAvvio) window.aggiornaAvvio(p);
  if (window.aggiornaCarte) window.aggiornaCarte(p);
}

function mostraChiave(p, chiave) {
  CHIAVE = chiave || CHIAVE;
  const riga = p.q('stato-chiave');
  if (!riga) return;
  riga.className = 'stato-chiave' + (CHIAVE.presente ? ' presente' : '');
  riga.textContent = CHIAVE.presente
    ? t('eng.key.loaded', { nome: CHIAVE.nome })
    : t('eng.key.none');
}

/* ── Riscrivere quello che non ha un data-t ───────────────────────────────── */

/* Le voci dei menu e la riga della chiave sono composte qui mettendo insieme un
 * pezzo che viene da Python e uno tradotto, quindi nessun data-t puo'
 * occuparsene e vanno riscritte a mano. E' l'unico motivo per cui questa
 * funzione esiste. */
function riempiMotore(p) {
  riempiMenu(p);
  mostraChiave(p, CHIAVE);
}

window.initMotore = initMotore;
window.riempiMotore = riempiMotore;
window.chiaveCaricata = () => CHIAVE.presente;
