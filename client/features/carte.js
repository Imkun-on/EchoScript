/* I tre riquadri: modelli, chiave, video.
 *
 * Cosa sono
 *     Le tre cose da sapere prima di poter cominciare. Ogni riquadro mostra
 *     COSA si e' scelto, e un pulsante per cambiarlo; il come si cambia sta in
 *     una finestra che si apre solo quando serve.
 *
 * Perche' il contenuto delle finestre non si costruisce al momento
 *     Perche' esiste gia'. I menu dei modelli li riempie Python all'avvio, e
 *     chi ascolta i loro cambiamenti e' gia' attaccato a QUEGLI elementi.
 *     Ricostruirli a ogni apertura vorrebbe dire riattaccare ogni volta tutti
 *     gli ascoltatori e ricordarsi quale valore era selezionato: due cose che
 *     si possono dimenticare, e che non danno errore quando si dimenticano.
 *
 *     Quindi gli elementi vivono in un magazzino nascosto dentro la pagina.
 *     Aprendo una finestra ci vengono spostati dentro, e alla chiusura tornano
 *     a casa. Sono sempre gli stessi oggetti: si portano dietro stato e
 *     collegamenti senza che nessuno ci pensi.
 *
 * La regola da non violare
 *     Ogni blocco spostato DEVE tornare nel magazzino alla chiusura. La
 *     finestra e' una sola e riempirla svuota quello che conteneva prima: se
 *     un blocco fosse ancora li' dentro nel momento in cui si apre un'altra
 *     finestra, verrebbe distrutto, e da quel momento i menu dei modelli non
 *     esisterebbero piu'. Ci pensa riporta(), chiamata dalla chiusura.
 */

/* Quale riquadro dei modelli serve, a seconda di dove si sta lavorando.
 * Si guarda il motore e non la sezione aperta perche' e' il motore a decidere
 * quali modelli verranno davvero usati. */
const MODULO_MODELLI = { local: '#modulo-modelli-locale', groq: '#modulo-modelli-cloud' };

/* Le tre voci del riepilogo dei modelli, per motore: quale scelta mostrare e
 * con che etichetta. Sono gli stessi nomi che Python usa nelle scelte. */
const VOCI_MODELLI = {
  local: [['whisper', 'eng.model.whisper'], ['ollama', 'eng.model.ollama'],
          ['vision', 'eng.model.vision']],
  groq: [['groq', 'eng.model.groq'], ['groq_testo', 'eng.model.groqtesto'],
         ['groq_vista', 'eng.model.groqvista']],
};

function initCarte() {
  $('#apri-modelli').addEventListener('click', apriModelli);
  $('#apri-video').addEventListener('click', apriVideo);
  aggiornaCarte();
}

/* ── Spostare i blocchi fra il magazzino e la finestra ────────────────────── */

function presta(selettore) {
  const blocco = $(selettore);
  blocco.dataset.prestato = '1';
  return blocco;
}

/* Rimette nel magazzino tutto quello che era stato prestato.
 *
 * Passa in rassegna la finestra invece di ricordarsi cosa aveva dato: cosi'
 * funziona anche se un giorno una finestra prendesse due blocchi, e soprattutto
 * non c'e' niente da tenere allineato fra chi presta e chi restituisce. */
function riporta() {
  const magazzino = $('#magazzino');
  $$('#finestra-corpo [data-prestato]').forEach((b) => {
    delete b.dataset.prestato;
    magazzino.appendChild(b);
  });
}

/* ── La finestra dei modelli ──────────────────────────────────────────────── */

function apriModelli() {
  const motore = scelte().motore === 'groq' ? 'groq' : 'local';
  finestra({
    titolo: t(motore === 'groq' ? 'fin.modelli.cloud' : 'fin.modelli.locale'),
    icona: 'cpu',
    corpo: [presta(MODULO_MODELLI[motore])],
    // Un bottone solo, e dice «Fatto» e non «Salva»: le scelte sono gia' state
    // salvate nell'istante in cui si e' toccato un menu. Un bottone «Salva»
    // farebbe credere che annullando si torni indietro, e non e' cosi'.
    azioni: [{ testo: t('fin.fatto'), tono: 'pieno', icona: 'spunta' }],
    suChiusura: () => { riporta(); aggiornaCarte(); },
  });
}

/* ── La finestra del video ────────────────────────────────────────────────── */

function apriVideo() {
  finestra({
    titolo: t('fin.video'),
    icona: 'video',
    corpo: [presta('#modulo-video')],
    azioni: [{ testo: t('fin.fatto'), tono: 'pieno', icona: 'spunta' }],
    suChiusura: () => { riporta(); aggiornaCarte(); },
  });
}

/* ── I riepiloghi ─────────────────────────────────────────────────────────── */

/* Una riga del riepilogo: a cosa serve, e cosa si e' scelto. */
function voce(chi, cosa) {
  const riga = el('div', 'carta-voce');
  riga.appendChild(el('div', 'chi', chi));
  riga.appendChild(el('div', 'cosa', cosa));
  return riga;
}

function aggiornaCarte() {
  aggiornaCartaModelli();
  aggiornaCartaChiave();
  aggiornaCartaVideo();
}

function aggiornaCartaModelli() {
  const motore = scelte().motore === 'groq' ? 'groq' : 'local';
  const box = $('#riepilogo-modelli');
  box.innerHTML = '';
  VOCI_MODELLI[motore].forEach(([chiave, etichetta]) => {
    box.appendChild(voce(t(etichetta), scelte()[chiave] || t('carta.vuoto')));
  });
}

/* La chiave serve solo in nuvola, e in locale il suo riquadro sparisce.
 *
 * Prima restava al suo posto, spento, con scritto perche' non serviva. Provato
 * a schermo e' risultato peggio: e' un terzo di larghezza occupato per dire
 * che li' non c'e' niente da fare, in una sezione che di suo non ha nessun
 * rapporto con Groq. Chi lavora in locale una chiave non ce l'ha e non deve
 * nemmeno pensarci.
 *
 * I due riquadri che restano si allargano da soli per riempire lo spazio: la
 * griglia conta i riquadri che ci sono, non quanti potrebbero essercene. */
function aggiornaCartaChiave() {
  $('#carta-chiave').hidden = scelte().motore !== 'groq';
}

/* Cosa si e' scelto di trascrivere. Finche' non si e' scelto niente, la riga
 * dice «nessuna sorgente» invece di restare vuota: una riga vuota si legge
 * come un difetto, una riga che dice di essere vuota si legge come uno stato. */
function aggiornaCartaVideo() {
  const box = $('#riepilogo-video');
  box.innerHTML = '';
  const youtube = scelte().sorgente !== 'local';
  const valore = youtube ? $('#url').value.trim() : $('#file').value.trim();
  box.appendChild(voce(t('src.label'),
                       t(youtube ? 'src.youtube' : 'src.local')));
  box.appendChild(voce(t(youtube ? 'src.input.url' : 'src.input.file'),
                       valore || t('carta.vuoto')));

  // Gli output aggiuntivi si elencano solo quando ce n'e' almeno uno acceso:
  // una riga che dice «nessuno» occuperebbe spazio per dire che non c'e'
  // niente da dire.
  const attivi = [['translate', 'opt.translate'], ['summarize', 'opt.summary'],
                  ['visual', 'opt.visual']]
    .filter(([k]) => scelte()[k]).map(([, k]) => t(k));
  if (attivi.length) box.appendChild(voce(t('opts.title'), attivi.join(' · ')));
}

window.initCarte = initCarte;
window.aggiornaCarte = aggiornaCarte;
// La usa il riepilogo finale, per il pulsante «Trascrivi un altro video».
window.apriVideoDaFuori = apriVideo;
