"""Il patto fra chi fa il lavoro e chi lo ha chiesto.

Il problema che risolve
    Le funzioni che fanno il lavoro vero (scaricare, dividere, trascrivere)
    devono poter essere chiamate sia dalla riga di comando sia da dentro una
    finestra. Ma le due cose vogliono comportamenti opposti quando qualcosa va
    storto: la riga di comando stampa in rosso e torna al menu, la finestra
    vuole una riga nel diario e una barra che si ferma.

    Se quelle funzioni sapessero come si mostra un errore, funzionerebbero solo
    per uno dei due. Quindi non lo sanno: sollevano una delle eccezioni di
    questo file e si fermano li'. A tradurla in qualcosa di visibile ci pensa
    chi ha chiamato, che e' l'unico a sapere chi sta guardando.

Le quattro eccezioni, e perche' sono quattro e non una
    Perche' portano a decisioni diverse, e distinguerle e' l'unico modo perche'
    chi le riceve possa prendere quella giusta:

    ``MediaError``
        Qualcosa e' andato storto scaricando o preparando l'audio. Si riprova
        o si rinuncia, ma il lavoro e' perduto.

    ``GroqRateLimit``
        Groq ha rifiutato perche' i crediti sono finiti. NON e' un guasto: e'
        un'attesa. Domani la stessa richiesta funzionera'. Chi la riceve salva
        un parziale invece di buttare via quello che era gia' stato fatto.

    ``TranscriptionInterrupted``
        La stessa cosa, ma a meta' di un video lungo, e si porta dietro i pezzi
        gia' trascritti perche' non vadano persi.

    La quarta e' l'assenza di eccezione: il lavoro e' andato bene.

Le due richiamate di riserva
    ``_noop_progress`` e ``_never_stop`` servono a far scrivere le funzioni di
    lavoro come se qualcuno stesse SEMPRE ascoltando. Senza, ogni riga che
    riferisce un avanzamento andrebbe protetta da un controllo, e quelle righe
    sono decine. Con una richiamata che non fa niente, il caso "nessuno sta
    guardando" smette di essere un caso.

Perche' non dipende da nulla
    Perche' lo importano tutti. Se questo file importasse qualcosa del
    programma, il primo modulo che lo usa chiuderebbe un cerchio.
"""
from __future__ import annotations


class MediaError(Exception):
    """Errore nelle funzioni media condivise (download, split, trascrizione locale).

    Le funzioni "core" di questo modulo sono SENZA interfaccia: non stampano e
    non decidono cosa mostrare, segnalano il guasto sollevando questa eccezione.
    Chi chiama la traduce nella propria UI: la CLI la cattura nei wrapper
    `_cli_*` (stampa in rosso e restituisce None), il motore la riavvolge in
    `EngineError` per la GUI."""


def _noop_progress(phase, current, total, detail=""):  # pragma: no cover - trivial
    """Callback di avanzamento di default: non fa nulla.

    Permette alle funzioni core di chiamare sempre `on_progress(...)` senza
    controllare ogni volta se qualcuno sta ascoltando."""


# Qualcuno ha chiesto di fermarsi (Ctrl+C dalla riga di comando).
#
# Sta qui e non dove viene premuto il tasto, perche' a doverlo LEGGERE sono le
# funzioni di lavoro, che di tastiere non sanno niente. Chi intercetta il tasto
# chiama chiedi_di_fermarsi(); chi lavora controlla fermarsi() fra un pezzo e
# l'altro, e smette con garbo invece di essere ucciso a meta' di una scrittura.
_fermare = False


def chiedi_di_fermarsi() -> None:
    """Segna che si vuole smettere.

    Non ferma niente da sola, e questo e' il punto: alza una bandierina e
    basta. A guardarla sono le funzioni di lavoro, fra un pezzo e l'altro, nei
    momenti in cui interrompersi non fa danni.

    La chiama chi intercetta il Ctrl+C dalla riga di comando. Potrebbe
    chiamarla anche un pulsante «annulla» dentro la finestra, il giorno in cui
    lo si volesse: da qui non si vede nessuna differenza fra i due.
    """
    global _fermare
    _fermare = True


def fermarsi() -> bool:
    """True se qualcuno ha chiesto di smettere.

    Va controllata nei punti in cui fermarsi e' sicuro: fra un blocco di audio
    e il successivo, fra un fotogramma e l'altro. Non in mezzo a una scrittura
    su disco, perche' li' interrompersi lascia un file a meta' che poi nessuno
    capisce da dove sia uscito.
    """
    return _fermare


def _never_stop() -> bool:  # pragma: no cover - trivial
    """Callback di annullamento di default: non si ferma mai.

    La CLI passa una funzione che legge il flag `_interrupted` (Ctrl+C); la GUI
    ha un suo meccanismo e lascia il default."""
    return False


class GroqRateLimit(Exception):
    """Sollevata quando Groq rifiuta per limite (429 / token-al-giorno).

    Permette a chi trascrive a blocchi di FERMARSI e salvare un checkpoint,
    invece di restituire un risultato incompleto silenziosamente."""


class TranscriptionInterrupted(Exception):
    """La trascrizione si e' fermata a meta', e si porta dietro quello che aveva.

    E' l'unica eccezione di questo file che trasporta dei dati invece che solo
    un messaggio, e il motivo e' tutto qui: quando Groq dice che i crediti sono
    finiti al blocco trenta su quaranta, quei trenta blocchi sono lavoro gia'
    fatto e gia' pagato. Buttarli via per poi rifarli domani sarebbe spendere
    due volte la stessa cosa.

    Chi la riceve salva i pezzi in un parziale, e «Riprendi» ripartira' dal
    trentunesimo.

    Attributi
        ``segments``  i pezzi di trascrizione gia' ottenuti
        ``done``      quanti blocchi erano stati completati
        ``total``     quanti ne erano previsti in tutto
        ``lang``      la lingua riconosciuta, che serve a riprendere coerenti
    """

    def __init__(self, segments: list, done: int, total: int, lang):
        """Raccoglie il lavoro gia' fatto, perche' non vada perduto.

        La lingua riconosciuta viaggia insieme ai pezzi e non viene ricavata di
        nuovo al momento di riprendere: riconoscerla una seconda volta, su un
        pezzo diverso dell'audio, puo' dare una risposta diversa, e il
        documento finale risulterebbe meta' in una lingua e meta' in un'altra.
        """
        self.segments = segments
        self.done = done
        self.total = total
        self.lang = lang
        super().__init__(f"Trascrizione interrotta al blocco {done}/{total}")


def _is_rate_limit(msg: str) -> bool:
    """Questo errore vuol dire «crediti finiti» o e' un guasto vero?

    La distinzione conta piu' di quanto sembri, perche' porta a due azioni
    opposte: «riprova fra poco» oppure «salva e torna domani».

    Si guarda dentro il TESTO dell'errore invece che a un codice, perche' il
    codice non c'e' sempre. La stessa condizione arriva a volte come un 429
    pulito, a volte come una frase dentro un errore generico, e a volte da
    Ollama che usa parole tutte sue. I sei pezzi di testo cercati qui sotto
    sono quelli osservati davvero, non un elenco teorico.
    """
    m = (msg or "").lower()
    return ("429" in m or "rate_limit" in m or "rate limit" in m
            or "tokens per" in m or "requests per" in m or "too many requests" in m)
