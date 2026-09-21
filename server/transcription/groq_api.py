"""Trascrivere un blocco di audio mandandolo ai server di Groq.

Un blocco alla volta, e perche'
    L'audio arriva gia' tagliato in pezzi da qualche minuto (vedi
    ``audio.py``). Qui si manda un pezzo, si aspetta la risposta, e si passa al
    prossimo. Chi tiene il conto e decide quando fermarsi sta piu' in alto.

    Il vantaggio di lavorare a pezzi e' che un guasto a meta' strada non porta
    via tutto: i pezzi gia' fatti sono salvati, e si riprende da li'.

Quando Groq dice di no
    Il rifiuto piu' comune non e' un guasto: e' "hai finito i crediti per
    oggi". Si distingue dagli altri errori e si solleva un'eccezione apposta,
    perche' porta a una decisione diversa: non "riprova", ma "salva quello che
    hai e torna domani".

I tempi delle parole
    Groq puo' restituire l'ora esatta di ogni singola parola, non solo di ogni
    frase. Costa un po' di piu' in dimensione della risposta, e serve a chi poi
    vuole saltare a un punto preciso del video. Si chiede solo se e' stato
    chiesto.
"""
from __future__ import annotations

import os
import time

from groq import Groq

from server.config import settings
from server.config.messages import msg
from server.config.settings import _USE_CONFIG, MAX_RETRIES, WORD_TIMESTAMPS
from server.state.credits import record_rate_limits
from server.utils.console import SYM_FAIL, console
from server.utils.contract import GroqRateLimit, _is_rate_limit, _noop_progress


def _coerce(obj, key):
    """Read 'key' from an item that may be a dict OR an object (the Groq SDK
    returns both depending on version): obj['key'] if a mapping, else
    getattr(obj, key)."""
    if isinstance(obj, dict):
        return obj.get(key)
    return getattr(obj, key, None)
def _extract_words(result) -> list[dict]:
    """Normalize Groq's per-word timestamps (when requested) to a flat list of
    {word, start, end}. Returns [] if the response carries no word timings."""
    raw = getattr(result, "words", None) or []
    words = []
    for w in raw:
        txt = _coerce(w, "word")
        start, end = _coerce(w, "start"), _coerce(w, "end")
        if txt is None or start is None or end is None:
            continue
        words.append({"word": str(txt), "start": float(start), "end": float(end)})
    return words
def _transcribe_chunk(client: Groq, chunk_path: str, prompt: str = "",
                      return_language: bool = False, language=_USE_CONFIG,
                      want_words: bool | None = None, on_headers=None):
    """Send ONE audio chunk to Groq and return the list of its segments.

    Uses response_format='verbose_json' to receive, in addition to the text, the
    start/end timestamps of each sentence ('segments'). 'prompt' contains the
    tail of the previous transcription: giving Whisper a bit of context improves
    continuity (proper names, terminology) from one chunk to the next.
    Retries up to MAX_RETRIES times in case of a network/API error.

    'language' forces the audio language (e.g. 'it'/'en'); the _USE_CONFIG
    sentinel means "use the settings.LANGUAGE config" (None there = auto-detect).
    'want_words' requests per-word timestamps (defaults to the WORD_TIMESTAMPS
    config); when on, each segment also carries a 'words' list (start/end/word).

    'on_headers' (optional): if given, the call uses the raw response and passes
    its HTTP headers to on_headers(headers) — so the engine can read the
    x-ratelimit-* budget. None (the CLI default) keeps the plain call unchanged.

    If return_language=True, returns (segments, language) where 'language' is the
    ISO code Whisper auto-detected (e.g. 'en'/'it'), otherwise just the segments
    (backward-compatible default for the CLI)."""
    lang_opt = settings.LANGUAGE if language is _USE_CONFIG else language
    words_on = WORD_TIMESTAMPS if want_words is None else want_words
    granularities = ["segment", "word"] if words_on else ["segment"]

    def _ret(segs, lang):
        return (segs, lang) if return_language else segs

    def _attach_words(seg_start: float, seg_end: float, words: list[dict]) -> list[dict]:
        """Pick the words whose start falls inside this segment's [start, end)."""
        return [w for w in words if seg_start - 0.05 <= w["start"] < seg_end + 0.05]

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            with open(chunk_path, "rb") as f:
                params = dict(
                    file=(os.path.basename(chunk_path), f.read()),
                    model=settings.GROQ_MODEL,
                    response_format="verbose_json",
                    timestamp_granularities=granularities,
                    language=lang_opt,            # None = auto-detection
                    prompt=prompt[-400:],         # last ~400 characters as context
                    temperature=0.0,             # 0 = more deterministic/faithful output
                )
                if on_headers is not None:
                    # Raw response so the caller can read the x-ratelimit-* headers
                    # (the Groq "credits"); .parse() yields the same parsed object.
                    # Header reading must NEVER cost us the transcription: on any
                    # unexpected SDK error (but not rate-limit/auth) we fall back to
                    # the plain call and simply skip the credit info.
                    try:
                        raw = client.audio.transcriptions.with_raw_response.create(**params)
                    except Exception as raw_err:
                        rmsg = str(raw_err)
                        if _is_rate_limit(rmsg) or "401" in rmsg or "403" in rmsg:
                            raise
                        result = client.audio.transcriptions.create(**params)
                    else:
                        try:
                            on_headers(raw.headers)
                        except Exception:
                            pass
                        # Crediti: registra i limiti del modello di trascrizione
                        # (a costo zero, dalla risposta che stiamo già leggendo).
                        record_rate_limits(settings.GROQ_MODEL, raw.headers)
                        result = raw.parse()
                else:
                    result = client.audio.transcriptions.create(**params)
            lang = getattr(result, "language", None)
            # result.segments is a list of objects with .start, .end, .text
            segments = getattr(result, "segments", None)
            if segments is None:
                # If for some reason there are no segments, we fall back to the whole text.
                return _ret([{"start": 0.0, "end": 0.0, "text": getattr(result, "text", "").strip()}], lang)
            words = _extract_words(result) if words_on else []
            out_segs = []
            for s in segments:
                ss, se = float(s["start"]), float(s["end"])
                seg = {"start": ss, "end": se, "text": s["text"].strip()}
                if words:
                    seg["words"] = _attach_words(ss, se, words)
                out_segs.append(seg)
            return _ret(out_segs, lang)
        except GroqRateLimit:
            raise
        except Exception as e:
            msg = str(e)
            # Limite Groq (429 / token-al-giorno): inutile insistere, fermiamoci
            # subito così chi chiama può salvare un checkpoint e riprendere dopo.
            if _is_rate_limit(msg):
                raise GroqRateLimit(msg)
            # Authentication/access errors (401/403): there is NO point retrying,
            # they do not resolve on their own. We stop immediately with a clear message.
            if "401" in msg or "403" in msg or "invalid_api_key" in msg:
                console.print(f"  [error]Accesso a Groq negato (chiave/rete): {e}[/error]")
                return _ret([], None)
            if attempt == MAX_RETRIES:
                console.print(f"  [error]Blocco fallito dopo {MAX_RETRIES} tentativi: {e}[/error]")
                return _ret([], None)
            # Increasing wait between one attempt and the next (linear backoff).
            time.sleep(2 * attempt)
    return _ret([], None)
