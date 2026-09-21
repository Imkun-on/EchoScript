/* I riquadri di una postazione: modelli, chiave, video.
 *
 * Cosa sono
 *     Le cose da sapere prima di poter cominciare, in questa stanza. Ogni
 *     riquadro mostra COSA si e' scelto, e un pulsante per cambiarlo; il come
 *     si cambia sta in una finestra che si apre solo quando serve.
 *
 *     In «Cloud» sono tre, in «Locale» due: li' la chiave non c'e' proprio,
 *     perche' non si paga niente, e i due che restano si allargano a riempire
 *     lo spazio. La griglia conta i riquadri che ci sono, non quanti
 *     potrebbero essercene.
 *
 * Perche' il contenuto delle finestre non si costruisce al momento
 *     Perche' esiste gia'. I menu dei modelli li riempie Python all'avvio, e
 *     chi ascolta i loro cambiamenti e' gia' attaccato a QUEGLI elementi.
 *     Ricostruirli a ogni apertura vorrebbe dire riattaccare ogni volta tutti
 *     gli ascoltatori e ricordarsi quale valore era selezionato: due cose che
 *     si possono dimenticare, e che non danno errore quando si dimenticano.
 *
 *     Quindi gli elementi vivono in un magazzino nascosto dentro la
 *     postazione. Aprendo una finestra ci vengono spostati dentro, e alla
 *     chiusura tornano a casa. Sono sempre gli stessi oggetti: si portano
 *     dietro stato e collegamenti senza che nessuno ci pensi.
 *
 * I magazzini sono due, uno per stanza
 *     Ed e' il motivo per cui riporta() ha bisogno di sapere a chi restituire.
 *     Rimettere il modulo dei modelli di «Cloud» nel magazzino di «Locale»
 *     sarebbe come rimettere a posto un attrezzo nel cassetto del vicino: non
 *     da' nessun errore, e la volta dopo non lo si trova piu'.
 *
 * La regola da non violare
 *     Ogni blocco spostato DEVE tornare nel suo magazzino alla chiusura. La
 *     finestra e' una sola per tutto il programma e riempirla svuota quello che
 *     conteneva prima: un blocco rimasto dentro verrebbe distrutto, e da quel
 *     momento i menu dei modelli di quella stanza non esisterebbero piu'. Ci
 *     pensa riporta(), che la chiusura chiama sempre, e ci pensa anche
 *     finestra() stessa, che chiude quella aperta prima di svuotarla.
 */

/* Le voci del riepilogo dei modelli, per stanza: quale scelta mostrare e con
 * che etichetta. Sono gli stessi nomi che Python usa nelle scelte. */
const VOCI_MODELLI = {
  locale: [['whisper', 'eng.model.whisper'], ['ollama', 'eng.model.ollama'],
           ['vision', 'eng.model.vision']],
  cloud:  [['groq', 'eng.model.groq'], ['groq_testo', 'eng.model.groqtesto'],
           ['groq_vista', 'eng.model.groqvista']],
};

function initCarte(p) {
  p.q('apri-modelli').addEventListener('click', () => apriModelli(p));
  p.q('apri-video').addEventListener('click', () => apriVideo(p));
  aggiornaCarte(p);
}

/* ── Spostare i blocchi fra il magazzino e la finestra ────────────────────── */

function presta(p, nome) {
  const blocco = p.q(nome);
  blocco.dataset.prestato = p.dove;
  return blocco;
}

/* Rimette nel magazzino della sua stanza tutto quello che era stato prestato.
 *
 * Passa in rassegna la finestra invece di ricordarsi cosa aveva dato: cosi'
 * funziona anche se un giorno una finestra prendesse due blocchi, e soprattutto
 * non c'e' niente da tenere allineato fra chi presta e chi restituisce.
 *
 * A quale magazzino tornare lo dice il blocco stesso, che se l'e' scritto
 * addosso nel momento in cui e' uscito. Chiederlo alla stanza che si sta
 * guardando sarebbe sbagliato: si puo' aprire una finestra e cambiare stanza
 * mentre e' aperta, e allora il blocco finirebbe nel magazzino dell'altra. */
function riporta() {
  $$('#finestra-corpo [data-prestato]').forEach((b) => {
    const casa = POSTI[b.dataset.prestato];
    delete b.dataset.prestato;
    if (casa) casa.q('magazzino').appendChild(b);
  });
}

/* ── La finestra dei modelli ──────────────────────────────────────────────── */

function apriModelli(p) {
  finestra({
    titolo: t(p.dove === 'cloud' ? 'fin.modelli.cloud' : 'fin.modelli.locale'),
    icona: 'cpu',
    corpo: [presta(p, p.dove === 'cloud' ? 'modulo-modelli-cloud'
                                         : 'modulo-modelli-locale')],
    // Un bottone solo, e dice «Fatto» e non «Salva»: le scelte sono gia' state
    // salvate nell'istante in cui si e' toccato un menu. Un bottone «Salva»
    // farebbe credere che annullando si torni indietro, e non e' cosi'.
    azioni: [{ testo: t('fin.fatto'), tono: 'pieno', icona: 'spunta' }],
    suChiusura: () => { riporta(); aggiornaCarte(p); },
  });
}

/* ── La finestra del video ────────────────────────────────────────────────── */

function apriVideo(p) {
  finestra({
    titolo: t('fin.video'),
    icona: 'video',
    corpo: [presta(p, 'modulo-video')],
    azioni: [{ testo: t('fin.fatto'), tono: 'pieno', icona: 'spunta' }],
    suChiusura: () => { riporta(); aggiornaCarte(p); },
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

function aggiornaCarte(p) {
  aggiornaCartaModelli(p);
  aggiornaCartaVideo(p);
}

function aggiornaCartaModelli(p) {
  const box = p.q('riepilogo-modelli');
  box.innerHTML = '';
  VOCI_MODELLI[p.dove].forEach(([chiave, etichetta]) => {
    box.appendChild(voce(t(etichetta), scelte()[chiave] || t('carta.vuoto')));
  });
}

/* Cosa si e' scelto di trascrivere IN QUESTA STANZA. Finche' non si e' scelto
 * niente, la riga dice «nessuna sorgente» invece di restare vuota: una riga
 * vuota si legge come un difetto, una riga che dice di essere vuota si legge
 * come uno stato. */
function aggiornaCartaVideo(p) {
  const box = p.q('riepilogo-video');
  box.innerHTML = '';
  const youtube = p.opz.sorgente !== 'local';
  const valore = youtube ? p.q('url').value.trim() : p.q('file').value.trim();
  box.appendChild(voce(t('src.label'), t(youtube ? 'src.youtube' : 'src.local')));
  box.appendChild(voce(t(youtube ? 'src.input.url' : 'src.input.file'),
                       valore || t('carta.vuoto')));

  // Gli output aggiuntivi si elencano solo quando ce n'e' almeno uno acceso:
  // una riga che dice «nessuno» occuperebbe spazio per dire che non c'e'
  // niente da dire.
  const attivi = [['translate', 'opt.translate'], ['summarize', 'opt.summary'],
                  ['visual', 'opt.visual']]
    .filter(([k]) => p.opz[k]).map(([, k]) => t(k));
  if (attivi.length) box.appendChild(voce(t('opts.title'), attivi.join(' · ')));
}

window.initCarte = initCarte;
window.aggiornaCarte = aggiornaCarte;
// La usa il riepilogo finale, per il pulsante «Trascrivi un altro video».
window.apriVideoDaFuori = apriVideo;
