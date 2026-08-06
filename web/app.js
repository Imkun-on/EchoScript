/* Nucleo della pagina: testi, cambio sezione, diario, avvisi, avanzamento.
 *
 * Regola unica, valida anche per i tre file delle sezioni: qui non si decide
 * niente di importante. La pagina raccoglie cio' che si sceglie, lo passa a
 * Python, e mostra cio' che Python risponde. Ogni scelta vera — se un URL sia
 * una playlist, se un video sia gia' stato trascritto, quanto costera' un
 * lavoro, in quante fasi si divide — sta gia' nel motore, ed e' li' che deve
 * restare: duplicarla qui significherebbe due risposte diverse alla stessa
 * domanda.
 */

let TESTI = {};
let LINGUA = 'it';
// Nessuna, finche' l'avvio non apre quella del motore salvato.
let SEZIONE = '';

/* Le scelte dell'interfaccia: motore, modelli, interruttori. Vivono qui e in
 * Python, non nel documento, perche' devono sopravvivere al cambio di lingua
 * (che riscrive le voci dei menu) e perche' Python le salva per la volta dopo. */
let SCELTE = {};

/* Il piano del lavoro in corso: l'elenco delle fasi. Serve a disegnare i
 * passaggi e a sapere quali sono gia' andati. Vuoto quando non si lavora. */
let PIANO = [];

const $ = (sel) => document.querySelector(sel);
const $$ = (sel) => Array.from(document.querySelectorAll(sel));

function t(chiave, valori) {
  const voce = TESTI[chiave];
  let testo = voce ? (voce[LINGUA] || voce.it || chiave) : chiave;
  if (valori) {
    for (const [k, v] of Object.entries(valori)) testo = testo.split('{' + k + '}').join(v);
  }
  return testo;
}

function traduciPagina() {
  $$('[data-t]').forEach((e) => { e.textContent = t(e.dataset.t); });
  $('#stato').textContent = t('status.' + (statoCorrente || 'idle'));
  if (!$('#diario').dataset.pieno) svuotaDiario();
  if (window.traduciMotore) window.traduciMotore();
  if (window.traduciTrascrivi) window.traduciTrascrivi();
  if (window.traduciCrediti) window.traduciCrediti();
}

/* ── Cambio sezione ───────────────────────────────────────────────────────── */

/* Le due sezioni di lavoro e il motore che ci gira dentro. Aprire «Cloud» E'
 * scegliere Groq: non c'e' un secondo gesto da fare ne' un interruttore da
 * ricordare, e il bottone «Trascrivi» che si preme e' quello dentro la stanza
 * in cui si sta. Era la cosa che l'interfaccia di prima non diceva. */
const MOTORE_DI = { locale: 'local', cloud: 'groq' };
const SEZIONE_DI = { local: 'locale', groq: 'cloud' };

function sezioneDiLavoro() { return SEZIONE_DI[SCELTE.motore] || 'locale'; }

function cambiaSezione(nome, immediato) {
  if (nome === SEZIONE && !immediato) return;
  const uscente = document.querySelector('.sezione.attiva');
  SEZIONE = nome;
  $$('.voce').forEach((v) => v.classList.toggle('attiva', v.dataset.va === nome));

  // Entrando in una sezione di lavoro il motore diventa il suo. Non si fa
  // mentre un lavoro gira: quello in corso ha gia' preso le sue opzioni, e
  // cambiare la scelta sotto gli occhi mostrerebbe un motore diverso da quello
  // che sta davvero lavorando.
  if (MOTORE_DI[nome] && MOTORE_DI[nome] !== SCELTE.motore && !window.lavoroInCorso) {
    salvaScelte({ motore: MOTORE_DI[nome] });
    if (window.sincronizzaMotore) window.sincronizzaMotore();
    if (window.aggiornaAvvio) window.aggiornaAvvio();
  }

  // Prima la sezione che se ne va sfuma e arretra, poi entra la nuova
  // dall'altro lato. Il ritardo e' quello dell'animazione di uscita, non un
  // numero scelto a caso.
  const entra = () => {
    $$('.sezione').forEach((s) => {
      s.classList.remove('uscita');
      s.classList.toggle('attiva', s.dataset.sez === nome);
    });
    spostaLavoro(nome);
  };

  if (uscente && uscente.dataset.sez !== nome && !immediato) {
    uscente.classList.add('uscita');
    uscente.classList.remove('attiva');
    setTimeout(entra, 200);
  } else {
    entra();
  }
}

/* La postazione — link o file, output, avvio, sorgente, diario — e' una sola e
 * si sposta nella sezione aperta. Duplicarla vorrebbe dire due link incollati e
 * due cronologie, e non sapere piu' quale delle due si sta guardando. Dove non
 * c'e' uno slot — «Crediti», che non lavora — semplicemente sparisce. */
function spostaLavoro(nome) {
  const slot = document.querySelector(`.sezione[data-sez="${nome}"] .slot-lavoro`);
  const posto = $('#postazione');
  if (slot) { slot.appendChild(posto); posto.style.display = ''; }
  else { posto.style.display = 'none'; }
}

/* ── Il diario ────────────────────────────────────────────────────────────── */

window.aggiungiRiga = (testo) => {
  const diario = $('#diario');
  if (!diario.dataset.pieno) { diario.innerHTML = ''; diario.dataset.pieno = '1'; }
  const riga = el('div', 'riga-log ' + classeRiga(testo), testo);
  diario.appendChild(riga);
  // Si tiene solo la coda: una playlist di cinquanta video produce migliaia di
  // righe, e tenerle tutte nel documento rallenta lo scorrimento.
  while (diario.childElementCount > 400) diario.removeChild(diario.firstChild);
  diario.scrollTop = diario.scrollHeight;
};

function classeRiga(testo) {
  // Le intestazioni di fase si riconoscono dal segno e non passano di qui: dicono
  // dove siamo, non com'e' andata. Verdi sarebbero una promessa che la fase non ha
  // ancora mantenuto: «Esportazione / salvataggio» contiene «salvat», e basterebbe
  // quello a farla sembrare riuscita mentre sta ancora cominciando.
  if (testo.includes('▸')) return 'fase';
  const b = testo.toLowerCase();
  if (b.includes('error') || b.includes('errore') || b.includes('✗') || b.includes('fallit')) return 'err';
  if (b.includes('✓') || b.includes('completat') || b.includes('salvat') || b.includes('fatto')) return 'ok';
  if (b.includes('warning') || b.includes('attenzione') || b.includes('⚠')) return 'warn';
  return '';
}

function svuotaDiario() {
  const d = $('#diario');
  d.dataset.pieno = ''; d.innerHTML = '';
  d.appendChild(statoVuoto(t('log.empty')));
}

function statoVuoto(testo) {
  const box = el('div', 'vuoto');
  box.appendChild(icona('i-vuoto'));
  box.appendChild(el('div', '', testo));
  return box;
}

/* ── Avvisi a comparsa ────────────────────────────────────────────────────── */

function avvisa(testo, tipo) {
  const box = el('div', 'avviso ' + (tipo || ''));
  box.appendChild(el('div', '', testo));
  $('#avvisi').appendChild(box);
  // Gli errori restano piu' a lungo: si vuole avere il tempo di leggerli.
  setTimeout(() => {
    box.classList.add('uscita');
    setTimeout(() => box.remove(), 300);
  }, tipo === 'fail' ? 7000 : 4000);
}

function errore(messaggio) {
  window.aggiungiRiga(messaggio);
  avvisa(messaggio, 'fail');
}

/* ── Stato del lavoro ─────────────────────────────────────────────────────── */

let statoCorrente = 'idle';

window.cambiaStato = (stato) => {
  statoCorrente = stato;
  $('#spia').className = 'spia ' + (stato === 'idle' ? '' : stato);
  $('#stato').textContent = t('status.' + stato);

  // Mentre si lavora nulla si puo' cambiare: ne' il motore, ne' la sorgente,
  // ne' gli interruttori. Non e' una precauzione formale — cambiare modello a
  // meta' trascrizione darebbe un risultato che non corrisponde a niente di
  // quello che si vede scritto.
  const inCorso = stato === 'working';
  // Serve anche fuori di qui: cambiare sezione cambierebbe il motore, e mentre
  // un lavoro gira il motore e' quello con cui e' partito, non quello della
  // stanza in cui si e' appena entrati a guardare.
  window.lavoroInCorso = inCorso;

  // Il bottone principale dice cosa sta succedendo invece di limitarsi a
  // spegnersi. Si cambia il data-t e non solo il testo, cosi' cambiare lingua a
  // meta' lavoro continua a scrivere la frase giusta.
  const testo = $('#testo-avvia');
  testo.dataset.t = inCorso ? 'src.busy' : 'src.start';
  testo.textContent = t(testo.dataset.t);
  $('#icona-avvia').setAttribute('href', inCorso ? '#i-clessidra' : '#i-avvia');

  $$('.bottone.pieno, .bottone.contorno').forEach((b) => { b.disabled = inCorso; });
  $$('.campo, .interruttore input').forEach((c) => { c.disabled = inCorso; });
  $$('.coda').forEach((c) => { c.disabled = inCorso; });

  if (!inCorso) {
    PIANO = [];
    $('#avanzamento').classList.remove('visibile');
    $('#badge-batch').hidden = true;
    if (window.riabilitaTrascrivi) window.riabilitaTrascrivi();
  }
};

/* Un lavoro comincia: si sa gia' quali fasi ci saranno, chi le fara' e cosa
 * produrranno. Dirlo tutto in anticipo e' cio' che trasforma un'attesa muta in
 * un'attesa che si capisce. */
window.iniziaLavoro = (dati) => {
  PIANO = dati.piano || [];
  $('#avanzamento').classList.add('visibile');
  $('#barra').style.width = '0%';
  $('#avanz-pct').textContent = '0%';
  $('#avanz-fase').textContent = t('phase.default');
  $('#avanz-dettaglio').textContent = '';
  $('#racconto-testo').textContent = t('narr.info');
  $('#racconto-piano').textContent = t('prog.plan') + ' ' + dati.frase;

  const motore = $('#badge-motore');
  motore.className = 'targhetta-motore ' + (dati.tono || '');
  motore.textContent = dati.motore || '';

  const nota = $('#badge-nota');
  nota.textContent = dati.nota || '';
  nota.hidden = !dati.nota;

  disegnaPassi(-1);
};

/* I passaggi: quelli fatti spuntati, quello in corso acceso, gli altri spenti.
 * E' la sola cosa che dice quanto manca alla FINE e non solo alla fase. */
function disegnaPassi(corrente) {
  const box = $('#passi');
  box.innerHTML = '';
  PIANO.forEach((fase, i) => {
    const stato = i < corrente ? ' fatto' : (i === corrente ? ' corrente' : '');
    const passo = el('span', 'passo' + stato);
    passo.appendChild(el('span', 'pallino'));
    passo.appendChild(el('span', '', t('phase.' + fase)));
    box.appendChild(passo);
  });
}

/* L'avanzamento vero.
 *
 *   fase       il nome della fase che il motore sta eseguendo;
 *   indice     la sua posizione nel piano (-1 se fuori piano);
 *   fasi       quante sono in tutto;
 *   globale    da 0 a 1, il riempimento della barra sull'INTERO lavoro, non
 *              sulla fase: e' Python a calcolarlo, perche' e' Python a sapere
 *              che una fase vale un quinto e non un mezzo;
 *   dettaglio  cosa sta lavorando in questo momento (un blocco, una sezione).
 */
window.avanzaLavoro = (fase, indice, fasi, globale, dettaglio) => {
  if (globale !== null && globale !== undefined) {
    $('#barra').style.width = (Math.max(0, Math.min(1, globale)) * 100).toFixed(1) + '%';
    $('#avanz-pct').textContent = Math.round(globale * 100) + '%';
  }
  const nome = TESTI['phase.' + fase] ? t('phase.' + fase) : t('phase.default');
  $('#avanz-fase').textContent = nome;
  $('#avanz-dettaglio').textContent = dettaglio || '';

  if (TESTI['narr.' + fase]) $('#racconto-testo').textContent = t('narr.' + fase);

  const badge = $('#badge-fase');
  if (indice >= 0) {
    badge.hidden = false;
    badge.textContent = t('prog.phase', { i: indice + 1, n: fasi });
    disegnaPassi(indice);
  } else {
    badge.hidden = true;
  }
};

/* La playlist: quale video, di quanti. Il resto della finestra racconta gia'
 * cosa sta succedendo a QUESTO video, quindi qui basta dire quale sia. */
window.lavoroBatch = (conteggio, titolo) => {
  const badge = $('#badge-batch');
  badge.hidden = false;
  badge.textContent = conteggio + '  ·  ' + titolo;
};

window.erroreLavoro = (messaggio) => {
  window.cambiaStato('error');
  window.aggiungiRiga(messaggio);
  finestra({
    icona: 'errore', tono: 'errore', titolo: t('err.title'),
    corpo: [messaggio || t('err.unknown')],
    azioni: [{ testo: t('comune.chiudi'), tono: 'pieno', icona: 'spunta' }],
  });
};

/* ── Le scelte, ricordate ─────────────────────────────────────────────────── */

/* Ogni modifica va anche a Python, che la salva e rispedisce la stima
 * aggiornata: il costo cambia col modello, e vederlo cambiare nell'istante in
 * cui si sceglie e' meta' del motivo per cui la stima esiste. */
async function salvaScelte(valori) {
  Object.assign(SCELTE, valori);
  const esito = await window.pywebview.api.imposta(valori);
  if (esito && esito.ok && window.mostraStima) window.mostraStima(esito.stima);
}

/* ── Avvio ────────────────────────────────────────────────────────────────── */

const T_AVVIO = performance.now();

/* I passi dell'avvio, contati.
 *
 * Sono i pezzi che vanno messi insieme prima che l'interfaccia sia usabile, ed
 * e' un elenco chiuso e noto: per questo la barra del velo puo' dire un numero
 * vero invece di scorrere avanti e indietro. Ogni chiamata a passoAvvio() e' un
 * pezzo davvero finito, non un'attesa a tempo. */
const PASSI_AVVIO = 6;
let passiFatti = 0;

/* Ma i passi non cominciano qui. Prima che questa pagina esistesse, Python ha
 * gia' caricato il ponte con WebView2 e tutto il motore, e l'ha raccontato sulla
 * barra della schermata di avvio: quella che si vede dal doppio clic. Questo
 * velo ne e' la seconda meta', quindi la sua barra riparte da dove l'altra si e'
 * fermata invece che da zero — e' lo stesso valore di APERTURA in
 * EchoScriptApp.py. Ripartire da zero farebbe tornare indietro una barra che
 * l'utente sta guardando, che e' il modo piu' rapido di far sembrare rotto un
 * avvio che sta andando bene. */
const BASE_AVVIO = 0.62;

function quotaAvvio() {
  return BASE_AVVIO + (1 - BASE_AVVIO) * (passiFatti / PASSI_AVVIO);
}

function passoAvvio() {
  passiFatti = Math.min(passiFatti + 1, PASSI_AVVIO);
  const b = document.querySelector('.avvio-barra span');
  if (b) b.style.width = (quotaAvvio() * 100).toFixed(0) + '%';
}

/* Toglie il velo di caricamento. Si puo' chiamare quante volte si vuole.
 *
 * I 500 ms minimi non sono un'attesa finta: su una macchina veloce la pagina e'
 * pronta in un attimo, e un velo che appare e sparisce in cinquanta millesimi
 * si vede come uno sfarfallio, non come un caricamento. */
function togliVelo() {
  const v = document.getElementById('velo-avvio');
  if (!v || v.dataset.uscita) return;
  v.dataset.uscita = '1';
  const resta = Math.max(0, 500 - (performance.now() - T_AVVIO));
  setTimeout(() => {
    v.classList.add('via');
    setTimeout(() => v.remove(), 600);
  }, resta);
}

function avvia() {
  /* La barra parte gia' riempita di cio' che Python ha fatto prima che questa
   * pagina esistesse. Si scrive subito, prima del primo disegno: cosi' il primo
   * fotogramma del velo mostra gia' la barra al punto giusto, invece di farla
   * scivolare da zero sotto gli occhi di chi la stava guardando ferma piu'
   * avanti un istante prima. */
  const b0 = document.querySelector('.avvio-barra span');
  if (b0) b0.style.width = (BASE_AVVIO * 100).toFixed(0) + '%';

  /* Se l'apertura si inceppa — un errore nel motore, una chiamata che non torna
   * — il velo deve comunque andarsene: meglio un'interfaccia a meta', che si
   * vede e si puo' chiudere, che una schermata di caricamento perpetua. */
  setTimeout(togliVelo, 12000);
  passoAvvio();                       // 1. la pagina e i suoi script ci sono

  window.addEventListener('pywebviewready', async () => {
    passoAvvio();                     // 2. il ponte con Python risponde
    const dati = await window.pywebview.api.avvio();
    passoAvvio();                     // 3. testi, scelte e modelli sono arrivati

    // La finestra adesso e' sullo schermo, quindi i fotogrammi ripartono: al
    // primo davvero composto si dice a Python di togliere l'immagine di
    // caricamento. Due requestAnimationFrame annidati perche' il primo finisce
    // il fotogramma in corso e il secondo comincia quello dopo, a disegno fatto.
    requestAnimationFrame(() => requestAnimationFrame(() => {
      try { window.pywebview.api.dipinta(); } catch (e) { /* la rete di
        sicurezza in Python la toglie comunque */ }
    }));

    TESTI = dati.testi;
    LINGUA = dati.lingua;
    SCELTE = dati.scelte;
    $('#lingua').value = LINGUA;

    if (window.initMotore) window.initMotore(dati);
    if (window.initTrascrivi) window.initTrascrivi(dati);
    if (window.initCrediti) window.initCrediti(dati);
    passoAvvio();                     // 4. le tre sezioni sono pronte

    traduciPagina();
    if (window.potenziaTendine) window.potenziaTendine();
    passoAvvio();                     // 5. tutto e' nella lingua giusta

    // Si riapre nella stanza in cui si lavorava l'ultima volta: la scelta del
    // motore e' salvata, e riportarla a schermo e' il modo di non far ricominciare
    // da capo chi aveva gia' deciso.
    cambiaSezione(sezioneDiLavoro(), true);
    window.cambiaStato('idle');

    $$('.voce[data-va]').forEach((v) =>
      v.addEventListener('click', () => cambiaSezione(v.dataset.va)));
    $('#svuota').addEventListener('click', svuotaDiario);

    $('#lingua').addEventListener('change', async (e) => {
      const esito = await window.pywebview.api.cambia_lingua(e.target.value);
      LINGUA = esito.lingua;
      traduciPagina();
    });

    // Ctrl+Invio avvia la trascrizione da qualunque sezione: chi ha appena
    // riempito il modulo ha le mani sulla tastiera, non sul mouse.
    document.addEventListener('keydown', (e) => {
      if (e.key !== 'Enter' || !(e.ctrlKey || e.metaKey) || finestraAperta()) return;
      e.preventDefault();
      const avvia = $('#avvia');
      if (!avvia.disabled) avvia.click();
    });

    // Trascinare un link o un file dentro la finestra: e' il gesto naturale, e
    // senza questo resterebbe l'unica cosa che ci si aspetta e non funziona.
    let dentro = 0;
    const velo = $('#velo-trascina');
    window.addEventListener('dragenter', (e) => {
      e.preventDefault(); dentro++; velo.classList.add('visibile');
    });
    window.addEventListener('dragover', (e) => e.preventDefault());
    window.addEventListener('dragleave', () => {
      if (--dentro <= 0) { dentro = 0; velo.classList.remove('visibile'); }
    });
    window.addEventListener('drop', (e) => {
      e.preventDefault(); dentro = 0; velo.classList.remove('visibile');
      const testo = (e.dataTransfer.getData('text/uri-list')
                  || e.dataTransfer.getData('text/plain') || '').trim();
      if (!testo || !window.accettaTrascinato) return;
      // Chi trascina un link mentre guarda i crediti vuole trascriverlo: lo si
      // porta nella postazione, che e' quella del motore scelto.
      cambiaSezione(sezioneDiLavoro());
      window.accettaTrascinato(testo);
    });

    // Ultima riga: da qui l'interfaccia e' disegnata, tradotta e reattiva.
    // Toglierlo prima avrebbe scoperto un'interfaccia che non risponde ancora ai
    // clic, che e' peggio di un attimo di attesa in piu'.
    passoAvvio();                     // 6. risponde ai comandi: si puo' usare
    togliVelo();
  });
}

// Cio' che i file delle sezioni usano.
window.t = t;
window.$ = $;
window.$$ = $$;
window.avvisa = avvisa;
window.errore = errore;
window.statoVuoto = statoVuoto;
window.cambiaSezione = cambiaSezione;
window.salvaScelte = salvaScelte;
window.scelte = () => SCELTE;
