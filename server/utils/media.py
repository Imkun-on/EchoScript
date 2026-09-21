"""Che materiale e' questo, e in che lingua parla.

Domande semplici a cui mezzo programma ha bisogno di rispondere: questo video
arriva da YouTube o e' un file che sta gia' sul disco? Quello che si sente e'
gia' italiano, o va tradotto?

Sono qui e non dentro chi le usa perche' le usano in tanti, e perche' la
risposta deve essere la stessa ovunque. Un video che per una parte del
programma e' "locale" e per un'altra no produce due comportamenti diversi
sullo stesso file, ed e' il genere di cosa che poi nessuno capisce.
"""
from __future__ import annotations


def _is_local(meta: dict) -> bool:
    """Questo materiale arriva da YouTube o da un file che c'era gia'?

    Sembra una domanda da niente e invece cambia parecchie cose piu' avanti:
    un file locale non si scarica, non ha una copertina da mostrare, non ha un
    canale ne' una data di pubblicazione, e nel documento finale quei campi
    vanno lasciati fuori invece che riempiti di vuoto.

    La risposta e' scritta nei metadati fin dall'inizio, cosi' nessuno deve
    dedurla guardando se c'e' un indirizzo web.
    """
    return meta.get("source") == "local"

def _lang_name(code: str | None) -> str | None:
    """Nome di una lingua, in italiano (default) o in inglese ('lang="en"').

    Accetta sia i codici ISO (faster-whisper: 'en') sia i nomi interi di Whisper
    (Groq: 'english'). None se assente. Il parametro 'lang' serve alla GUI in
    inglese, che vuole i nomi lingua in inglese ('English' invece di 'Inglese')."""
    if not code:
        return None
    c = str(code).split("-")[0].strip().lower()
    full = {"italian": "it", "english": "en", "spanish": "es",
            "french": "fr", "german": "de"}
    c = full.get(c, c)
    names_it = {"it": "Italiano", "en": "Inglese", "es": "Spagnolo",
                "fr": "Francese", "de": "Tedesco"}
    names = names_it
    return names.get(c, str(code).upper())

def _is_italian(code: str | None) -> bool:
    """True se il codice/nome lingua indica l'italiano (es. 'it', 'italian').

    Usata per saltare la traduzione automatica quando l'audio è già in italiano
    (tradurre it -> it sarebbe inutile)."""
    if not code:
        return False
    c = str(code).split("-")[0].strip().lower()
    return c in ("it", "ita", "italian", "italiano")

def _lang_code(code: str | None) -> str | None:
    """Codice ISO a 2 lettere da un codice/nome lingua ('english'->'en'), o None.

    Normalizza sia i codici (faster-whisper: 'en') sia i nomi interi (Groq:
    'english') e alcuni nomi italiani ('inglese')."""
    if not code:
        return None
    c = str(code).split("-")[0].strip().lower()
    full = {"italian": "it", "english": "en", "spanish": "es", "french": "fr",
            "german": "de", "ita": "it", "eng": "en", "italiano": "it",
            "inglese": "en", "spagnolo": "es", "francese": "fr", "tedesco": "de"}
    return full.get(c, c)

def _is_same_language(detected: str | None, target: str | None) -> bool:
    """True se l'audio rilevato è GIÀ nella lingua 'target': tradurre sarebbe inutile.

    Generalizza _is_italian a una lingua qualsiasi: con interfaccia in inglese il
    target della traduzione è l'inglese, quindi un audio inglese non va tradotto."""
    d, t = _lang_code(detected), _lang_code(target)
    return bool(d and t and d == t)
