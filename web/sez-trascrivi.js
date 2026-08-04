/* Sezione «Trascrivi»: la sorgente, gli output aggiuntivi, il lavoro.
 *
 * Il filo del discorso, in ordine:
 *
 *   1. si dice cosa trascrivere (un link, o un file) e si preme «Guarda cos'e'»;
 *   2. Python legge i metadati e la pagina chiede conferma — con la copertina,
 *      i dati e la stima davanti: e' l'unico momento in cui ci si accorge di
 *      aver incollato il link sbagliato PRIMA di spendere crediti;
 *   3. confermato, la scheda resta nella colonna di sinistra;
 *   4. «Trascrivi» chiede a Python se ci sono ostacoli — manca la chiave, il
 *      video c'e' gia', esiste un parziale — e a seconda della risposta parte o
 *      apre una finestra di scelte;
 *   5. mentre lavora parlano l'avanzamento e il diario;
 *   6. alla fine una finestra dice cosa e' stato scritto e dove.
 *
 * Nessuno di questi passaggi decide qualcosa: le domande le pone Python, che e'
 * l'unico a sapere cosa c'e' gia' sul disco.
 */

/* L'ultima scheda ricevuta. Serve a ridisegnarla quando cambia la lingua: le
 * etichette («Canale», «Durata») sono chiavi di traduzione, i valori no. */
let SCHEDA = null;

function initTrascrivi(dati) {
  // Gli interruttori partono da come erano l'ultima volta: sono scelte che si
  // fanno una volta e si tengono, non decisioni da ripetere a ogni video.
  const s = scelte();
  $('#opt-translate').checked = !!s.translate;
  $('#opt-summarize').checked = !!s.summarize;
  $('#opt-visual').checked = !!s.visual;
  [['#opt-translate', 'translate'], ['#opt-summarize', 'summarize'],
   ['#opt-visual', 'visual']].forEach(([sel, chiave]) => {
    $(sel).addEventListener('change', (e) => salvaScelte({ [chiave]: e.target.checked }));
  });

  $('#sorgente').value = s.sorgente || 'youtube';
  $('#sorgente').addEventListener('change', (e) => {
    salvaScelte({ sorgente: e.target.value });
    sincronizzaSorgente();
    dimentica();
  });
  sincronizzaSorgente();

  // Cambiare l'URL invalida la conferma precedente: e' il modo piu' facile di
  // trascrivere il video sbagliato, e con Groq costa anche crediti.
  $('#url').addEventListener('input', dimentica);
  $('#url').addEventListener('keydown', (e) => { if (e.key === 'Enter') leggiSorgente(); });

  $('#leggi').addEventListener('click', leggiSorgente);
  $('#sfoglia').addEventListener('click', scegliFile);
  $('#avvia').addEventListener('click', premiAvvia);

  svuotaScheda();
  aggiornaAvvio();
}

/* I due ingressi occupano lo stesso posto: si vede solo quello della sorgente
 * scelta, e il bottone «Guarda cos'e'» ha senso solo per un link — un file lo
 * si e' gia' visto scegliendolo. */
function sincronizzaSorgente() {
  const youtube = scelte().sorgente === 'youtube';
  $('#ingresso-youtube').hidden = !youtube;
  $('#ingresso-file').hidden = youtube;
  $('#leggi').style.display = youtube ? '' : 'none';
}

/* ── La scheda della sorgente ─────────────────────────────────────────────── */

function mostraScheda(scheda) {
  SCHEDA = scheda;
  const box = $('#sorgente-scheda');
  box.innerHTML = '';
  box.appendChild(disegnaScheda(scheda, false));
  mostraStima(scheda.stima);
  aggiornaAvvio();
}

/* La stessa scheda serve nella colonna e dentro la finestra di conferma:
 * costruirla una volta sola e' cio' che garantisce che quello che si conferma
 * sia esattamente quello che poi si vede. */
function disegnaScheda(scheda, dentroFinestra) {
  const box = el('div', 'scheda-sorgente');

  const copertina = el('div', 'scheda-copertina');
  if (scheda.miniatura) {
    // L'immagine si aggiunge solo se arriva davvero: un riquadro con l'icona
    // rotta sarebbe peggio del riquadro vuoto.
    const img = new Image();
    img.alt = '';
    img.onload = () => { copertina.innerHTML = ''; copertina.appendChild(img); };
    img.src = scheda.miniatura;
    copertina.appendChild(icona(scheda.tipo === 'file' ? 'i-file-audio' : 'i-video'));
  } else {
    copertina.appendChild(icona(scheda.tipo === 'file' ? 'i-file-audio' : 'i-video'));
  }
  box.appendChild(copertina);

  box.appendChild(el('div', 'scheda-nome', scheda.titolo));
  box.appendChild(righeDati((scheda.righe || []).map(
    (r) => ({ nome: t(r.chiave), valore: r.valore }))));

  // La stima dentro la finestra sta nel corpo, perche' li' e' il numero su cui
  // si decide; nella colonna sta invece nella riga del titolo, dove si vede
  // anche mentre si guarda altro.
  if (dentroFinestra && scheda.stima) {
    const targhetta = el('span', 'targhetta', scheda.stima);
    const riga = el('div', '');
    riga.appendChild(targhetta);
    box.appendChild(riga);
  }

  if (scheda.voci && scheda.voci.length) {
    const elenco = el('div', 'elenco-video');
    scheda.voci.forEach((v, i) => {
      const riga = el('div', 'riga-video');
      riga.appendChild(el('span', 'numero', String(i + 1).padStart(2, '0')));
      riga.appendChild(el('span', 'titolo', v.titolo));
      riga.appendChild(el('span', 'durata', v.durata || ''));
      elenco.appendChild(riga);
    });
    box.appendChild(elenco);
  }
  return box;
}

function svuotaScheda() {
  SCHEDA = null;
  const box = $('#sorgente-scheda');
  box.innerHTML = '';
  box.appendChild(statoVuoto(t('src.empty')));
  mostraStima('');
}

function mostraStima(testo) {
  const targhetta = $('#stima');
  targhetta.textContent = testo || '';
  targhetta.style.display = testo ? '' : 'none';
}

async function dimentica() {
  if (!SCHEDA) return;
  await window.pywebview.api.dimentica();
  svuotaScheda();
  aggiornaAvvio();
}

/* ── Leggere la sorgente ──────────────────────────────────────────────────── */

async function leggiSorgente() {
  const bottone = $('#leggi');
  const etichetta = bottone.querySelector('span');
  etichetta.textContent = t('src.load.loading');
  bottone.disabled = true;
  const esito = await window.pywebview.api.carica_info($('#url').value);
  if (!esito.ok) { finiscoLettura(); errore(esito.errore); }
}

/* Su una playlist si sta parecchio: ogni video va letto uno per uno. Dirlo e'
 * la differenza fra un'attesa e un sospetto di blocco. */
window.caricamentoPlaylist = () => {
  $('#leggi').querySelector('span').textContent = t('src.load.playlist');
};

function finiscoLettura() {
  const bottone = $('#leggi');
  bottone.querySelector('span').textContent = t('src.load');
  bottone.disabled = false;
}

window.erroreSorgente = (messaggio) => {
  finiscoLettura();
  errore(messaggio);
};

/* La conferma: copertina, dati, stima, e la domanda. Chiederla e' cio' che
 * evita di trascrivere il video sbagliato — che con Groq non e' solo tempo. */
window.chiediConferma = (scheda) => {
  finiscoLettura();
  const playlist = scheda.tipo === 'playlist';
  finestra({
    icona: playlist ? 'riassumi' : 'video',
    titolo: t(playlist ? 'playlist.title' : 'confirm.title'),
    corpo: [
      disegnaScheda(scheda, true),
      playlist ? t('playlist.question', { n: (scheda.voci || []).length })
               : t('confirm.question'),
    ],
    azioni: [
      { testo: t('comune.annulla'), tono: 'contorno', azione: () => dimentica() },
      { testo: t('comune.conferma'), tono: 'pieno', icona: 'spunta',
        azione: () => {
          mostraScheda(scheda);
          avvisa(playlist
            ? t('playlist.ok', { titolo: scheda.titolo, n: (scheda.voci || []).length })
            : t('confirm.ok', { titolo: scheda.titolo }), 'ok');
        } },
    ],
    // Chiudere con Esc e' come annullare: la sorgente non e' confermata, e
    // lasciarla valida sarebbe l'errore peggiore che questa finestra possa fare.
    suChiusura: () => { if (!SCHEDA) dimentica(); },
  });
};

async function scegliFile() {
  const esito = await window.pywebview.api.scegli_file();
  if (!esito.ok) { errore(esito.errore); return; }
  if (esito.annullato) return;
  $('#file').value = esito.scheda.titolo;
  mostraScheda(esito.scheda);
}

/* Un link trascinato dentro la finestra vale come un link incollato. Un file
 * trascinato no: il percorso che il browser espone non e' quello vero del
 * disco, e aprirlo fallirebbe in silenzio — meglio dire di usare «Sfoglia». */
window.accettaTrascinato = (testo) => {
  if (!/^https?:/i.test(testo)) { avvisa(t('err.no_url'), 'fail'); return; }
  $('#sorgente').value = 'youtube';
  salvaScelte({ sorgente: 'youtube' });
  sincronizzaSorgente();
  $('#url').value = testo;
  leggiSorgente();
};

/* ── Avviare ──────────────────────────────────────────────────────────────── */

/* Il bottone si accende solo quando si puo' davvero partire. Resta comunque
 * cliccabile quando non si puo': premendolo si scopre cosa manca, che e' piu'
 * utile di un bottone spento che non spiega perche'. */
function aggiornaAvvio() {
  const pronto = !!SCHEDA && (scelte().motore !== 'groq' || window.chiaveCaricata());
  $('#avvia').style.opacity = pronto ? '1' : '.55';
}

async function premiAvvia() {
  const esito = await window.pywebview.api.prepara();
  if (!esito.ok) { errore(esito.errore); return; }

  if (esito.stato === 'manca') {
    const elenco = el('div', 'passi');
    esito.voci.forEach((v) => {
      const passo = el('span', 'passo');
      passo.appendChild(el('span', 'pallino'));
      passo.appendChild(el('span', '', v));
      elenco.appendChild(passo);
    });
    finestra({
      icona: 'avviso', tono: 'attenzione', titolo: t('warn.title'),
      corpo: [t('warn.prefix'), elenco],
      azioni: [{ testo: t('comune.chiudi'), tono: 'pieno', icona: 'spunta' }],
    });
    return;
  }

  if (esito.stato === 'gia' || esito.stato === 'ripresa') {
    finestra({
      icona: esito.stato === 'gia' ? 'riassumi' : 'clessidra',
      titolo: esito.titolo,
      corpo: [esito.desc, ...esito.voci.map(
        (v) => voceScelta(v, (scelta) => window.pywebview.api.esegui(scelta.azione)))],
      azioni: [{ testo: t('comune.annulla'), tono: 'contorno' }],
    });
    return;
  }

  window.pywebview.api.esegui('nuova');
}

function riabilitaTrascrivi() {
  sincronizzaSorgente();
  aggiornaAvvio();
}

/* ── Il risultato ─────────────────────────────────────────────────────────── */

window.mostraRisultato = (res) => {
  const corpo = [];

  if (res.miniatura) {
    const copertina = el('div', 'scheda-copertina');
    const img = new Image();
    img.alt = '';
    img.onload = () => { copertina.innerHTML = ''; copertina.appendChild(img); };
    img.src = res.miniatura;
    copertina.appendChild(icona('i-video'));
    corpo.push(copertina);
  }

  (res.avvisi || []).forEach((a) => corpo.push(el('div', 'avviso-riquadro', '⚠ ' + a)));

  corpo.push(righeDati((res.dati || []).map(
    (d) => ({ nome: t(d.chiave), valore: d.valore }))));
  corpo.push(riquadroPercorso(t('res.saved'), res.cartella));

  (res.gruppi || []).forEach((g) => {
    const box = el('div', 'gruppo-file');
    const testa = el('div', 'cartella');
    testa.appendChild(icona('i-cartella'));
    testa.appendChild(el('span', '', g.cartella));
    box.appendChild(testa);
    g.file.forEach((n) => box.appendChild(el('div', 'nome-file', n)));
    corpo.push(box);
  });

  if (res.crediti && res.crediti.length) {
    corpo.push(el('div', 'etichetta', t('res.credits')));
    corpo.push(righeDati(res.crediti.map(
      (c) => ({ nome: t(c.chiave), valore: c.valore }))));
  }

  // L'analisi visiva produce un documento a parte: dirlo e basta, senza un
  // modo di aprirlo, vorrebbe dire farlo cercare a mano fra le sottocartelle.
  if (res.visiva) {
    const blocco = el('div', 'blocco-visiva');
    blocco.appendChild(icona('i-occhio'));
    const testo = el('div', 'testo');
    testo.appendChild(el('div', 'titolo', t('res.visual')));
    testo.appendChild(el('div', 'desc', t('res.visual.count', { n: res.visiva.n })));
    blocco.appendChild(testo);
    const bottone = el('button', 'bottone contorno');
    bottone.appendChild(el('span', '', t('res.visual.open')));
    bottone.addEventListener('click', () => window.pywebview.api.apri('visiva'));
    blocco.appendChild(bottone);
    corpo.push(blocco);
  }

  finestra({
    icona: 'spunta', tono: 'riuscito', titolo: res.titolo, corpo,
    azioni: [
      // Non chiude: si apre la cartella e si torna a guardare il riepilogo.
      { testo: t('res.open'), tono: 'contorno', icona: 'cartella', chiudi: false,
        azione: () => window.pywebview.api.apri('cartella') },
      { testo: t('comune.chiudi'), tono: 'pieno', icona: 'spunta' },
    ],
  });
};

window.mostraRisultatoPlaylist = (res) => {
  const corpo = [];
  if (res.avviso) corpo.push(el('div', 'avviso-riquadro', '⚠ ' + res.avviso));

  const conteggi = el('div', 'conteggi');
  (res.conteggi || []).filter(Boolean).forEach((c) => {
    const voce = el('span', 'conteggio ' + c.tono);
    voce.appendChild(el('span', 'pallino'));
    voce.appendChild(el('span', '', c.testo));
    conteggi.appendChild(voce);
  });
  corpo.push(conteggi);
  corpo.push(riquadroPercorso(t('playlist.res.folder'), res.cartella));

  if ((res.voci || []).length) {
    const elenco = el('div', 'elenco-video');
    res.voci.forEach((v) => {
      const riga = el('div', 'riga-video ' + v.tono);
      riga.appendChild(el('span', 'titolo', v.titolo));
      elenco.appendChild(riga);
    });
    corpo.push(elenco);
  }

  finestra({
    icona: 'spunta', tono: 'riuscito', titolo: res.titolo, corpo,
    azioni: [
      { testo: t('res.open'), tono: 'contorno', icona: 'cartella', chiudi: false,
        azione: () => window.pywebview.api.apri('cartella') },
      { testo: t('comune.chiudi'), tono: 'pieno', icona: 'spunta' },
    ],
  });
};

/* ── Quando Groq finisce i crediti ────────────────────────────────────────── */

/* Non e' un errore, ed e' per questo che non e' rosso: non si e' rotto niente,
 * il parziale e' salvato, e ci sono due modi veri di proseguire. */
window.creditiFiniti = (dati) => {
  const azioni = [{ testo: t('rate.later'), tono: 'contorno', icona: 'clessidra' }];
  if (dati.puo_locale) {
    azioni.push({ testo: t('rate.local'), tono: 'ambra', icona: 'casa',
                  azione: () => window.pywebview.api.continua_in_locale() });
  }
  finestra({
    icona: 'clessidra', tono: 'attenzione', titolo: dati.titolo,
    corpo: [dati.testo], azioni,
  });
};

/* Il riassunto si e' fermato a meta' per gli stessi crediti. La trascrizione
 * pero' e' salva, quindi la scelta e' solo su come finire il riassunto: adesso
 * in locale, o piu' tardi. In ogni caso il risultato si vede. */
window.riassuntoInterrotto = (res) => {
  finestra({
    icona: 'clessidra', tono: 'attenzione', titolo: t('sumlocal.title'),
    corpo: [t('sumlocal.msg')],
    azioni: [
      { testo: t('sumlocal.no'), tono: 'contorno',
        azione: () => window.mostraRisultato(res) },
      { testo: t('sumlocal.yes'), tono: 'ambra', icona: 'casa',
        azione: () => window.pywebview.api.concludi_in_locale() },
    ],
  });
};

/* ── Cambio lingua ────────────────────────────────────────────────────────── */

function traduciTrascrivi() {
  if (SCHEDA) mostraScheda(SCHEDA);
  else svuotaScheda();
  // La stima e' una frase composta da Python: gliela si richiede nella lingua
  // nuova invece di provare a tradurla qui, dove il numero non c'e'.
  salvaScelte({});
  sincronizzaSorgente();
}

window.initTrascrivi = initTrascrivi;
window.traduciTrascrivi = traduciTrascrivi;
window.riabilitaTrascrivi = riabilitaTrascrivi;
window.aggiornaAvvio = aggiornaAvvio;
window.mostraStima = mostraStima;
