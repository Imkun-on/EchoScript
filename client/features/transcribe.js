/* Il lavoro di una postazione: la sorgente, gli output aggiuntivi, la corsa.
 *
 * Il filo del discorso, in ordine:
 *
 *   1. si dice cosa trascrivere: un file, o un link (anche piu' d'uno), che
 *      si legge da solo appena incollato (o dopo un attimo di pausa mentre lo
 *      si scrive);
 *   2. Python legge i metadati e la pagina apre l'anteprima in una finestra,
 *      con la copertina, i dati e la stima davanti: e' l'unico momento in cui
 *      ci si accorge di aver incollato il link sbagliato PRIMA di spendere
 *      crediti;
 *   3. confermato, la scheda resta nel riquadro in fondo;
 *   4. «Trascrivi» chiede a Python se ci sono ostacoli (manca la chiave, il
 *      video c'e' gia', esiste un parziale) e a seconda della risposta parte o
 *      apre una finestra di scelte;
 *   5. mentre lavora parla l'avanzamento;
 *   6. alla fine una finestra dice cosa e' stato scritto e dove.
 *
 * Tutto questo succede DUE volte, una per stanza, e le due volte non si
 * toccano. Ogni funzione qui dentro riceve come primo argomento la postazione
 * di cui si sta occupando, e non esiste piu' nessun modo di scrivere una riga
 * che vada a prendere il pezzo sbagliato: non c'e' un «il link», c'e' «il link
 * di questa postazione».
 *
 * Nessuno di questi passaggi decide qualcosa: le domande le pone Python, che e'
 * l'unico a sapere cosa c'e' gia' sul disco.
 */

/* Gli interruttori degli output: l'id nella pagina e il nome della scelta
 * che Python ricorda. */
const INTERRUTTORI = [['opt-translate', 'translate'], ['opt-summarize', 'summarize'],
                      ['opt-charts', 'grafici'], ['opt-comments', 'commenti']];

function initTrascrivi(p) {
  // Gli interruttori partono da come erano l'ultima volta: sono scelte che si
  // fanno una volta e si tengono, non decisioni da ripetere a ogni video. Le
  // due stanze partono uguali e da qui in poi divergono.
  INTERRUTTORI.forEach(([nome, chiave]) => {
    p.q(nome).checked = !!p.opz[chiave];
    p.q(nome).addEventListener('change', (e) => {
      salvaScelte({ [chiave]: e.target.checked }, p);
      sincronizzaDipendenti(p);
      aggiornaCarte(p);
    });
  });
  // Quanto dettagliato il riassunto: esteso, normale, breve, punti chiave.
  p.q('opt-detail').value = p.opz.dettaglio || 'esteso';
  p.q('opt-detail').addEventListener('change', (e) => {
    salvaScelte({ dettaglio: e.target.value }, p);
    aggiornaCarte(p);
  });
  sincronizzaDipendenti(p);

  p.q('sorgente').value = p.opz.sorgente || 'youtube';
  p.q('sorgente').addEventListener('change', (e) => {
    salvaScelte({ sorgente: e.target.value }, p);
    sincronizzaSorgente(p);
    // Cambiare tipo di sorgente ricomincia da capo, ma non durante un lavoro:
    // li' serve solo a scegliere cosa mettere in coda, e il video che sta
    // girando non si tocca.
    if (!p.lavora()) dimentica(p, 'tutto');
  });
  sincronizzaSorgente(p);

  // Il link si legge da solo. Incollato, subito: e' un gesto finito. Scritto
  // a mano, dopo un attimo di pausa: leggere a ogni tasto vorrebbe dire
  // interrogare YouTube con mezzo indirizzo. Invio legge subito, anche lo
  // stesso link di prima: e' il modo di riprovare dopo un errore.
  //
  // Scrivere un link nuovo NON cancella piu' la sorgente confermata: la
  // conferma adesso e' esplicita, nell'anteprima, e l'anteprima chiede se
  // sostituirla o mettere il nuovo video in coda.
  p.q('url').addEventListener('input', () => programmaLettura(p, false));
  // Tanti link incollati insieme, uno per riga: la casella e' di una riga
  // sola e i ritorni a capo li butterebbe via, incollando i link uno
  // all'altro. Li si mette in fila separati da uno spazio, e diventano una coda.
  p.q('url').addEventListener('paste', (e) => {
    const incollato = ((e.clipboardData && e.clipboardData.getData('text')) || '').trim();
    if (/\s/.test(incollato)) {
      e.preventDefault();
      p.q('url').value = incollato.split(/\s+/).join(' ');
    }
    setTimeout(() => programmaLettura(p, true), 0);
  });
  p.q('url').addEventListener('keydown', (e) => {
    if (e.key !== 'Enter') return;
    p.ultimoLetto = null;
    programmaLettura(p, true);
  });

  p.q('sfoglia').addEventListener('click', () => scegliFile(p));
  p.q('avvia').addEventListener('click', () => premiAvvia(p));
  p.q('annulla').addEventListener('click', () => annullaLavoro(p));

  svuotaScheda(p);
  aggiornaAvvio(p);
}

/* Grafici e commenti sono aggiunte al riassunto: senza riassunto non c'e'
 * niente a cui aggiungerli. Restano visibili, grigi, con la loro spiegazione
 * sostituita da quello che serve per accenderli: un interruttore che sparisce
 * e ricompare farebbe ballare la finestra. */
function sincronizzaDipendenti(p) {
  const riassunto = p.q('opt-summarize').checked;
  [['opt-charts', 'opt.charts.desc'], ['opt-comments', 'opt.comments.desc']]
    .forEach(([nome, desc]) => {
      const input = p.q(nome);
      input.disabled = !riassunto || p.lavora();
      const riga = input.closest('.interruttore');
      riga.classList.toggle('spento', !riassunto);
      riga.querySelector('.interruttore-nota').textContent =
        t(riassunto ? desc : 'opt.needsummary');
    });
  // Anche la misura del riassunto: senza riassunto non misura niente.
  p.q('opt-detail').disabled = !riassunto || p.lavora();
  p.q('riga-dettaglio').classList.toggle('spento', !riassunto);
  if (window.aggiornaTendine) window.aggiornaTendine();
}

/* I due ingressi occupano lo stesso posto: si vede solo quello della sorgente
 * scelta. */
function sincronizzaSorgente(p) {
  const youtube = p.opz.sorgente !== 'local';
  p.q('ingresso-youtube').hidden = !youtube;
  p.q('ingresso-file').hidden = youtube;
  // Il menu della sorgente lo disegna la pagina: se qualcuno ha cambiato il
  // <select> da codice (un link trascinato dentro), il bottone mostrerebbe
  // ancora la voce di prima mentre la scelta vera e' gia' un'altra.
  if (window.aggiornaTendine) window.aggiornaTendine();
}

/* ── La scheda della sorgente ─────────────────────────────────────────────── */

function mostraScheda(p, scheda) {
  p.scheda = scheda;
  const box = p.q('sorgente-scheda');
  box.innerHTML = '';
  box.appendChild(disegnaScheda(scheda, false));
  mostraStima(p, scheda.stima);
  aggiornaAvvio(p);
  aggiornaCarte(p);
  aggiornaVoci();
}

/* La stessa scheda serve nel riquadro e dentro la finestra di conferma:
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
  // si decide; nel riquadro sta invece nella riga del titolo, dove si vede
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

function svuotaScheda(p) {
  p.scheda = null;
  const box = p.q('sorgente-scheda');
  box.innerHTML = '';
  box.appendChild(statoVuoto(t('src.empty')));
  mostraStima(p, '');
  aggiornaVoci();
}

function mostraStima(p, testo) {
  const targhetta = p.q('stima');
  targhetta.textContent = testo || '';
  targhetta.style.display = testo ? '' : 'none';
}

/* Lascia cadere qualcosa, e Python con lei.
 *
 *   'proposta'  l'anteprima rifiutata: la sorgente confermata resta dov'e';
 *   'tutto'     si ricomincia: sorgente, playlist e coda (la coda solo se la
 *               postazione non sta lavorando, perche' e' la sua scaletta). */
async function dimentica(p, cosa) {
  cosa = cosa || 'tutto';
  const esito = await window.pywebview.api.dimentica(cosa, p.dove);
  if (cosa === 'tutto') {
    svuotaScheda(p);
    aggiornaAvvio(p);
    aggiornaCarte(p);
  }
  if (esito && esito.coda) mostraCoda(p, esito.coda);
}

/* ── La coda ──────────────────────────────────────────────────────────────── */

/* I video che aspettano il loro turno, sotto la scheda della sorgente. Ognuno
 * ha il suo × per toglierlo prima che parta: una coda da cui non si puo'
 * togliere niente si svuota solo ricominciando da capo. */
function mostraCoda(p, coda) {
  p.coda = coda || [];
  const blocco = p.q('coda-blocco');
  const lista = p.q('coda-lista');
  lista.innerHTML = '';
  p.coda.forEach((v, i) => {
    const riga = el('div', 'riga-video');
    riga.appendChild(el('span', 'numero', String(i + 1).padStart(2, '0')));
    riga.appendChild(el('span', 'titolo', v.titolo + (v.playlist ? '  ·  ' + v.playlist : '')));
    riga.appendChild(el('span', 'durata', v.durata || ''));
    const togli = el('button', 'togli');
    togli.title = t('coda.remove');
    togli.appendChild(icona('i-togli'));
    togli.addEventListener('click', async () => {
      const esito = await window.pywebview.api.togli_dalla_coda(i, p.dove);
      if (esito && esito.coda) mostraCoda(p, esito.coda);
    });
    riga.appendChild(togli);
    lista.appendChild(riga);
  });
  blocco.hidden = !p.coda.length;
  aggiornaAvvio(p);
  aggiornaCarte(p);
  aggiornaVoci();
}

/* Python dice che la coda e' cambiata: un video e' partito, e non aspetta piu'. */
ascolta('aggiornaCoda', (p, coda) => mostraCoda(p, coda));

/* ── Leggere la sorgente ──────────────────────────────────────────────────── */

/* Un indirizzo che valga la pena mandare a YouTube: comincia per http e ha
 * almeno un punto dopo. Mezzo link scritto a mano non passa, e non si
 * disturba nessuno finche' non e' completo. */
const SEMBRA_UN_LINK = /^https?:\/\/[^\s/]+\.\S+(\s+https?:\/\/[^\s/]+\.\S+)*$/i;

function programmaLettura(p, subito) {
  clearTimeout(p.timerLettura);
  const indirizzo = p.q('url').value.trim();
  if (!SEMBRA_UN_LINK.test(indirizzo)) {
    if (!p.inLettura) statoLettura(p, 'src.load.hint', false);
    return;
  }
  if (indirizzo === p.ultimoLetto) return;
  p.timerLettura = setTimeout(() => leggiSorgente(p), subito ? 0 : 800);
}

/* La riga sotto la casella del link: che cosa sta succedendo. */
function statoLettura(p, chiave, attiva) {
  const riga = p.q('lettura');
  if (!riga) return;
  riga.dataset.t = chiave;
  riga.textContent = t(chiave);
  riga.classList.toggle('attiva', !!attiva);
}

async function leggiSorgente(p) {
  const indirizzo = p.q('url').value.trim();
  p.ultimoLetto = indirizzo;
  p.inLettura = true;
  statoLettura(p, 'src.load.loading', true);
  const esito = await window.pywebview.api.carica_info(indirizzo, p.dove);
  if (!esito.ok) { finiscoLettura(p); erroreDi(p, esito.errore); }
}

/* Su una playlist si sta parecchio: ogni video va letto uno per uno. Dirlo e'
 * la differenza fra un'attesa e un sospetto di blocco. */
ascolta('caricamentoPlaylist', (p) => statoLettura(p, 'src.load.playlist', true));

function finiscoLettura(p) {
  p.inLettura = false;
  statoLettura(p, 'src.load.hint', false);
}

/* Una risposta che riguarda un link diverso da quello nella casella e'
 * vecchia: nel frattempo il link e' cambiato. Python lascia gia' cadere le
 * letture superate, ma una risposta puo' essere in viaggio proprio mentre si
 * incolla quello nuovo. */
function superata(p, dati) {
  return !!(dati && dati.url) && dati.url !== p.q('url').value.trim();
}

/* La lettura del link e' caduta. Non un avviso che sparisce da solo dopo
 * sette secondi, ma una finestra che dice quale link, di che cosa si tratta
 * e, sotto, il testo tecnico: e' quello che serve a capire se riprovare,
 * correggere il link o segnalare un difetto del programma. */
ascolta('erroreSorgente', (p, e) => {
  if (superata(p, e)) return;
  finiscoLettura(p);
  const corpo = [];
  if (e.video) corpo.push(riquadroPercorso(e.et_video || t('err.link'), e.video));
  corpo.push(paragrafo(e.causa || t('err.unknown')));
  if (e.dettaglio) corpo.push(riquadroDettaglio(e.et_dettaglio, e.dettaglio));
  finestraDi(p, {
    icona: 'errore', tono: 'errore', titolo: t('err.src.title'), corpo,
    azioni: [{ testo: t('comune.chiudi'), tono: 'pieno', icona: 'spunta' }],
  });
});

/* La conferma: copertina, dati, stima, e la domanda. Chiederla e' cio' che
 * evita di trascrivere il video sbagliato, che con Groq non e' solo tempo.
 *
 * Passa da finestraDi e non da finestra: leggere una playlist lunga richiede
 * parecchi secondi, e in quei secondi si puo' benissimo essere andati
 * nell'altra stanza a far partire un secondo lavoro. In quel caso la domanda
 * aspetta, invece di piombare addosso a chi sta facendo altro. */
ascolta('chiediConferma', (p, scheda) => {
  if (superata(p, scheda)) return;
  finiscoLettura(p);
  mostraAnteprima(p, scheda);
});

/* L'anteprima, e i bottoni che servono in questo momento.
 *
 * Nella postazione vuota basta «Conferma». Se c'e' gia' un video confermato
 * la domanda diventa un'altra: sostituirlo, o mettere il nuovo in coda. Se la
 * postazione sta lavorando si puo' solo mettere in coda: il video che gira
 * non si sostituisce a meta'. */
function mostraAnteprima(p, scheda) {
  const tipo = scheda.tipo;
  const n = (scheda.voci || []).length;
  let domanda = t('confirm.question');
  if (tipo === 'playlist') domanda = t('playlist.question', { n });
  else if (tipo === 'gruppo') domanda = t('coda.group.question');
  if (scheda.lavora) domanda = t('confirm.question.busy');
  else if (scheda.ha_sorgente && p.scheda) {
    domanda = t('confirm.question.more', { titolo: p.scheda.titolo });
  }

  // Segnato quando si preme un bottone di conferma: la chiusura della
  // finestra, che viene prima dell'azione, non deve buttare via la proposta
  // che il bottone sta per confermare.
  let scelto = false;
  const scegli = (modo) => () => { scelto = true; conferma(p, modo, scheda); };

  const azioni = [
    // Annullare riapre la finestra del video: chi rifiuta l'anteprima quasi
    // sempre vuole correggere il link, non ricominciare a cercarlo.
    { testo: t('comune.annulla'), tono: 'contorno',
      azione: () => { scelto = true; p.ultimoLetto = null;
                      dimentica(p, 'proposta'); apriVideoDaFuori(p); } },
  ];
  if (scheda.lavora) {
    azioni.push({ testo: t('confirm.queue'), tono: 'pieno', icona: 'spunta',
                  azione: scegli('coda') });
  } else if (scheda.ha_sorgente) {
    azioni.push({ testo: t('confirm.replace'), tono: 'contorno', icona: 'rifai',
                  azione: scegli('sostituisci') });
    azioni.push({ testo: t('confirm.queue'), tono: 'pieno', icona: 'spunta',
                  azione: scegli('coda') });
  } else {
    azioni.push({ testo: t('comune.conferma'), tono: 'pieno', icona: 'spunta',
                  azione: scegli('sostituisci') });
  }

  finestraDi(p, {
    icona: tipo === 'playlist' || tipo === 'gruppo' ? 'riassumi'
         : (tipo === 'file' ? 'file-audio' : 'video'),
    titolo: t(tipo === 'playlist' ? 'playlist.title' : 'confirm.title'),
    corpo: [disegnaScheda(scheda, true), domanda],
    azioni,
    // Chiudere con Esc e' come annullare: la proposta non e' confermata, e
    // lasciarla valida sarebbe l'errore peggiore che questa finestra possa fare.
    // Il rinvio lascia prima eseguire il bottone premuto, che e' quello che
    // decide davvero.
    suChiusura: () => setTimeout(() => {
      if (!scelto) { p.ultimoLetto = null; dimentica(p, 'proposta'); }
    }, 0),
  });
}

/* Conferma la proposta: come sorgente, o in coda. */
async function conferma(p, modo, scheda) {
  const esito = await window.pywebview.api.conferma(modo, p.dove);
  if (!esito.ok) { erroreDi(p, esito.errore); return; }
  if (esito.scheda) {
    mostraScheda(p, esito.scheda);
    avvisa(scheda.tipo === 'playlist'
      ? t('playlist.ok', { titolo: scheda.titolo, n: (scheda.voci || []).length })
      : t('confirm.ok', { titolo: esito.scheda.titolo }), 'ok');
  } else {
    // In coda: la casella si svuota, pronta per il link successivo.
    p.q('url').value = '';
    p.ultimoLetto = null;
    avvisa(t('confirm.queued', { titolo: scheda.titolo, n: (esito.coda || []).length }), 'ok');
  }
  mostraCoda(p, esito.coda);
}

async function scegliFile(p) {
  const esito = await window.pywebview.api.scegli_file(p.dove);
  if (!esito.ok) { erroreDi(p, esito.errore); return; }
  if (esito.annullato) return;
  p.q('file').value = esito.scheda.titolo;
  // Un file scelto da se' non ha bisogno di anteprima quando la postazione e'
  // vuota: lo si e' appena visto nel selettore. Serve solo per chiedere
  // «sostituisco o metto in coda?».
  if (!esito.scheda.ha_sorgente && !esito.scheda.lavora) conferma(p, 'sostituisci', esito.scheda);
  else mostraAnteprima(p, esito.scheda);
}

/* Un link trascinato dentro la finestra vale come un link incollato, e vale
 * per la stanza in cui e' stato lasciato cadere. Un file trascinato no: il
 * percorso che il browser espone non e' quello vero del disco, e aprirlo
 * fallirebbe in silenzio: meglio dire di usare «Sfoglia». */
window.accettaTrascinato = (p, testo) => {
  if (!/https?:\/\//i.test(testo)) { avvisa(t('err.no_url'), 'fail'); return; }
  p.q('sorgente').value = 'youtube';
  salvaScelte({ sorgente: 'youtube' }, p);
  sincronizzaSorgente(p);
  p.q('url').value = testo.trim();
  leggiSorgente(p);
};

/* ── Avviare ──────────────────────────────────────────────────────────────── */

/* Il bottone si accende solo quando si puo' davvero partire. Resta comunque
 * cliccabile quando non si puo': premendolo si scopre cosa manca, che e' piu'
 * utile di un bottone spento che non spiega perche'. */
function aggiornaAvvio(p) {
  const qualcosa = !!p.scheda || !!(p.coda && p.coda.length);
  const pronto = qualcosa && (p.motore !== 'groq' || window.chiaveCaricata());
  p.q('avvia').style.opacity = pronto ? '1' : '.55';
}

/* Fa partire un'azione e, se Python la rifiuta, dice perche'. */
async function esegui(p, azione) {
  const esito = await window.pywebview.api.esegui(azione, p.dove);
  if (esito && !esito.ok) erroreDi(p, esito.errore);
}

async function premiAvvia(p, saltaCrediti) {
  const esito = await window.pywebview.api.prepara(!!saltaCrediti, p.dove);
  if (!esito.ok) { erroreDi(p, esito.errore); return; }

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

  /* I crediti Groq non bastano per tutto l'audio: lo si dice prima, e si
   * lascia decidere. «Parti lo stesso» rifa' i controlli saltando solo
   * questo, perche' gli altri (video gia' fatto, parziale) valgono ancora. */
  if (esito.stato === 'crediti') {
    finestra({
      icona: 'clessidra', tono: 'attenzione', titolo: esito.titolo,
      corpo: [esito.desc, ...esito.voci.map((v) => voceScelta(v, () => premiAvvia(p, true)))],
      azioni: [{ testo: t('comune.annulla'), tono: 'contorno' }],
    });
    return;
  }

  if (esito.stato === 'gia' || esito.stato === 'ripresa') {
    finestra({
      icona: esito.stato === 'gia' ? 'riassumi' : 'clessidra',
      titolo: esito.titolo,
      corpo: [esito.desc, ...esito.voci.map(
        (v) => voceScelta(v, (scelta) => esegui(p, scelta.azione)))],
      azioni: [{ testo: t('comune.annulla'), tono: 'contorno' }],
    });
    return;
  }

  esegui(p, 'nuova');
}

/* «Annulla» durante il lavoro. Il lavoro non si ferma di colpo ma al primo
 * punto sicuro, e il bottone lo dice mentre aspetta. */
async function annullaLavoro(p) {
  const bottone = p.q('annulla');
  bottone.disabled = true;
  bottone.querySelector('span').textContent = t('prog.cancelling');
  await window.pywebview.api.annulla(p.dove);
}

ascolta('lavoroAnnullato', (p, dati) => {
  finestraDi(p, {
    icona: 'clessidra', tono: 'attenzione', titolo: dati.titolo,
    corpo: [dati.testo],
    azioni: [{ testo: t('comune.chiudi'), tono: 'pieno', icona: 'spunta' }],
  });
});

function riabilitaTrascrivi(p) {
  sincronizzaSorgente(p);
  sincronizzaDipendenti(p);
  aggiornaAvvio(p);
}

/* ── Il risultato ─────────────────────────────────────────────────────────── */

ascolta('mostraRisultato', (p, res) => {
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

  /* «Leggi»: il documento in una finestra sua, con formule e grafici gia'
   * disegnati. Stanno nel corpo e non fra i bottoni in fondo apposta: aprire
   * un documento non deve chiudere il riepilogo. */
  if ((res.documenti || []).length) {
    const riga = el('div', 'riga-leggi');
    res.documenti.forEach((d) => {
      const bottone = el('button', 'bottone contorno');
      bottone.appendChild(icona('i-leggi'));
      bottone.appendChild(el('span', '', t('res.read') + ' ' + d.etichetta));
      bottone.addEventListener('click', async () => {
        const esito = await window.pywebview.api.leggi(d.percorso, p.dove);
        if (esito && !esito.ok && esito.errore) erroreDi(p, esito.errore);
      });
      riga.appendChild(bottone);
    });
    corpo.push(riga);
  }

  finestraDi(p, {
    icona: 'spunta', tono: 'riuscito', titolo: res.titolo, corpo,
    azioni: [
      // Non chiude: si apre la cartella e si torna a guardare il riepilogo.
      { testo: t('res.open'), tono: 'contorno', icona: 'cartella', chiudi: false,
        azione: () => window.pywebview.api.apri('cartella', p.dove) },
      { testo: t('comune.chiudi'), tono: 'contorno', icona: 'spunta' },
      // La via piu' corta per il video successivo. Azzera SOLO la sorgente e
      // riapre la finestra del video: modelli e chiave restano come sono,
      // perche' fra un video e l'altro quasi mai cambiano, e rifarli scegliere
      // ogni volta sarebbe far ripetere una risposta gia' data.
      { testo: t('res.ancora'), tono: 'pieno', icona: 'rifai',
        azione: () => { azzeraSorgente(p); apriVideoDaFuori(p); } },
    ],
  });
});

/* Svuota la sorgente per ricominciare con un altro video, in questa stanza.
 *
 * Gli interruttori degli output NON si toccano: chi ha appena chiesto
 * trascrizione piu' riassunto quasi sempre vuole lo stesso anche per il
 * prossimo, e spegnerli sarebbe una sorpresa scoperta solo alla fine. */
function azzeraSorgente(p) {
  p.q('url').value = '';
  p.q('file').value = '';
  p.ultimoLetto = null;
  dimentica(p, 'tutto');
}

ascolta('mostraRisultatoPlaylist', (p, res) => {
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
      const riga = el('div', 'riga-video ' + v.tono + (v.causa ? ' con-causa' : ''));
      riga.appendChild(el('span', 'titolo', v.titolo));
      /* Un video non riuscito porta con se' il perche'. Senza, l'elenco diceva
       * quali erano andati male e lasciava a chi legge il compito di indovinare
       * se valesse la pena rilanciare: tre video privati e tre cadute di rete
       * si leggevano identici, e sono due situazioni opposte. */
      if (v.causa) riga.appendChild(el('span', 'causa', v.causa));
      if (v.dettaglio) riga.appendChild(riquadroDettaglio(res.et_dettaglio, v.dettaglio));
      elenco.appendChild(riga);
    });
    corpo.push(elenco);
  }

  /* Se qualcosa non e' riuscito la finestra non si presenta come un successo
   * pieno: la spunta verde su un batch in cui tre video sono caduti e' una
   * bugia piccola, ma e' quella che fa chiudere la finestra senza leggerla. */
  const tuttoBene = !(res.voci || []).some((v) => v.tono === 'attenzione');

  finestraDi(p, {
    icona: tuttoBene ? 'spunta' : 'errore',
    tono: tuttoBene ? 'riuscito' : 'attenzione',
    titolo: res.titolo, corpo,
    azioni: [
      { testo: t('res.open'), tono: 'contorno', icona: 'cartella', chiudi: false,
        azione: () => window.pywebview.api.apri('cartella', p.dove) },
      { testo: t('comune.chiudi'), tono: 'pieno', icona: 'spunta' },
    ],
  });
});

/* ── Quando Groq finisce i crediti ────────────────────────────────────────── */

/* Non e' un errore, ed e' per questo che non e' rosso: non si e' rotto niente,
 * il parziale e' salvato, e ci sono due modi veri di proseguire.
 *
 * Il lavoro resta nella stanza in cui e' cominciato anche scegliendo di
 * finirlo sul computer: cambia il modello che lo porta a termine, non la
 * scrivania su cui sta. Spostarlo vorrebbe dire lasciare a meta' strada il suo
 * avanzamento, nella stanza di prima. */
ascolta('creditiFiniti', (p, dati) => {
  // Senza parziale (i crediti erano finiti prima di cominciare) non c'e'
  // niente da riprendere domani ne' da finire in locale: resta solo «ho capito».
  const azioni = [{ testo: t(dati.puo_locale ? 'rate.later' : 'rate.ok'),
                    tono: 'contorno', icona: 'clessidra' }];
  if (dati.puo_locale) {
    azioni.push({ testo: t('rate.local'), tono: 'ambra', icona: 'casa',
                  azione: async () => {
                    const esito = await window.pywebview.api.continua_in_locale(p.dove);
                    if (esito && !esito.ok) erroreDi(p, esito.errore);
                  } });
  }
  finestraDi(p, {
    icona: 'clessidra', tono: 'attenzione', titolo: dati.titolo,
    corpo: [dati.testo], azioni,
  });
});

/* Il riassunto si e' fermato a meta' per gli stessi crediti. La trascrizione
 * pero' e' salva, quindi la scelta e' solo su come finire il riassunto: adesso
 * in locale, o piu' tardi. In ogni caso il risultato si vede. */
ascolta('riassuntoInterrotto', (p, res) => {
  finestraDi(p, {
    icona: 'clessidra', tono: 'attenzione', titolo: t('sumlocal.title'),
    corpo: [t('sumlocal.msg')],
    azioni: [
      { testo: t('sumlocal.no'), tono: 'contorno',
        azione: () => window.__instrada(p.dove, 'mostraRisultato', [res]) },
      { testo: t('sumlocal.yes'), tono: 'ambra', icona: 'casa',
        azione: async () => {
          const esito = await window.pywebview.api.concludi_in_locale(p.dove);
          if (esito && !esito.ok) erroreDi(p, esito.errore);
        } },
    ],
  });
});

/* ── Riscrivere quello che non ha un data-t ───────────────────────────────── */

function riempiTrascrivi(p) {
  if (p.scheda) mostraScheda(p, p.scheda);
  else svuotaScheda(p);
  mostraCoda(p, p.coda);
  sincronizzaDipendenti(p);
  // La stima e' una frase composta da Python: gliela si richiede invece di
  // provare a comporla qui, dove il numero non c'e'.
  salvaScelte({}, p);
  sincronizzaSorgente(p);
}

window.initTrascrivi = initTrascrivi;
window.riempiTrascrivi = riempiTrascrivi;
window.riabilitaTrascrivi = riabilitaTrascrivi;
window.aggiornaAvvio = aggiornaAvvio;
window.mostraCoda = mostraCoda;
window.mostraStima = mostraStima;
