"""EchoScript: il punto da cui parte tutto.

Cosa fa questo file
    Poco, ed e' voluto. Apre la finestra con dentro la pagina e avvia il giro
    degli eventi. Nient'altro.

    Il resto del programma sta in ``server/``, diviso per mestiere: chi risponde
    alla pagina in ``controllers/``, chi mette in fila il lavoro in
    ``services/``, chi lo esegue nelle altre cartelle. L'interfaccia sta in
    ``client/``, ed e' una pagina web normale.

Perche' l'interfaccia e' una pagina web
    Perche' Windows il motore per mostrarla ce l'ha gia' installato. L'aspetto
    sta nel CSS, la struttura nell'HTML, il comportamento in un file
    JavaScript per sezione, e Python fa solo da ponte verso il motore, che non
    cambia di una riga: ``server/services/pipeline.py`` e ``transcriber.py``
    non sanno nemmeno che esista un'interfaccia.

    L'interfaccia precedente era scritta con un motore grafico Python: un file
    solo da tremilaquattrocento righe in cui colori, testi, disposizione,
    finestre e orchestrazione stavano mescolati, e per spostare un bottone
    bisognava leggere il codice che lancia i thread. Adesso quelle cose stanno
    in file diversi, e non c'e' piu' nessun motore grafico da impacchettare:
    l'eseguibile dimagrisce di decine di megabyte.

Come parlano fra loro i due mondi
    In una direzione sola ciascuno, ed e' questo che tiene il tutto semplice:

      dalla pagina a Python   ``pywebview.api.nome(...)`` chiama direttamente
                              un metodo di ``Api``. Nessun protocollo, nessun
                              server, nessuna porta aperta sul computer.

      da Python alla pagina   ``bridge.verso_pagina(...)`` esegue una funzione
                              della pagina. Serve per cio' che arriva quando
                              vuole chi lo manda: righe di diario,
                              avanzamento, fine lavoro.
"""
from __future__ import annotations

import os
import sys
import threading

# La radice del progetto raggiungibile, cosi' `import transcriber` funziona sia
# lanciando i sorgenti sia da dentro l'eseguibile.
_QUI = os.path.dirname(os.path.abspath(__file__))
if _QUI not in sys.path:
    sys.path.insert(0, _QUI)

# ── Cosa si importa subito, e cosa no ─────────────────────────────
#
# Qui sotto ci sono soltanto cose leggere: i percorsi, i testi, il ponte con la
# finestra. Messe insieme costano meno di mezzo secondo.
#
# Il motore no. transcriber si porta dietro Groq, yt-dlp e Rich, e da solo
# prende cinque volte il tempo di tutto il resto: e' l'attesa vera, quella che
# chi ha fatto doppio clic si trova davanti. Importarlo qui vorrebbe dire
# restare senza niente sullo schermo per tutto quel tempo, perche' finche' un
# import non finisce non gira nessuna riga di programma e quindi non c'e'
# nessuno che possa disegnare un'attesa.
#
# Percio' si aspetta: la finestra si apre con quello che c'e', e il motore
# arriva da dietro. Lo carica carica_motore(), dentro api.py.

import webview

from server.config import i18n
from server.config.paths import risorsa as _risorsa
from server.config.strings import TESTI
from server.controllers import api, bridge

i18n.register(TESTI)


# ── L'avvio: cosa si vede, e in che ordine ───────────────────────────────────
#
# Chi fa doppio clic su un eseguibile aspetta diversi secondi mentre il
# contenuto viene riestratto in una cartella temporanea, e in quei secondi non
# gira una riga di questo file: se sullo schermo non compare niente, il doppio
# clic sembra non aver funzionato e se ne fa un altro, avviando due copie. La
# sequenza e' questa:
#
#   1. si importano solo le cose leggere: i percorsi, i testi, il ponte con
#      la finestra. Meno di mezzo secondo in tutto;
#   2. la finestra si apre SUBITO, a schermo intero, con dentro la pagina. Il
#      velo di caricamento la copre: stesso marchio, stesso viola, stesso nero
#      dell'icona del programma;
#   3. da dietro il velo si carica il motore, e a ogni pezzo caricato la barra
#      del velo avanza (vedi _carica_motore in cima al file);
#   4. la pagina chiede a Python i testi e le scelte. Quella richiesta aspetta
#      che il motore sia pronto, ed e' li' che i due tempi si incontrano;
#   5. il velo sfuma e sotto c'e' l'interfaccia.
#
# Il punto 2 e' quello che ha cambiato tutto. Prima la finestra restava
# nascosta e l'attesa la copriva un'immagine disegnata dall'avviatore di
# PyInstaller: misura fissa, mai riscalata, e come unica cosa animabile una
# riga di testo lunga diciannove caratteri. Una barra che puo' stare solo in
# diciannove punti si muove a scatti perche' non puo' fare altro, e un'immagine
# che non si riscala non puo' stare a schermo intero.
#
# Adesso quella schermata e' la pagina stessa, disegnata dal CSS: scorre
# davvero e si adatta a qualunque schermo.



def main() -> None:
    """Apre la finestra, e da li' in poi sta a guardare.

    E' tutto quello che questo file sa fare, di proposito. Crea la finestra,
    la consegna al ponte perche' chiunque altro possa raggiungerla, e avvia il
    giro degli eventi passando come primo lavoro il caricamento del motore.

    Da quel momento il programma e' guidato da fuori: la pagina chiede, i
    metodi di ``Api`` rispondono, i thread riferiscono. Qui non torna piu'
    niente finche' non si chiude la finestra.
    """
    # Il motore parte per primo, in un thread suo, prima ancora che esista una
    # finestra.
    #
    # La posizione l'ha decisa una misura, non un'intuizione. Consegnando il
    # caricamento a webview.start(), come si faceva prima, non partiva quando
    # la finestra compariva: partiva quando il motore grafico di Windows aveva
    # finito di inizializzarsi, e su questa macchina sono diciassette secondi.
    # Solo dopo cominciavano i due secondi scarsi di import. I due tempi
    # stavano in fila, uno dopo l'altro, e nessuno dei due sapeva dell'altro.
    #
    # Lanciandolo qui i due tempi si sovrappongono: mentre Windows prepara il
    # suo motore grafico, Python importa il proprio. Misurato su questa
    # macchina, dal doppio clic all'interfaccia usabile si e' passati da 20,7 a
    # 12,2 secondi, senza che cambiasse una riga di cio' che viene caricato.
    #
    # Si puo' fare perche' importare non ha bisogno di nessuna finestra. Gli
    # avanzamenti che il caricamento manda alla pagina prima che la pagina
    # esista vanno persi, e va bene cosi': bridge.verso_pagina se ne accorge e
    # non fa niente, e la barra riparte dal valore giusto appena c'e' qualcuno
    # che la guarda.
    #
    # daemon=True perche' non deve trattenere il programma alla chiusura: chi
    # chiude la finestra vuole che il programma finisca, non che aspetti la
    # fine di un import.
    threading.Thread(target=api.carica_motore, daemon=True).start()

    finestra = webview.create_window(
        'EchoScript',
        _risorsa('client', 'index.html'),
        js_api=api.Api(),
        # Massimizzata, non a schermo intero, e la differenza si vede subito.
        #
        # «Schermo intero» in pywebview vuol dire senza cornice: la finestra
        # copre tutto, compresa la barra delle applicazioni, e con la cornice
        # spariscono anche i tre pulsanti in alto a destra. Per un lettore
        # video va bene; per un programma con cui si lavora no, perche' per
        # chiuderlo o metterlo da parte bisogna sapere una scorciatoia da
        # tastiera.
        #
        # «Massimizzata» occupa lo stesso spazio ma resta una finestra normale:
        # barra del titolo, riduci a icona, ingrandisci, chiudi, e la barra
        # delle applicazioni sotto. Le misure qui sotto non sono un doppione,
        # sono quelle a cui torna quando la si rimpicciolisce.
        maximized=True,
        width=1180,
        height=800,
        min_size=(940, 640),
        # Il fondo della finestra prima che la pagina dipinga: il nero
        # violaceo del tema (--f1 in style.css). Con qualunque altro colore ogni
        # avvio comincerebbe con un lampo di un tema che non esiste piu'.
        background_color='#0a0a16',
        text_select=False,
        # Visibile subito. Prima restava nascosta perche' l'attesa la copriva
        # un'immagine disegnata da PyInstaller; adesso l'attesa e' dentro la
        # pagina, quindi la pagina deve vedersi. Il lampo bianco con cui
        # WebView2 dipinge se stesso prima di inizializzarsi non si vede lo
        # stesso, perche' il fondo della finestra e' gia' il nero del tema.
    )

    # Da adesso la finestra e' raggiungibile da chiunque debba parlare alla
    # pagina, senza che nessuno se la debba passare di mano in mano.
    bridge.imposta(finestra)

    # L'icona della finestra. Su Windows pywebview, se non gliela si passa, la
    # estrae dall'eseguibile: lanciando i sorgenti finirebbe quella di
    # python.exe, quindi gliela si indica sempre quando c'e'.
    icona = _risorsa('assets', 'EchoScript.ico')
    webview.start(icon=icona if os.path.isfile(icona) else None)



if __name__ == '__main__':
    main()
