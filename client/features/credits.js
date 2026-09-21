/* Sezione «Crediti»: quanto audio e' gia' andato a Groq, e quanto ne resta.
 *
 * Perche' e' una sezione e non una finestra
 *     Perche' e' la risposta a «posso ancora trascrivere questo video oggi?», e
 *     quella domanda si fa prima di cominciare, non in mezzo a un'altra cosa.
 *     Una finestra la si apre, la si legge e la si chiude; una sezione ci si
 *     torna.
 *
 * Da dove arrivano i numeri
 *     Dalle richieste gia' fatte. Groq riporta negli header di ogni risposta
 *     quanto e' rimasto, e il motore se lo tiene: qui lo si rilegge e basta.
 *     Aprire questa sezione NON contatta Groq e non consuma alcun credito —
 *     che e' l'unico motivo per cui puo' esistere un bottone «Aggiorna» senza
 *     che premerlo costi qualcosa.
 */

function initCrediti() {
  $('#aggiorna-crediti').addEventListener('click', mostraCrediti);
  svuotaCrediti();

  // Entrando nella sezione i numeri si rileggono da soli: costa nulla, e
  // trovare dati vecchi di un'ora sarebbe peggio di non trovarne.
  document.querySelector('.voce[data-va="crediti"]')
    .addEventListener('click', mostraCrediti);
}

async function mostraCrediti() {
  const esito = await window.pywebview.api.crediti();
  if (!esito.ok) return;
  const box = $('#crediti');
  box.innerHTML = '';

  if (!esito.modelli.length) { svuotaCrediti(); return; }

  esito.modelli.forEach((m) => {
    const scheda = el('div', 'credito');

    const testa = el('div', 'credito-testa');
    testa.appendChild(el('span', 'credito-ruolo', m.ruolo));
    testa.appendChild(el('span', 'credito-modello', m.modello + '  ·  ' + m.aggiornato));
    scheda.appendChild(testa);

    // Un modello mai chiamato in questa sessione lo si dice esplicitamente:
    // una scheda vuota si leggerebbe come «zero crediti rimasti», che e'
    // l'opposto della verita'.
    if (m.nota) scheda.appendChild(el('div', 'credito-riga', m.nota));

    m.voci.forEach((v) => {
      const voce = el('div', 'credito-voce');
      voce.appendChild(el('div', 'credito-tipo', v.nome));
      voce.appendChild(el('div', 'credito-riga', v.usato));
      voce.appendChild(el('div', 'credito-riga forte', v.residuo));
      if (v.ripristino) voce.appendChild(el('div', 'credito-riga', v.ripristino));
      scheda.appendChild(voce);
    });

    box.appendChild(scheda);
  });
}

function svuotaCrediti() {
  const box = $('#crediti');
  box.innerHTML = '';
  box.appendChild(statoVuoto(t('lim.empty')));
}

/* Le schede sono composte da Python nella lingua corrente: cambiandola si
 * richiedono, invece di provare a tradurre qui frasi che contengono numeri. */
function traduciCrediti() {
  if ($('#crediti').querySelector('.credito')) mostraCrediti();
  else svuotaCrediti();
}

window.initCrediti = initCrediti;
window.traduciCrediti = traduciCrediti;
