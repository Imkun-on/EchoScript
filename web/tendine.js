/* Menu a tendina disegnati dalla pagina.
 *
 * Il perche' e' semplice: l'elenco che si apre da un <select> lo disegna il
 * sistema operativo, non la pagina. Nessuna riga di CSS puo' toccarlo, quindi
 * su un tema scuro si apre un rettangolo bianco di Windows in mezzo a tutto il
 * resto. L'unico modo di averlo del tema e' costruirlo.
 *
 * Come e' fatto, e perche' cosi'
 *     Il <select> vero non si butta: resta nella pagina, nascosto, e continua a
 *     essere la fonte della verita'. Sopra gli si mette un bottone e un pannello
 *     disegnati qui. Quando si sceglie una voce si aggiorna il <select> e si
 *     lancia il suo evento 'change'.
 *
 *     Il vantaggio e' che tutto il resto del programma non se ne accorge:
 *     ``$('#m-whisper').value`` continua a rispondere, i listener su 'change'
 *     continuano a scattare, e i file delle sezioni non cambiano di una riga.
 *
 * Chi riempie il <select> dopo
 *     I modelli arrivano da Python a finestra gia' aperta, e i ✓ dei modelli
 *     Ollama gia' scaricati arrivano ancora piu' tardi. Invece di chiedere a
 *     quel codice di avvisarci, un osservatore guarda le opzioni del <select>:
 *     se cambiano, il pannello si ridisegna da solo.
 */

function potenziaTendine() {
  document.querySelectorAll('select').forEach(potenzia);
}

function potenzia(select) {
  if (select.dataset.potenziato) return;
  select.dataset.potenziato = '1';

  const guscio = document.createElement('div');
  guscio.className = 'tendina';
  select.parentNode.insertBefore(guscio, select);
  guscio.appendChild(select);

  const bottone = document.createElement('button');
  bottone.type = 'button';
  bottone.className = 'tendina-testa campo';
  bottone.innerHTML = '<span class="tendina-valore"></span><span class="tendina-punta"></span>';
  guscio.appendChild(bottone);

  const pannello = document.createElement('div');
  pannello.className = 'tendina-pannello';
  document.body.appendChild(pannello);

  let aperto = false;
  let evidenziato = -1;

  const voci = () => Array.from(select.options);

  function mostraValore() {
    const scelta = select.options[select.selectedIndex];
    bottone.querySelector('.tendina-valore').textContent = scelta ? scelta.textContent : '';
    bottone.disabled = select.disabled;
  }

  function costruisci() {
    pannello.innerHTML = '';
    voci().forEach((o, i) => {
      const voce = document.createElement('button');
      voce.type = 'button';
      voce.className = 'tendina-voce' + (i === select.selectedIndex ? ' tendina-scelta' : '');
      voce.textContent = o.textContent;
      if (o.title) voce.title = o.title;
      voce.addEventListener('click', (e) => { e.stopPropagation(); scegli(i); });
      voce.addEventListener('mousemove', () => evidenzia(i));
      pannello.appendChild(voce);
    });
    mostraValore();
  }

  function evidenzia(i) {
    evidenziato = i;
    Array.from(pannello.children).forEach((v, k) =>
      v.classList.toggle('evidenziata', k === i));
    const v = pannello.children[i];
    if (v) v.scrollIntoView({ block: 'nearest' });
  }

  function scegli(i) {
    select.selectedIndex = i;
    // L'evento va lanciato a mano: cambiare selectedIndex da codice non ne
    // genera uno, e tutto il resto del programma ascolta 'change'.
    select.dispatchEvent(new Event('change', { bubbles: true }));
    mostraValore();
    chiudi();
  }

  function apri() {
    if (aperto || select.disabled) return;
    costruisci();
    aperto = true;
    guscio.classList.add('aperta');

    // Posizione fissa calcolata all'apertura: dentro il flusso il pannello
    // verrebbe tagliato dai contenitori che nascondono cio' che deborda.
    const r = bottone.getBoundingClientRect();
    const altezzaMax = Math.min(300, window.innerHeight - r.bottom - 16);
    const sopra = altezzaMax < 140 && r.top > 160;
    pannello.style.width = 'auto';
    pannello.style.minWidth = r.width + 'px';
    pannello.style.left = r.left + 'px';
    pannello.style.maxHeight = (sopra ? Math.min(300, r.top - 16) : altezzaMax) + 'px';
    if (sopra) {
      pannello.style.top = 'auto';
      pannello.style.bottom = (window.innerHeight - r.top + 6) + 'px';
    } else {
      pannello.style.bottom = 'auto';
      pannello.style.top = (r.bottom + 6) + 'px';
    }
    pannello.classList.add('visibile', sopra ? 'verso-alto' : 'verso-basso');

    // Se crescendo e' uscito dal bordo destro lo si riporta dentro: un elenco
    // tagliato a meta' e' peggio di uno stretto.
    const largo = pannello.getBoundingClientRect();
    if (largo.right > window.innerWidth - 12) {
      pannello.style.left = Math.max(12, window.innerWidth - 12 - largo.width) + 'px';
    }
    evidenzia(select.selectedIndex);
  }

  function chiudi() {
    if (!aperto) return;
    aperto = false;
    guscio.classList.remove('aperta');
    pannello.classList.remove('visibile', 'verso-alto', 'verso-basso');
  }

  bottone.addEventListener('click', (e) => { e.stopPropagation(); aperto ? chiudi() : apri(); });
  bottone.addEventListener('keydown', (e) => {
    if (['ArrowDown', 'ArrowUp', 'Enter', ' '].includes(e.key)) {
      e.preventDefault();
      if (!aperto) { apri(); return; }
    }
    if (!aperto) return;
    if (e.key === 'ArrowDown') evidenzia(Math.min(evidenziato + 1, voci().length - 1));
    else if (e.key === 'ArrowUp') evidenzia(Math.max(evidenziato - 1, 0));
    else if (e.key === 'Enter' || e.key === ' ') scegli(evidenziato);
    else if (e.key === 'Escape') chiudi();
  });

  document.addEventListener('click', chiudi);
  window.addEventListener('resize', chiudi);
  // Chi riempie il <select> dopo non deve ricordarsi di avvisare nessuno.
  new MutationObserver(() => { if (aperto) costruisci(); else mostraValore(); })
    .observe(select, { childList: true, subtree: true, characterData: true });

  mostraValore();
}

window.potenziaTendine = potenziaTendine;
