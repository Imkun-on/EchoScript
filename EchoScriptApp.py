"""EchoScriptApp — interfaccia grafica in HTML, con Python come padrone di casa.

Com'e' fatta
    Una pagina web mostrata dentro il WebView che Windows ha gia' installato.
    L'aspetto sta nel CSS, la struttura nell'HTML, il comportamento in un file
    JavaScript per sezione, e Python fa solo da ponte verso il motore, che non
    cambia di una riga: ``core/engine.py`` e ``transcriber.py`` non sanno
    nemmeno che esiste un'interfaccia.

    L'interfaccia precedente era scritta con un motore grafico Python, un file
    solo da tremilaquattrocento righe in cui palette, testi, disposizione,
    finestre modali e orchestrazione stavano mescolati: per spostare un bottone
    bisognava leggere il codice che lancia i thread. Con la pagina web quelle
    cose stanno in file diversi, e non c'e' piu' nessun motore grafico da
    impacchettare: WebView2 e' gia' nel sistema, e l'eseguibile dimagrisce di
    decine di megabyte.

Come parlano fra loro i due mondi
    In una sola direzione ciascuno, ed e' questo che tiene il tutto semplice:

      JavaScript -> Python   ``pywebview.api.nome(...)`` chiama direttamente un
                             metodo di ``Api``. Nessun protocollo, nessun
                             server, nessuna porta aperta.

      Python -> JavaScript   ``_verso_pagina(...)`` esegue una funzione della
                             pagina. Serve per cio' che arriva quando vuole lui:
                             righe di diario, avanzamento, fine lavoro.

Il lavoro lungo non blocca la finestra
    Ogni operazione che dura piu' di un istante gira in un thread suo e
    riferisce alla pagina mentre procede. La finestra resta viva: si legge il
    diario, e soprattutto si vede che sta succedendo qualcosa.
"""
from __future__ import annotations

import datetime as _dt
import io
import json
import os
import re
import sys
import threading
import traceback

_QUI = os.path.dirname(os.path.abspath(__file__))
for _p in (os.path.join(_QUI, 'core'), _QUI):
    if _p not in sys.path:
        sys.path.insert(0, _p)

# ── La barra della schermata di avvio ────────────────────────────────────────
#
# Questo blocco viene prima di ogni import pesante, e non e' un dettaglio di
# stile: sono proprio quegli import l'attesa che la barra deve raccontare. Il
# ponte con WebView2 e il motore — che si porta dietro Groq, yt-dlp e Rich —
# prendono insieme la maggior parte dei secondi fra il doppio clic e la
# finestra. Importandoli prima di poter disegnare, la barra resterebbe ferma
# proprio mentre succede tutto.
#
# Fuori dall'eseguibile il modulo non esiste e non c'e' nessuna schermata:
# `_avanza` diventa un giro a vuoto e il programma parte come sempre.
try:
    import pyi_splash as _splash          # type: ignore[import-not-found]
except ImportError:
    _splash = None

from Shared.avvio import barra as _barra_avvio

# Quanto vale ogni pezzo dell'avvio sulla barra. Non sono numeri decorativi: il
# motore da solo pesa quanto tutto il resto messo insieme, ed e' giusto che la
# barra ci stia sopra a lungo invece di correre e poi piantarsi.
#
# APERTURA e' il punto in cui questa schermata passa la mano alla pagina: da li'
# in poi a riempire e' il velo di caricamento dentro la finestra, che riparte
# esattamente da questo valore (BASE_AVVIO in web/app.js) invece che da zero.
# E' l'unica ragione per cui le due schermate sembrano una barra sola.
APERTURA = 0.62


def _avanza(quota: float) -> None:
    """Porta la barra della schermata di avvio a ``quota`` (da 0 a 1)."""
    if _splash is None:
        return
    try:
        _splash.update_text(_barra_avvio(quota))
    except Exception:
        # La schermata puo' essere gia' stata chiusa: non e' un guasto, e non
        # deve certo impedire al programma di finire di avviarsi.
        pass


_avanza(0.0)

from Shared import i18n
from Shared.percorsi import dati as _dati, risorsa as _risorsa, impacchettato
from Shared.strings_app import TESTI
_avanza(0.06)               # i testi: sono dizionari, e' immediato

import webview
_avanza(0.22)               # il ponte con WebView2

import transcriber as tx     # gli helper puri condivisi con la riga di comando
_avanza(0.50)               # il motore: Groq, yt-dlp, Rich — il tratto piu' lungo

import engine                # core/engine.py
_avanza(0.56)               # l'orchestrazione, che sopra il motore costa poco

i18n.register(TESTI)

# La finestra e' l'unica: la si tiene qui perche' i thread di lavoro devono
# poterla raggiungere per spingere gli aggiornamenti alla pagina.
_finestra: webview.Window | None = None

# pywebview 6 ha rinominato le costanti dei selettori di file. Si prendono le
# nuove quando esistono e si ricade sulle vecchie: cosi' il programma non stampa
# avvisi di deprecazione sulle versioni recenti e continua a girare su quelle
# precedenti.
_DLG_APRI = getattr(getattr(webview, 'FileDialog', None), 'OPEN',
                    getattr(webview, 'OPEN_DIALOG', 10))


# ── Dove finiscono le trascrizioni ───────────────────────────────────────────
# Fuori dall'eseguibile e' la stessa cartella della riga di comando, cosi' le
# due interfacce vedono lo stesso archivio e il controllo "questo video c'e'
# gia'" funziona a prescindere da come lo si e' trascritto. Dentro l'eseguibile
# quella cartella sarebbe temporanea, quindi si va accanto all'.exe.
RISULTATI = _dati('results') if impacchettato() else engine.RESULTS_DIR


# ── Cataloghi dei modelli ────────────────────────────────────────────────────
# Le chiavi di descrizione seguono il nome del modello ('model.small') o il
# numero di catalogo di transcriber.py ('om.text.2'): cosi' aggiungere un
# modello e' una riga qui e una nel file dei testi, non una modifica al codice.
#
# Sono divisi in due gruppi che non si mescolano mai — quelli che girano sul
# computer e quelli che girano sui server Groq — perche' e' cosi' che sono
# divise le due sezioni dell'interfaccia: scegliere il motore sceglie il gruppo
# intero, trascrizione e riassunto e analisi visiva insieme.

_WHISPER = ('base', 'small', 'medium', 'large-v3', 'large-v3-turbo')
_OLLAMA_TESTO = [(nome, ram, f'om.text.{k}')
                 for k, (nome, ram, _d) in tx.OLLAMA_TEXT_MODELS.items()]
_OLLAMA_VISTA = [(nome, ram, f'om.vis.{k}')
                 for k, (nome, ram, _d) in tx.OLLAMA_VISION_MODELS.items()]

_GROQ = ('whisper-large-v3-turbo', 'whisper-large-v3')
_GROQ_TESTO = [(nome, f'gm.text.{k}') for k, (nome, _d) in tx.GROQ_TEXT_MODELS.items()]
_GROQ_VISTA = [(nome, f'gm.vis.{k}') for k, (nome, _d) in tx.GROQ_VISION_MODELS.items()]


# ── L'avvio: cosa si vede, e in che ordine ───────────────────────────────────
#
# Chi fa doppio clic su un eseguibile aspetta diversi secondi mentre il
# contenuto viene riestratto in una cartella temporanea, e in quei secondi non
# gira una riga di questo file: se sullo schermo non compare niente, il doppio
# clic sembra non aver funzionato e se ne fa un altro, avviando due copie. La
# sequenza e' questa:
#
#   1. il bootloader di PyInstaller mostra l'immagine di caricamento, che porta
#      gia' disegnato il binario vuoto della barra;
#   2. il programma parte e riempie quella barra a ogni pezzo caricato (vedi
#      _avanza in cima al file), mentre prepara la finestra ma la tiene
#      *nascosta*;
#   3. la pagina si carica e chiama avvio(): li' la finestra compare, ma
#      l'immagine resta ancora sopra;
#   4. al primo fotogramma davvero disegnato la pagina chiama dipinta(), e
#      l'immagine se ne va scoprendo il velo di caricamento — stesso marchio,
#      stesso viola, e la barra del velo riparte da dove quella dell'immagine
#      si era fermata, quindi non si vede nessuno scambio;
#   5. la barra finisce di riempirsi per passi veri e sfuma sull'interfaccia.
#
# E' una barra sola, disegnata due volte da due programmi diversi. Il punto 2 e'
# quello che conta per la finestra: mostrandola subito, per un istante si
# vedrebbe il bianco con cui WebView2 dipinge se stesso finche' non ha finito di
# inizializzarsi: un lampo bianco in un programma tutto nero e viola e'
# esattamente cio' che si nota di piu'.

_gia_mostrata = False
_gia_chiusa = False


def _mostra_finestra() -> None:
    """Fuori la finestra. Chiamarla piu' di una volta non fa danni."""
    global _gia_mostrata
    if _gia_mostrata or _finestra is None:
        return
    _gia_mostrata = True
    try:
        _finestra.show()
    except Exception:
        pass


def _chiudi_caricamento() -> None:
    """Via l'immagine di PyInstaller.

    Va fatto dopo aver mostrato la finestra, non prima: finche' la finestra e'
    nascosta WebView2 non disegna nulla, e nell'istante in cui compare le
    servono ancora un paio di secondi per impaginare. Togliendo l'immagine
    subito, quei secondi sarebbero un rettangolo nero e vuoto.
    """
    global _gia_chiusa
    if _gia_chiusa or _splash is None:
        return
    _gia_chiusa = True
    try:
        _splash.close()
    except Exception:
        pass


def _pronti() -> None:
    """Tutt'e due, per la rete di sicurezza: meglio scoperti che invisibili."""
    _mostra_finestra()
    _chiudi_caricamento()


def _scadenza_avvio(secondi: int = 25) -> None:
    """Rete di sicurezza: la finestra deve comparire comunque.

    Se qualcosa impedisce alla pagina di arrivare fino in fondo — un errore nel
    motore grafico di Windows, un file che non si carica — senza questa il
    programma resterebbe una schermata di caricamento immobile, con la finestra
    nascosta e niente da chiudere se non il Gestione attivita'.
    """
    orologio = threading.Timer(secondi, _pronti)
    orologio.daemon = True      # non deve trattenere il programma alla chiusura
    orologio.start()


def _json_per_js(valore) -> str:
    """JSON valido anche come pezzo di codice JavaScript.

    JSON e JavaScript non coincidono del tutto: U+2028 e U+2029 sono caratteri
    legittimi dentro una stringa JSON ma terminano una riga in JavaScript, quindi
    finirebbero dentro ``window.funzione(...)`` spezzando l'istruzione a meta'.
    Un titolo di video che li contiene farebbe fallire la chiamata in silenzio —
    l'errore lo vedrebbe solo la console della pagina, che qui non si apre. Si
    riscrivono nella loro forma con la barra rovesciata, che JSON accetta e
    JavaScript legge come lo stesso carattere.
    """
    return (json.dumps(valore, ensure_ascii=False, default=str)
            .replace('\u2028', '\\u2028').replace('\u2029', '\\u2029'))


def _verso_pagina(funzione: str, *argomenti) -> None:
    """Esegue una funzione JavaScript della pagina, da qualunque thread.

    Gli argomenti passano per JSON: e' l'unico modo di trasportare un dizionario
    Python dentro la pagina senza inventarsi una codifica, e protegge da apici e
    accenti che altrimenti spezzerebbero la chiamata.
    """
    if _finestra is None:
        return
    try:
        args = ', '.join(_json_per_js(a) for a in argomenti)
        _finestra.evaluate_js(f'window.{funzione}({args})')
    except Exception:
        # Una finestra chiusa mentre un thread stava ancora riferendo non e' un
        # errore: e' il normale ordine di spegnimento.
        pass


def _ora() -> str:
    """L'ora, per le righe del diario: dice quanto e' durato ogni pezzo."""
    return _dt.datetime.now().strftime('%H:%M:%S')


class Diario(io.TextIOBase):
    """Raccoglie cio' che i moduli stampano e lo manda alla pagina, riga a riga.

    ``transcriber.py`` parla con Rich, che colora scrivendo sequenze di
    controllo ANSI: dentro una pagina web quelle diventerebbero caratteri strani
    in mezzo al testo, quindi si tolgono. Il colore lo rimette la pagina, in
    base a cosa dice la riga.

    Chi ci scrive davvero, e chi no
        Nessuno dei due moduli chiamati da qui stampa qualcosa. ``engine.py``
        non contiene una sola print, e le funzioni di ``transcriber.py`` che
        usa (``download_audio``, ``split_audio``, ``transcribe_local``) sono le
        versioni nude, quelle che riferiscono solo col callback; a stampare con
        Rich sono i wrapper ``_cli_*``, che chiama soltanto la riga di comando.

        Quindi su questa strada il dirottamento di ``stdout`` cattura solo i
        guasti — il traceback di ``_in_thread`` — e il diario lo riempie
        ``Avanzamento``, che racconta le fasi mentre la barra le mostra. Questa
        classe resta perche' il giorno in cui uno di quei moduli avesse
        qualcosa da dire, lo direbbe nel posto giusto senza modifiche.
    """

    _ANSI = re.compile(r'\x1b\[[0-9;]*[A-Za-z]')

    def __init__(self):
        self._resto = ''
        self._lucchetto = threading.Lock()

    def write(self, s: str) -> int:      # type: ignore[override]
        if not s:
            return 0
        with self._lucchetto:
            self._resto += s
            while '\n' in self._resto:
                riga, self._resto = self._resto.split('\n', 1)
                self._manda(riga)
        return len(s)

    def flush(self) -> None:
        with self._lucchetto:
            if self._resto:
                self._manda(self._resto)
                self._resto = ''

    def _manda(self, grezza: str) -> None:
        testo = self._ANSI.sub('', grezza).rstrip()
        if testo:
            _verso_pagina('aggiungiRiga', testo)


class Avanzamento:
    """Traduce le fasi del motore in una barra che non torna mai indietro.

    Il motore riferisce ``(fase, corrente, totale, dettaglio)`` e non sa quante
    fasi ci siano in tutto: quello lo decide chi avvia il lavoro, in base a cosa
    e' stato chiesto (un file locale non si scarica, solo Groq divide in
    blocchi, traduzione e riassunto ci sono solo se spuntati).

    Ogni fase occupa una fetta ``[i/n, (i+1)/n]`` del totale, e dentro la fetta
    si interpola col progresso vero. Quando una fase non sa quanto manca — sta
    caricando un modello — la barra resta all'inizio della sua fetta invece di
    girare a vuoto: cosi' quando si muove vuol dire qualcosa.

    Scrive anche il diario, dagli stessi dati. Non e' una ripetizione: la barra
    dice dove siamo adesso e cancella cio' che c'era prima, il diario tiene
    l'ordine e le ore. Su un lavoro lungo — novanta secondi fermi a caricare un
    modello — o su una playlist di cinquanta video, quello che e' gia' successo
    conta quanto quello che sta succedendo.
    """

    def __init__(self, piano: list[str]):
        self.piano = piano
        self._massimo = 0.0
        self._fase_detta: str | None = None
        self._dettaglio_detto = ''

    def _nome(self, fase: str) -> str:
        """Il nome leggibile della fase, con lo stesso ripiego della pagina.

        Una chiave assente tornerebbe come chiave — 'phase.pippo' scritto in
        chiaro nel diario — mentre qui serve una frase.
        """
        chiave = 'phase.' + fase
        return i18n.t(chiave if chiave in i18n.catalogo() else 'phase.default')

    def _racconta(self, fase: str, dettaglio: str) -> None:
        """Una riga di diario quando cambia qualcosa, e solo allora.

        Il motore riferisce anche molte volte al secondo con lo stesso testo:
        scriverle tutte farebbe un muro di righe identiche in cui non si legge
        piu' niente, e il diario tiene solo le ultime quattrocento.
        """
        if fase != self._fase_detta:
            self._fase_detta = fase
            self._dettaglio_detto = ''
            _verso_pagina('aggiungiRiga', f'{_ora()}  ▸ {self._nome(fase)}')
        if dettaglio and dettaglio != self._dettaglio_detto:
            self._dettaglio_detto = dettaglio
            _verso_pagina('aggiungiRiga', f'{_ora()}     {dettaglio}')

    def riferisci(self, fase: str, corrente, totale, dettaglio: str = '') -> None:
        self._racconta(fase, dettaglio or '')
        if fase not in self.piano:
            # Una fase fuori piano (rara: il motore ne aggiunge una che non
            # avevamo previsto) muove il testo ma non la barra, che altrimenti
            # salterebbe a un punto sbagliato.
            _verso_pagina('avanzaLavoro', fase, -1, len(self.piano), None, dettaglio or '')
            return
        i = self.piano.index(fase)
        dentro = (max(0.0, min(1.0, corrente / totale))
                  if (corrente is not None and totale) else 0.0)
        globale = max((i + dentro) / len(self.piano), self._massimo)
        self._massimo = globale
        _verso_pagina('avanzaLavoro', fase, i, len(self.piano), globale, dettaglio or '')

    def concludi(self) -> None:
        """Il lavoro e' finito: la barra arriva in fondo e ci resta.

        Serve perche' l'ultima fase riferisce l'ultimo blocco e poi tace: senza
        questa la barra si fermerebbe al 96% con tutto gia' scritto sul disco.
        """
        self._massimo = 1.0
        _verso_pagina('avanzaLavoro', self.piano[-1], len(self.piano) - 1,
                      len(self.piano), 1.0, '')
        _verso_pagina('aggiungiRiga', f'{_ora()}  {i18n.t("log.done")}')


def piano_fasi(motore: str, sorgente: str, opzioni: dict) -> list[str]:
    """Sequenza ordinata delle fasi di un lavoro.

    Dipende dal contesto: un file locale non si scarica, solo Groq divide
    l'audio in blocchi, e le fasi facoltative si aggiungono solo se richieste —
    nello stesso ordine in cui il motore le esegue (visiva, traduzione,
    riassunto), che e' dopo aver scritto la trascrizione.
    """
    piano = ['info']
    if sorgente != 'local':
        piano.append('download')
    if motore == 'groq':
        piano.append('prepare')
    piano += ['transcribe', 'export']
    if opzioni.get('visual'):
        piano.append('visual')
    if opzioni.get('translate'):
        piano.append('translate')
    if opzioni.get('summarize'):
        piano.append('summarize')
    return piano


class Api:
    """I metodi che la pagina puo' chiamare, e nient'altro.

    Ogni metodo restituisce un dizionario con almeno ``ok``: la pagina non deve
    mai ricevere un'eccezione Python, che in JavaScript arriverebbe come un
    rifiuto senza spiegazione.

    Qui non si decide niente di importante. Se un video sia una playlist, se
    esista gia' una trascrizione, quanto costera' un lavoro: sono domande a cui
    rispondono ``core/engine.py`` e ``transcriber.py``, e questo file si limita
    a girare la risposta alla pagina.
    """

    def __init__(self):
        self._occupato = False
        self._avanz: Avanzamento | None = None

        # La sorgente confermata: metadati letti, percorso o URL, ed eventuale
        # playlist. Vive qui e non nella pagina perche' e' il motore a produrla
        # e il motore a riceverla indietro: farla passare per JavaScript
        # significherebbe copiarla due volte e rischiare che divergano.
        self._meta: dict | None = None
        self._src: str = ''
        self._playlist: dict | None = None

        self._chiave = ''
        self._chiave_nome = ''
        self._ultima_cartella = ''
        self._ultima_visiva = ''

        # Modelli gia' scaricati in Ollama, per i ✓ nei menu. None = ancora
        # ignoto (la lettura avviene in sottofondo e resta muta se Ollama e'
        # spento: non deve rallentare l'avvio ne' fallire rumorosamente).
        self._ollama_presenti: set[str] | None = None

        prefs = i18n.load_prefs()
        self.scelte = {
            'motore':  prefs.get('motore', 'local'),
            'sorgente': prefs.get('sorgente', 'youtube'),
            # I tre modelli locali...
            'whisper': prefs.get('whisper', 'small'),
            'ollama':  prefs.get('ollama', tx.OLLAMA_MODEL),
            'vision':  prefs.get('vision', tx.OLLAMA_VISION_MODEL),
            # ...e i tre di Groq, che fanno gli stessi tre mestieri sui server.
            'groq':    prefs.get('groq', _GROQ[0]),
            'groq_testo': prefs.get('groq_testo', tx.GROQ_SUMMARY_MODEL),
            'groq_vista': prefs.get('groq_vista', tx.GROQ_VISION_MODEL),
            'translate': bool(prefs.get('translate', False)),
            'summarize': bool(prefs.get('summarize', False)),
            'visual':    bool(prefs.get('visual', False)),
        }
        # La sezione crediti elenca i modelli Groq leggendoli da transcriber:
        # allinearli subito evita che mostri i default di .env finche' non parte
        # il primo lavoro.
        self._applica_groq()

    # ── Avvio ────────────────────────────────────────────────────────────────

    def dipinta(self) -> dict:
        """La finestra ha disegnato il primo fotogramma: si puo' scoprire.

        Ora che la finestra e' visibile i fotogrammi ricominciano, quindi questa
        chiamata arriva davvero — a differenza di quando era ancora nascosta.
        """
        _chiudi_caricamento()
        return {'ok': True}

    def avvio(self) -> dict:
        """Tutto cio' che serve alla pagina per disegnarsi la prima volta.

        E' anche il primo segno di vita della pagina, e l'unico momento in cui
        si possa mostrare la finestra: finche' resta nascosta WebView2 non
        disegna un fotogramma — sospende perfino requestAnimationFrame — quindi
        aspettare di sapere che ha dipinto sarebbe aspettare per sempre.
        """
        _mostra_finestra()
        threading.Thread(target=self._leggi_ollama, daemon=True).start()
        return {
            'ok': True,
            'lingua': i18n.get_language(),
            'testi': i18n.catalogo(),
            'scelte': self.scelte,
            'modelli': self._modelli(),
            'chiave': self._stato_chiave(),
            'cartella': RISULTATI,
        }

    def _leggi_ollama(self) -> None:
        """In sottofondo: quali modelli Ollama sono gia' sul disco.

        Serve solo per i ✓ nei menu. Se Ollama non gira la risposta e' None e
        non succede nulla: e' un'informazione in piu', non un requisito.
        """
        presenti = tx._ollama_installed_models()
        if not presenti:
            return
        self._ollama_presenti = presenti
        _verso_pagina('aggiornaModelli', self._modelli())

    def _applica_groq(self) -> None:
        """Porta in transcriber i modelli Groq scelti nella sezione «Motore».

        Servono anche fuori da un lavoro — la sezione crediti li elenca per
        chiedere quanto e' rimasto — quindi non basta passarli fra le opzioni al
        momento di partire.
        """
        tx.GROQ_MODEL = self.scelte['groq']
        tx.GROQ_SUMMARY_MODEL = self.scelte['groq_testo']
        tx.GROQ_VISION_MODEL = self.scelte['groq_vista']

    def _modelli(self) -> dict:
        """I sei cataloghi di modelli, gia' con etichetta e descrizione.

        Le etichette le compone Python perche' e' Python a sapere quali modelli
        esistono e quali sono gia' scaricati; la pagina si limita a riempirne
        dei menu. Le descrizioni passano per chiave di traduzione, cosi'
        cambiando lingua non serve richiederle di nuovo.
        """
        def spunta(nome: str) -> str:
            if self._ollama_presenti is None:
                return ''
            return ' ✓' if tx._ollama_has_model(nome, self._ollama_presenti) else ''

        # La memoria richiesta e' un inciso, non una voce a se': fra parentesi
        # attaccata al nome. Con un separatore la riga finiva con tre stacchi in
        # fila — nome, memoria, descrizione — e non si capiva piu' dove
        # cominciasse il giudizio sul modello.
        ollama = [{'valore': n, 'nome': f'{n}{spunta(n)} ({ram})', 'chiave': k}
                  for n, ram, k in _OLLAMA_TESTO]
        vision = [{'valore': n, 'nome': f'{n}{spunta(n)} ({ram})', 'chiave': k}
                  for n, ram, k in _OLLAMA_VISTA]

        # I modelli Groq non si scaricano, quindi niente ✓ e niente memoria: il
        # nome basta a se stesso, la descrizione dice il resto.
        groq_testo = [{'valore': n, 'nome': n, 'chiave': k} for n, k in _GROQ_TESTO]
        groq_vista = [{'valore': n, 'nome': n, 'chiave': k} for n, k in _GROQ_VISTA]

        # Un modello fuori catalogo — imposto da .env, o scelto quando il
        # catalogo era diverso — va comunque offerto, o il valore selezionato non
        # esisterebbe fra le voci e la pagina ripiegherebbe sulla prima,
        # cambiando di nascosto il modello scelto. Si guarda la scelta salvata,
        # non il valore del modulo: sono la stessa cosa solo al primo avvio.
        for elenco, corrente in ((ollama, self.scelte['ollama']),
                                 (vision, self.scelte['vision']),
                                 (groq_testo, self.scelte['groq_testo']),
                                 (groq_vista, self.scelte['groq_vista'])):
            if corrente and corrente not in [v['valore'] for v in elenco]:
                # Nome nudo: non si puo' sapere da dove venga (.env o una scelta
                # di ieri), e scriverlo sbagliato sarebbe peggio che tacere.
                elenco.insert(0, {'valore': corrente, 'nome': corrente, 'chiave': ''})

        return {
            # Sul computer.
            'whisper': [{'valore': m, 'nome': '', 'chiave': f'model.{m}'} for m in _WHISPER],
            'ollama':  ollama,
            'vision':  vision,
            # Sui server Groq.
            'groq':    [{'valore': m, 'nome': '', 'chiave': f'groqm.{m}'} for m in _GROQ],
            'groq_testo': groq_testo,
            'groq_vista': groq_vista,
        }

    def cambia_lingua(self, codice: str) -> dict:
        i18n.set_language(codice)
        i18n.save(codice)
        return {'ok': True, 'lingua': i18n.get_language()}

    def imposta(self, valori: dict) -> dict:
        """Registra una scelta dell'interfaccia e la ricorda per la volta dopo.

        Motore, modelli e interruttori non sono impostazioni del progetto: sono
        abitudini di chi usa il programma, e rifarle a ogni avvio sarebbe
        scortese. La stima di costo/tempo dipende da alcune di queste, quindi si
        ricalcola qui e torna gia' pronta.
        """
        self.scelte.update({k: v for k, v in (valori or {}).items() if k in self.scelte})
        i18n.save_prefs(**self.scelte)
        self._applica_groq()
        return {'ok': True, 'stima': self._stima()}

    # ── La chiave Groq ───────────────────────────────────────────────────────

    def _stato_chiave(self) -> dict:
        return {'presente': bool(self._chiave), 'nome': self._chiave_nome}

    def scegli_chiave(self) -> dict:
        """Legge la chiave Groq da un file .txt scelto dal sistema.

        Il file puo' essere la chiave nuda o una riga in stile .env: si prende
        il primo valore utile e si tolgono virgolette e commenti, cosi' funziona
        con quello che la console di Groq fa scaricare senza chiedere di
        ripulirlo a mano.
        """
        try:
            scelti = _finestra.create_file_dialog(
                _DLG_APRI, allow_multiple=False,
                file_types=('Testo (*.txt)', 'Tutti (*.*)'))
        except Exception as exc:                       # noqa: BLE001
            return {'ok': False, 'errore': str(exc)}
        if not scelti:
            return {'ok': True, 'chiave': self._stato_chiave()}

        percorso = scelti[0]
        try:
            # utf-8-sig: un .txt salvato su Windows comincia spesso con un BOM,
            # che finirebbe dentro la chiave e la farebbe rifiutare da Groq con
            # un errore che non dice niente.
            with open(percorso, encoding='utf-8-sig') as fh:
                grezzo = fh.read()
        except OSError as exc:
            return {'ok': False, 'errore': i18n.t('eng.key.unreadable', e=exc)}

        chiave = self._estrai_chiave(grezzo)
        if not chiave:
            return {'ok': False, 'errore': i18n.t('eng.key.invalid')}

        self._chiave = chiave
        self._chiave_nome = os.path.basename(percorso)
        return {'ok': True, 'chiave': self._stato_chiave()}

    @staticmethod
    def _estrai_chiave(grezzo: str) -> str:
        """Il primo valore utile di un file: chiave nuda o riga NOME=valore."""
        for riga in grezzo.splitlines():
            riga = riga.strip()
            if not riga or riga.startswith('#'):
                continue
            if '=' in riga:
                riga = riga.split('=', 1)[1]
            riga = riga.strip().strip('"').strip("'").strip()
            if riga:
                return riga
        return ''

    # ── Leggere la sorgente ──────────────────────────────────────────────────

    def carica_info(self, testo: str) -> dict:
        """Guarda cosa c'e' dietro un link, senza scaricare nulla.

        Torna subito: il lavoro vero avviene in un thread, e la pagina viene
        avvisata a cose fatte. Cosi' la finestra non si congela nei secondi in
        cui yt-dlp interroga YouTube — che su una playlist lunga sono parecchi,
        perche' ogni video va letto uno per uno.
        """
        if self._occupato:
            return {'ok': False, 'errore': i18n.t('err.busy')}
        testo = (testo or '').strip()
        if not testo:
            return {'ok': False, 'errore': i18n.t('err.no_url')}
        threading.Thread(target=self._carica_davvero, args=(testo,), daemon=True).start()
        return {'ok': True, 'avviato': True}

    def _carica_davvero(self, url: str) -> None:
        try:
            playlist = engine.get_playlist_info(url) if 'list=' in url else None
            if playlist and playlist['count'] >= 1:
                self._carica_playlist(url, playlist)
                return
            meta = engine.get_video_info(url)
            self._meta, self._src, self._playlist = meta, url, None
            _verso_pagina('chiediConferma', self._scheda_video(meta))
        except Exception as exc:                       # noqa: BLE001
            _verso_pagina('erroreSorgente', str(exc))

    def _carica_playlist(self, url: str, playlist: dict) -> None:
        """Legge i metadati di ogni video della playlist, saltando i non disponibili.

        Un video privato o rimosso non deve far fallire l'intera lettura: se ne
        salta uno, non si perde la playlist. La pagina intanto vede la riga
        "leggo i video…", perche' su una lista lunga qui si sta parecchio.
        """
        _verso_pagina('caricamentoPlaylist')
        voci = []
        for indirizzo in playlist['entries']:
            try:
                voci.append(engine.get_video_info(indirizzo))
            except Exception:                          # noqa: BLE001, S112
                pass
        if not voci:
            _verso_pagina('erroreSorgente', i18n.t('playlist.none'))
            return
        sottocartella = tx._safe_filename(
            playlist.get('title') or playlist.get('channel') or 'playlist')
        self._playlist = {'title': playlist.get('title'),
                          'channel': playlist.get('channel'),
                          'subdir': sottocartella, 'items': voci}
        self._meta, self._src = voci[0], url
        _verso_pagina('chiediConferma', self._scheda_playlist(self._playlist))

    def scegli_file(self) -> dict:
        """Apre il selettore di file del sistema per un audio o un video.

        I formati accettati sono esattamente quelli che accetta la riga di
        comando: il filtro si costruisce da ``tx.AUDIO_EXTENSIONS``, cosi'
        aggiungerne uno vale per tutt'e due senza toccare questo file.
        """
        estensioni = ' '.join(f'*{e}' for e in sorted(tx.AUDIO_EXTENSIONS))
        try:
            scelti = _finestra.create_file_dialog(
                _DLG_APRI, allow_multiple=False,
                file_types=(f'Audio e video ({estensioni})', 'Tutti (*.*)'))
        except Exception as exc:                       # noqa: BLE001
            return {'ok': False, 'errore': str(exc)}
        if not scelti:
            return {'ok': True, 'annullato': True}

        percorso = scelti[0]
        meta = tx.local_file_meta(percorso)
        self._meta, self._src, self._playlist = meta, percorso, None
        return {'ok': True, 'scheda': self._scheda_file(meta, percorso)}

    def dimentica(self) -> dict:
        """La sorgente non vale piu': l'URL e' cambiato, o si e' annullata.

        Serve perche' una conferma vecchia non deve restare valida per un link
        nuovo: sarebbe il modo piu' facile di trascrivere il video sbagliato,
        che con Groq costa anche crediti.
        """
        self._meta = self._playlist = None
        self._src = ''
        return {'ok': True}

    # ── Le schede della sorgente ─────────────────────────────────────────────

    def _scheda_video(self, meta: dict) -> dict:
        """Il video ridotto a cio' che va mostrato: copertina, titolo, dati, stima.

        Le voci facoltative (mi piace, iscritti, categoria, lingua) compaiono
        solo quando ci sono, cosi' la scheda non si riempie di campi vuoti.
        """
        righe = [
            ('info.channel', meta.get('channel') or '—'),
            ('info.views', tx._format_views(meta.get('views'))),
            ('info.date', tx._format_upload_date(meta.get('upload_date'))),
            ('info.duration', tx._format_duration(meta.get('duration'))),
        ]
        if meta.get('likes') is not None:
            righe.append(('info.likes', tx._format_views(meta['likes'])))
        if meta.get('subscribers') is not None:
            righe.append(('info.subs', tx._format_views(meta['subscribers'])))
        if meta.get('category'):
            righe.append(('info.category', meta['category']))
        lingua = tx._lang_name(meta.get('detected_language') or meta.get('language'),
                              i18n.get_language())
        if lingua:
            righe.append(('info.language', lingua))
        capitoli = meta.get('chapters') or []
        righe.append(('info.chapters',
                      i18n.t('chapters.some', n=len(capitoli)) if capitoli
                      else i18n.t('chapters.none')))

        return {
            'tipo': 'video',
            'titolo': meta.get('title') or '?',
            'miniatura': meta.get('thumbnail') or '',
            'righe': [{'chiave': k, 'valore': str(v)} for k, v in righe],
            'stima': self._stima(meta),
        }

    def _scheda_playlist(self, playlist: dict) -> dict:
        voci = playlist['items']
        totale = sum((m.get('duration') or 0) for m in voci)
        return {
            'tipo': 'playlist',
            'titolo': playlist.get('title') or playlist.get('channel') or '?',
            'miniatura': (voci[0].get('thumbnail') or '') if voci else '',
            'righe': [
                {'chiave': 'info.channel', 'valore': playlist.get('channel') or '—'},
                {'chiave': 'info.videos', 'valore': str(len(voci))},
                {'chiave': 'info.duration', 'valore': tx._format_duration(totale)},
            ],
            'stima': self._stima({'duration': totale}),
            'voci': [{'titolo': m.get('title') or '?',
                      'durata': tx._format_duration(m.get('duration'))} for m in voci],
        }

    def _scheda_file(self, meta: dict, percorso: str) -> dict:
        return {
            'tipo': 'file',
            'titolo': meta.get('title') or os.path.basename(percorso),
            'miniatura': '',
            'righe': [
                {'chiave': 'info.file', 'valore': os.path.basename(percorso)},
                {'chiave': 'info.duration',
                 'valore': tx._format_duration(meta.get('duration'))},
            ],
            'stima': self._stima(meta),
        }

    def _stima(self, meta: dict | None = None) -> str:
        """Costo (Groq) o tempo (locale) previsti per la sorgente corrente.

        Cambia col motore e col modello scelti, quindi si ricalcola a ogni
        modifica invece di essere fissata quando la sorgente viene letta: e' il
        numero su cui si decide se usare il cloud o aspettare.
        """
        meta = meta if meta is not None else self._meta
        if not meta:
            return ''
        if self._playlist and meta is self._meta:
            meta = {'duration': sum((m.get('duration') or 0)
                                    for m in self._playlist['items'])}
        motore = self.scelte['motore']
        modello = self.scelte['groq'] if motore == 'groq' else self.scelte['whisper']
        stima = tx.estimate_job(meta, motore, modello)
        if stima['backend'] == 'groq':
            return i18n.t('est.cost', c=f"{stima['cost_usd']:.3f}", m=modello)
        dispositivo = 'GPU' if stima.get('device') == 'cuda' else 'CPU'
        return i18n.t('est.time', t=tx._format_duration(stima['seconds']), d=dispositivo)

    # ── Avviare il lavoro ────────────────────────────────────────────────────

    def _opzioni(self, motore: str | None = None) -> dict:
        """Il dizionario che il motore si aspetta, dalle scelte dell'interfaccia.

        Passano i modelli di entrambi i mondi, ma il motore ne usa uno solo: e'
        ``backend`` a decidere, e con «local» la chiave non parte nemmeno, cosi'
        una trascrizione sul computer resta sul computer anche se una chiave e'
        caricata per altri lavori.
        """
        motore = motore or self.scelte['motore']
        return {
            'backend': motore,
            'model': self.scelte['whisper'],
            'ollama_model': self.scelte['ollama'],
            'ollama_vision_model': self.scelte['vision'],
            'groq_model': self.scelte['groq'],
            'groq_summary_model': self.scelte['groq_testo'],
            'groq_vision_model': self.scelte['groq_vista'],
            'api_key': self._chiave if motore == 'groq' else '',
            'export': True,
            'source_kind': self.scelte['sorgente'],
            # I nomi delle cartelle seguono la lingua dell'interfaccia.
            'ui_lang': i18n.get_language(),
            'translate': self.scelte['translate'],
            'summarize': self.scelte['summarize'],
            'visual': self.scelte['visual'],
        }

    def prepara(self) -> dict:
        """Cosa succede se si preme «Trascrivi», prima di spendere qualcosa.

        Tre risposte possibili, e nessuna avvia niente da sola:

          manca    non ci sono i presupposti (chiave, sorgente): l'elenco di
                   cosa manca, che la pagina mostra in una finestra;
          gia      il video e' gia' nella cartella dei risultati: si offre di
                   rifarlo, riprenderlo, o riusarlo per traduzione/riassunto;
          ripresa  esiste un parziale: si offre di continuarlo o buttarlo;
          pronto   niente di tutto cio', si puo' partire.

        Chiedere prima invece di trascrivere e basta e' cio' che evita di
        rispendere crediti Groq su un lavoro gia' fatto.
        """
        if self._occupato:
            return {'ok': False, 'errore': i18n.t('err.busy')}

        mancano = []
        if self.scelte['motore'] == 'groq' and not self._chiave:
            mancano.append(i18n.t('warn.key'))
        if not self._meta:
            mancano.append(i18n.t('warn.src.yt') if self.scelte['sorgente'] == 'youtube'
                           else i18n.t('warn.src.local'))
        if mancano:
            return {'ok': True, 'stato': 'manca', 'voci': mancano}

        # Una playlist si avvia sempre: il controllo "gia' fatto" lo fa il batch
        # video per video, saltando quelli presenti senza spendere un credito.
        if self._playlist:
            return {'ok': True, 'stato': 'pronto'}

        meta = self._meta
        if tx.transcription_exists(RISULTATI, meta['title']):
            voci = [{'azione': 'nuova', 'icona': 'rifai', 'tono': 'attenzione',
                     'titolo': i18n.t('already.again'),
                     'desc': i18n.t('already.again.desc')}]
            if engine.can_resume(meta, RISULTATI):
                nota = engine.resume_hint(meta, RISULTATI, i18n.get_language())
                desc = i18n.t('already.resume.desc')
                voci.append({'azione': 'riprendi_post', 'icona': 'riprendi', 'tono': 'primario',
                             'titolo': i18n.t('already.resume'),
                             'desc': f'{desc} ({nota})' if nota else desc})
            voci.append({'azione': 'traduci', 'icona': 'traduci', 'tono': 'primario',
                         'titolo': i18n.t('already.translate'),
                         'desc': i18n.t('already.translate.desc')})
            voci.append({'azione': 'riassumi', 'icona': 'riassumi', 'tono': 'primario',
                         'titolo': i18n.t('already.summary'),
                         'desc': i18n.t('already.summary.desc')})
            return {'ok': True, 'stato': 'gia', 'titolo': i18n.t('already.title'),
                    'desc': i18n.t('already.desc'), 'voci': voci}

        parziale = (tx.load_checkpoint(meta) if self.scelte['motore'] == 'groq'
                    else tx.load_local_checkpoint(meta))
        if parziale:
            return {'ok': True, 'stato': 'ripresa', 'titolo': i18n.t('resume.title'),
                    'desc': i18n.t('resume.desc'),
                    'voci': [
                        {'azione': 'riprendi', 'icona': 'riprendi', 'tono': 'primario',
                         'titolo': i18n.t('resume.go'),
                         'desc': i18n.t('resume.go.desc',
                                        **self._quanto_fatto(parziale))},
                        {'azione': 'ricomincia', 'icona': 'rifai', 'tono': 'attenzione',
                         'titolo': i18n.t('resume.restart'),
                         'desc': i18n.t('resume.restart.desc')},
                    ]}

        return {'ok': True, 'stato': 'pronto'}

    @staticmethod
    def _quanto_fatto(parziale: dict) -> dict:
        """Il minutaggio raggiunto da un parziale, non il conteggio dei blocchi.

        Dire "blocco 7 di 19" non significa niente per chi guarda: e' un
        dettaglio di come il programma spezza l'audio. "1:10:00 di 3:12:00" e'
        la stessa informazione detta in un modo che si capisce.
        """
        if 'done_seconds' in parziale:
            fatti = int(parziale.get('done_seconds', 0))
        else:
            blocco = parziale.get('chunk_seconds') or tx.CHUNK_SECONDS
            fatti = int(parziale.get('done_chunks', 0)) * blocco
        durata = int(parziale.get('duration', 0) or 0)
        if durata:
            fatti = min(fatti, durata)
        return {'fatto': tx._format_timestamp(fatti),
                'totale': tx._format_timestamp(durata)}

    def esegui(self, azione: str = 'nuova') -> dict:
        """Avvia davvero il lavoro, con l'azione scelta.

        ``nuova`` trascrive da capo; ``riprendi`` continua dal parziale;
        ``ricomincia`` lo butta e riparte; ``traduci``, ``riassumi`` e
        ``riprendi_post`` riusano la trascrizione gia' salvata e non spendono un
        credito di trascrizione.
        """
        if self._occupato:
            return {'ok': False, 'errore': i18n.t('err.busy')}
        if not self._meta:
            return {'ok': False, 'errore': i18n.t('err.no_file')}

        if self._playlist:
            self._in_thread(self._playlist_davvero)
            return {'ok': True, 'avviato': True}

        if azione == 'ricomincia':
            meta = self._meta
            (tx.delete_local_checkpoint if self.scelte['motore'] == 'local'
             else tx.delete_checkpoint)(meta)
            azione = 'nuova'

        if azione in ('traduci', 'riassumi', 'riprendi_post'):
            self._in_thread(self._dopo_davvero, azione)
        else:
            self._in_thread(self._trascrivi_davvero, azione == 'riprendi')
        return {'ok': True, 'avviato': True}

    def _apri_lavoro(self, opzioni: dict, piano: list[str]) -> None:
        """Prepara la pagina per un lavoro nuovo: piano, checklist, barra a zero."""
        self._avanz = Avanzamento(piano)
        parti = [i18n.t('ov.base')]
        if opzioni.get('visual'):
            parti.append(i18n.t('ov.visual'))
        if opzioni.get('translate'):
            parti.append(i18n.t('ov.translate'))
        if opzioni.get('summarize'):
            parti.append(i18n.t('ov.summary'))
        parti.append(i18n.t('ov.save'))
        frase = (', '.join(parti[:-1]) + i18n.t('comune.e') + parti[-1]
                 if len(parti) > 1 else parti[0])
        motore = opzioni['backend']
        _verso_pagina('iniziaLavoro', {
            'piano': piano,
            'frase': frase[:1].upper() + frase[1:] + '.',
            'motore': (i18n.t('engine.groq', model=opzioni['groq_model'])
                       if motore == 'groq'
                       else i18n.t('engine.local', model=opzioni['model'])),
            'tono': 'cloud' if motore == 'groq' else 'locale',
            'nota': '' if motore == 'groq' else i18n.t('engine.local.hint'),
        })

    def _riferisci(self, fase, corrente, totale, dettaglio='') -> None:
        """Il callback che il motore chiama mentre lavora (dal thread di lavoro)."""
        if self._avanz:
            self._avanz.riferisci(fase, corrente, totale, dettaglio)

    def _trascrivi_davvero(self, riprendi: bool) -> None:
        opzioni = self._opzioni()
        piano = piano_fasi(opzioni['backend'], self.scelte['sorgente'], opzioni)
        self._apri_lavoro(opzioni, piano)
        meta_iniziale = self._meta
        # Il crediti-esauriti non si intercetta qui: lo raccoglie _in_thread, che
        # lo tratta per quello che e' — un'attesa, non un guasto — ed e' l'unico
        # posto in cui la distinzione va fatta, invece che in ogni lavoro.
        meta, segmenti, etichetta, cliente = engine.transcribe_only(
            self._src, opzioni, on_progress=self._riferisci, resume=riprendi)
        risultato = engine.save_results(
            meta, segmenti, etichetta, opzioni, RISULTATI, cliente,
            on_progress=self._riferisci)
        self._avanz.concludi()
        # Il riassunto fermato per crediti esauriti non e' un errore: la
        # trascrizione e' salvata, e si puo' concludere in locale senza rifare
        # nulla. Chiederlo qui e' l'unico momento in cui la domanda ha senso.
        if risultato.get('summary_status') == 'partial' and opzioni['backend'] == 'groq':
            _verso_pagina('riassuntoInterrotto', self._risultato(risultato, meta_iniziale))
        else:
            _verso_pagina('mostraRisultato', self._risultato(risultato, meta_iniziale))

    def _dopo_davvero(self, azione: str) -> None:
        """Traduzione, riassunto o ripresa su un video gia' trascritto."""
        opzioni = self._opzioni()
        opzioni.update({'translate': True, 'summarize': True, 'visual': False})
        piano = {'traduci': ['info', 'translate'],
                 'riassumi': ['info', 'summarize'],
                 'riprendi_post': ['info', 'translate', 'summarize']}[azione]
        self._apri_lavoro(opzioni, piano)
        funzione = {'traduci': engine.translate_only,
                    'riassumi': engine.summary_only,
                    'riprendi_post': engine.resume}[azione]
        risultato = funzione(self._meta, opzioni, RISULTATI, on_progress=self._riferisci)
        self._avanz.concludi()
        if risultato.get('summary_status') == 'partial' and opzioni['backend'] == 'groq':
            _verso_pagina('riassuntoInterrotto', self._risultato(risultato, self._meta))
        else:
            _verso_pagina('mostraRisultato', self._risultato(risultato, self._meta))

    def concludi_in_locale(self) -> dict:
        """Finisce sul computer un riassunto che Groq ha lasciato a meta'.

        Riparte dalla sezione in cui si e' fermato: le sezioni gia' riassunte
        non si rifanno, e non serve alcuna chiave.
        """
        if self._occupato:
            return {'ok': False, 'errore': i18n.t('err.busy')}
        # La finestra puo' restare aperta mentre si cambia il link, e cambiarlo
        # dimentica la sorgente: senza questo controllo il lavoro partirebbe
        # senza sapere su cosa, e fallirebbe a meta' con un errore oscuro.
        if not self._meta:
            return {'ok': False, 'errore': i18n.t('err.no_file')}
        self._in_thread(self._riassunto_locale)
        return {'ok': True, 'avviato': True}

    def _riassunto_locale(self) -> None:
        opzioni = self._opzioni(motore='local')
        opzioni.update({'api_key': '', 'translate': True,
                        'summarize': True, 'visual': False})
        self._apri_lavoro(opzioni, ['info', 'summarize'])
        risultato = engine.summary_only(self._meta, opzioni, RISULTATI,
                                        on_progress=self._riferisci)
        self._avanz.concludi()
        _verso_pagina('mostraRisultato', self._risultato(risultato, self._meta))

    def continua_in_locale(self) -> dict:
        """Completa sul computer una trascrizione Groq rimasta senza crediti.

        Riusa il parziale gia' salvato: solo la coda non ancora trascritta passa
        dal modello locale, e viene ricucita con quello che c'era. Si sposta
        anche la scelta del motore, cosi' tornando alla sezione «Motore» si
        trova quello che sta davvero girando.
        """
        if self._occupato:
            return {'ok': False, 'errore': i18n.t('err.busy')}
        if not self._meta or not self._src:
            return {'ok': False, 'errore': i18n.t('err.no_file')}
        self.scelte['motore'] = 'local'
        i18n.save_prefs(**self.scelte)
        self._in_thread(self._coda_in_locale)
        return {'ok': True, 'avviato': True, 'scelte': self.scelte}

    def _coda_in_locale(self) -> None:
        opzioni = self._opzioni(motore='local')
        piano = piano_fasi('local', self.scelte['sorgente'], opzioni)
        self._apri_lavoro(opzioni, piano)
        meta, segmenti, etichetta, _ = engine.continue_local_from_groq(
            self._src, opzioni, on_progress=self._riferisci)
        risultato = engine.save_results(meta, segmenti, etichetta, opzioni,
                                        RISULTATI, None, on_progress=self._riferisci)
        self._avanz.concludi()
        _verso_pagina('mostraRisultato', self._risultato(risultato, self._meta))

    # ── Playlist ─────────────────────────────────────────────────────────────

    def _playlist_davvero(self) -> None:
        """Trascrive in fila tutti i video di una playlist confermata.

        Tre regole, e sono quelle che rendono il batch sopportabile su una lista
        lunga: un video gia' presente si salta senza spendere nulla; uno che
        fallisce non ferma gli altri; se Groq esaurisce i crediti ci si ferma li'
        — quelli fatti restano salvati e domani si riprende.
        """
        playlist = self._playlist
        voci = playlist['items']
        radice = os.path.join(RISULTATI, playlist['subdir'])
        opzioni = self._opzioni()
        opzioni['source_kind'] = 'youtube'

        fatti: list[dict] = []
        saltati: list[str] = []
        falliti: list[str] = []
        senza_crediti = False

        for numero, meta in enumerate(voci, 1):
            # Il controllo «c'e' gia'» viene PRIMA di annunciare il lavoro: un
            # video saltato non deve azzerare la barra e riscrivere il piano per
            # poi non fare niente, che a schermo si legge come un lavoro partito
            # e subito bloccato.
            if tx.transcription_exists(radice, meta['title']):
                saltati.append(meta['title'])
                continue

            piano = piano_fasi(opzioni['backend'], 'youtube', opzioni)
            self._apri_lavoro(opzioni, piano)
            _verso_pagina('lavoroBatch',
                          i18n.t('playlist.batch', i=numero, n=len(voci)),
                          meta.get('title') or '?')
            try:
                meta2, segmenti, etichetta, cliente = engine.transcribe_only(
                    meta.get('webpage_url') or '', opzioni,
                    on_progress=self._riferisci, resume=False)
                fatti.append(engine.save_results(
                    meta2, segmenti, etichetta, opzioni, radice, cliente,
                    on_progress=self._riferisci))
                # Come per un video singolo: l'ultima fase riferisce e poi tace,
                # quindi senza questa la barra di ogni video resterebbe a un
                # passo dalla fine con tutto gia' scritto sul disco.
                self._avanz.concludi()
            except engine.RateLimitReached:
                senza_crediti = True
                break
            except Exception:                          # noqa: BLE001
                falliti.append(meta['title'])
                continue

        self._ultima_cartella = radice
        _verso_pagina('mostraRisultatoPlaylist', {
            'titolo': i18n.t('playlist.res.title'),
            'cartella': radice,
            'avviso': i18n.t('playlist.stopped') if senza_crediti else '',
            'conteggi': [
                {'tono': 'ok', 'testo': i18n.t('playlist.res.done', n=len(fatti))},
                {'tono': 'neutro', 'testo': i18n.t('playlist.res.skipped', n=len(saltati))}
                if saltati else None,
                {'tono': 'attenzione', 'testo': i18n.t('playlist.res.failed', n=len(falliti))}
                if falliti else None,
            ],
            'voci': ([{'tono': 'ok', 'titolo': r.get('title', '?')} for r in fatti]
                     + [{'tono': 'neutro', 'titolo': t} for t in saltati]
                     + [{'tono': 'attenzione', 'titolo': t} for t in falliti]),
        })

    # ── Il risultato ─────────────────────────────────────────────────────────

    def _risultato(self, res: dict, meta: dict | None) -> dict:
        """Il risultato del motore, ridotto a cio' che la finestra deve mostrare.

        I file vengono raggruppati per cartella perche' e' cosi' che stanno sul
        disco, ed e' l'unico modo in cui l'elenco di dieci nomi resta leggibile.
        """
        self._ultima_cartella = res.get('video_dir', '')
        visiva = res.get('visual') or {}
        self._ultima_visiva = visiva.get('dir') or ''

        gruppi: dict[str, list[str]] = {}
        for percorso in res.get('files', []):
            taglio = percorso.find('/')
            cartella = percorso[:taglio] if taglio >= 0 else ''
            nome = percorso[taglio + 1:] if taglio >= 0 else percorso
            gruppi.setdefault(cartella, []).append(nome)

        crediti = res.get('credits') or {}
        residuo = None
        for voce in (crediti.get('limits') or []):
            if voce.get('kind') == 'audio_seconds' and voce.get('remaining') is not None:
                residuo = voce['remaining']
                break

        return {
            'titolo': i18n.t('res.title'),
            'miniatura': (meta or {}).get('thumbnail') or '',
            'avvisi': res.get('warnings') or [],
            'dati': [
                {'chiave': 'res.engine', 'valore': res.get('engine_label', '')},
                {'chiave': 'res.segments', 'valore': str(res.get('segments', 0))},
                {'chiave': 'res.words', 'valore': f"~{res.get('words', 0)}"},
                {'chiave': 'res.sections',
                 'valore': str(res.get('sections') or i18n.t('res.continuous'))},
            ],
            'cartella': res.get('video_dir', ''),
            'gruppi': [{'cartella': c or i18n.t('res.root'), 'file': f}
                       for c, f in gruppi.items()],
            'crediti': ([
                {'chiave': 'res.credits.used',
                 'valore': tx._format_timestamp(crediti.get('audio_seconds_used') or 0)},
            ] + ([{'chiave': 'res.credits.left',
                   'valore': tx._format_timestamp(residuo)}] if residuo is not None else [])
            ) if crediti else [],
            'visiva': ({'n': visiva['count'], 'cartella': visiva.get('dir', '')}
                       if visiva.get('count') else None),
        }

    # ── Crediti Groq ─────────────────────────────────────────────────────────

    def crediti(self) -> dict:
        """I crediti residui per modello, letti dalla cache passiva.

        Le richieste vere (trascrizione, riassunto, analisi visiva) portano
        indietro negli header quanto e' rimasto: qui li si rilegge e basta.
        Aprire questa sezione NON contatta Groq e non consuma nulla, quindi e'
        istantanea e la si puo' guardare quanto si vuole.
        """
        modelli = []
        for m in engine.get_cached_credits():
            ruolo = m.get('role', 'other')
            voci = []
            for it in (m.get('items') or []):
                tipo = it.get('kind', '')
                voci.append({
                    'tipo': tipo,
                    'nome': i18n.t(f'lim.kind.{tipo}'),
                    'usato': i18n.t('lim.used', v=self._quantita(it, it.get('used'))),
                    'residuo': i18n.t('lim.left', v=self._residuo(it)),
                    'ripristino': (i18n.t('lim.reset', v=self._ripristino(it))
                                   if it.get('reset_seconds') is not None else ''),
                })
            modelli.append({
                'ruolo': i18n.t(f'lim.role.{ruolo}'),
                'modello': m.get('model', ''),
                # 'or' e non un default di get(): la chiave c'e' sempre, ma vale
                # None finche' quel modello non e' stato chiamato, e "aggiornato
                # alle None" e' esattamente il genere di riga che fa sembrare
                # rotto un programma che sta funzionando.
                'aggiornato': i18n.t('lim.checked', v=m.get('checked_at') or '—'),
                'voci': voci,
                'nota': ('' if voci else
                         (i18n.t('lim.none') if m.get('used') else i18n.t('lim.unused'))),
            })
        return {'ok': True, 'modelli': modelli}

    def _quantita(self, voce: dict, valore) -> str:
        """Una quantita' di credito: l'audio come durata, il resto come numero."""
        if valore is None:
            return '?'
        if voce.get('kind') == 'audio_seconds':
            return tx._format_timestamp(valore)
        return f'{int(valore):,}'.replace(',', '.')

    def _residuo(self, voce: dict) -> str:
        rimasto, limite = voce.get('remaining'), voce.get('limit')
        if limite is not None:
            return i18n.t('lim.remaining', rem=self._quantita(voce, rimasto),
                          lim=self._quantita(voce, limite))
        return i18n.t('lim.remaining_only', rem=self._quantita(voce, rimasto))

    def _ripristino(self, voce: dict) -> str:
        """Quando i crediti tornano: l'ora esatta piu' l'attesa che manca.

        L'ora da sola non dice quanto aspettare, l'attesa da sola non dice
        quando tornare: servono tutt'e due, ed e' l'unica riga di questa finestra
        su cui si prende una decisione.
        """
        durata = self._durata_breve(voce['reset_seconds'])
        orologio = self._quando(voce.get('reset_at_iso'))
        if orologio:
            return i18n.t('lim.reset.at', orologio=orologio, durata=durata)
        return i18n.t('lim.reset.in', durata=durata)

    @staticmethod
    def _durata_breve(secondi: float) -> str:
        """Durata compatta: '2h 5m', '3m 20s', '45s'."""
        s = int(round(secondi or 0))
        ore, minuti, sec = s // 3600, (s % 3600) // 60, s % 60
        pezzi = []
        if ore:
            pezzi.append(f'{ore}h')
        if minuti:
            pezzi.append(f'{minuti}m')
        if sec or not pezzi:
            pezzi.append(f'{sec}s')
        return ' '.join(pezzi)

    @staticmethod
    def _quando(iso: str | None) -> str:
        """L'istante di ripristino detto come lo direbbe una persona."""
        if not iso:
            return ''
        try:
            quando = _dt.datetime.fromisoformat(iso)
        except ValueError:
            return ''
        oggi = _dt.date.today()
        hm = quando.strftime('%H:%M')
        if quando.date() == oggi:
            return i18n.t('lim.reset.today', hm=hm)
        if quando.date() == oggi + _dt.timedelta(days=1):
            return i18n.t('lim.reset.tomorrow', hm=hm)
        return i18n.t('lim.reset.date', dm=quando.strftime('%d/%m'), hm=hm)

    # ── Aprire cose nel sistema ──────────────────────────────────────────────

    def apri(self, quale: str = 'cartella') -> dict:
        """Apre nel sistema la cartella dei risultati o quella dell'analisi visiva."""
        percorso = self._ultima_visiva if quale == 'visiva' else self._ultima_cartella
        if not percorso:
            return {'ok': False}
        try:
            if os.name == 'nt':
                os.startfile(percorso)                 # type: ignore[attr-defined]
            else:
                import webbrowser
                webbrowser.open('file://' + percorso)
        except OSError:
            return {'ok': False}
        return {'ok': True}

    def apri_url(self, indirizzo: str) -> dict:
        """Apre un indirizzo nel browser predefinito (per «Ottieni una chiave»)."""
        import webbrowser
        try:
            webbrowser.open(indirizzo)
        except Exception:                              # noqa: BLE001
            return {'ok': False}
        return {'ok': True}

    # ── Utilita' interne ─────────────────────────────────────────────────────

    def _in_thread(self, funzione, *argomenti) -> None:
        """Fa girare il lavoro fuori dal thread della finestra.

        L'output dei moduli viene dirottato al diario solo per la durata del
        lavoro: farlo per sempre catturerebbe anche i messaggi di pywebview, che
        alla pagina non servono.

        Il crediti-esauriti non passa di qui come errore: e' una condizione
        prevista e recuperabile, non un guasto, e chi la incontra la gestisce da
        se' con una finestra che offre come proseguire.
        """
        def guscio():
            self._occupato = True
            _verso_pagina('cambiaStato', 'working')
            diario = Diario()
            vecchio_out, vecchio_err = sys.stdout, sys.stderr
            sys.stdout = sys.stderr = diario
            try:
                funzione(*argomenti)
                _verso_pagina('cambiaStato', 'done')
            except engine.RateLimitReached as exc:
                self._crediti_finiti(exc)
            except engine.EngineError as exc:
                _verso_pagina('erroreLavoro', str(exc))
            except Exception as exc:                   # noqa: BLE001
                _verso_pagina('aggiungiRiga', traceback.format_exc())
                _verso_pagina('erroreLavoro', i18n.t('err.unexpected', e=exc))
            finally:
                diario.flush()
                sys.stdout, sys.stderr = vecchio_out, vecchio_err
                self._occupato = False

        threading.Thread(target=guscio, daemon=True).start()

    def _crediti_finiti(self, exc) -> None:
        """Groq ha esaurito i crediti: e' un'attesa, non un guasto.

        Il parziale e' gia' stato salvato dal motore, quindi le due uscite sono
        entrambe vere: tornare domani e riprendere, o finire adesso sul proprio
        computer. Dirlo in rosso sarebbe sbagliato: non si e' rotto niente.
        """
        _verso_pagina('creditiFiniti', {
            'titolo': i18n.t('rate.title'),
            'testo': i18n.t('rate.msg',
                            fatto=tx._format_timestamp(int(getattr(exc, 'done_seconds', 0) or 0)),
                            totale=tx._format_timestamp(int(getattr(exc, 'total_seconds', 0) or 0))),
            'puo_locale': self._src != '' and self._meta is not None,
        })


def main() -> None:
    global _finestra
    _scadenza_avvio()

    i18n.set_language(i18n.load_saved() or 'it')

    _finestra = webview.create_window(
        'EchoScript',
        _risorsa('web', 'index.html'),
        js_api=Api(),
        width=1180,
        height=800,
        min_size=(940, 640),
        # Il fondo della finestra prima che la pagina dipinga: il nero
        # violaceo del tema (--f1 in style.css). Con qualunque altro colore ogni
        # avvio comincerebbe con un lampo di un tema che non esiste piu'.
        background_color='#0a0a16',
        text_select=False,
        # Nascosta finche' la pagina non e' pronta: vedi il commento in cima al
        # file. La mostra _pronti().
        hidden=True,
    )

    # La finestra c'e': da qui in poi l'attesa e' tutta di WebView2, che nessuno
    # puo' misurare dall'esterno. La barra si ferma qui e riparte dentro la
    # pagina, che sa raccontare i propri passi.
    _avanza(APERTURA)

    # L'icona della finestra. Su Windows pywebview, se non gliela si passa, la
    # estrae dall'eseguibile: lanciando i sorgenti finirebbe quella di
    # python.exe, quindi gliela si indica sempre quando c'e'.
    icona = _risorsa('assets', 'EchoScript.ico')
    # 'func' viene eseguito appena il giro della finestra e' partito, cioe' nel
    # mezzo dell'unico tratto che nessuno puo' misurare: quello in cui WebView2
    # si inizializza e carica la pagina. Non e' molto, ma e' un movimento vero in
    # un momento in cui altrimenti la barra resterebbe immobile per qualche
    # secondo — e una barra immobile e' esattamente cio' che fa pensare a un
    # programma piantato. Resta sotto al primo passo del velo, cosi' quando le
    # due schermate si scambiano la barra non torna mai indietro.
    webview.start(lambda: _avanza(0.66),
                  icon=icona if os.path.isfile(icona) else None)


if __name__ == '__main__':
    main()
