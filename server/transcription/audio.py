"""Preparare l'audio e tagliarlo in pezzi.

Perche' si taglia
    Perche' chi trascrive ha un limite di dimensione per richiesta, e un'ora di
    parlato non ci sta. Il file viene riportato a un formato leggero e poi
    diviso in blocchi di qualche minuto.

Perche' i tagli non cadono a caso
    Ogni blocco viene trascritto separatamente, quindi un taglio in mezzo a una
    parola la spezza in due meta' che nessun modello sa rimettere insieme. I
    tagli seguono i confini dei blocchi ma il conto dei secondi resta continuo,
    cosi' i tempi che si leggono nella trascrizione sono quelli veri del video
    e non quelli del pezzetto.
"""
from __future__ import annotations

import os
import subprocess

from server.config import settings
from server.config.messages import msg
from server.config.settings import AUDIO_BITRATE, AUDIO_SAMPLE_RATE, CHUNK_SECONDS
from server.utils.contract import MediaError, _never_stop, _noop_progress
from server.utils.ffmpeg import _probe_duration


def split_audio(audio_path: str, duration: float, workdir: str,
                on_progress=_noop_progress, should_stop=_never_stop) -> list[tuple[float, str]]:
    """Split the audio into chunks of CHUNK_SECONDS, re-encoding them to 16 kHz mono.

    For each chunk it launches ffmpeg with:
      -ss <start>     -> skip to the chunk's start second
      -t  <duration>  -> take only CHUNK_SECONDS seconds
      -ac 1           -> 1 channel (mono)
      -ar 16000       -> 16 kHz (format Whisper likes)
    Returns a list of pairs (offset_in_seconds, mp3_file_path).
    The offset is used later to correct each chunk's timestamps.
    Versione senza interfaccia: l'avanzamento esce da `on_progress` e
    `should_stop()` permette di annullare a metà. Wrapper CLI:
    `_cli_split_audio`."""
    chunks: list[tuple[float, str]] = []
    # Senza durata il ciclo qui sotto non entrerebbe nemmeno una volta e la
    # trascrizione uscirebbe vuota con un «Nessun testo trascritto» che non
    # spiega niente. Si riprova a misurarla dal file e, se non si riesce, lo si
    # dice: il guasto è ffprobe/file illeggibile, non l'audio senza parole.
    if not duration:
        duration = _probe_duration(audio_path)
    if not duration:
        raise MediaError(
            "Impossibile determinare la durata dell'audio: il file potrebbe "
            "essere danneggiato o ffprobe non è raggiungibile.")
    # Number of chunks computed in advance (rounded up) to give the bar a total.
    # max(1, ...) avoids 0 chunks on very short audio.
    n_chunks = max(1, int((duration + CHUNK_SECONDS - 1) // CHUNK_SECONDS))

    start = 0.0
    idx = 0
    while start < duration:
        if should_stop():
            break
        out_path = os.path.join(workdir, f"chunk_{idx:03d}.mp3")
        cmd = [
            "ffmpeg", "-y",                 # -y = overwrite without asking
            "-ss", str(start),              # start point
            "-t", str(CHUNK_SECONDS),       # how many seconds to take
            "-i", audio_path,               # input file
            "-ac", "1",                     # mono
            "-ar", str(AUDIO_SAMPLE_RATE),  # 16 kHz
            "-b:a", AUDIO_BITRATE,          # audio bitrate
            out_path,
        ]
        # stdout/stderr discarded: we only care that the file gets created.
        subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
        chunks.append((start, out_path))
        start += CHUNK_SECONDS
        idx += 1
        on_progress("prepare", idx, n_chunks, msg("chunk_prep", i=idx, n=n_chunks))
    return chunks
