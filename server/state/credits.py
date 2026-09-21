"""Quanto si e' gia' consumato di Groq, e quanto ne resta.

Come si fa a saperlo senza chiedere
    Non si chiede. Ogni risposta che Groq manda indietro, per qualunque cosa
    (una trascrizione, un riassunto, la lettura di un fotogramma), porta con
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
from datetime import datetime, timedelta

# === CREDITI GROQ: CACHE DEI RATE-LIMIT PER MODELLO ==========================
# Groq non espone un endpoint "saldo": il budget del piano free arriva SOLO
# negli header x-ratelimit-* di ogni risposta, e sono PER MODELLO (whisper per
# la trascrizione, gpt-oss per il riassunto, qwen per la visiva). Invece di
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
    riassunto, visiva). Best-effort: non solleva mai."""
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
