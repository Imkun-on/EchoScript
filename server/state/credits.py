"""Quanto si e' gia' consumato di Groq, e quanto ne resta.

Come si fa a saperlo senza chiedere
    Non si chiede. Ogni risposta che Groq manda indietro, per qualunque cosa
    (una trascrizione, un riassunto), porta con
    se' delle intestazioni che dicono quanto se n'e' andato e quanto manca al
    ripristino. Qui quelle intestazioni vengono lette al volo e messe da parte.

    Il vantaggio e' che il conto e' sempre aggiornato senza spendere una sola
    richiesta per tenerlo. Lo svantaggio e' che prima di aver fatto qualcosa
    non si sa niente, ed e' giusto cosi': e' un promemoria di quello che e'
    successo, non un interrogatorio.

Cosa NON e'
    Non e' un limite che qualcuno fa rispettare. Quando i crediti finiscono e'
    Groq a rifiutare, e il programma se ne accorge dall'errore. Questi numeri
    servono a dirlo PRIMA, cosi' non si comincia un video di due ore sapendo
    gia' che si fermera' a meta'.

"""
from __future__ import annotations

import re
import threading
import time
from datetime import datetime, timedelta

from server.utils.contract import Annullato, fermarsi

# === CREDITI GROQ: CACHE DEI RATE-LIMIT PER MODELLO ==========================
# Groq non espone un endpoint "saldo": il budget del piano free arriva SOLO
# negli header x-ratelimit-* di ogni risposta, e sono PER MODELLO (whisper per
# la trascrizione, gpt-oss per il riassunto). Invece di
# sprecare una chiamata vera, e quindi un credito, ad ogni clic sul pulsante
# "crediti", registriamo qui gli header che le richieste REALI già producono:
# il pulsante legge questa cache, a costo zero. La cache vive per la sessione.
_RATE_LIMIT_UNITS = {"ms": 0.001, "s": 1.0, "m": 60.0, "h": 3600.0, "d": 86400.0}
_RATE_LIMIT_CACHE: dict[str, dict] = {}  # model -> {model, items, checked_at_iso}


def _rate_limit_reset_seconds(value: str | None) -> float | None:
    """Da «fra quanto torneranno i crediti» a un numero di secondi.

    Groq lo dice a parole sue: ``2m59.56s``, ``986ms``, ``1h0m0s``. Sono forme
    diverse della stessa informazione, e nessuna e' un numero.

    Qui si cercano tutte le coppie numero-unita' presenti e si sommano. Il giro
    largo invece di un formato solo serve perche' quelle forme cambiano fra un
    tipo di limite e l'altro, e un lettore rigido si romperebbe alla prima
    variante non prevista.

    None se non c'e' niente di leggibile: chi chiama mostrera' «non lo so»
    invece di «fra zero secondi», che sarebbe una bugia.
    """
    if not value:
        return None
    total, found = 0.0, False
    for num, unit in re.findall(r"([0-9.]+)\s*(ms|s|m|h|d)", value):
        try:
            total += float(num) * _RATE_LIMIT_UNITS[unit]
            found = True
        except (ValueError, KeyError):
            pass
    return total if found else None


def _rate_limit_num(value) -> float | None:
    """Trasforma in numero quello che e' arrivato, senza far cadere niente.

    I valori arrivano dalle intestazioni di una risposta, quindi sono testo, e
    ogni tanto sono testo che non e' un numero: vuoto, assente, o qualcosa di
    inatteso. Qui in quel caso si restituisce None invece di sollevare un
    errore.

    E' una scelta, non pigrizia: questi numeri servono a mostrare un conto
    approssimativo a chi guarda. Far fallire una trascrizione perche'
    un'intestazione era scritta male sarebbe sproporzionato.
    """
    if value is None:
        return None
    try:
        return float(value)
    except (ValueError, TypeError):
        return None


def ratelimit_groups(headers):
    """Legge gli header x-ratelimit-* e restituisce le terne grezze.

    Genera (kind, remaining, limit, reset_seconds) per i soli gruppi presenti
    nella risposta; 'kind' ∈ 'audio_seconds' | 'requests' | 'tokens'. Ordine:
    audio-seconds per primo (è quello che frena la trascrizione), poi
    requests/tokens.

    È la parte comune ai due modi di presentare i limiti: la cache di
    transcriber li salva col MOMENTO ASSOLUTO di azzeramento (parse_ratelimit_headers),
    la GUI li vuole come durata + orario (engine._parse_ratelimit_headers).
    Entrambe partono da qui, così la lettura degli header sta scritta una volta sola."""
    def get(name: str):
        """Legge un'intestazione senza fidarsi di come e' fatto il contenitore.

        Le intestazioni arrivano dal client di Groq, e a seconda della versione
        possono essere un dizionario normale o un oggetto suo. Il try serve a
        non dover sapere quale dei due: se il modo di chiedere non funziona,
        vale come «quell'intestazione non c'era».
        """
        try:
            return headers.get(name)
        except Exception:
            return None

    for kind, suffix in (("audio_seconds", "audio-seconds"),
                         ("requests", "requests"),
                         ("tokens", "tokens")):
        remaining = _rate_limit_num(get(f"x-ratelimit-remaining-{suffix}"))
        limit = _rate_limit_num(get(f"x-ratelimit-limit-{suffix}"))
        reset_s = _rate_limit_reset_seconds(get(f"x-ratelimit-reset-{suffix}"))
        if remaining is None and limit is None and reset_s is None:
            continue
        yield kind, remaining, limit, reset_s


def parse_ratelimit_headers(headers) -> list[dict]:
    """Header x-ratelimit-* -> lista di gruppi limite, già con il MOMENTO ASSOLUTO
    di azzeramento (così la cache resta valida anche letta molto dopo).

    Ogni voce: {kind, remaining, limit, reset_at_iso}."""
    now = datetime.now()
    items: list[dict] = []
    for kind, remaining, limit, reset_s in ratelimit_groups(headers):
        reset_at = (now + timedelta(seconds=reset_s)) if reset_s is not None else None
        items.append({
            "kind": kind,
            "remaining": remaining,
            "limit": limit,
            "reset_at_iso": reset_at.isoformat() if reset_at else None,
        })
    return items


def record_rate_limits(model: str, headers) -> list[dict]:
    """Registra in cache i limiti letti dagli header di una risposta Groq REALE.

    A costo zero: gli header viaggiano con richieste che faremmo comunque. Va
    chiamata accanto a ogni chiamata Groq andata a buon fine (trascrizione,
    riassunto). Best-effort: non solleva mai."""
    try:
        items = parse_ratelimit_headers(headers)
    except Exception:
        return []
    if items:
        _RATE_LIMIT_CACHE[model] = {
            "model": model,
            "items": items,
            "checked_at_iso": datetime.now().isoformat(),
        }
    return items


def cached_rate_limits() -> list[dict]:
    """Snapshot per-modello dei limiti registrati finora (per il pulsante crediti).

    Lista (eventualmente vuota) di {model, items, checked_at_iso}. Vuota finché
    non è stata fatta almeno una chiamata Groq reale in questa sessione."""
    return list(_RATE_LIMIT_CACHE.values())


# === QUANDO GROQ DICE «NON ADESSO» ===========================================
#
# Groq rifiuta con lo stesso codice (429) due situazioni opposte. C'e' il
# limite AL MINUTO, che si libera da solo in qualche secondo, e c'e' il limite
# AL GIORNO (o all'ora, per l'audio), che vuol dire tornare fra ore. Prima le
# due cose si confondevano: il client di Groq riprovava da solo aspettando in
# silenzio, e chi guardava vedeva una barra ferma senza sapere se stesse
# lavorando o se fosse finito tutto.
#
# Adesso il client non riprova piu' da solo (``max_retries=0``) e la decisione
# si prende qui: un'attesa breve si fa, dicendo a schermo quanto manca; un'attesa
# lunga non si fa affatto, e si avvisa subito che i crediti sono finiti.

# Oltre questa attesa non conviene aspettare: e' un limite giornaliero o orario,
# e la cosa giusta e' fermarsi e dirlo.
ATTESA_MASSIMA = 60.0


def _intestazioni_errore(exc):
    """Le intestazioni della risposta che ha portato l'errore, se ci sono."""
    return getattr(getattr(exc, "response", None), "headers", None)


def secondi_da_aspettare(exc) -> float | None:
    """Quanti secondi Groq chiede di aspettare prima di riprovare.

    Lo dice in due posti: l'intestazione ``retry-after`` e la frase
    dell'errore («Please try again in 7m12.5s»). Si guarda prima la prima, che
    e' un numero; la frase serve quando l'intestazione non c'e'.
    """
    headers = _intestazioni_errore(exc)
    if headers is not None:
        try:
            ms = headers.get("retry-after-ms")
            if ms is not None:
                return float(ms) / 1000.0
            sec = headers.get("retry-after")
            if sec is not None:
                return float(sec)
        except (TypeError, ValueError, AttributeError):
            pass
    m = re.search(r"try again in\s+([0-9hms.\s]+)", str(exc), flags=re.I)
    return _rate_limit_reset_seconds(m.group(1)) if m else None


def attesa_breve(exc) -> float | None:
    """I secondi da aspettare, ma solo se l'attesa e' breve; altrimenti None.

    None vuol dire «non aspettare»: o Groq non ha detto quanto, o ha detto
    troppo. In tutti e due i casi aspettare sarebbe il silenzio lungo che
    questa funzione esiste per evitare.
    """
    testo = str(exc).lower()
    if "per day" in testo or "per hour" in testo:
        return None
    s = secondi_da_aspettare(exc)
    if s is None or s > ATTESA_MASSIMA:
        return None
    return max(1.0, s)


def ora_di_ripresa(exc) -> str | None:
    """A che ora tornano i crediti, detto come orario («16:45»), se si sa."""
    s = secondi_da_aspettare(exc)
    if s is None:
        return None
    return (datetime.now() + timedelta(seconds=s)).strftime("%H:%M")


def registra_da_errore(model: str, exc) -> None:
    """Mette in cache i limiti che arrivano anche dentro un rifiuto.

    Anche la risposta 429 porta le intestazioni x-ratelimit-*, e sono le piu'
    preziose: dicono che il conto e' a zero e fino a quando. Tenerle serve a
    esauriti(), che cosi' puo' avvisare al lavoro successivo senza nemmeno
    contattare Groq.
    """
    headers = _intestazioni_errore(exc)
    if headers is not None:
        record_rate_limits(model, headers)


def esauriti(model: str) -> str | None:
    """Se in cache risulta che i crediti di 'model' sono finiti, l'ora in cui tornano.

    Guarda l'ultima fotografia dei limiti: se uno dei conti e' a zero e il suo
    ripristino e' ancora lontano piu' di ATTESA_MASSIMA, i crediti per ora
    sono finiti, e partire vorrebbe dire solo farsi dire di no. None se non
    risulta niente, compreso il caso in cui non si sa: nel dubbio si prova.
    """
    snap = _RATE_LIMIT_CACHE.get(model)
    if not snap:
        return None
    adesso = datetime.now()
    for it in snap.get("items", []):
        rem, quando = it.get("remaining"), it.get("reset_at_iso")
        if rem is None or rem > 0 or not quando:
            continue
        try:
            ripristino = datetime.fromisoformat(quando)
        except ValueError:
            continue
        if (ripristino - adesso).total_seconds() > ATTESA_MASSIMA:
            return ripristino.strftime("%H:%M")
    return None


def aspetta(secondi: float, avvisa=None) -> None:
    """Aspetta, dicendo ogni secondo quanto manca.

    'avvisa(rimasti)' riceve i secondi ancora da aspettare, arrotondati: e'
    quello che trasforma una barra ferma in un conto alla rovescia.
    """
    fine = time.monotonic() + secondi
    while True:
        # «Annulla» durante l'attesa vale subito, non dopo il conto alla rovescia.
        if fermarsi():
            raise Annullato()
        rimasti = fine - time.monotonic()
        if rimasti <= 0:
            return
        if avvisa is not None:
            try:
                avvisa(int(rimasti + 0.999))
            except Exception:
                pass
        time.sleep(min(1.0, rimasti))


def audio_residuo(model: str) -> tuple[float, str | None] | None:
    """Quanti secondi di audio restano per 'model', e a che ora si ricaricano.

    Serve a dire PRIMA di partire che un video non ci sta: «restano 20 minuti
    di audio, il video ne dura 45». None se la cache non ne sa niente, oppure
    se il momento del ripristino e' gia' passato: in quel caso il numero
    salvato non vale piu', e fidarsene vorrebbe dire avvisare a torto.
    """
    snap = _RATE_LIMIT_CACHE.get(model)
    if not snap:
        return None
    for it in snap.get("items", []):
        if it.get("kind") != "audio_seconds" or it.get("remaining") is None:
            continue
        ora = None
        if it.get("reset_at_iso"):
            try:
                ripristino = datetime.fromisoformat(it["reset_at_iso"])
            except ValueError:
                return None
            if ripristino <= datetime.now():
                return None
            ora = ripristino.strftime("%H:%M")
        return float(it["remaining"]), ora
    return None


# === QUANTO HA CONSUMATO QUESTO LAVORO =======================================
#
# Per la colonna «Crediti» dello storico. Groq misura due cose diverse: i
# secondi di audio trascritti (con un minimo di dieci per richiesta) e i token
# del riassunto. Si contano qui, mentre le risposte arrivano, e ogni lavoro ha
# il suo conto: le postazioni sono due e possono lavorare insieme, quindi il
# conto sta attaccato al thread del lavoro, come il segnale di «Annulla».
_consumo = threading.local()


def azzera_consumo() -> None:
    """Comincia un conto nuovo per il lavoro che parte in questo thread."""
    _consumo.v = {"audio_s": 0.0, "token": 0}


def aggiungi_consumo(audio_s: float = 0.0, token: int = 0) -> None:
    """Somma al conto di questo thread quello che una risposta di Groq ha costato."""
    v = getattr(_consumo, "v", None)
    if v is None:
        azzera_consumo()
        v = _consumo.v
    v["audio_s"] += float(audio_s or 0.0)
    v["token"] += int(token or 0)


def consumo() -> dict:
    """Il conto di questo thread fin qui: {'audio_s', 'token'}."""
    return dict(getattr(_consumo, "v", None) or {"audio_s": 0.0, "token": 0})
