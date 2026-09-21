/* Il lavoro di una postazione: la sorgente, gli output aggiuntivi, la corsa.
 *
 * Il filo del discorso, in ordine:
 *
 *   1. si dice cosa trascrivere (un link, o un file) e si preme «Guarda cos'e'»;
 *   2. Python legge i metadati e la pagina chiede conferma, con la copertina,
 *      i dati e la stima davanti: e' l'unico momento in cui ci si accorge di
 *      aver incollato il link sbagliato PRIMA di spendere crediti;
 *   3. confermato, la scheda resta nel riquadro in fondo;
 *   4. «Trascrivi» chiede a Python se ci sono ostacoli (manca la chiave, il
 *      video c'e' gia', esiste un parziale) e a seconda della risposta parte o
 *      apre una finestra di scelte;
 *   5. mentre lavora parlano l'avanzamento e il diario;
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

function initTrascrivi(p) {
  // Gli interruttori partono da come erano l'ultima volta: sono scelte che si
  // fanno una volta e si tengono, non decisioni da ripetere a ogni video. Le
  // due stanze partono uguali e da qui in poi divergono.
  p.q('opt-translate').checked = !!p.opz.translate;
  p.q('opt-summarize').checked = !!p.opz.summarize;
  p.q('opt-visual').checked = !!p.opz.visual;
  [['opt-translate', 'translate'], ['opt-summarize', 'summarize'],
   ['opt-visual', 'visual']].forEach(([nome, chiave]) => {
    p.q(nome).addEventListener('change', (e) => {
      salvaScelte({ [chiave]: e.target.checked }, p);
      aggiornaCarte(p);
    });
  });

  p.q('sorgente').value = p.opz.sorgente || 'youtube';
  p.q('sorgente').addEventListener('change', (e) => {
    salvaScelte({ sorgente: e.target.value }, p);
    sincronizzaSorgente(p);
    dimentica(p);
  });
  sincronizzaSorgente(p);

  // Cambiare l'URL invalida la conferma precedente: e' il modo piu' facile di
  // trascrivere il video sbagliato, e con Groq costa anche crediti.
  p.q('url').addEventListener('input', () => dimentica(p));
  p.q('url').addEventListener('keydown',
    (e) => { if (e.key === 'Enter') leggiSorgente(p); });

  p.q('leggi').addEventListener('click', () => leggiSorgente(p));
  p.q('sfoglia').addEventListener('click', () => scegliFile(p));
  p.q('avvia').addEventListener('click', () => premiAvvia(p));

  svuotaScheda(p);
  aggiornaAvvio(p);
}

/* I due ingressi occupano lo stesso posto: si vede solo quello della sorgente
 * scelta, e il bottone «Guarda cos'e'» ha senso solo per un link: un file lo
 * si e' gia' visto scegliendolo. */
function sincronizzaSorgente(p) {
  const youtube = p.opz.sorgente !== 'local';
  p.q('ingresso-youtube').hidden = !youtube;
  p.q('ingresso-file').hidden = youtube;
  p.q('leggi').style.display = youtube ? '' : 'none';
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

async function dimentica(p) {
  if (!p.scheda) return;
  await window.pywebview.api.dimentica(p.dove);
  svuotaScheda(p);
  aggiornaAvvio(p);
  aggiornaCarte(p);
}

/* ── Leggere la sorgente ──────────────────────────────────────────────────── */

async function leggiSorgente(p) {
  const bottone = p.q('leggi');
  bottone.querySelector('span').textContent = t('src.load.loading');
  bottone.disabled = true;
  const esito = await window.pywebview.api.carica_info(p.q('url').value, p.dove);
  if (!esito.ok) { finiscoLettura(p); erroreDi(p, esito.errore); }
}

/* Su una playlist si sta parecchio: ogni video va letto uno per uno. Dirlo e'
 * la differenza fra un'attesa e un sospetto di blocco. */
ascolta('caricamentoPlaylist', (p) => {
  p.q('leggi').querySelector('span').textContent = t('src.load.playlist');
});

function finiscoLettura(p) {
  const bottone = p.q('leggi');
  bottone.querySelector('span').textContent = t('src.load');
  bottone.disabled = false;
}

ascolta('erroreSorgente', (p, messaggio) => {
  finiscoLettura(p);
  erroreDi(p, messaggio);
});

/* La conferma: copertina, dati, stima, e la domanda. Chiederla e' cio' che
 * evita di trascrivere il video sbagliato, che con Groq non e' solo tempo.
 *
 * Passa da finestraDi e non da finestra: leggere una playlist lunga richiede
 * parecchi secondi, e in quei secondi si puo' benissimo essere andati
 * nell'altra stanza a far partire un secondo lavoro. In quel caso la domanda
 * aspetta, invece di piombare addosso a chi sta facendo altro. */
ascolta('chiediConferma', (p, scheda) => {
  finiscoLettura(p);
  const playlist = scheda.tipo === 'playlist';
  finestraDi(p, {
    icona: playlist ? 'riassumi' : 'video',
    titolo: t(playlist ? 'playlist.title' : 'confirm.title'),
    corpo: [
      disegnaScheda(scheda, true),
      playlist ? t('playlist.question', { n: (scheda.voci || []).length })
               : t('confirm.question'),
    ],
    azioni: [
      { testo: t('comune.annulla'), tono: 'contorno', azione: () => dimentica(p) },
      { testo: t('comune.conferma'), tono: 'pieno', icona: 'spunta',
        azione: () => {
          mostraScheda(p, scheda);
          avvisa(playlist
            ? t('playlist.ok', { titolo: scheda.titolo, n: (scheda.voci || []).length })
            : t('confirm.ok', { titolo: scheda.titolo }), 'ok');
        } },
    ],
    // Chiudere con Esc e' come annullare: la sorgente non e' confermata, e
    // lasciarla valida sarebbe l'errore peggiore che questa finestra possa fare.
    suChiusura: () => { if (!p.scheda) dimentica(p); },
  });
});

async function scegliFile(p) {
  const esito = await window.pywebview.api.scegli_file(p.dove);
  if (!esito.ok) { erroreDi(p, esito.errore); return; }
  if (esito.annullato) return;
  p.q('file').value = esito.scheda.titolo;
  mostraScheda(p, esito.scheda);
}

/* Un link trascinato dentro la finestra vale come un link incollato, e vale
 * per la stanza in cui e' stato lasciato cadere. Un file trascinato no: il
 * percorso che il browser espone non e' quello vero del disco, e aprirlo
 * fallirebbe in silenzio: meglio dire di usare «Sfoglia». */
window.accettaTrascinato = (p, testo) => {
  if (!/^https?:/i.test(testo)) { avvisa(t('err.no_url'), 'fail'); return; }
  p.q('sorgente').value = 'youtube';
  salvaScelte({ sorgente: 'youtube' }, p);
  sincronizzaSorgente(p);
  p.q('url').value = testo;
  leggiSorgente(p);
};

/* ── Avviare ──────────────────────────────────────────────────────────────── */

/* Il bottone si accende solo quando si puo' davvero partire. Resta comunque
 * cliccabile quando non si puo': premendolo si scopre cosa manca, che e' piu'
 * utile di un bottone spento che non spiega perche'. */
function aggiornaAvvio(p) {
  const pronto = !!p.scheda && (p.motore !== 'groq' || window.chiaveCaricata());
  p.q('avvia').style.opacity = pronto ? '1' : '.55';
}

async function premiAvvia(p) {
  const esito = await window.pywebview.api.prepara(p.dove);
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

  if (esito.stato === 'gia' || esito.stato === 'ripresa') {
    finestra({
      icona: esito.stato === 'gia' ? 'riassumi' : 'clessidra',
      titolo: esito.titolo,
      corpo: [esito.desc, ...esito.voci.map(
        (v) => voceScelta(v, (scelta) =>
          window.pywebview.api.esegui(scelta.azione, p.dove)))],
      azioni: [{ testo: t('comune.annulla'), tono: 'contorno' }],
    });
    return;
  }

  window.pywebview.api.esegui('nuova', p.dove);
}

function riabilitaTrascrivi(p) {
  sincronizzaSorgente(p);
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
    bottone.addEventListener('click', () => window.pywebview.api.apri('visiva', p.dove));
    blocco.appendChild(bottone);
    corpo.push(blocco);
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
  svuotaScheda(p);
  aggiornaAvvio(p);
  aggiornaCarte(p);
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
      const riga = el('div', 'riga-video ' + v.tono);
      riga.appendChild(el('span', 'titolo', v.titolo));
      elenco.appendChild(riga);
    });
    corpo.push(elenco);
  }

  finestraDi(p, {
    icona: 'spunta', tono: 'riuscito', titolo: res.titolo, corpo,
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
 * diario e il suo avanzamento, nella stanza di prima. */
ascolta('creditiFiniti', (p, dati) => {
  const azioni = [{ testo: t('rate.later'), tono: 'contorno', icona: 'clessidra' }];
  if (dati.puo_locale) {
    azioni.push({ testo: t('rate.local'), tono: 'ambra', icona: 'casa',
                  azione: () => window.pywebview.api.continua_in_locale(p.dove) });
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
        azione: () => window.pywebview.api.concludi_in_locale(p.dove) },
    ],
  });
});

/* ── Riscrivere quello che non ha un data-t ───────────────────────────────── */

function riempiTrascrivi(p) {
  if (p.scheda) mostraScheda(p, p.scheda);
  else svuotaScheda(p);
  // La stima e' una frase composta da Python: gliela si richiede invece di
  // provare a comporla qui, dove il numero non c'e'.
  salvaScelte({}, p);
  sincronizzaSorgente(p);
}

window.initTrascrivi = initTrascrivi;
window.riempiTrascrivi = riempiTrascrivi;
window.riabilitaTrascrivi = riabilitaTrascrivi;
window.aggiornaAvvio = aggiornaAvvio;
window.mostraStima = mostraStima;
