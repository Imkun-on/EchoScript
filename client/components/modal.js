/* La finestra modale, una sola, riempita di volta in volta.
 *
 * Perche' una sola
 *     I momenti in cui il programma deve fermarsi e chiedere sono sei: conferma
 *     di un video, conferma di una playlist, cosa fare di un video gia'
 *     trascritto, come proseguire una ripresa, crediti esauriti, e il riepilogo
 *     finale. Sei strutture separate vorrebbero dire sei posti in cui allineare
 *     la stessa animazione, lo stesso bordo, lo stesso tasto Esc. Qui c'e' una
 *     struttura e sei chiamate.
 *
 * Cosa NON fa
 *     Non decide niente. Riceve un titolo, dei pezzi di contenuto e un elenco di
 *     bottoni, e li mette al loro posto. Il significato — cosa vuol dire
 *     «Riprendi», quando offrirlo — sta nelle sezioni, che e' dove si capisce
 *     leggendo.
 *
 * Le briciole di costruzione (el, paragrafo, riquadro…) stanno qui e non in
 * app.js perche' servono soprattutto a riempire questa finestra, e tenerle
 * accanto a chi le usa risparmia un viaggio fra i file.
 */

/* Costruttore minimo di elementi: tag, classe, testo. Il testo passa SEMPRE per
 * textContent, mai per innerHTML: i titoli dei video arrivano da YouTube, e un
 * titolo con dentro un tag non deve poter diventare markup. */
function el(tag, classe, testo) {
  const nodo = document.createElement(tag);
  if (classe) nodo.className = classe;
  if (testo !== undefined && testo !== null) nodo.textContent = testo;
  return nodo;
}

function icona(nome, classe) {
  const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
  svg.setAttribute('viewBox', '0 0 24 24');
  svg.setAttribute('class', classe || 'icona');
  const uso = document.createElementNS('http://www.w3.org/2000/svg', 'use');
  uso.setAttribute('href', '#' + nome);
  svg.appendChild(uso);
  return svg;
}

function paragrafo(testo) {
  return el('p', '', testo);
}

/* Il riquadro con un percorso dentro: dove sono finiti i file, dove sta la
 * playlist. Il percorso resta selezionabile perche' la prima cosa che se ne fa
 * e' copiarlo. */
function riquadroPercorso(etichetta, percorso) {
  const box = el('div', 'riquadro-cartella');
  box.appendChild(el('div', 'etichetta-piccola', etichetta));
  box.appendChild(el('div', 'percorso', percorso));
  return box;
}

/* Una riga di dati «nome: valore», di quelle che riempiono le schede. */
function righeDati(righe) {
  const box = el('div', 'dati');
  righe.forEach((r) => {
    const dato = el('div', 'dato');
    dato.appendChild(el('span', 'dato-nome', r.nome + ':'));
    dato.appendChild(el('span', 'dato-valore', r.valore));
    box.appendChild(dato);
  });
  return box;
}

/* Una scelta cliccabile dentro la finestra: icona, titolo, spiegazione.
 * La finestra si chiude PRIMA di eseguire l'azione: se l'azione apre a sua
 * volta una finestra — succede — la vecchia deve essersene gia' andata. */
function voceScelta(voce, azione) {
  const bottone = el('button', 'voce-scelta' + (voce.tono === 'attenzione' ? ' attenzione' : ''));
  const riquadro = el('span', 'riquadro-icona');
  riquadro.appendChild(icona('i-' + (voce.icona || 'freccia')));
  bottone.appendChild(riquadro);

  const testo = el('span', 'testo');
  testo.appendChild(el('span', 'titolo', voce.titolo));
  if (voce.desc) testo.appendChild(el('span', 'desc', voce.desc));
  bottone.appendChild(testo);
  bottone.appendChild(icona('i-freccia', 'chevron'));

  bottone.addEventListener('click', () => { chiudiFinestra(); azione(voce); });
  return bottone;
}

/* ── La finestra ──────────────────────────────────────────────────────────── */

let _suChiusura = null;

function finestra(opzioni) {
  const velo = document.getElementById('velo-finestra');
  const riquadro = document.getElementById('finestra');
  const corpo = document.getElementById('finestra-corpo');
  const azioni = document.getElementById('finestra-azioni');

  riquadro.className = 'finestra' + (opzioni.tono ? ' ' + opzioni.tono : '');
  document.getElementById('finestra-titolo').textContent = opzioni.titolo || '';
  riquadro.querySelector('.finestra-testa .icona use')
    .setAttribute('href', '#i-' + (opzioni.icona || 'onda'));

  corpo.innerHTML = '';
  (opzioni.corpo || []).forEach((pezzo) => {
    if (pezzo === null || pezzo === undefined) return;
    corpo.appendChild(typeof pezzo === 'string' ? paragrafo(pezzo) : pezzo);
  });

  azioni.innerHTML = '';
  (opzioni.azioni || []).forEach((a) => {
    const bottone = el('button', 'bottone ' + (a.tono || 'contorno'));
    if (a.icona) bottone.appendChild(icona('i-' + a.icona));
    bottone.appendChild(el('span', '', a.testo));
    bottone.addEventListener('click', () => {
      // Chi non chiude esplicitamente resta aperto: serve al bottone «Apri la
      // cartella», che si preme e poi si torna a guardare il riepilogo.
      if (a.chiudi !== false) chiudiFinestra();
      if (a.azione) a.azione();
    });
    azioni.appendChild(bottone);
  });

  _suChiusura = opzioni.suChiusura || null;
  velo.classList.add('visibile');
  corpo.scrollTop = 0;
  // Il primo bottone prende il fuoco: chi ha appena letto ha le mani sulla
  // tastiera, e Invio deve fare la cosa piu' probabile.
  const primo = azioni.querySelector('.bottone.pieno') || azioni.querySelector('.bottone');
  if (primo) primo.focus();
}

function chiudiFinestra() {
  const velo = document.getElementById('velo-finestra');
  if (!velo.classList.contains('visibile')) return;
  velo.classList.remove('visibile');
  const chiusura = _suChiusura;
  _suChiusura = null;
  if (chiusura) chiusura();
}

function finestraAperta() {
  return document.getElementById('velo-finestra').classList.contains('visibile');
}

// Esc chiude, ed e' l'unico modo di uscire da una finestra senza scegliere:
// cliccare fuori no, perche' su una domanda importante — «ritrascrivo tutto?» —
// un clic distratto a lato non deve valere come risposta.
document.addEventListener('keydown', (e) => {
  if (e.key === 'Escape') chiudiFinestra();
});

window.el = el;
window.icona = icona;
window.paragrafo = paragrafo;
window.riquadroPercorso = riquadroPercorso;
window.righeDati = righeDati;
window.voceScelta = voceScelta;
window.finestra = finestra;
window.chiudiFinestra = chiudiFinestra;
window.finestraAperta = finestraAperta;
