"""La barra della schermata di avvio: dov'e', com'e' fatta, quanto e' piena.

Il problema che risolve
    Fra il doppio clic sull'eseguibile e la comparsa della finestra passano
    diversi secondi, e in quei secondi non gira una riga del programma: e' il
    bootloader di PyInstaller che carica l'interprete, poi Python che importa i
    moduli pesanti. Senza niente sullo schermo il doppio clic sembra non aver
    funzionato, se ne fa un altro, e partono due copie.

    La schermata di avvio copre quell'attesa, ma un'immagine ferma dice solo
    «sto facendo qualcosa», non «quanto manca». La barra dice quanto manca.

Perche' e' fatta di testo
    Perche' e' tutto cio' che si puo' muovere. La schermata di PyInstaller e'
    un'immagine immobile piu' UNA riga di testo aggiornabile da Python
    (``pyi_splash.update_text``): non c'e' modo di disegnarci sopra. Quindi la
    barra e' una fila di trattini pesanti U+2501 che in Consolas si attaccano
    l'uno all'altro senza stacchi, e formano una linea continua spessa tre
    pixel.

Le due meta' della barra
    Il BINARIO — la parte vuota — non e' testo: e' disegnato dentro
    ``assets/caricamento.png`` (vedi ``assets/marchio.py``). Cosi' c'e' dal
    primo istante, prima che esista un interprete Python che possa scrivere
    qualcosa, ed e' un rettangolo arrotondato vero invece di un ripiego fatto
    di caratteri.

    Il RIEMPIMENTO e' il testo, scritto sopra il binario mano a mano che
    l'avvio procede.

    C'e' anche un motivo tecnico per tenerli separati: il testo iniziale finisce
    dentro un file Tcl che Tcl 8.6 rilegge con la codifica di sistema, non in
    UTF-8, quindi un carattere non ASCII scritto li' comparirebbe come
    scarabocchio. Gli aggiornamenti successivi viaggiano invece su un canale
    dichiarato UTF-8, e sono sicuri. Il binario disegnato toglie di mezzo il
    problema: all'inizio non c'e' nessun testo da scrivere.

Perche' misura 190x3
    Perche' e' esattamente la barra del velo di caricamento che le succede
    dentro la pagina (``.avvio-barra`` in ``web/style.css``). Le due schermate
    si passano il turno a meta' avvio, e nell'istante dello scambio la barra
    deve restare dov'era: stessa larghezza, stesso spessore, stesso viola.
"""
from __future__ import annotations

# Il carattere e' a spaziatura fissa perche' la barra dev'essere larga uguale a
# se stessa a ogni aggiornamento: con un carattere proporzionale il riempimento
# cambierebbe larghezza a seconda di quanti trattini ha, e la barra si
# allungherebbe invece di riempirsi.
CARATTERE = 'Consolas'

# Corpo NEGATIVO: in Tcl/Tk un numero negativo sono pixel, uno positivo punti.
# Servono i pixel. L'immagine e' larga 440 pixel e non viene mai riscalata,
# mentre i punti crescono con i DPI dello schermo: su un monitor al 150% una
# barra misurata in punti sborderebbe dall'immagine.
CORPO = -18

# --lume, lo stesso viola con cui si riempie la barra del velo.
COLORE = '#a78bfa'

# ━ U+2501. Fra tutti i caratteri che disegnano una linea e' l'unico che in
# Consolas esiste davvero, si attacca al vicino senza stacchi e resta sottile:
# i blocchi di un ottavo (U+2581) non ci sono e verrebbero fuori come rettangoli
# vuoti, il blocco pieno e' alto quanto una riga di testo.
SEGNO = '━'

# Diciannove trattini a corpo 18 fanno 190 pixel esatti: la larghezza della
# barra del velo. Sono anche i passi in cui la barra si puo' muovere, e bastano:
# i momenti veri dell'avvio sono cinque o sei, non cento.
CELLE = 19

# Angolo in basso a sinistra del testo dentro l'immagine 440x260 (Tk ancora il
# testo a «sw»). Da questo punto il glifo disegna la linea tredici pixel piu' in
# alto, spessa tre: sono le righe su cui marchio.py disegna il binario, ed e'
# per questo che i due combaciano.
POSIZIONE = (125, 231)

# Il binario disegnato nell'immagine: x, y, larghezza, spessore. Deve stare
# dove il riempimento andra' a finire, altrimenti si vedrebbero due barre
# scalate di qualche pixel.
BINARIO = (125, 218, 190, 3)


def barra(quota: float) -> str:
    """Il riempimento della barra a ``quota`` (da 0 a 1), come riga di testo.

    A zero e' la stringa vuota: il binario disegnato resta scoperto, che e'
    esattamente come dev'essere una barra ancora ferma.
    """
    quota = 0.0 if quota < 0 else (1.0 if quota > 1 else quota)
    return SEGNO * round(CELLE * quota)
