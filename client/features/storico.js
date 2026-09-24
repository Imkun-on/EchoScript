/* Lo storico: una tabella con tutto quello che e' stato trascritto.
 *
 * Le colonne, nell'ordine
 *     URL, canale, video, durata (in minuti), crediti usati, singolo o
 *     playlist, stato (completo o a meta'), modo (Locale o Cloud), data. In
 *     fondo a ogni riga i gesti che servono: leggere il documento, aprire la
 *     cartella, togliere la riga.
 *
 * Chi decide cosa c'e' dentro
 *     Python, come sempre: e' lui che scrive una riga quando un lavoro finisce
 *     o si ferma, e che le ricostruisce dalle trascrizioni gia' salvate la
 *     prima volta. Qui si disegna, si filtra mentre si scrive nella casella di
 *     ricerca, e si passano a Python i clic.
 *
 * Perche' si rilegge a ogni ingresso
 *     Perche' i lavori finiscono mentre si guarda altro. Una tabella letta una
 *     volta all'avvio mostrerebbe a meta' un video che nel frattempo e' stato
 *     completato.
 */

let RIGHE_STORICO = [];

function initStorico() {
  $('#storico-cerca').placeholder = t('hist.search');
  $('#storico-cerca').addEventListener('input', disegnaStorico);
  $('#storico-aggiorna').addEventListener('click', apriStorico);
}

async function apriStorico() {
  if (!window.pywebview) return;
  const esito = await window.pywebview.api.storico();
  RIGHE_STORICO = (esito && esito.voci) || [];
  disegnaStorico();
}

/* Una cella di testo semplice. */
function cella(testo, classe) {
  const td = el('td', classe || '');
  td.appendChild(document.createTextNode(testo || ''));
  return td;
}

/* Un gesto in fondo alla riga: un bottoncino con un'icona e il suo titolo. */
function gesto(nome, titolo, azione) {
  const b = el('button', 'gesto');
  b.title = titolo;
  b.appendChild(icona(nome));
  b.addEventListener('click', azione);
  return b;
}

async function apriDaStorico(riga, cosa) {
  const esito = await window.pywebview.api.storico_apri(riga.id, cosa);
  if (esito && !esito.ok && esito.errore) errore(esito.errore);
}

function disegnaStorico() {
  const filtro = ($('#storico-cerca').value || '').trim().toLowerCase();
  const righe = RIGHE_STORICO.filter((r) => !filtro || [r.titolo, r.canale, r.playlist, r.url]
    .some((c) => (c || '').toLowerCase().includes(filtro)));

  const corpo = $('#storico-righe');
  corpo.innerHTML = '';
  righe.forEach((r) => {
    const tr = el('tr', r.completo ? '' : 'a-meta');

    // Il link si apre nel browser; un file locale apre la cartella che lo contiene.
    const tdUrl = el('td', 'col-url');
    const link = el('a', '', r.url || '—');
    link.href = '#';
    link.title = r.url || '';
    link.addEventListener('click', (e) => { e.preventDefault(); apriDaStorico(r, 'link'); });
    tdUrl.appendChild(link);
    tr.appendChild(tdUrl);

    tr.appendChild(cella(r.canale, 'col-canale'));
    tr.appendChild(cella(r.titolo, 'col-titolo'));
    tr.appendChild(cella(r.durata, 'col-numero'));
    tr.appendChild(cella(r.crediti, 'col-numero'));
    // Il tipo: video singolo, playlist o audio registrato (un file dal
    // disco). Il nome della playlist sta nel suggerimento, passandoci sopra.
    const tipo = r.playlist ? 'hist.playlist' : (r.locale ? 'hist.file' : 'hist.single');
    const tdTipo = cella(t(tipo), r.playlist ? 'col-playlist' : 'col-singolo');
    if (r.playlist) tdTipo.title = r.playlist;
    tr.appendChild(tdTipo);

    const tdStato = el('td');
    tdStato.appendChild(el('span', 'bollino ' + (r.completo ? 'ok' : 'attenzione'),
                           t(r.completo ? 'hist.done' : 'hist.half')));
    tr.appendChild(tdStato);

    const tdModo = el('td');
    const tono = r.modo === 'Locale' ? 'locale' : 'cloud';
    tdModo.appendChild(el('span', 'bollino ' + tono, r.modo));
    tr.appendChild(tdModo);

    tr.appendChild(cella(r.data, 'col-data'));

    const tdGesti = el('td', 'col-gesti');
    if (r.leggibile) tdGesti.appendChild(gesto('i-leggi', t('hist.read'), () => apriDaStorico(r, 'leggi')));
    tdGesti.appendChild(gesto('i-cartella', t('hist.folder'), () => apriDaStorico(r, 'cartella')));
    tdGesti.appendChild(gesto('i-togli', t('hist.remove'), async () => {
      const esito = await window.pywebview.api.storico_togli(r.id);
      RIGHE_STORICO = (esito && esito.voci) || [];
      disegnaStorico();
    }));
    tr.appendChild(tdGesti);
    corpo.appendChild(tr);
  });

  $('#storico-conta').textContent = t('hist.count', { n: righe.length });
  const vuoto = $('#storico-vuoto');
  vuoto.innerHTML = '';
  if (!righe.length) vuoto.appendChild(statoVuoto(t('hist.empty')));
}

window.initStorico = initStorico;
window.apriStorico = apriStorico;
