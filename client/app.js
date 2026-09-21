/* Nucleo della pagina: testi, cambio sezione, diario, avvisi, avanzamento.
 *
 * Regola unica, valida anche per i tre file delle sezioni: qui non si decide
 * niente di importante. La pagina raccoglie cio' che si sceglie, lo passa a
 * Python, e mostra cio' che Python risponde. Ogni scelta vera (se un URL sia
 * una playlist, se un video sia gia' stato trascritto, quanto costera' un
 * lavoro, in quante fasi si divide) sta gia' nel motore, ed e' li' che deve
 * restare: duplicarla qui significherebbe due risposte diverse alla stessa
 * domanda.
 */

let TESTI = {};
// Nessuna, finche' l'avvio non apre quella del motore salvato.
let SEZIONE = '';

/* Le scelte dell'interfaccia: motore, modelli, interruttori. Vivono qui e in
 * Python, non nel documento, perche' Python le salva per la volta dopo e le
 * ritrova al prossimo avvio. */
let SCELTE = {};

const $ = (sel) => document.querySelector(sel);
const $$ = (sel) => Array.from(document.querySelectorAll(sel));

/* La frase che sta dietro una chiave, con i buchi riempiti.
 *
 * Una chiave che non esiste torna indietro cosi' com'e': a schermo si vede una
 * stringa strana, che e' brutta ma dice subito dove si e' sbagliato a scrivere.
 * Meglio di un'etichetta vuota, che non dice niente a nessuno. */
function t(chiave, valori) {
  let testo = TESTI[chiave];
  if (testo === undefined) testo = chiave;
  if (valori) {
    for (const [k, v] of Object.entries(valori)) testo = testo.split('{' + k + '}').join(v);
  }
  return testo;
}

/* Riempie di testo ogni elemento che porta un data-t.
 *
 * Si chiama una volta sola, all'avvio. Finche' c'erano due lingue serviva a
 * riscrivere la pagina intera a ogni cambio; adesso e' il riempimento
 * iniziale, e il nome e' rimasto quello perche' il lavoro che fa e' lo stesso. */
function riempiTesti() {
  $$('[data-t]').forEach((e) => { e.textContent = t(e.dataset.t); });
  // Due postazioni, quindi due volte tutto quello che riguarda il lavoro: due
  // spie, due diari, due riepiloghi. Il ciclo e' la forma piu' onesta di
  // dirlo, e aggiungere una terza stanza un giorno non richiederebbe di
  // tornare qui a scrivere una terza riga.
  Object.values(POSTI).forEach((p) => {
    p.q('stato').textContent = t('status.' + (p.stato || 'idle'));
    if (!p.q('diario').dataset.pieno) svuotaDiario(p);
    if (window.riempiMotore) window.riempiMotore(p);
    if (window.riempiTrascrivi) window.riempiTrascrivi(p);
    if (window.aggiornaCarte) window.aggiornaCarte(p);
  });
  aggiornaVoci();
}

/* ── Cambio sezione ───────────────────────────────────────────────────────── */

/* Cambiare sezione adesso e' solo cambiare stanza.
 *
 * Prima era anche un altro gesto travestito: entrando in «Cloud» si cambiava
 * la scelta del motore, e con essa la postazione unica si portava dietro tutto
 * quello che stava facendo. Adesso le postazioni sono due e stanno ferme
 * ciascuna nella sua: cambiare stanza non tocca piu' niente di quello che ci
 * sta dentro, e soprattutto non tocca l'altra.
 *
 * Il motore non si sceglie piu' da nessuna parte, perche' la stanza E' il
 * motore: in «Locale» si trascrive su questo computer, in «Cloud» sui server
 * Groq, e non c'e' piu' una seconda cosa che possa dire il contrario. */
function cambiaSezione(nome, immediato) {
  if (nome === SEZIONE && !immediato) return;
  const uscente = document.querySelector('.sezione.attiva');
  SEZIONE = nome;
  $$('.voce').forEach((v) => v.classList.toggle('attiva', v.dataset.va === nome));

  // Si ricorda in quale stanza si stava, per riaprirci il programma la volta
  // dopo. E' l'unica cosa che il cambio di stanza salva, ed e' una comodita':
  // non cambia niente di quello che le due postazioni stanno facendo.
  if (POSTI[nome] && SCELTE.motore !== MOTORE_DI[nome]) {
    SCELTE.motore = MOTORE_DI[nome];
    if (window.pywebview) window.pywebview.api.imposta({ motore: MOTORE_DI[nome] }, nome);
  }

  // Prima la sezione che se ne va sfuma e arretra, poi entra la nuova
  // dall'altro lato. Il ritardo e' quello dell'animazione di uscita, non un
  // numero scelto a caso.
  const entra = () => {
    $$('.sezione').forEach((s) => {
      s.classList.remove('uscita');
      s.classList.toggle('attiva', s.dataset.sez === nome);
    });
    // Se mentre si era di la' questa stanza aveva finito qualcosa, il suo
    // riepilogo ha aspettato fin qui: adesso si puo' aprire.
    apriSospeso(nome);
  };

  if (uscente && uscente.dataset.sez !== nome && !immediato) {
    uscente.classList.add('uscita');
    uscente.classList.remove('attiva');
    setTimeout(entra, 200);
  } else {
    entra();
  }
}

/* ── Il diario ────────────────────────────────────────────────────────────── */

/* Ogni postazione ha il suo diario, e le righe che arrivano portano scritto di
 * quale lavoro parlano: ci pensa __instrada a consegnarle qui con la postazione
 * giusta davanti. Mescolarli in uno solo, con due lavori insieme, avrebbe
 * prodotto una cronologia in cui nessuna riga si sa piu' a chi appartiene. */
ascolta('aggiungiRiga', (p, testo) => {
  const diario = p.q('diario');
  if (!diario.dataset.pieno) { diario.innerHTML = ''; diario.dataset.pieno = '1'; }
  const riga = el('div', 'riga-log ' + classeRiga(testo), testo);
  diario.appendChild(riga);
  // Si tiene solo la coda: una playlist di cinquanta video produce migliaia di
  // righe, e tenerle tutte nel documento rallenta lo scorrimento.
  while (diario.childElementCount > 400) diario.removeChild(diario.firstChild);
  diario.scrollTop = diario.scrollHeight;
});

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

function svuotaDiario(p) {
  const d = p.q('diario');
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
  avvisa(messaggio, 'fail');
}

/* Un errore che appartiene a un lavoro: oltre all'avviso a comparsa, che passa,
 * finisce nel diario di quella postazione, che resta. */
function erroreDi(p, messaggio) {
  window.__instrada(p.dove, 'aggiungiRiga', [messaggio]);
  avvisa(messaggio, 'fail');
}

/* ── Stato del lavoro ─────────────────────────────────────────────────────── */

/* Cosa si blocca mentre un lavoro gira, e perche' il blocco si ferma sulla
 * porta della stanza.
 *
 * Dentro la postazione che sta lavorando non si cambia piu' niente: ne' i
 * modelli, ne' la sorgente, ne' gli interruttori. Non e' una precauzione
 * formale: cambiare modello a meta' trascrizione darebbe un risultato che non
 * corrisponde a niente di quello che si vede scritto.
 *
 * Ma si ferma li'. L'altra stanza resta viva e si puo' preparare, avviare e
 * guardare: e' esattamente la ragione per cui le postazioni sono due. Prima il
 * blocco prendeva la pagina intera, e un lavoro in corso rendeva inerte anche
 * la meta' del programma che non c'entrava niente. */
ascolta('cambiaStato', (p, stato) => {
  p.stato = stato;
  p.q('spia').className = 'spia ' + (stato === 'idle' ? '' : stato);
  p.q('stato').textContent = t('status.' + stato);

  const inCorso = stato === 'working';

  // Il bottone principale dice cosa sta succedendo invece di limitarsi a
  // spegnersi.
  const testo = p.q('testo-avvia');
  testo.dataset.t = inCorso ? 'src.busy' : 'src.start';
  testo.textContent = t(testo.dataset.t);
  p.q('icona-avvia').setAttribute('href', inCorso ? '#i-clessidra' : '#i-avvia');

  p.tutti('.bottone.pieno, .bottone.contorno').forEach((b) => { b.disabled = inCorso; });
  p.tutti('.campo, .interruttore input').forEach((c) => { c.disabled = inCorso; });

  if (!inCorso) {
    p.piano = [];
    p.q('avanzamento').classList.remove('visibile');
    p.q('badge-batch').hidden = true;
    if (window.riabilitaTrascrivi) window.riabilitaTrascrivi(p);
  }
  aggiornaVoci();
});

/* Un lavoro comincia: si sa gia' quali fasi ci saranno, chi le fara' e cosa
 * produrranno. Dirlo tutto in anticipo e' cio' che trasforma un'attesa muta in
 * un'attesa che si capisce. */
ascolta('iniziaLavoro', (p, dati) => {
  p.piano = dati.piano || [];
  p.q('avanzamento').classList.add('visibile');
  p.q('barra').style.width = '0%';
  p.q('avanz-pct').textContent = '0%';
  p.q('avanz-fase').textContent = t('phase.default');
  p.q('avanz-dettaglio').textContent = '';
  p.q('racconto-testo').textContent = t('narr.info');
  p.q('racconto-piano').textContent = t('prog.plan') + ' ' + dati.frase;

  const motore = p.q('badge-motore');
  motore.className = 'targhetta-motore ' + (dati.tono || '');
  motore.textContent = dati.motore || '';

  const nota = p.q('badge-nota');
  nota.textContent = dati.nota || '';
  nota.hidden = !dati.nota;

  disegnaPassi(p, -1);
  aggiornaVoci();
});

/* I passaggi: quelli fatti spuntati, quello in corso acceso, gli altri spenti.
 * E' la sola cosa che dice quanto manca alla FINE e non solo alla fase. */
function disegnaPassi(p, corrente) {
  const box = p.q('passi');
  box.innerHTML = '';
  p.piano.forEach((fase, i) => {
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
ascolta('avanzaLavoro', (p, fase, indice, fasi, globale, dettaglio) => {
  if (globale !== null && globale !== undefined) {
    p.q('barra').style.width = (Math.max(0, Math.min(1, globale)) * 100).toFixed(1) + '%';
    p.q('avanz-pct').textContent = Math.round(globale * 100) + '%';
  }
  const nome = TESTI['phase.' + fase] ? t('phase.' + fase) : t('phase.default');
  p.q('avanz-fase').textContent = nome;
  p.q('avanz-dettaglio').textContent = dettaglio || '';

  if (TESTI['narr.' + fase]) p.q('racconto-testo').textContent = t('narr.' + fase);

  const badge = p.q('badge-fase');
  if (indice >= 0) {
    badge.hidden = false;
    badge.textContent = t('prog.phase', { i: indice + 1, n: fasi });
    disegnaPassi(p, indice);
  } else {
    badge.hidden = true;
  }
});

/* La playlist: quale video, di quanti. Il resto del pannello racconta gia' cosa
 * sta succedendo a QUESTO video, quindi qui basta dire quale sia. */
ascolta('lavoroBatch', (p, conteggio, titolo) => {
  const badge = p.q('badge-batch');
  badge.hidden = false;
  badge.textContent = conteggio + '  ·  ' + titolo;
});

ascolta('erroreLavoro', (p, messaggio) => {
  window.__instrada(p.dove, 'cambiaStato', ['error']);
  window.__instrada(p.dove, 'aggiungiRiga', [messaggio]);
  finestraDi(p, {
    icona: 'errore', tono: 'errore', titolo: t('err.title'),
    corpo: [messaggio || t('err.unknown')],
    azioni: [{ testo: t('comune.chiudi'), tono: 'pieno', icona: 'spunta' }],
  });
});

/* ── Le scelte, ricordate ─────────────────────────────────────────────────── */

/* Ogni modifica va anche a Python, che la salva e rispedisce la stima
 * aggiornata: il costo cambia col modello, e vederlo cambiare nell'istante in
 * cui si sceglie e' meta' del motivo per cui la stima esiste.
 *
 * La postazione da cui arriva la scelta viaggia insieme alla scelta, perche'
 * non tutte valgono per tutto il programma. I modelli si', sono le stesse sei
 * tendine da qualunque stanza le si guardi. La sorgente e i tre interruttori
 * no: appartengono alla stanza in cui sono stati toccati, e spuntare
 * «riassunto» in «Cloud» non deve spuntarlo anche di la'.
 *
 * Anche la stima torna indietro con l'indirizzo, ed e' il motivo per cui la si
 * rimette a schermo nella postazione giusta invece che «nella pagina»: la
 * stessa sorgente vista da «Locale» costa un tempo e vista da «Cloud» costa
 * dei soldi, e sono due numeri veri che convivono. */
async function salvaScelte(valori, p) {
  p = p || posto();
  Object.assign(SCELTE, valori);
  Object.assign(p.opz, valori);
  const esito = await window.pywebview.api.imposta(valori, p.dove);
  if (esito && esito.ok && window.mostraStima) window.mostraStima(p, esito.stima);
}

/* ── Avvio ────────────────────────────────────────────────────────────────── */

const T_AVVIO = performance.now();

/* La barra del velo, e perche' e' fatta di due pezzi.
 *
 * Il velo copre TUTTO l'avvio, dal primo istante in cui la finestra compare
 * fino a quando l'interfaccia e' usabile. Ma in quell'intervallo succedono due
 * cose diverse, e nessuna delle due sa niente dell'altra:
 *
 *   da 0 a 0.80   Python carica il motore. La pagina non ha modo di sapere a
 *                 che punto sia, quindi e' Python a dirglielo chiamando
 *                 avanzamentoAvvio() (vedi _carica_motore in EchoScriptApp.py);
 *
 *   da 0.80 a 1   la pagina si monta da se': chiede i testi, riempie le
 *                 sezioni, apre la stanza giusta. Qui i passi sono un elenco
 *                 chiuso e noto, quindi si contano.
 *
 * La barra e' una sola e non torna mai indietro, da qualunque delle due parti
 * arrivi il numero. */
const BASE_PAGINA = 0.80;
const PASSI_AVVIO = 5;
let passiFatti = 0;

/* Le tre quote della barra, e perche' non bastava una.
 *
 * `mostrata`  dov'e' disegnata adesso, e cambia a ogni fotogramma;
 * `vera`      l'ultimo traguardo raggiunto davvero;
 * `tetto`     fin dove le si lascia strisciare mentre aspetta il prossimo.
 *
 * Il tetto e' l'unica cosa che rende la barra scorrevole invece che a scatti.
 * Fra un traguardo e l'altro possono passare due o tre secondi, e in quei
 * secondi una barra onesta resterebbe immobile: ma una barra immobile, a chi
 * la guarda, non dice "sto lavorando", dice "mi sono piantato". Cosi' a ogni
 * traguardo il tetto viene messo un quarto piu' avanti di dove si e' arrivati,
 * e la barra ci scivola dentro rallentando.
 *
 * Il tetto non viene mai raggiunto, perche' l'avvicinamento e' proporzionale a
 * quanto manca: piu' si avvicina, piu' va piano. Quindi la barra e' sempre in
 * movimento e non supera mai un traguardo che non e' stato tagliato. */
let quotaMostrata = 0;
let quotaVera = 0;
let quotaTetto = 0;

function traguardo(q) {
  if (q <= quotaVera) return;         // mai indietro
  quotaVera = Math.min(q, 1);
  quotaTetto = quotaVera + (1 - quotaVera) * 0.25;
}

function animaBarra() {
  quotaMostrata += (quotaTetto - quotaMostrata) * 0.035;
  const b = document.querySelector('.avvio-barra span');
  if (b) b.style.width = (quotaMostrata * 100).toFixed(2) + '%';
  if (quotaMostrata < 0.999) requestAnimationFrame(animaBarra);
}

/* Python dice a che punto e' il caricamento del motore. Il numero arriva
 * gia' nella scala di questa barra: la sua ultima tappa vale esattamente
 * BASE_PAGINA, cioe' il punto in cui il racconto passa da Python alla
 * pagina. Le due meta' si toccano li' senza salti. */
window.avanzamentoAvvio = (quota) => traguardo(quota);

function passoAvvio() {
  passiFatti = Math.min(passiFatti + 1, PASSI_AVVIO);
  traguardo(BASE_PAGINA + (1 - BASE_PAGINA) * (passiFatti / PASSI_AVVIO));
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
  /* La barra comincia a muoversi subito, prima ancora che ci sia qualcosa da
   * raccontare. Il primo traguardo e' piccolo di proposito: serve solo a dare
   * al tetto un valore diverso da zero, perche' con tetto a zero la barra
   * resterebbe ferma e il primo fotogramma del velo sarebbe immobile. */
  traguardo(0.03);
  requestAnimationFrame(animaBarra);

  /* Se l'apertura si inceppa, per esempio un import fallito o una chiamata che
   * non torna, il velo deve comunque andarsene: meglio un'interfaccia a meta',
   * che si vede e si puo' chiudere, di una schermata di caricamento perpetua.
   *
   * Settantacinque secondi e non dodici come prima, perche' adesso sotto il
   * velo c'e' anche il caricamento del motore: al primo avvio dopo
   * l'installazione Windows deve leggere qualche centinaio di megabyte da
   * disco, e su una macchina lenta dodici secondi non bastano. Questa e' una
   * rete di sicurezza, non una scadenza: deve scattare solo quando qualcosa si
   * e' rotto davvero. */
  setTimeout(togliVelo, 75000);
  passoAvvio();                       // 1. la pagina e i suoi script ci sono

  window.addEventListener('pywebviewready', async () => {
    passoAvvio();                     // 2. il ponte con Python risponde
    const dati = await window.pywebview.api.avvio();
    passoAvvio();                     // 3. testi, scelte e modelli sono arrivati

    TESTI = dati.testi;
    SCELTE = dati.scelte;

    // Le due postazioni si costruiscono QUI, prima di ogni altra cosa che le
    // riguardi. Tutto quello che viene dopo va a cercare i pezzi del lavoro
    // dentro una postazione: se non esistessero ancora, ogni ricerca tornerebbe
    // a mani vuote e l'interfaccia si monterebbe sopra il niente.
    creaPosti();
    Object.values(POSTI).forEach((p) => {
      // Le due stanze partono dalle stesse abitudini dell'ultima volta e da qui
      // divergono: e' Python a tenerle, ed e' Python che le ha appena mandate.
      p.opz = {
        sorgente: SCELTE.sorgente, translate: SCELTE.translate,
        summarize: SCELTE.summarize, visual: SCELTE.visual,
      };
      if (window.initMotore) window.initMotore(p, dati);
      if (window.initTrascrivi) window.initTrascrivi(p);
      // I riquadri per ultimi: riassumono quello che i due qui sopra hanno
      // appena messo a posto, quindi devono leggere una situazione gia' pronta.
      if (window.initCarte) window.initCarte(p);
    });
    passoAvvio();                     // 4. le due sezioni sono pronte

    riempiTesti();
    if (window.potenziaTendine) window.potenziaTendine();
    passoAvvio();                     // 5. ogni etichetta ha il suo testo

    // Si riapre nella stanza in cui si lavorava l'ultima volta. E' l'unica
    // cosa che il motore salvato decide ancora: non piu' con che cosa si
    // trascrive, che adesso lo dice la stanza, ma solo quale delle due aprire
    // per prima.
    cambiaSezione(SCELTE.motore === 'groq' ? 'cloud' : 'locale', true);
    Object.values(POSTI).forEach((p) => {
      window.__instrada(p.dove, 'cambiaStato', ['idle']);
      p.q('svuota').addEventListener('click', () => svuotaDiario(p));
    });

    $$('.voce[data-va]').forEach((v) =>
      v.addEventListener('click', () => cambiaSezione(v.dataset.va)));

    // Ctrl+Invio avvia la trascrizione della stanza che si sta guardando: chi
    // ha appena riempito il modulo ha le mani sulla tastiera, non sul mouse.
    // Della stanza che si guarda e non di tutte e due, perche' una scorciatoia
    // che fa partire un lavoro che non si sta vedendo e' una trappola.
    document.addEventListener('keydown', (e) => {
      if (e.key !== 'Enter' || !(e.ctrlKey || e.metaKey) || finestraAperta()) return;
      e.preventDefault();
      const avvia = posto().q('avvia');
      if (avvia && !avvia.disabled) avvia.click();
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
      // Il link trascinato va nella stanza che si sta guardando, che e' quella
      // in cui e' stato lasciato cadere. Prima veniva portato «dove sta il
      // motore scelto», che con una postazione sola era l'unico posto
      // possibile; adesso i posti sono due e quello giusto e' dove ha mirato
      // la mano.
      window.accettaTrascinato(posto(), testo);
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
window.erroreDi = erroreDi;
window.statoVuoto = statoVuoto;
window.cambiaSezione = cambiaSezione;
window.salvaScelte = salvaScelte;
window.scelte = () => SCELTE;
