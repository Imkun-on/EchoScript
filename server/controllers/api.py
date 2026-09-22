"""Cio' che la pagina puo' chiedere a Python, e la risposta che riceve.

Che mestiere fa
    Sta in mezzo. La pagina sa disegnare e raccogliere clic ma non sa
    trascrivere niente; il motore sa trascrivere ma non sa che esiste una
    finestra. Ogni metodo pubblico di ``Api`` e' una domanda che la pagina puo'
    fare: quel metodo chiama chi la sa eseguire e restituisce la risposta in
    una forma che la pagina possa mostrare.

    E' lo stesso mestiere che in un'applicazione web fa un controller, solo
    senza indirizzi web in mezzo: la pagina scrive ``pywebview.api.carica_info(...)``
    e finisce dentro il metodo ``carica_info`` qui sotto, direttamente. Niente
    protocollo, niente server, nessuna porta aperta sul computer.

Il lavoro lungo non blocca la finestra
    Ogni operazione che dura piu' di un istante viene messa in un thread suo e
    riferisce alla pagina mentre procede, passando da ``bridge``. La finestra
    resta viva: si legge il diario e, soprattutto, si vede che sta succedendo
    qualcosa invece di una finestra che non risponde.

Perche' il motore si importa tardi
    Questo modulo viene caricato mentre la finestra si sta aprendo, e in quel
    momento importare il motore costerebbe qualche secondo di schermo vuoto.
    Percio' i nomi ``tx`` ed ``engine`` nascono vuoti e li riempie
    ``carica_motore()``, che gira quando la pagina e' gia' sotto gli occhi di
    chi aspetta. Nulla di quello che viene eseguito PRIMA di allora puo'
    toccarli: ne' il corpo di questo modulo, ne' il costruttore di ``Api``.
"""
from __future__ import annotations

import io
import os
import sys
import threading
import traceback

import webview

from server.config import i18n, settings
from server.utils import text
from server.controllers import bridge
from server.config import settings
from server.services import estimate
from server.sources import metadata
from server.state import checkpoints, jobs
from server.utils import contract, media, ollama


# I due nomi del motore restano vuoti finche' non li riempie carica_motore().
engine = None               # il direttore d'orchestra
RISULTATI = ''              # dove finiscono le trascrizioni: lo sa engine

# Alzato quando il motore e' pronto. La pagina, al suo primo saluto, si mette
# qui ad aspettare: e' il punto in cui i due tempi si incontrano senza che
# nessuno dei due debba sapere quanto ha impiegato l'altro.
MOTORE_PRONTO = threading.Event()


# ═══════════════════════════════════════════════════════════════════════════
#  DUE POSTAZIONI, E COME SI FA A NON CONFONDERLE
# ═══════════════════════════════════════════════════════════════════════════
#
# «Locale» e «Cloud» sono due posti di lavoro veri e indipendenti. In ciascuno
# si puo' avere una sorgente diversa, e in entrambi puo' girare un lavoro nello
# stesso momento: mentre Groq trascrive sui suoi server, questo computer puo'
# trascriverne un altro per conto suo. Sono due mestieri che non si contendono
# niente, e farli aspettare a turno sarebbe stato buttare via meta' del tempo.
#
# Da qui nasce un problema che prima non esisteva: quando qualcosa ha da dire
# alla pagina, la pagina deve sapere A QUALE delle due postazioni si riferisce.
# Una percentuale di avanzamento senza quel dato non vuol dire niente: e' come
# gridare «sono all'ottanta per cento» in una stanza con due lavagne.
#
# Passarlo a mano avrebbe voluto dire aggiungere un argomento a una trentina di
# chiamate sparse, e bastava dimenticarne una perche' una riga finisse sulla
# lavagna sbagliata senza che nessun controllo se ne accorgesse.
#
# Invece lo si legge dal thread. Ogni lavoro gira nel suo, e un thread appartiene
# a una postazione sola dal primo istante alla fine: quindi il thread stesso E'
# la risposta alla domanda, e nessuno ha bisogno di ricordarsi di portarsela
# dietro. Chi avvia un lavoro scrive qui dentro dove sta lavorando, e da quel
# momento tutto quello che quel thread dice parte gia' con l'indirizzo giusto.
_DOVE = threading.local()


def _qui() -> str:
    """In quale delle due postazioni sta lavorando il thread che chiama.

    Il ripiego e' «locale» e non un errore perche' questa domanda la fanno
    anche thread che non appartengono a nessun lavoro, per esempio quello della
    finestra quando la pagina chiede qualcosa: li' non c'e' una risposta
    sbagliata, c'e' una risposta che non serve a nessuno.
    """
    return getattr(_DOVE, 'dove', 'locale')


def _verso_pagina(funzione: str, *argomenti) -> None:
    """Dice qualcosa alla pagina, a nome della postazione che sta parlando.

    E' la stessa cosa di prima con l'indirizzo davanti. La pagina riceve tutto
    da un'unica porta, ``__instrada``, che guarda l'indirizzo e consegna alla
    postazione giusta: cosi' un avanzamento che arriva da «Cloud» non tocca
    niente di quello che si sta guardando in «Locale».
    """
    bridge.verso_pagina('__instrada', _qui(), funzione, list(argomenti))


def _verso_tutti(funzione: str, *argomenti) -> None:
    """Dice qualcosa che non riguarda nessuna postazione in particolare.

    Sono due sole cose: a che punto e' l'avvio del programma, e i cataloghi dei
    modelli quando Ollama finisce di farsi interrogare. Non appartengono a un
    lavoro, quindi non hanno un indirizzo, quindi passano dalla porta di
    servizio invece che dallo smistamento.
    """
    bridge.verso_pagina(funzione, *argomenti)


class Smistatore(io.TextIOBase):
    """Manda quello che viene stampato al diario del lavoro che l'ha stampato.

    Perche' non basta piu' dirottare l'uscita standard
        Prima il lavoro era uno solo: gli si puntava contro ``sys.stdout`` per
        tutta la sua durata e si rimetteva a posto alla fine. Con due lavori
        insieme quel gesto non funziona piu', perche' ``sys.stdout`` e' uno per
        tutto il programma: il secondo a partire sovrascriverebbe il primo, e
        le righe dei due finirebbero mescolate in un diario solo.

    Cosa si fa invece
        Questo oggetto prende il posto dell'uscita standard una volta sola,
        all'avvio, e non se ne va piu'. Ogni lavoro si registra qui dicendo
        «il thread che sto per usare scrive sul mio diario». Quando arriva
        qualcosa, si guarda da quale thread arriva e lo si consegna li'.

        Quello che non viene da nessun lavoro, per esempio i messaggi di
        pywebview, passa dritto all'uscita vera come se questo oggetto non ci
        fosse. E' il motivo per cui puo' restare installato per sempre senza
        rubare niente a nessuno.
    """

    def __init__(self, vera):
        """Tiene da parte l'uscita vera e apre il registro dei diari.

        Il lucchetto protegge il registro e non la scrittura: a scrivere sono
        thread diversi su diari diversi, che non si pestano i piedi, ma
        iscriversi e cancellarsi capita mentre un altro sta cercando, e una
        ricerca dentro un dizionario che cambia e' il genere di guaio che si
        manifesta una volta su mille avvii.
        """
        self._vera = vera
        self._diari: dict[int, Diario] = {}
        self._lucchetto = threading.Lock()

    def registra(self, diario) -> None:
        """Da adesso quello che stampa QUESTO thread va in questo diario."""
        with self._lucchetto:
            self._diari[threading.get_ident()] = diario

    def dimentica(self) -> None:
        """Il lavoro e' finito: questo thread torna a scrivere sull'uscita vera.

        Si chiama sempre, anche quando e' andata male, perche' un thread che
        resta iscritto dopo essere morto lascia nel registro un diario che
        nessuno svuotera' mai.
        """
        with self._lucchetto:
            self._diari.pop(threading.get_ident(), None)

    def write(self, s: str) -> int:        # type: ignore[override]
        with self._lucchetto:
            diario = self._diari.get(threading.get_ident())
        if diario is not None:
            return diario.write(s)
        return self._vera.write(s) if self._vera is not None else len(s)

    def flush(self) -> None:
        if self._vera is not None:
            try:
                self._vera.flush()
            except Exception:
                pass


# Prende il posto dell'uscita standard una volta sola, quando questo modulo
# viene importato, e non lo lascia piu'. Finche' nessun lavoro si registra non
# fa assolutamente niente: passa tutto all'uscita vera.
_SMISTATORE = Smistatore(sys.stdout)
sys.stdout = sys.stderr = _SMISTATORE

# Le tappe del caricamento, con quanto pesa ciascuna sulla barra.
#
# I numeri sono misurati, non scelti a occhio: importare il motore costa cinque
# volte quanto importare il ponte con la finestra, perche' si porta dietro Groq,
# yt-dlp e Rich. Dando a ogni tappa la stessa fetta la barra correrebbe fino a
# meta' e poi si pianterebbe, che e' esattamente il difetto che si voleva
# togliere.
_TAPPA_PARTENZA = 0.15
_TAPPA_MOTORE = 0.55        # i moduli pesanti: il tratto lungo
_TAPPA_ORCHESTRA = 0.70     # il direttore d'orchestra, che sopra costa poco
_TAPPA_PRONTO = 0.80        # da qui in poi riempie la pagina


def carica_motore() -> None:
    """Importa il motore mentre la finestra e' gia' sullo schermo.

    Viene eseguita da pywebview appena il giro della finestra e' partito, cioe'
    quando la pagina e il suo velo di caricamento sono gia' visibili. Da li' in
    poi ogni pezzo caricato fa avanzare la barra del velo.

    Perche' l'evento viene alzato nel finally
        Perche' se un import fallisce, la pagina resterebbe ad aspettare per
        sempre un segnale che non arriverebbe mai: barra ferma, nessun
        messaggio, e l'unico modo di uscirne e' chiudere la finestra. Alzandolo
        comunque la pagina prosegue, prova a chiedere quello che le serve, e
        l'errore vero viene a galla invece di restare nascosto dietro
        un'attesa infinita.
    """
    global engine, RISULTATI
    try:
        _avanzamento(_TAPPA_PARTENZA)

        # Importare il direttore d'orchestra tira dentro tutto il resto: Groq,
        # yt-dlp, Rich, faster-whisper. E' il tratto lungo dell'avvio, e l'unico
        # che valga la pena raccontare sulla barra.
        from server.services import pipeline as _pipeline
        engine = _pipeline
        _avanzamento(_TAPPA_MOTORE)

        # Gli elenchi dei modelli: si leggono dalle impostazioni, quindi
        # costano niente. Stanno dopo l'import pesante solo per tenere in
        # ordine il racconto della barra.
        riempi_cataloghi()
        _avanzamento(_TAPPA_ORCHESTRA)

        # Fuori dall'eseguibile e' la stessa cartella della riga di comando,
        # cosi' le due interfacce vedono lo stesso archivio e il controllo
        # "questo video c'e' gia'" funziona a prescindere da come lo si e'
        # trascritto. Dentro l'eseguibile quella cartella sarebbe temporanea,
        # quindi si va accanto all'.exe.
        # Una riga sola e non piu' un bivio: adesso e' pipeline a chiedere a
        # paths dove sta la cartella dei dati, e paths risponde gia' in modo
        # diverso a seconda che si stia lanciando i sorgenti o l'eseguibile.
        # Il bivio che c'era qui faceva lo stesso lavoro una seconda volta.
        RISULTATI = engine.RESULTS_DIR
        _avanzamento(_TAPPA_PRONTO)
    finally:
        MOTORE_PRONTO.set()


def _avanzamento(quota: float) -> None:
    """Dice alla pagina a che punto e' il caricamento del motore, da 0 a 1.

    Se la pagina non c'e' ancora, il messaggio si perde e non succede niente.
    Capita davvero nei primi istanti, perche' il motore comincia a caricarsi
    prima che la finestra esista: e' voluto, ed e' il motivo per cui l'avvio
    dura la meta' di prima.
    """
    _verso_tutti('avanzamentoAvvio', quota)


# pywebview 6 ha rinominato le costanti dei selettori di file. Si prendono le
# nuove quando esistono e si ricade sulle vecchie: cosi' il programma non stampa
# avvisi di deprecazione sulle versioni recenti e continua a girare su quelle
# precedenti.
_DLG_APRI = getattr(getattr(webview, 'FileDialog', None), 'OPEN',
                    getattr(webview, 'OPEN_DIALOG', 10))



# ── Cataloghi dei modelli ────────────────────────────────────────────────────
# Le chiavi di descrizione seguono il nome del modello ('model.small') o il
# numero di catalogo di transcriber.py ('om.text.2'): cosi' aggiungere un
# modello e' una riga qui e una nel file dei testi, non una modifica al codice.
#
# Sono divisi in due gruppi che non si mescolano mai (quelli che girano sul
# computer e quelli che girano sui server Groq), perche' e' cosi' che sono
# divise le due sezioni dell'interfaccia: scegliere il motore sceglie il gruppo
# intero, trascrizione e riassunto e analisi visiva insieme.

# I modelli di trascrizione sono scritti qui perche' sono un elenco fisso e
# corto, che non dipende da niente.
_WHISPER = ('base', 'small', 'medium', 'large-v3', 'large-v3-turbo')
_GROQ = ('whisper-large-v3-turbo', 'whisper-large-v3')

# Gli altri quattro invece si costruiscono leggendo i cataloghi di
# transcriber.py, che al momento in cui si legge questo file non e' ancora
# stato importato: nascono vuoti e li riempie riempi_cataloghi(), chiamata
# da carica_motore() appena il motore c'e'.
#
# Nessuno li legge prima di allora. Chi li usa sono i metodi che rispondono
# alla pagina, e la pagina non puo' chiedere niente finche' non ha ricevuto
# risposta da avvio(), che a sua volta aspetta il motore.
_OLLAMA_TESTO: list = []
_OLLAMA_VISTA: list = []
_GROQ_TESTO: list = []
_GROQ_VISTA: list = []


def riempi_cataloghi() -> None:
    """Costruisce gli elenchi dei modelli leggendoli dalle impostazioni.

    Ogni voce si porta dietro la chiave del testo che la descrive
    ('om.text.2', 'gm.vis.1'). E' il motivo per cui aggiungere un modello resta
    una riga nelle impostazioni e una nel file dei testi: il codice che disegna
    i menu non sa quali modelli esistono, li chiede.
    """
    global _OLLAMA_TESTO, _OLLAMA_VISTA, _GROQ_TESTO, _GROQ_VISTA
    _OLLAMA_TESTO = [(nome, ram, f'om.text.{k}')
                     for k, (nome, ram, _d) in settings.OLLAMA_TEXT_MODELS.items()]
    _OLLAMA_VISTA = [(nome, ram, f'om.vis.{k}')
                     for k, (nome, ram, _d) in settings.OLLAMA_VISION_MODELS.items()]
    _GROQ_TESTO = [(nome, f'gm.text.{k}')
                   for k, (nome, _d) in settings.GROQ_TEXT_MODELS.items()]
    _GROQ_VISTA = [(nome, f'gm.vis.{k}')
                   for k, (nome, _d) in settings.GROQ_VISION_MODELS.items()]



class Diario(io.TextIOBase):
    """Dove finisce cio' che i moduli stampano, adesso che non lo legge piu' nessuno.

    Com'era
        Queste righe finivano in un riquadro a schermo, il diario, accanto alla
        sorgente. Il riquadro e' stato tolto: raccontava lo stesso lavoro che la
        barra di avanzamento racconta meglio, e quando qualcosa andava storto la
        riga che contava finiva sepolta sotto centinaia di righe di servizio.
        Adesso un guasto apre una finestra che dice su quale video, di che cosa
        si tratta e qual era il testo tecnico.

    Perche' la classe non e' sparita insieme al riquadro
        Perche' il suo altro mestiere, quello silenzioso, serve ancora. Il
        programma installato gira SENZA console (``console=False`` nello spec di
        PyInstaller): l'uscita standard, li', non e' un terminale, e una print
        arrivata nel momento sbagliato diventa un guasto vero in un punto che
        con quella print non c'entra niente.

        Questa classe e' il paracadute. Prende quello che qualcuno stampa, dice
        di averlo preso, e non ne fa niente.

    Chi ci scrive davvero
        Quasi nessuno, ed e' il motivo per cui buttare via va bene. ``engine.py``
        non contiene una sola print, e le funzioni di trascrizione chiamate da
        qui sono le versioni nude, quelle che riferiscono solo col callback; a
        stampare con Rich sono i wrapper ``_cli_*``, che chiama soltanto la riga
        di comando. Quello che passava di qui erano le fasi, che si vedono nella
        barra, e i guasti, che adesso arrivano nella finestra dell'errore con il
        loro traceback allegato.
    """

    def write(self, s: str) -> int:      # type: ignore[override]
        """Accetta quello che qualcuno ha stampato e lo lascia cadere.

        Il numero restituito e' quanti caratteri si e' presi in carico, e va
        restituito per davvero: chi stampa lo controlla, e un conto che non
        torna lo fa riprovare all'infinito.
        """
        return len(s or '')

    def flush(self) -> None:
        """Non c'e' niente in sospeso da mandare, ma il metodo deve esistere.

        Python lo chiama sull'uscita standard in momenti che non decidiamo noi,
        per esempio alla chiusura del programma. Una classe che non ce l'ha
        farebbe fallire quella chiamata.
        """


class Avanzamento:
    """Traduce le fasi del motore in una barra che non torna mai indietro.

    Il motore riferisce ``(fase, corrente, totale, dettaglio)`` e non sa quante
    fasi ci siano in tutto: quello lo decide chi avvia il lavoro, in base a cosa
    e' stato chiesto (un file locale non si scarica, solo Groq divide in
    blocchi, traduzione e riassunto ci sono solo se spuntati).

    Ogni fase occupa una fetta ``[i/n, (i+1)/n]`` del totale, e dentro la fetta
    si interpola col progresso vero. Quando una fase non sa quanto manca, per
    esempio mentre carica un modello, la barra resta all'inizio della sua
    fetta invece di
    girare a vuoto: cosi' quando si muove vuol dire qualcosa.

    Scrive anche il diario, dagli stessi dati. Non e' una ripetizione: la barra
    dice dove siamo adesso e cancella cio' che c'era prima, il diario tiene
    l'ordine e le ore. Su un lavoro lungo (novanta secondi fermi a caricare un
    modello) o su una playlist di cinquanta video, quello che e' gia' successo
    conta quanto quello che sta succedendo.
    """

    def __init__(self, piano: list[str]):
        """Parte da un piano: l'elenco delle fasi previste per questo lavoro.

        Serve a poter dire un numero vero invece di far girare una barra a
        vuoto. Sapendo che le fasi sono cinque e che si e' alla terza, la barra
        puo' dire sessanta per cento e non mentire.

        Il massimo raggiunto si tiene da parte perche' la barra non deve MAI
        tornare indietro: una fase che riferisce un valore piu' basso della
        precedente capita, e vedere una barra che arretra fa pensare che
        qualcosa sia andato storto anche quando va tutto bene.
        """
        self.piano = piano
        self._massimo = 0.0

    def riferisci(self, fase: str, corrente, totale, dettaglio: str = '') -> None:
        """Il motore dice a che punto e'; qui diventa una barra.

        Traduce due cose diverse in una sola: quanto manca alla fine di QUESTA
        fase, e quanto pesa questa fase sul lavoro intero. Il motore sa solo la
        prima, perche' non ha idea di quante altre fasi siano previste.
        """
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


def piano_fasi(motore: str, sorgente: str, opzioni: dict) -> list[str]:
    """Sequenza ordinata delle fasi di un lavoro.

    Dipende dal contesto: un file locale non si scarica, solo Groq divide
    l'audio in blocchi, e le fasi facoltative si aggiungono solo se richieste,
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


class Posto:
    """Una delle due postazioni di lavoro: «Locale» o «Cloud».

    Cosa ci sta dentro
        Tutto quello che appartiene a UN lavoro e non all'altro: la sorgente
        confermata, se c'e' qualcosa in corso, e a che punto e'. Niente di
        tutto questo ha senso fuori dalla stanza in cui e' stato scelto.

    Cosa NON ci sta dentro
        La chiave di Groq, i cataloghi dei modelli, le cartelle aperte per
        ultime. Sono cose del programma, non del lavoro: la chiave e' la stessa
        chiave da qualunque parte la si guardi, e averne due copie vorrebbe
        dire solo poterle far divergere.

    Perche' sono due oggetti e non due prefissi
        Perche' cosi' aggiungere un dato al lavoro e' aggiungere un campo qui,
        e vale automaticamente per tutte e due le postazioni. Con due gruppi di
        variabili prefissate, ogni dato nuovo andrebbe scritto due volte, e la
        volta in cui se ne scrive una sola e' quella in cui «Cloud» comincia a
        ricordarsi qualcosa che «Locale» dimentica.
    """

    def __init__(self, dove: str, motore: str):
        """Una postazione vuota, che sa solo come si chiama e con cosa lavora.

        Il motore e' deciso qui e non cambia mai: «Locale» trascrive su questo
        computer e «Cloud» sui server Groq, e sono le due cose che danno il nome
        alle stanze. Prima era una scelta che viaggiava a parte e poteva non
        corrispondere alla stanza in cui si era; adesso la stanza E' la scelta,
        e non c'e' piu' niente da tenere allineato.
        """
        self.dove = dove
        self.motore = motore

        # Un lavoro in corso qui dentro. L'altra postazione non lo guarda: e'
        # esattamente il motivo per cui si puo' lavorare in due.
        self.occupato = False
        self.avanz: Avanzamento | None = None

        # La sorgente confermata: metadati letti, percorso o URL, ed eventuale
        # playlist. Vive qui e non nella pagina perche' e' il motore a produrla
        # e il motore a riceverla indietro: farla passare per JavaScript
        # significherebbe copiarla due volte e rischiare che divergano.
        self.meta: dict | None = None
        self.src: str = ''
        self.playlist: dict | None = None

        # Dove sono finiti i file dell'ultimo lavoro FINITO QUI. Servono al
        # bottone «Apri la cartella» del riepilogo, che e' il riepilogo di
        # questa postazione: con un valore solo per tutto il programma,
        # finendo due lavori a poca distanza, il bottone del primo avrebbe
        # aperto la cartella del secondo.
        self.ultima_cartella = ''
        self.ultima_visiva = ''

        # Gli interruttori degli output. Stanno qui e non fra le scelte
        # generali perche' si sceglie video per video: si puo' volere il
        # riassunto di quello che sta girando in nuvola e non di quello che sta
        # girando su questo computer.
        self.opz: dict = {}


class Api:
    """I metodi che la pagina puo' chiamare, e nient'altro.

    Ogni metodo restituisce un dizionario con almeno ``ok``: la pagina non deve
    mai ricevere un'eccezione Python, che in JavaScript arriverebbe come un
    rifiuto senza spiegazione.

    Qui non si decide niente di importante. Se un video sia una playlist, se
    esista gia' una trascrizione, quanto costera' un lavoro: sono domande a cui
    rispondono ``server/services/pipeline.py`` e ``transcriber.py``, e questo file si limita
    a girare la risposta alla pagina.
    """

    def __init__(self):
        """Prepara lo stato di una sessione di lavoro, ancora vuoto.

        Qui NON si tocca il motore, e non e' un caso: questo oggetto nasce
        insieme alla finestra, e la finestra nasce prima del motore. Tutto
        quello che ha bisogno di sapere qualcosa del motore si riempie dopo,
        in _leggi_scelte(), quando la pagina fa il suo primo saluto.

        C'e' un controllo automatico che verifica proprio questa cosa, perche'
        e' un errore che non si vede compilando: si vede solo aprendo il
        programma e trovandolo piantato sulla schermata di caricamento.
        """
        # Le due postazioni. Da qui in avanti nessun lavoro ha uno stato
        # suo sparso dentro questo oggetto: ce l'ha dentro la sua postazione,
        # e questo oggetto sa solo quali postazioni esistono.
        self._posti = {'locale': Posto('locale', 'local'),
                       'cloud':  Posto('cloud', 'groq')}

        self._chiave = ''
        self._chiave_nome = ''

        # Modelli gia' scaricati in Ollama, per i ✓ nei menu. None = ancora
        # ignoto (la lettura avviene in sottofondo e resta muta se Ollama e'
        # spento: non deve rallentare l'avvio ne' fallire rumorosamente).
        self._ollama_presenti: set[str] | None = None

        # Le scelte si riempiono dopo, in _leggi_scelte(). Non qui, perche'
        # questo oggetto nasce insieme alla finestra e la finestra nasce prima
        # del motore: i valori di ripiego dei modelli stanno dentro
        # transcriber.py, che a quel punto non e' ancora stato importato.
        self.scelte: dict = {}


    def _p(self) -> Posto:
        """La postazione a cui appartiene il thread che sta chiamando.

        E' il perno di tutto il file: da qui in giu' nessuno nomina mai «Locale»
        o «Cloud», si dice soltanto «la mia postazione» e la risposta arriva da
        se'. Chi lavora in nuvola trova la sua, chi lavora in locale trova la
        sua, e lo stesso identico codice serve tutti e due.

        Chi ci ha messo dentro la risposta sono due soli posti: i metodi che la
        pagina chiama, che ricevono dalla pagina in quale stanza e' stato
        premuto il bottone, e l'involucro che fa partire i lavori, che la
        scrive nel thread appena nato. Tutto il resto la legge e basta.
        """
        return self._posti[_qui()]

    @staticmethod
    def _entra(dove: str) -> str:
        """Segna in quale postazione si sta lavorando, e risponde come si chiama.

        La chiamano come prima riga tutti i metodi che la pagina puo' invocare.
        Il ripiego su «locale» e' voluto: se dalla pagina arrivasse un nome che
        non esiste, la cosa giusta e' lavorare nella prima stanza invece di
        far saltare la chiamata, perche' sarebbe comunque un lavoro vero che
        qualcuno ha chiesto.
        """
        _DOVE.dove = dove if dove in ('locale', 'cloud') else 'locale'
        return _DOVE.dove

    def _leggi_scelte(self) -> None:
        """Le scelte con cui l'interfaccia si presenta: le ultime usate.

        Ognuna ha due possibili provenienze. La prima e' settings.json, cioe'
        quello che si era scelto l'ultima volta. La seconda, quando li' non
        c'e' niente perche' e' il primo avvio, e' il valore di ripiego preso da
        transcriber.py, che a sua volta lo legge dal file .env se c'e'.

        Va chiamata DOPO che il motore e' stato importato, perche' e' li' che
        stanno quei valori di ripiego.
        """
        prefs = i18n.load_prefs()
        self.scelte = {
            'motore':  prefs.get('motore', 'local'),
            'sorgente': prefs.get('sorgente', 'youtube'),
            # I tre modelli locali...
            'whisper': prefs.get('whisper', 'small'),
            'ollama':  prefs.get('ollama', settings.OLLAMA_MODEL),
            'vision':  prefs.get('vision', settings.OLLAMA_VISION_MODEL),
            # ...e i tre di Groq, che fanno gli stessi tre mestieri sui server.
            'groq':    prefs.get('groq', _GROQ[0]),
            'groq_testo': prefs.get('groq_testo', settings.GROQ_SUMMARY_MODEL),
            'groq_vista': prefs.get('groq_vista', settings.GROQ_VISION_MODEL),
            'translate': bool(prefs.get('translate', False)),
            'summarize': bool(prefs.get('summarize', False)),
            'visual':    bool(prefs.get('visual', False)),
        }
        # Le due postazioni nascono uguali, con le abitudini dell'ultima
        # volta. Da qui in poi divergono appena qualcuno tocca un interruttore
        # in una delle due: quello che si salva su disco e' un punto di
        # partenza, non un vincolo che le tiene legate.
        for posto in self._posti.values():
            posto.opz = {c: self.scelte[c] for c in self.SCELTE_DEL_POSTO}

        # Allinea subito i modelli Groq a quelli scelti, invece di lasciare
        # quelli di .env finche' non parte il primo lavoro.
        self._applica_groq()

    # ── Avvio ────────────────────────────────────────────────────────────────

    def avvio(self) -> dict:
        """Tutto cio' che serve alla pagina per disegnarsi la prima volta.

        Qui i due tempi si incontrano. La pagina e' gia' a schermo da qualche
        istante, perche' la finestra si apre prima che il motore esista; il
        motore ci mette qualche secondo ad arrivare. Questa chiamata aspetta
        che sia arrivato, e nel frattempo il velo di caricamento resta davanti
        con la sua barra che avanza.

        L'attesa ha un tetto. Se il motore non arrivasse mai, per un import
        fallito o un file di libreria corrotto, senza tetto questa risposta
        non tornerebbe indietro e la pagina resterebbe sotto il velo per
        sempre, senza dire niente a nessuno. Con il tetto, dopo un minuto si
        risponde lo stesso: la pagina si scopre, l'interfaccia e' a meta' e
        qualcosa non funzionera', ma almeno si VEDE che qualcosa non funziona.
        """
        MOTORE_PRONTO.wait(timeout=60)
        self._leggi_scelte()
        threading.Thread(target=self._leggi_ollama, daemon=True).start()
        return {
            'ok': True,
            'lingua': i18n.LINGUA,
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
        presenti = ollama._ollama_installed_models()
        if not presenti:
            return
        self._ollama_presenti = presenti
        _verso_tutti('aggiornaModelli', self._modelli())

    def _applica_groq(self) -> None:
        """Porta in transcriber i modelli Groq scelti nella sezione «Motore».

        Servono anche fuori da un lavoro, per esempio a chi chiede quanti
        crediti restano, quindi non basta passarli fra le opzioni al
        momento di partire.
        """
        settings.GROQ_MODEL = self.scelte['groq']
        settings.GROQ_SUMMARY_MODEL = self.scelte['groq_testo']
        settings.GROQ_VISION_MODEL = self.scelte['groq_vista']

    def _modelli(self) -> dict:
        """I sei cataloghi di modelli, gia' con etichetta e descrizione.

        Le etichette le compone Python perche' e' Python a sapere quali modelli
        esistono e quali sono gia' scaricati; la pagina si limita a riempirne
        dei menu. Le descrizioni passano per chiave di traduzione, cosi'
        cambiando lingua non serve richiederle di nuovo.
        """
        def spunta(nome: str) -> str:
            """La spunta accanto a un modello gia' scaricato in Ollama.

            Nessuna spunta quando ancora non si sa: la lettura di Ollama avviene
            in sottofondo e puo' non essere arrivata. Mostrare «non scaricato»
            in quel momento sarebbe una bugia, e manderebbe a scaricare
            qualcosa che c'e' gia'.
            """
            if self._ollama_presenti is None:
                return ''
            return ' ✓' if ollama._ollama_has_model(nome, self._ollama_presenti) else ''

        # La memoria richiesta e' un inciso, non una voce a se': fra parentesi
        # attaccata al nome. Con un separatore la riga finiva con tre stacchi in
        # fila (nome, memoria, descrizione) e non si capiva piu' dove
        # cominciasse il giudizio sul modello.
        ollama = [{'valore': n, 'nome': f'{n}{spunta(n)} ({ram})', 'chiave': k}
                  for n, ram, k in _OLLAMA_TESTO]
        vision = [{'valore': n, 'nome': f'{n}{spunta(n)} ({ram})', 'chiave': k}
                  for n, ram, k in _OLLAMA_VISTA]

        # I modelli Groq non si scaricano, quindi niente ✓ e niente memoria: il
        # nome basta a se stesso, la descrizione dice il resto.
        groq_testo = [{'valore': n, 'nome': n, 'chiave': k} for n, k in _GROQ_TESTO]
        groq_vista = [{'valore': n, 'nome': n, 'chiave': k} for n, k in _GROQ_VISTA]

        # Un modello fuori catalogo, imposto da .env oppure scelto quando il
        # catalogo era diverso, va comunque offerto: altrimenti il valore
        # selezionato non
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

    # Le scelte che appartengono al singolo lavoro e non al programma. Sono
    # quelle che le due postazioni tengono separate: la sorgente e i tre
    # interruttori degli output.
    SCELTE_DEL_POSTO = ('sorgente', 'translate', 'summarize', 'visual')

    def imposta(self, valori: dict, dove: str = 'locale') -> dict:
        """Registra una scelta dell'interfaccia e la ricorda per la volta dopo.

        Modelli e interruttori non sono impostazioni del progetto: sono
        abitudini di chi usa il programma, e rifarle a ogni avvio sarebbe
        scortese. La stima di costo/tempo dipende da alcune di queste, quindi si
        ricalcola qui e torna gia' pronta.

        Le scelte finiscono in due posti diversi
            La sorgente e i tre interruttori vanno nella postazione da cui
            arrivano, perche' li' devono restare: spuntare «riassunto» in
            «Cloud» non deve spuntarlo anche di la'.

            I modelli vanno nelle scelte generali, perche' le sei tendine sono
            sei e non dodici.

            Su disco si salva comunque tutto, e vale come punto di partenza al
            prossimo avvio: e' un valore ricordato, non un valore condiviso.
            Le due postazioni nascono uguali e divergono appena qualcuno tocca
            un interruttore.
        """
        posto = self._posti[self._entra(dove)]
        valori = valori or {}

        for chiave in self.SCELTE_DEL_POSTO:
            if chiave in valori:
                posto.opz[chiave] = valori[chiave]

        self.scelte.update({k: v for k, v in valori.items() if k in self.scelte})
        i18n.save_prefs(**self.scelte)
        self._applica_groq()
        return {'ok': True, 'stima': self._stima()}

    # ── La chiave Groq ───────────────────────────────────────────────────────

    def _stato_chiave(self) -> dict:
        """Cosa sapere della chiave Groq, senza mai mandarla alla pagina.

        Si dice solo SE c'e' e da quale file e' stata presa. La chiave in se'
        resta in memoria qui dentro e non attraversa mai il ponte verso
        l'interfaccia: una chiave che arriva nella pagina e' una chiave che si
        puo' leggere aprendo gli strumenti del browser, e non c'e' nessun
        motivo per cui debba trovarsi li'.
        """
        return {'presente': bool(self._chiave), 'nome': self._chiave_nome}

    def scegli_chiave(self) -> dict:
        """Legge la chiave Groq da un file .txt scelto dal sistema.

        Il file puo' essere la chiave nuda o una riga in stile .env: si prende
        il primo valore utile e si tolgono virgolette e commenti, cosi' funziona
        con quello che la console di Groq fa scaricare senza chiedere di
        ripulirlo a mano.
        """
        try:
            scelti = bridge.attuale().create_file_dialog(
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
        """Pesca la chiave da un file di testo, comunque sia scritto dentro.

        Chi scarica la chiave dalla console di Groq si ritrova un file che a
        volte contiene solo la chiave, a volte una riga tipo `GROQ_API_KEY=...`,
        a volte con virgolette intorno e un commento sopra. Chiedere di
        ripulirlo a mano sarebbe scortese e per giunta un'altra occasione di
        sbagliare.

        Quindi si prende la prima riga che non sia vuota ne' un commento, si
        butta via quello che sta prima dell'uguale se c'e', e si tolgono le
        virgolette.
        """
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

    def carica_info(self, testo: str, dove: str = 'locale') -> dict:
        """Guarda cosa c'e' dietro un link, senza scaricare nulla.

        Torna subito: il lavoro vero avviene in un thread, e la pagina viene
        avvisata a cose fatte. Cosi' la finestra non si congela nei secondi in
        cui yt-dlp interroga YouTube, che su una playlist lunga sono parecchi,
        perche' ogni video va letto uno per uno.
        """
        # Prima riga di tutte: da quale delle due stanze arriva questo
        # clic. Da qui in poi lo sa il thread, e ogni cosa che questo
        # metodo dira' alla pagina partira' gia' con l'indirizzo giusto.
        self._entra(dove)
        if self._p().occupato:
            return {'ok': False, 'errore': i18n.t('err.busy')}
        testo = (testo or '').strip()
        if not testo:
            return {'ok': False, 'errore': i18n.t('err.no_url')}
        # Anche questo thread nasce senza sapere dov'e', quindi l'indirizzo
        # glielo si passa come primo argomento. Vale per la lettura di un link
        # esattamente come per un lavoro: la conferma che ne esce deve aprirsi
        # nella stanza in cui qualcuno ha incollato quel link, non nell'altra.
        threading.Thread(target=self._carica_davvero, args=(testo, _qui()),
                         daemon=True).start()
        return {'ok': True, 'avviato': True}

    def _carica_davvero(self, url: str, dove: str = 'locale') -> None:
        """Legge cosa c'e' dietro un link, in un thread a parte.

        Sta in un thread perche' su una playlist lunga yt-dlp interroga YouTube
        un video per volta, e sono parecchi secondi. Farlo nel thread della
        finestra la bloccherebbe: niente si muove, niente risponde, e sembra
        piantato.

        Prima si guarda se e' una playlist, perche' un link di playlist
        contiene anche un video e trattandolo come singolo si prenderebbe solo
        quello, senza dire niente degli altri quarantanove.
        """
        _DOVE.dove = dove
        try:
            playlist = engine.get_playlist_info(url) if 'list=' in url else None
            if playlist and playlist['count'] >= 1:
                self._carica_playlist(url, playlist)
                return
            meta = engine.get_video_info(url)
            self._p().meta, self._p().src, self._p().playlist = meta, url, None
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
        sottocartella = text._safe_filename(
            playlist.get('title') or playlist.get('channel') or 'playlist')
        self._p().playlist = {'title': playlist.get('title'),
                          'channel': playlist.get('channel'),
                          'subdir': sottocartella, 'items': voci}
        self._p().meta, self._p().src = voci[0], url
        _verso_pagina('chiediConferma', self._scheda_playlist(self._p().playlist))

    def scegli_file(self, dove: str = 'locale') -> dict:
        """Apre il selettore di file del sistema per un audio o un video.

        I formati accettati sono esattamente quelli che accetta la riga di
        comando: il filtro si costruisce da ``settings.AUDIO_EXTENSIONS``, cosi'
        aggiungerne uno vale per tutt'e due senza toccare questo file.
        """
        # Prima riga di tutte: da quale delle due stanze arriva questo
        # clic. Da qui in poi lo sa il thread, e ogni cosa che questo
        # metodo dira' alla pagina partira' gia' con l'indirizzo giusto.
        self._entra(dove)
        estensioni = ' '.join(f'*{e}' for e in sorted(settings.AUDIO_EXTENSIONS))
        try:
            scelti = bridge.attuale().create_file_dialog(
                _DLG_APRI, allow_multiple=False,
                file_types=(f'Audio e video ({estensioni})', 'Tutti (*.*)'))
        except Exception as exc:                       # noqa: BLE001
            return {'ok': False, 'errore': str(exc)}
        if not scelti:
            return {'ok': True, 'annullato': True}

        percorso = scelti[0]
        meta = metadata.local_file_meta(percorso)
        self._p().meta, self._p().src, self._p().playlist = meta, percorso, None
        return {'ok': True, 'scheda': self._scheda_file(meta, percorso)}

    def dimentica(self, dove: str = 'locale') -> dict:
        """La sorgente non vale piu': l'URL e' cambiato, o si e' annullata.

        Serve perche' una conferma vecchia non deve restare valida per un link
        nuovo: sarebbe il modo piu' facile di trascrivere il video sbagliato,
        che con Groq costa anche crediti.
        """
        # Prima riga di tutte: da quale delle due stanze arriva questo
        # clic. Da qui in poi lo sa il thread, e ogni cosa che questo
        # metodo dira' alla pagina partira' gia' con l'indirizzo giusto.
        self._entra(dove)
        self._p().meta = self._p().playlist = None
        self._p().src = ''
        return {'ok': True}

    # ── Le schede della sorgente ─────────────────────────────────────────────

    def _scheda_video(self, meta: dict) -> dict:
        """Il video ridotto a cio' che va mostrato: copertina, titolo, dati, stima.

        Le voci facoltative (mi piace, iscritti, categoria, lingua) compaiono
        solo quando ci sono, cosi' la scheda non si riempie di campi vuoti.
        """
        righe = [
            ('info.channel', meta.get('channel') or '—'),
            ('info.views', text._format_views(meta.get('views'))),
            ('info.date', text._format_upload_date(meta.get('upload_date'))),
            ('info.duration', text._format_duration(meta.get('duration'))),
        ]
        if meta.get('likes') is not None:
            righe.append(('info.likes', text._format_views(meta['likes'])))
        if meta.get('subscribers') is not None:
            righe.append(('info.subs', text._format_views(meta['subscribers'])))
        if meta.get('category'):
            righe.append(('info.category', meta['category']))
        lingua = media._lang_name(meta.get('detected_language') or meta.get('language'),
                              i18n.LINGUA)
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
        """La scheda da mostrare per una playlist, prima di confermare.

        La durata totale e' il numero che conta davvero: e' quello da cui si
        capisce se si sta per cominciare una cosa da dieci minuti o da sei ore.
        Il numero di video da solo non lo dice, perche' cinquanta video possono
        essere cinquanta minuti o due giornate.
        """
        voci = playlist['items']
        totale = sum((m.get('duration') or 0) for m in voci)
        return {
            'tipo': 'playlist',
            'titolo': playlist.get('title') or playlist.get('channel') or '?',
            'miniatura': (voci[0].get('thumbnail') or '') if voci else '',
            'righe': [
                {'chiave': 'info.channel', 'valore': playlist.get('channel') or '—'},
                {'chiave': 'info.videos', 'valore': str(len(voci))},
                {'chiave': 'info.duration', 'valore': text._format_duration(totale)},
            ],
            'stima': self._stima({'duration': totale}),
            'voci': [{'titolo': m.get('title') or '?',
                      'durata': text._format_duration(m.get('duration'))} for m in voci],
        }

    def _scheda_file(self, meta: dict, percorso: str) -> dict:
        """La scheda da mostrare per un file scelto dal disco.

        Piu' scarna di quella di un video: niente copertina, niente canale,
        niente data di pubblicazione, perche' un file non ha nessuna di quelle
        cose. Restano il nome e la durata, che sono anche le uniche due da cui
        si capisce se si e' scelto il file giusto.
        """
        return {
            'tipo': 'file',
            'titolo': meta.get('title') or os.path.basename(percorso),
            'miniatura': '',
            'righe': [
                {'chiave': 'info.file', 'valore': os.path.basename(percorso)},
                {'chiave': 'info.duration',
                 'valore': text._format_duration(meta.get('duration'))},
            ],
            'stima': self._stima(meta),
        }

    def _stima(self, meta: dict | None = None) -> str:
        """Costo (Groq) o tempo (locale) previsti per la sorgente corrente.

        Cambia col motore e col modello scelti, quindi si ricalcola a ogni
        modifica invece di essere fissata quando la sorgente viene letta: e' il
        numero su cui si decide se usare il cloud o aspettare.
        """
        meta = meta if meta is not None else self._p().meta
        if not meta:
            return ''
        if self._p().playlist and meta is self._p().meta:
            meta = {'duration': sum((m.get('duration') or 0)
                                    for m in self._p().playlist['items'])}
        # Il motore e' quello della stanza, non una scelta a parte: la stessa
        # sorgente vista da «Locale» costa un tempo e vista da «Cloud» costa
        # dei soldi, e sono due numeri diversi che convivono benissimo.
        motore = self._p().motore
        modello = self.scelte['groq'] if motore == 'groq' else self.scelte['whisper']
        stima = estimate.estimate_job(meta, motore, modello)
        if stima['backend'] == 'groq':
            return i18n.t('est.cost', c=f"{stima['cost_usd']:.3f}", m=modello)
        dispositivo = 'GPU' if stima.get('device') == 'cuda' else 'CPU'
        return i18n.t('est.time', t=text._format_duration(stima['seconds']), d=dispositivo)

    # ── Avviare il lavoro ────────────────────────────────────────────────────

    def _opzioni(self, motore: str | None = None) -> dict:
        """Il dizionario che il motore si aspetta, dalle scelte dell'interfaccia.

        Passano i modelli di entrambi i mondi, ma il motore ne usa uno solo: e'
        ``backend`` a decidere, e con «local» la chiave non parte nemmeno, cosi'
        una trascrizione sul computer resta sul computer anche se una chiave e'
        caricata per altri lavori.

        Da dove vengono i valori, che non e' piu' un posto solo
            I modelli vengono dalle scelte generali, perche' sono gli stessi da
            qualunque stanza li si guardi: le sei tendine esistono in un
            esemplare ciascuna, tre per il computer e tre per Groq.

            Il motore e gli interruttori vengono invece dalla postazione. Il
            motore perche' ADESSO e' la stanza: lavorare in «Cloud» vuol dire
            Groq, e non c'e' piu' una scelta separata che potrebbe dire il
            contrario. Gli interruttori perche' si decidono video per video, e
            si puo' benissimo volere il riassunto di quello che gira in nuvola
            e non di quello che gira qui.
        """
        posto = self._p()
        motore = motore or posto.motore
        opz = posto.opz
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
            'source_kind': opz.get('sorgente', 'youtube'),
            # I nomi delle cartelle seguono la lingua dell'interfaccia.
            'translate': bool(opz.get('translate')),
            'summarize': bool(opz.get('summarize')),
            'visual': bool(opz.get('visual')),
        }

    def prepara(self, dove: str = 'locale') -> dict:
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
        # Prima riga di tutte: da quale delle due stanze arriva questo
        # clic. Da qui in poi lo sa il thread, e ogni cosa che questo
        # metodo dira' alla pagina partira' gia' con l'indirizzo giusto.
        self._entra(dove)
        if self._p().occupato:
            return {'ok': False, 'errore': i18n.t('err.busy')}

        mancano = []
        if self._p().motore == 'groq' and not self._chiave:
            mancano.append(i18n.t('warn.key'))
        if not self._p().meta:
            mancano.append(i18n.t('warn.src.yt') if self.scelte['sorgente'] == 'youtube'
                           else i18n.t('warn.src.local'))
        if mancano:
            return {'ok': True, 'stato': 'manca', 'voci': mancano}

        # Una playlist si avvia sempre: il controllo "gia' fatto" lo fa il batch
        # video per video, saltando quelli presenti senza spendere un credito.
        if self._p().playlist:
            return {'ok': True, 'stato': 'pronto'}

        meta = self._p().meta
        if jobs.transcription_exists(RISULTATI, meta['title']):
            voci = [{'azione': 'nuova', 'icona': 'rifai', 'tono': 'attenzione',
                     'titolo': i18n.t('already.again'),
                     'desc': i18n.t('already.again.desc')}]
            if engine.can_resume(meta, RISULTATI):
                nota = engine.resume_hint(meta, RISULTATI, i18n.LINGUA)
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

        parziale = (checkpoints.load_checkpoint(meta) if self._p().motore == 'groq'
                    else checkpoints.load_local_checkpoint(meta))
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
            blocco = parziale.get('chunk_seconds') or settings.CHUNK_SECONDS
            fatti = int(parziale.get('done_chunks', 0)) * blocco
        durata = int(parziale.get('duration', 0) or 0)
        if durata:
            fatti = min(fatti, durata)
        return {'fatto': text._format_timestamp(fatti),
                'totale': text._format_timestamp(durata)}

    def esegui(self, azione: str = 'nuova', dove: str = 'locale') -> dict:
        """Avvia davvero il lavoro, con l'azione scelta.

        ``nuova`` trascrive da capo; ``riprendi`` continua dal parziale;
        ``ricomincia`` lo butta e riparte; ``traduci``, ``riassumi`` e
        ``riprendi_post`` riusano la trascrizione gia' salvata e non spendono un
        credito di trascrizione.
        """
        # Prima riga di tutte: da quale delle due stanze arriva questo
        # clic. Da qui in poi lo sa il thread, e ogni cosa che questo
        # metodo dira' alla pagina partira' gia' con l'indirizzo giusto.
        self._entra(dove)
        if self._p().occupato:
            return {'ok': False, 'errore': i18n.t('err.busy')}
        if not self._p().meta:
            return {'ok': False, 'errore': i18n.t('err.no_file')}

        if self._p().playlist:
            self._in_thread(self._playlist_davvero)
            return {'ok': True, 'avviato': True}

        if azione == 'ricomincia':
            meta = self._p().meta
            (checkpoints.delete_local_checkpoint if self._p().motore == 'local'
             else checkpoints.delete_checkpoint)(meta)
            azione = 'nuova'

        if azione in ('traduci', 'riassumi', 'riprendi_post'):
            self._in_thread(self._dopo_davvero, azione)
        else:
            self._in_thread(self._trascrivi_davvero, azione == 'riprendi')
        return {'ok': True, 'avviato': True}

    def _apri_lavoro(self, opzioni: dict, piano: list[str]) -> None:
        """Prepara la pagina per un lavoro che sta per cominciare.

        Manda tre cose insieme: l'elenco delle fasi previste, la riga che
        riassume cosa si e' chiesto, e la barra riportata a zero.

        L'elenco delle fasi arriva prima che il lavoro cominci, e non mentre
        procede, apposta: chi guarda vede subito quanti passaggi saranno, e
        quindi capisce se sta aspettando due minuti o venti.
        """
        self._p().avanz = Avanzamento(piano)
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
        """La funzione che il motore chiama per dire a che punto e'.

        Gliela si passa quando gli si chiede di lavorare, ed e' l'unico modo
        che ha di farsi sentire: il motore non sa che esiste una finestra, sa
        solo di avere qualcuno a cui riferire.

        Gira nel thread di lavoro, non in quello della finestra. Va bene,
        perche' tutto quello che fa e' passare la notizia al ponte, che se la
        cava da qualunque thread.
        """
        if self._p().avanz:
            self._p().avanz.riferisci(fase, corrente, totale, dettaglio)

    def _trascrivi_davvero(self, riprendi: bool) -> None:
        """Il lavoro completo su un video: dall'audio al documento finito.

        E' la strada principale del programma. Gira in un thread a parte, e
        riferisce alla pagina man mano.

        Il caso «crediti finiti» non viene intercettato qui di proposito: lo
        raccoglie _in_thread, che lo tratta per quello che e', cioe' un'attesa
        e non un guasto. Prenderlo qui vorrebbe dire scriverne il trattamento
        in cinque punti diversi, e prima o poi uno resterebbe indietro.
        """
        opzioni = self._opzioni()
        piano = piano_fasi(opzioni['backend'], self.scelte['sorgente'], opzioni)
        self._apri_lavoro(opzioni, piano)
        meta_iniziale = self._p().meta
        # Il crediti-esauriti non si intercetta qui: lo raccoglie _in_thread, che
        # lo tratta per quello che e', cioe' un'attesa e non un guasto, ed e'
        # l'unico
        # posto in cui la distinzione va fatta, invece che in ogni lavoro.
        meta, segmenti, etichetta, cliente = engine.transcribe_only(
            self._p().src, opzioni, on_progress=self._riferisci, resume=riprendi)
        risultato = engine.save_results(
            meta, segmenti, etichetta, opzioni, RISULTATI, cliente,
            on_progress=self._riferisci)
        self._p().avanz.concludi()
        # Il riassunto fermato per crediti esauriti non e' un errore: la
        # trascrizione e' salvata, e si puo' concludere in locale senza rifare
        # nulla. Chiederlo qui e' l'unico momento in cui la domanda ha senso.
        if risultato.get('summary_status') == 'partial' and opzioni['backend'] == 'groq':
            _verso_pagina('riassuntoInterrotto', self._risultato(risultato, meta_iniziale))
        else:
            _verso_pagina('mostraRisultato', self._risultato(risultato, meta_iniziale))

    def _dopo_davvero(self, azione: str) -> None:
        """Fare qualcosa in piu' su un video che era gia' stato trascritto.

        Tradurre, riassumere, o riprendere un lavoro rimasto a meta'. Nessuna
        delle tre ritrascrive niente: ripartono dai file gia' sul disco, ed e'
        il motivo per cui costano pochissimo rispetto al lavoro originale.

        L'analisi visiva resta spenta anche se era accesa nei menu: rifarla
        vorrebbe dire riscaricare il video e rimandare tutti i fotogrammi, che
        e' il contrario di quello che si sta chiedendo.
        """
        opzioni = self._opzioni()
        opzioni.update({'translate': True, 'summarize': True, 'visual': False})
        piano = {'traduci': ['info', 'translate'],
                 'riassumi': ['info', 'summarize'],
                 'riprendi_post': ['info', 'translate', 'summarize']}[azione]
        self._apri_lavoro(opzioni, piano)
        funzione = {'traduci': engine.translate_only,
                    'riassumi': engine.summary_only,
                    'riprendi_post': engine.resume}[azione]
        risultato = funzione(self._p().meta, opzioni, RISULTATI, on_progress=self._riferisci)
        self._p().avanz.concludi()
        if risultato.get('summary_status') == 'partial' and opzioni['backend'] == 'groq':
            _verso_pagina('riassuntoInterrotto', self._risultato(risultato, self._p().meta))
        else:
            _verso_pagina('mostraRisultato', self._risultato(risultato, self._p().meta))

    def concludi_in_locale(self, dove: str = 'cloud') -> dict:
        """Finisce sul computer un riassunto che Groq ha lasciato a meta'.

        Riparte dalla sezione in cui si e' fermato: le sezioni gia' riassunte
        non si rifanno, e non serve alcuna chiave.
        """
        # Prima riga di tutte: da quale delle due stanze arriva questo
        # clic. Da qui in poi lo sa il thread, e ogni cosa che questo
        # metodo dira' alla pagina partira' gia' con l'indirizzo giusto.
        self._entra(dove)
        if self._p().occupato:
            return {'ok': False, 'errore': i18n.t('err.busy')}
        # La finestra puo' restare aperta mentre si cambia il link, e cambiarlo
        # dimentica la sorgente: senza questo controllo il lavoro partirebbe
        # senza sapere su cosa, e fallirebbe a meta' con un errore oscuro.
        if not self._p().meta:
            return {'ok': False, 'errore': i18n.t('err.no_file')}
        self._in_thread(self._riassunto_locale)
        return {'ok': True, 'avviato': True}

    def _riassunto_locale(self) -> None:
        """Finisce in locale un riassunto che Groq ha lasciato a meta'.

        E' la via d'uscita quando i crediti finiscono durante un riassunto: il
        parziale e' gia' salvato, e da li' si puo' proseguire sul proprio
        computer invece di aspettare domani.

        Si forza il motore locale anche se nei menu era scelto Groq, perche' e'
        esattamente il punto: Groq in questo momento non risponde piu'.
        """
        opzioni = self._opzioni(motore='local')
        opzioni.update({'api_key': '', 'translate': True,
                        'summarize': True, 'visual': False})
        self._apri_lavoro(opzioni, ['info', 'summarize'])
        risultato = engine.summary_only(self._p().meta, opzioni, RISULTATI,
                                        on_progress=self._riferisci)
        self._p().avanz.concludi()
        _verso_pagina('mostraRisultato', self._risultato(risultato, self._p().meta))

    def continua_in_locale(self, dove: str = 'cloud') -> dict:
        """Completa sul computer una trascrizione Groq rimasta senza crediti.

        Riusa il parziale gia' salvato: solo la coda non ancora trascritta passa
        dal modello locale, e viene ricucita con quello che c'era.

        Il lavoro NON cambia stanza
            Resta in «Cloud», dove e' cominciato, e da li' continua a
            raccontarsi. Cambia solo il modello che lo porta a termine, ed e'
            ``_opzioni(motore='local')`` a imporlo.

            Prima questa riga spostava anche la scelta del motore, quando la
            scelta era una cosa a parte che si poteva spostare. Adesso il
            motore E' la stanza: spostarlo vorrebbe dire far saltare il lavoro
            da una lavagna all'altra a meta' strada, lasciando il suo diario e
            il suo avanzamento in quella di prima.
        """
        # Prima riga di tutte: da quale delle due stanze arriva questo
        # clic. Da qui in poi lo sa il thread, e ogni cosa che questo
        # metodo dira' alla pagina partira' gia' con l'indirizzo giusto.
        self._entra(dove)
        if self._p().occupato:
            return {'ok': False, 'errore': i18n.t('err.busy')}
        if not self._p().meta or not self._p().src:
            return {'ok': False, 'errore': i18n.t('err.no_file')}
        self._in_thread(self._coda_in_locale)
        return {'ok': True, 'avviato': True}

    def _coda_in_locale(self) -> None:
        """Finisce in locale una trascrizione che Groq ha lasciato a meta'.

        Come il riassunto locale, ma sui blocchi di audio: quelli gia'
        trascritti da Groq si tengono, e i rimanenti si macinano qui.

        Il documento che ne esce e' stato scritto da due motori diversi, e
        l'etichetta in testa lo dice: la qualita' puo' cambiare a meta',
        e chi rilegge deve poterlo sapere.
        """
        opzioni = self._opzioni(motore='local')
        piano = piano_fasi('local', self.scelte['sorgente'], opzioni)
        self._apri_lavoro(opzioni, piano)
        meta, segmenti, etichetta, _ = engine.continue_local_from_groq(
            self._p().src, opzioni, on_progress=self._riferisci)
        risultato = engine.save_results(meta, segmenti, etichetta, opzioni,
                                        RISULTATI, None, on_progress=self._riferisci)
        self._p().avanz.concludi()
        _verso_pagina('mostraRisultato', self._risultato(risultato, self._p().meta))

    # ── Playlist ─────────────────────────────────────────────────────────────

    def _playlist_davvero(self) -> None:
        """Trascrive in fila tutti i video di una playlist confermata.

        Tre regole, e sono quelle che rendono il batch sopportabile su una lista
        lunga: un video gia' presente si salta senza spendere nulla; uno che
        fallisce non ferma gli altri; se Groq esaurisce i crediti ci si ferma li'
        I blocchi gia' fatti restano salvati e domani si riprende.

        Le cartelle portano davanti il numero d'ordine della playlist, che e'
        l'ordine in cui i video sono elencati su YouTube. Senza, aprendo la
        cartella di un corso di trenta lezioni si trovano trenta titoli
        ordinati alfabeticamente, e capire da dove si comincia vuol dire
        tornare su YouTube a guardare la playlist.
        """
        playlist = self._p().playlist
        voci = playlist['items']
        radice = os.path.join(RISULTATI, playlist['subdir'])
        opzioni = self._opzioni()
        opzioni['source_kind'] = 'youtube'

        fatti: list[dict] = []
        saltati: list[str] = []
        # I falliti non sono piu' solo un titolo. Un elenco di titoli in fondo a
        # un batch di trenta video dice che tre non sono riusciti e non dice
        # perche': tre video privati e tre guasti di rete si leggono uguali,
        # mentre nel primo caso non c'e' niente da fare e nel secondo basta
        # rilanciare. Adesso ogni fallito si porta dietro la sua spiegazione.
        falliti: list[dict] = []
        senza_crediti = False

        for numero, meta in enumerate(voci, 1):
            # Il controllo «c'e' gia'» viene PRIMA di annunciare il lavoro: un
            # video saltato non deve azzerare la barra e riscrivere il piano per
            # poi non fare niente, che a schermo si legge come un lavoro partito
            # e subito bloccato.
            if jobs.transcription_exists(radice, meta['title']):
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
                # Il numero d'ordine va attaccato ai dati del video PRIMA di
                # salvare, perche' meta2 arriva fresco da YouTube e di essere
                # il quarto video di una playlist non ne sa niente. Da qui in
                # poi se lo porta dietro, e lo ritrovano sia chi scrive la
                # trascrizione sia chi scrive le note visive.
                meta2['_num_playlist'] = text.numero_playlist(numero, len(voci))
                fatti.append(engine.save_results(
                    meta2, segmenti, etichetta, opzioni, radice, cliente,
                    on_progress=self._riferisci))
                # Come per un video singolo: l'ultima fase riferisce e poi tace,
                # quindi senza questa la barra di ogni video resterebbe a un
                # passo dalla fine con tutto gia' scritto sul disco.
                self._p().avanz.concludi()
            except engine.RateLimitReached:
                senza_crediti = True
                break
            except Exception as exc:                   # noqa: BLE001
                falliti.append(self._scheda_errore(exc, meta['title']))
                continue

        self._p().ultima_cartella = radice
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
            # I falliti portano con se' la causa e il testo tecnico, e vengono
            # messi PER PRIMI: sono l'unica cosa di questo riepilogo su cui ci
            # sia qualcosa da decidere, e in fondo a un elenco di trenta video
            # riusciti non li leggerebbe nessuno.
            'voci': ([{'tono': 'attenzione', 'titolo': f['video'],
                       'causa': f['causa'], 'dettaglio': f['dettaglio']} for f in falliti]
                     + [{'tono': 'ok', 'titolo': r.get('title', '?')} for r in fatti]
                     + [{'tono': 'neutro', 'titolo': t} for t in saltati]),
            'et_dettaglio': i18n.t('err.dettaglio'),
        })

    # ── Il risultato ─────────────────────────────────────────────────────────

    def _risultato(self, res: dict, meta: dict | None) -> dict:
        """Il risultato del motore, ridotto a cio' che la finestra deve mostrare.

        I file vengono raggruppati per cartella perche' e' cosi' che stanno sul
        disco, ed e' l'unico modo in cui l'elenco di dieci nomi resta leggibile.
        """
        self._p().ultima_cartella = res.get('video_dir', '')
        visiva = res.get('visual') or {}
        self._p().ultima_visiva = visiva.get('dir') or ''

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
                 'valore': text._format_timestamp(crediti.get('audio_seconds_used') or 0)},
            ] + ([{'chiave': 'res.credits.left',
                   'valore': text._format_timestamp(residuo)}] if residuo is not None else [])
            ) if crediti else [],
            'visiva': ({'n': visiva['count'], 'cartella': visiva.get('dir', '')}
                       if visiva.get('count') else None),
        }

    # ── Aprire cose nel sistema ──────────────────────────────────────────────

    def apri(self, quale: str = 'cartella', dove: str = 'locale') -> dict:
        """Apre una cartella con il gestore di file del sistema.

        E' il modo piu' rapido di arrivare ai file appena prodotti, e sostituisce
        il dover ricordare dove il programma li aveva messi.

        Su Windows c'e' una chiamata apposta; altrove si passa dal meccanismo
        che apre gli indirizzi, che davanti a un percorso locale apre il
        gestore di file.
        """
        # Prima riga di tutte: da quale delle due stanze arriva questo
        # clic. Da qui in poi lo sa il thread, e ogni cosa che questo
        # metodo dira' alla pagina partira' gia' con l'indirizzo giusto.
        self._entra(dove)
        percorso = self._p().ultima_visiva if quale == 'visiva' else self._p().ultima_cartella
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
        """Apre un indirizzo nel browser di chi sta usando il programma.

        Serve al pulsante «Ottieni una chiave», che porta alla pagina di Groq.
        Si apre fuori e non dentro la finestra apposta: dentro sarebbe una
        pagina web dentro un'altra pagina web, senza barra degli indirizzi e
        senza il proprio accesso gia' fatto.
        """
        import webbrowser
        try:
            webbrowser.open(indirizzo)
        except Exception:                              # noqa: BLE001
            return {'ok': False}
        return {'ok': True}

    # ── Utilita' interne ─────────────────────────────────────────────────────

    def _in_thread(self, funzione, *argomenti) -> None:
        """Fa girare il lavoro fuori dal thread della finestra.

        Il passaggio di consegne fra i due thread
            Questo metodo gira nel thread della finestra, che sa in quale
            stanza e' stato premuto il bottone perche' gliel'ha appena detto
            la pagina. Il lavoro girera' invece in un thread nuovo, che non sa
            niente di niente.

            Quindi l'indirizzo si legge QUI e si consegna la' dentro, come
            prima riga. Leggerlo dentro il thread nuovo non funzionerebbe: e'
            appena nato, la sua variabile e' vuota, e risponderebbe «locale» a
            tutti, compreso un lavoro partito da «Cloud».

        Il crediti-esauriti non passa di qui come errore: e' una condizione
        prevista e recuperabile, non un guasto, e chi la incontra la gestisce da
        se' con una finestra che offre come proseguire.
        """
        dove = _qui()
        posto = self._posti[dove]

        def guscio():
            """Fa girare il lavoro in un thread, con tutte le reti di sicurezza.

            E' l'involucro che sta intorno a ogni operazione lunga, e fa cinque
            cose che nessuna di quelle operazioni deve ripetere per conto suo:

            dice a questo thread in quale postazione si trova, e da quel
            momento tutto cio' che dira' arriva alla lavagna giusta;

            segna che si sta lavorando, cosi' la pagina non ne fa partire due
            NELLA STESSA STANZA, mentre nell'altra si puo' eccome;

            manda quello che viene stampato dentro il diario di questa
            postazione, e non in quello dell'altra;

            distingue i crediti finiti da un guasto vero, perche' sono due
            cose diverse e portano a due messaggi diversi;

            e si cancella dal registro alla fine, anche quando e' andata male.
            """
            _DOVE.dove = dove
            posto.occupato = True
            _verso_pagina('cambiaStato', 'working')

            # Il diario si iscrive allo smistatore invece di prendere il posto
            # dell'uscita standard. E' la differenza che permette ai due lavori
            # di convivere: prima il secondo a partire avrebbe sovrascritto il
            # dirottamento del primo, e le righe dei due sarebbero finite
            # mescolate in un diario solo.
            diario = Diario()
            _SMISTATORE.registra(diario)
            try:
                funzione(*argomenti)
                _verso_pagina('cambiaStato', 'done')
            except engine.RateLimitReached as exc:
                self._crediti_finiti(exc)
            except engine.EngineError as exc:
                _verso_pagina('erroreLavoro', self._scheda_errore(exc))
            except Exception as exc:                   # noqa: BLE001
                # Un guasto che non era previsto: qui il dettaglio tecnico e' il
                # traceback intero e non la sola frase dell'eccezione. Prima
                # finiva nel diario, che non c'e' piu'; buttarlo via sarebbe
                # stato togliere l'unica cosa da cui si capisce dove si e' rotto.
                _verso_pagina('erroreLavoro',
                              self._scheda_errore(exc, dettaglio=traceback.format_exc()))
            finally:
                diario.flush()
                _SMISTATORE.dimentica()
                posto.occupato = False

        threading.Thread(target=guscio, daemon=True).start()

    def _scheda_errore(self, exc, titolo_video: str | None = None,
                       dettaglio: str | None = None) -> dict:
        """Un errore messo in una forma che chi legge possa capire.

        Le tre cose che servono, e perche' sono tre
            Quale video, che cosa e' successo, e il testo tecnico. La prima
            serve perche' in una playlist di trenta video «non e' riuscito» da
            solo non dice niente. La seconda perche' «HTTP Error 403:
            Forbidden» e' esatto e incomprensibile, e chi legge deve poter
            capire se riprovare, aspettare o lasciar perdere. La terza perche'
            il testo originale, per quanto oscuro, e' l'unica cosa che permette
            di cercare in rete o di farsi aiutare, e cancellarlo sarebbe
            togliere l'unico appiglio vero.

            La spiegazione a parole non sostituisce il testo tecnico: gli sta
            sopra. Chi vuole solo sapere se ha senso riprovare legge la prima
            riga e si ferma, chi vuole capire davvero continua.

        Il titolo, e perche' puo' arrivare da fuori
            Di norma e' quello del video su cui si sta lavorando adesso. Ma in
            una playlist il video fermo non e' quello della postazione, e' uno
            dei trenta della lista: in quel caso chi chiama lo passa, e non lo
            si va a indovinare.

        Il dettaglio, quando e' piu' lungo della frase dell'eccezione
            Per un guasto imprevisto chi chiama passa il traceback intero. La
            frase da sola direbbe «KeyError: title», che non basta a capire
            dove: la famiglia dell'errore si continua a leggere dalla frase,
            perche' il traceback e' pieno di parole che porterebbero fuori
            strada, ma quello che si mostra sotto e' il traceback.
        """
        messaggio = str(exc) or i18n.t('err.unknown')
        famiglia = contract.classifica_errore(messaggio)
        if titolo_video is None:
            meta = self._p().meta
            titolo_video = (meta or {}).get('title') or ''
        return {
            'titolo': i18n.t('err.title'),
            'video': titolo_video,
            'causa': i18n.t('err.causa.' + famiglia),
            'dettaglio': dettaglio or messaggio,
            'et_video': i18n.t('err.video'),
            'et_dettaglio': i18n.t('err.dettaglio'),
        }

    def _crediti_finiti(self, exc) -> None:
        """Groq ha esaurito i crediti: e' un'attesa, non un guasto.

        Il parziale e' gia' stato salvato dal motore, quindi le due uscite sono
        entrambe vere: tornare domani e riprendere, o finire adesso sul proprio
        computer. Dirlo in rosso sarebbe sbagliato: non si e' rotto niente.
        """
        _verso_pagina('creditiFiniti', {
            'titolo': i18n.t('rate.title'),
            'testo': i18n.t('rate.msg',
                            fatto=text._format_timestamp(int(getattr(exc, 'done_seconds', 0) or 0)),
                            totale=text._format_timestamp(int(getattr(exc, 'total_seconds', 0) or 0))),
            'puo_locale': self._p().src != '' and self._p().meta is not None,
        })
