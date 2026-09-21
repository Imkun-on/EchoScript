"""Le domande che si fanno a ffmpeg sui file audio e video.

ffmpeg e ffprobe sono due programmi a parte, non librerie: ci si parla
lanciandoli e leggendo quello che stampano. Qui stanno le domande che il resto
del programma ha bisogno di fargli.

Perche' una risposta sbagliata non deve fermare tutto
    Se ffprobe non risponde o dice qualcosa di incomprensibile, queste funzioni
    restituiscono zero invece di sollevare un errore. La durata e' un numero
    che serve a stimare e a dividere, non a decidere se si puo' lavorare: senza,
    si lavora lo stesso, solo con una stima peggiore.
"""
from __future__ import annotations

import subprocess


def _probe_duration(audio_path: str) -> float:
    """Ask ffprobe for the duration of an audio file (in seconds).

    Used only as a fallback if the duration was not present in the YouTube
    metadata. If ffprobe also fails, it returns 0 (the splitting into chunks
    will produce nothing and the user will be warned)."""
    try:
        out = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", audio_path],
            capture_output=True, text=True, check=True,
        )
        return float(out.stdout.strip())
    except Exception:
        return 0.0
