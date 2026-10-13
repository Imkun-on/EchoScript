/* Le due postazioni di lavoro, e come si fa a non confonderle.
 *
 * Cosa sono
 *     «Locale» e «Cloud» sono due scrivanie vere e indipendenti. Ognuna ha la
 *     sua sorgente, i suoi interruttori e il suo avanzamento, e in tutte e due
 *     puo' esserci un lavoro in corso nello stesso momento:
 *     mentre Groq trascrive sui suoi server, questo computer puo' trascriverne
 *     un altro per conto suo. Sono due mestieri che non si contendono niente,
 *     e farli aspettare a turno sarebbe stato buttare via meta' del tempo.
 *
 * Com'era prima, e perche' non andava
 *     C'era una postazione sola, che traslocava nella stanza aperta. Avviando
 *     una trascrizione in nuvola e passando poi in locale, in locale ci si
 *     trovava davanti l'avanzamento e la sorgente di quello che
 *     stava girando di la'. Le due stanze erano due porte sulla stessa
 *     scrivania, e la seconda non si poteva usare finche' la prima era
 *     occupata.
 *
 * Come si tengono separate
 *     Ogni copia porta davanti a ogni identificatore il nome della sua stanza.
 *     «url» diventa «locale-url» e «cloud-url»: sono due caselle diverse, e non
 *     esiste piu' un modo di scriverle che possa colpire quella sbagliata per
 *     distrazione. Chi vuole un pezzo di una postazione lo chiede alla
 *     postazione, con p.q('url'), e non c'e' nessun'altra strada.
 *
 * Come fa il motore a parlare alla stanza giusta
 *     Tutto quello che Python ha da dire arriva da un'unica porta, __instrada,
 *     con l'indirizzo davanti. Qui si guarda l'indirizzo e si consegna. Una
 *     percentuale di avanzamento senza quel dato non vorrebbe dire niente: e'
 *     come gridare «sono all'ottanta per cento» in una stanza con due lavagne.
 */

/* Ogni stanza ha il suo motore, e non e' piu' una scelta a parte: lavorare in
 * «Cloud» E' scegliere Groq. Prima esistevano tutte e due le cose, la stanza e
 * la scelta, e potevano contraddirsi. */
const MOTORE_DI = { locale: 'local', cloud: 'groq' };

/* Cosa si toglie a ciascuna copia dopo averla fatta.
 *
 * Le due postazioni nascono dallo stesso stampo ma non restano identiche.
 * Ognuna tiene solo i modelli del proprio motore, perche' le tendine sono sei
 * in tutto e non dodici: averle doppie vorrebbe dire due copie della stessa
 * scelta da tenere allineate, e prima o poi disallineate.
 *
 * La chiave resta soltanto in «Cloud», che e' l'unica stanza in cui si paga
 * qualcosa. In locale sarebbe un blocco del pannello delle opzioni messo li'
 * per dire che non c'e' niente da fare. */
const DA_POTARE = {
  locale: ['#modulo-modelli-cloud', '#carta-chiave'],
  cloud:  ['#modulo-modelli-locale'],
};

const POSTI = {};

/* ── Una postazione ───────────────────────────────────────────────────────── */

function Posto(dove, radice) {
  this.dove = dove;
  this.motore = MOTORE_DI[dove];
  this.radice = radice;

  /* La sorgente confermata qui dentro. Vive nella postazione e non in una
   * variabile sola del file perche' le due stanze possono avere due video
   * diversi pronti a partire, ed e' proprio il punto di tutto questo. */
  this.scheda = null;

  /* Il piano del lavoro in corso: l'elenco delle fasi previste. Vuoto quando
   * non si lavora. */
  this.piano = [];

  this.stato = 'idle';

  /* Le opzioni del riassunto, che si decidono video per video: si puo'
   * volere un riassunto breve di quello che gira in nuvola ed esteso di quello
   * che gira qui. */
  this.opz = {};

  /* Una finestra che ha qualcosa da dire a questa stanza mentre si sta
   * guardando l'altra. Vedi finestraDi(), qui sotto. */
  this.sospeso = null;

  /* Quanto e' stato fatto della fase in corso, da 0 a 1, o null quando non si
   * sa. Lo ripete la barra di stato, che si vede da tutte e due le stanze. */
  this.quota = null;
}

/* Il pezzo di QUESTA postazione che si chiama cosi'.
 *
 * E' l'unico modo di arrivare a un elemento del lavoro, e l'unico che non
 * possa prendere quello dell'altra stanza. Il nome si scrive nudo, «url», e
 * il prefisso lo mette questa funzione: chi scrive il codice non deve
 * ricordarsi niente. */
Posto.prototype.q = function (nome) {
  return document.getElementById(this.dove + '-' + nome);
};

/* Tutti i pezzi di questa postazione che corrispondono a un selettore.
 * Cerca DENTRO la postazione, quindi non puo' uscirne. */
Posto.prototype.tutti = function (sel) {
  return Array.from(this.radice.querySelectorAll(sel));
};

Posto.prototype.lavora = function () { return this.stato === 'working'; };

/* Il nome leggibile della stanza, quello scritto nella testata. */
Posto.prototype.nome = function () { return t('menu.' + this.dove); };

/* ── Costruire le due copie ───────────────────────────────────────────────── */

/* Fa le due postazioni vere a partire dal modello, e le mette nelle stanze.
 *
 * L'ordine dei due gesti conta, e non e' scambiabile: prima si pota e poi si
 * mettono i prefissi. Potare cerca i pezzi col loro nome nudo, quello scritto
 * nella pagina, che dopo il prefisso non esiste piu'. Invertendoli, le due
 * copie resterebbero intere e ciascuna si ritroverebbe i modelli dell'altra. */
function creaPosti() {
  const modello = document.getElementById('modello-postazione');
  Object.keys(MOTORE_DI).forEach((dove) => {
    const radice = modello.content.firstElementChild.cloneNode(true);

    DA_POTARE[dove].forEach((sel) => {
      const via = radice.querySelector(sel);
      if (via) via.remove();
    });

    // L'intestazione e' la stessa per tutte e due e la riempie la stanza: la
    // sua icona, e le chiavi dei tre testi, che poi riempiTesti() traduce
    // insieme a tutti gli altri.
    const stanza = document.querySelector('.sezione[data-sez="' + dove + '"]');
    radice.querySelector('#simbolo-uso').setAttribute('href', '#' + stanza.dataset.icona);
    [['occhiello', 'occhiello'], ['titolo', 'title'], ['intro', 'desc']].forEach(([id, coda]) => {
      radice.querySelector('#' + id).dataset.t = 'sez.' + dove + '.' + coda;
    });

    radice.querySelectorAll('[id]').forEach((e) => { e.id = dove + '-' + e.id; });

    stanza.appendChild(radice);
    POSTI[dove] = new Posto(dove, radice);
  });
}

/* La postazione della stanza che si sta guardando. La usano i gesti fatti col
 * mouse, che per definizione avvengono in quella che si ha davanti. */
function posto() { return POSTI[SEZIONE] || POSTI.locale; }

/* ── La porta da cui entra tutto quello che dice Python ───────────────────── */

const EVENTI = {};

function ascolta(nome, funzione) { EVENTI[nome] = funzione; }

/* L'unica porta. Python chiama sempre questa, con l'indirizzo davanti, e qui
 * si consegna alla postazione giusta.
 *
 * Un nome sconosciuto viene lasciato cadere in silenzio invece di dare errore:
 * un motore piu' nuovo della pagina puo' raccontare cose che questa versione
 * non sa ancora disegnare, e in quel caso la cosa giusta e' non disegnarle,
 * non fermare tutto. */
window.__instrada = (dove, nome, argomenti) => {
  const p = POSTI[dove];
  const funzione = EVENTI[nome];
  if (!p || !funzione) return;
  funzione.apply(null, [p].concat(argomenti || []));
};

/* ── Le finestre che riguardano una stanza sola ───────────────────────────── */

/* Apre una finestra a nome di una postazione, ma solo se la si sta guardando.
 *
 * Il problema che risolve
 *     La finestra modale e' una sola e copre tutto lo schermo. Con due lavori
 *     insieme, quello che finisce per primo aprirebbe il suo riepilogo davanti
 *     alla faccia di chi sta ancora preparando l'altro, in una stanza che non
 *     c'entra niente. Peggio: chiuderebbe la finestra che quella persona aveva
 *     aperto in quel momento.
 *
 * Cosa si fa invece
 *     Se la stanza non e' quella che si sta guardando, la finestra aspetta.
 *     Intanto si dice con un avviso che di la' e' successo qualcosa, il puntino
 *     sulla sua icona si accende e nella testata compare la pillola che ci
 *     porta. Entrando in quella stanza, la finestra si apre.
 *
 *     Cosi' il lavoro in parallelo e' davvero in parallelo: quello che succede
 *     di la' si viene a sapere subito, ma non interrompe quello che si sta
 *     facendo di qua. Si va a vedere quando si ha voglia. */
function finestraDi(p, opzioni) {
  if (p.dove === SEZIONE) { finestra(opzioni); return; }
  p.sospeso = opzioni;
  aggiornaVoci();
  avvisa(t('posti.altrove', { stanza: p.nome() }), opzioni.tono === 'errore' ? 'fail' : 'ok');
}

/* Entrando in una stanza, si guarda se c'era qualcosa da leggere.
 *
 * Il rinvio di un attimo serve a far finire l'animazione di entrata: una
 * finestra che compare mentre la stanza sotto sta ancora scivolando dentro si
 * vede come uno strappo. */
function apriSospeso(dove) {
  const p = POSTI[dove];
  if (!p || !p.sospeso) return;
  const opzioni = p.sospeso;
  p.sospeso = null;
  aggiornaVoci();
  setTimeout(() => finestra(opzioni), 260);
}

/* ── Le voci della colonna, la testata, la barra di stato ─────────────────── */

/* Ogni voce dice cosa sta facendo la sua stanza, senza bisogno di entrarci.
 *
 * E' un puntino sull'icona, e a riposo non c'e': blu che pulsa se li' dentro
 * si lavora, rosso se un lavoro e' caduto, ambra se c'e' qualcosa da leggere.
 * E' proprio l'informazione che serve mentre si lavora in parallelo, ed e'
 * quella che si vuole senza dover cambiare stanza per averla. */
function aggiornaVoci() {
  Object.keys(MOTORE_DI).forEach((dove) => {
    const p = POSTI[dove];
    const segno = $('#targhetta-' + dove);
    if (!p || !segno) return;

    let tono = 'spenta';
    let testo = '';
    if (p.sospeso) { tono = 'sospesa'; testo = t('posti.attesa'); }
    else if (p.stato === 'working') { tono = 'lavora'; testo = t('posti.lavoro'); }
    else if (p.stato === 'error') { tono = 'guasto'; testo = t('posti.errore'); }

    segno.className = 'targhetta-menu ' + tono;
    segno.textContent = testo;
  });
  aggiornaCornice();
}

/* Lo stesso, detto per esteso: nella testata la pillola che porta alla stanza
 * di cui c'e' da sapere qualcosa, in fondo la barra di stato.
 *
 * La pillola sceglie una stanza sola, in quest'ordine: quella che ha un
 * riepilogo da far leggere, poi quella che lavora mentre si guarda l'altra,
 * poi quella che lavora e basta.
 *
 * La barretta in fondo ripete la percentuale della fase in corso, ma solo
 * quando a lavorare e' una stanza sola: con due insieme un numero unico non
 * sarebbe di nessuna delle due. */
function aggiornaCornice() {
  const posti = Object.values(POSTI);
  const lavorano = posti.filter((p) => p.lavora());
  const sospeso = posti.find((p) => p.sospeso);
  const meta = sospeso || lavorano.find((p) => p.dove !== SEZIONE) || lavorano[0];

  const pillola = $('#pillola-lavori');
  pillola.hidden = !meta;
  pillola.classList.toggle('sospesa', !!sospeso);
  pillola.dataset.va = meta ? meta.dove : '';
  $('#pillola-testo').textContent = !meta ? ''
    : sospeso ? t('posti.altrove', { stanza: sospeso.nome() })
              : t('testata.lavoro') + '  ·  ' + meta.nome();

  $('#stato-testo').textContent = lavorano.length
    ? t('testata.lavoro') + '  ·  ' + lavorano.map((p) => p.nome()).join(t('comune.e'))
    : t('stato.pronto');
  $('#stato-punto').classList.toggle('lavora', lavorano.length > 0);

  const quota = lavorano.length === 1 ? lavorano[0].quota : null;
  const noto = quota !== null && quota !== undefined;
  $('#stato-avanzo').hidden = !noto;
  if (noto) {
    $('#stato-cursa').style.width = (quota * 100).toFixed(1) + '%';
    $('#stato-percento').textContent = Math.round(quota * 100) + '%';
  }
}

window.creaPosti = creaPosti;
window.posto = posto;
window.apriSospeso = apriSospeso;
window.aggiornaVoci = aggiornaVoci;
window.aggiornaCornice = aggiornaCornice;
window.finestraDi = finestraDi;
window.ascolta = ascolta;
