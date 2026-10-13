"""Le frasi che finiscono sotto gli occhi di chi usa il programma.

A cosa serve
    Tenere in un posto solo tutto il testo visibile, invece di averlo sparso
    dentro il codice che lo mostra. Chi scrive il programma chiama
    ``t('chiave')`` e non si preoccupa di come sia scritta la frase; chi vuole
    cambiare una parola apre ``strings.py`` e la cambia li', senza andare a
    cercare in quale funzione era finita.

    Il vantaggio si vede soprattutto per la pagina: riceve TUTTE le frasi in un
    colpo solo all'avvio e poi riempie da se' ogni elemento che porta un
    ``data-t``. Senza questo, ogni etichetta sarebbe una domanda a Python.

Perche' non c'e' piu' la scelta della lingua
    C'era, e il programma parlava italiano o inglese. Reggere due lingue non
    costa solo il doppio delle frasi: costa anche che ogni testo nuovo va
    scritto due volte, che ogni correzione va fatta due volte, e che una delle
    due e' sempre un po' indietro rispetto all'altra. Il programma parla
    italiano, e le frasi sono la meta'.

    Di quel meccanismo resta ``LINGUA``, qui sotto. Non e' un avanzo
    dimenticato: piu' di un punto del programma deve DIRE in che lingua sta
    lavorando, per esempio per chiamare per nome la lingua parlata dentro un
    video. Quei punti chiedono qui invece di scriversi ``'it'`` per conto loro,
    cosi' la risposta e' una sola e sta in un posto solo.

Cosa NON e' scritto qui
    I commenti, le spiegazioni delle funzioni e i nomi delle funzioni stesse.
    Quelli servono a chi legge il codice, non a chi lo usa, e non passano di
    qui.

Dove finiscono le abitudini di chi usa il programma
    In ``settings.json``, nella cartella dei dati: accanto all'eseguibile
    quando il programma e' installato, accanto ai sorgenti quando si lavora sul
    codice. Quale motore, quali modelli, quali interruttori. Sono scelte di chi
    lo usa e non del progetto, e infatti quel file non viene mai messo sotto
    controllo di versione.
"""
from __future__ import annotations

import json

from server.config.paths import dati as _dati

# La lingua in cui il programma parla. Una sola, e non cambia.
#
# Resta una costante, e non una parola scritta a mano nei punti che ne hanno
# bisogno, perche' quei punti sono sparsi: se un giorno dovesse tornare la
# scelta della lingua, sono questi i posti da cui ripartire, e averli tutti
# agganciati allo stesso nome li rende trovabili in un secondo.
LINGUA = 'it'

_SETTINGS_FILE = _dati('settings.json')

_catalogo: dict[str, str] = {}


# ── Il catalogo ──────────────────────────────────────────────────────────────

def register(catalogo: dict[str, str]) -> None:
    """Aggiunge al catalogo comune un blocco di frasi.

    Le frasi vivono in un file a parte (``strings.py``) e si registrano qui
    quando quel file viene caricato. E' un giro in piu' rispetto a scriverle
    direttamente qui dentro, e serve a tenere separate due cose diverse: da una
    parte il testo, che cambia spesso ed e' lungo da leggere; dall'altra la
    macchina che lo distribuisce, che cambia quasi mai.
    """
    _catalogo.update(catalogo)


def catalogo() -> dict[str, str]:
    """Tutte le frasi insieme, per spedirle alla pagina in un colpo solo.

    La pagina si traduce da se': all'avvio riceve questo dizionario intero e
    poi riempie ogni elemento che porta un attributo ``data-t``. Il giro
    alternativo sarebbe una domanda a Python per ogni etichetta, cioe' qualche
    centinaio di scambi fra la pagina e il programma per disegnare una
    schermata che e' sempre la stessa.
    """
    return _catalogo


def t(chiave: str, **kwargs) -> str:
    """La frase che sta dietro ``chiave``, con i buchi riempiti.

    I buchi sono quelli di ``str.format``, cioe' ``{nome}`` dentro la frase e
    ``nome=valore`` alla chiamata. Scriverli col nome e non con la posizione
    serve a chi legge il catalogo: nel file dei testi si capisce cosa andra' a
    finire in quel punto senza dover trovare chi chiama.

    Due cose non fanno cadere il programma, di proposito:

    Una chiave che non esiste torna indietro cosi' com'e'. A schermo si vede
    una stringa strana tipo ``sez.cloud.titlo``, che e' brutta ma dice subito
    dove si e' sbagliato a scrivere. L'alternativa sarebbe interrompere una
    trascrizione a meta' per un errore di battitura in un'etichetta.

    Una frase con un buco sbagliato si mostra grezza, con le graffe in
    evidenza. Stesso ragionamento: e' un difetto visibile, non un lavoro
    perduto.
    """
    testo = _catalogo.get(chiave)
    if testo is None:
        return chiave
    try:
        return testo.format(**kwargs) if kwargs else testo
    except (KeyError, IndexError):
        return testo


# ── Le abitudini di chi usa il programma ─────────────────────────────────────
#
# Quale motore, quali modelli, quali interruttori lasciati accesi. Non sono
# impostazioni del progetto: sono scelte fatte una volta e che sarebbe scortese
# far rifare a ogni avvio.

def load_prefs() -> dict:
    """Le preferenze salvate. Un file assente o rotto vale come "nessuna".

    Qualunque cosa vada storta, si riparte dai valori di partenza. Il motivo e'
    che queste sono comodita', non dati: perdere la memoria di quale modello
    era selezionato costa un clic, mentre fermare l'avvio del programma perche'
    un file di comodita' e' illeggibile sarebbe sproporzionato.
    """
    try:
        with open(_SETTINGS_FILE, encoding='utf-8') as fh:
            letto = json.load(fh)
    except (OSError, ValueError):
        return {}
    return letto if isinstance(letto, dict) else {}


def save_prefs(**valori) -> None:
    """Scrive alcune preferenze, lasciando intatte le altre.

    Rilegge il file prima di riscriverlo, e non lo sovrascrive con le sole
    chiavi ricevute. Serve a non cancellare, senza accorgersene, le scelte che
    una parte diversa del programma aveva salvato li' dentro.

    Un errore di scrittura viene ignorato in silenzio, per lo stesso motivo
    spiegato qui sopra: al massimo la prossima volta bisognera' riscegliere.
    """
    contenuto = load_prefs()
    contenuto.update({k: v for k, v in valori.items() if v is not None})
    try:
        with open(_SETTINGS_FILE, 'w', encoding='utf-8') as fh:
            json.dump(contenuto, fh, indent=2)
    except OSError:
        pass
