"""Procurarsi l'audio, da YouTube o da un file che c'e' gia'.

Perche' solo l'audio
    Perche' trascrivere non ha bisogno d'altro, e la differenza di peso e'
    enorme: un'ora di video sono centinaia di megabyte, la stessa ora di audio
    compresso sono una ventina. Su una playlist di cinquanta video quella
    differenza e' fra un lavoro che finisce e uno che riempie il disco.

    Il video intero si scarica solo quando si e' chiesta anche l'analisi
    visiva, perche' li' servono i fotogrammi.

Non stampa niente
    Riferisce quello che sta succedendo chiamando una funzione che gli viene
    passata. Chi l'ha chiamato decide se scriverlo in un terminale, metterlo in
    un diario dentro una finestra, o ignorarlo.
"""
from __future__ import annotations

import os
import subprocess

import yt_dlp

from server.config import settings
from server.config.messages import msg
from server.utils.contract import MediaError, _never_stop, _noop_progress
from server.utils.text import _safe_filename


def download_audio(url: str, workdir: str, on_progress=_noop_progress,
                   should_stop=_never_stop) -> str:
    """Download ONLY the video's audio into the temporary folder `workdir`.

    Versione SENZA interfaccia, condivisa da CLI e GUI: l'avanzamento esce da
    `on_progress(phase, current, total, detail)` invece di essere disegnato qui,
    così chi chiama decide se mostrarlo con una barra rich, in una GUI o per
    niente. `should_stop()` viene interrogata a ogni tick per poter annullare
    (la CLI la aggancia a Ctrl+C). Restituisce il percorso del file audio;
    solleva MediaError se qualcosa va storto. Wrapper CLI: `_cli_download_audio`."""
    out_template = os.path.join(workdir, "audio.%(ext)s")  # %(ext)s = the actual extension chosen by yt-dlp

    def _hook(d: dict) -> None:
        """Callback called by yt-dlp with the download status."""
        if should_stop():
            # Raising an exception here interrupts the yt-dlp download.
            raise KeyboardInterrupt
        if d["status"] == "downloading":
            total = d.get("total_bytes") or d.get("total_bytes_estimate")
            done = d.get("downloaded_bytes", 0)
            on_progress("download", done, total, msg("dl_audio"))
        elif d["status"] == "finished":
            # Download finished: but yt-dlp now EXTRACTS the audio with ffmpeg (a
            # few seconds, without a percentage). We signal it so it does not look stuck.
            on_progress("download", None, None, msg("extract_audio"))

    def _pp_hook(d: dict) -> None:
        """Post-processor callback (the audio conversion after the download).

        It serves to NOT leave the screen frozen during the audio extraction: we
        report it so the user sees that the work continues."""
        if d.get("status") == "started":
            on_progress("download", None, None, msg("convert_audio"))

    ydl_opts = {
        "format": "bestaudio/best",   # the best audio-only track available
        "outtmpl": out_template,
        "quiet": True,
        "no_warnings": True,
        "noprogress": True,           # suppress yt-dlp's internal bar (we draw our own)
        "progress_hooks": [_hook],
        "postprocessor_hooks": [_pp_hook],  # to show the progress of the conversion
        # Extracts/normalizes the audio into m4a via ffmpeg (already present on the system).
        "postprocessors": [{
            "key": "FFmpegExtractAudio",
            "preferredcodec": "m4a",
        }],
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])
    except Exception as e:
        raise MediaError(f"Errore nel download audio: {e}")

    # The postprocessor produces a .m4a: we look for it in the working folder.
    for fname in os.listdir(workdir):
        if fname.startswith("audio."):
            return os.path.join(workdir, fname)
    raise MediaError("File audio non trovato dopo il download.")
