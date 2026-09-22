"""Mettere in bella: durate, date, numeri, nomi di file.

Che roba c'e' qui
    Le funzioncine che nessun modulo puo' rivendicare come proprie perche' le
    usano tutti. Trasformare 3725 secondi in "1h 02m 05s", 1234567 in "1,2M",
    un titolo di video in qualcosa che Windows accetti come nome di cartella.

Perche' stanno insieme in un posto solo
    Perche' se ognuno se le riscrivesse, prima o poi due parti dello stesso
    programma direbbero la stessa durata in due modi diversi, e chi guarda si
    chiederebbe quale delle due e' quella giusta. Sono dettagli piccoli, ma
    sono esattamente i dettagli che fanno sembrare un programma fatto a pezzi.

Perche' non dipendono da nient'altro
    Di proposito. Questo file non importa nessun altro modulo del programma, e
    non deve cominciare a farlo: e' l'ultimo anello della catena, quello che
    tutti possono chiamare senza il rischio di chiudere un cerchio di import.
    Il giorno in cui una di queste funzioni avesse bisogno di sapere qualcosa
    del resto del programma, vuol dire che non era una funzione di questo file.
"""
from __future__ import annotations

import os
import re
import time
from datetime import datetime


# --- Le funzioni ---

def _format_duration(seconds) -> str:
    """Convert a number of seconds into 'H:MM:SS' (or 'M:SS' if under an hour).

    E.g. 3725 -> '1:02:05'. If the value is not a valid number, returns '?'."""
    try:
        seconds = int(seconds)
    except (ValueError, TypeError):
        return "?"
    h, rem = divmod(seconds, 3600)   # divmod returns (quotient, remainder)
    m, s = divmod(rem, 60)
    if h:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m}:{s:02d}"


def _format_timestamp(seconds: float) -> str:
    """Convert seconds (including decimals) into 'HH:MM:SS' for the timings in the text.

    E.g. 75.4 -> '00:01:15'. Used in front of every transcribed sentence."""
    total = int(seconds)
    h, rem = divmod(total, 3600)
    m, s = divmod(rem, 60)
    return f"{h:02d}:{m:02d}:{s:02d}"


def _format_views(value) -> str:
    """Format the view count using the dot as the thousands separator (IT style).

    E.g. 1234567 -> '1.234.567'. If it is not a valid number, returns it as is."""
    try:
        return f"{int(value):,}".replace(",", ".")
    except (ValueError, TypeError):
        return str(value) if value not in (None, "") else "?"


def _format_upload_date(raw) -> str:
    """yt-dlp provides the date as a 'YYYYMMDD' string (e.g. '20240115').

    Here we transform it into 'DD/MM/YYYY'. If the format is not the expected
    one, we return the raw value without crashing."""
    if not raw:
        return "?"
    try:
        return datetime.strptime(str(raw), "%Y%m%d").strftime("%d/%m/%Y")
    except ValueError:
        return str(raw)


def _safe_filename(name: str) -> str:
    """Clean up a title so that it is a valid file name on Windows.

    Replaces the forbidden characters (\\ / : * ? \" < > |) with an underscore and
    shortens overly long titles, so as not to break the filesystem."""
    name = re.sub(r'[<>:"/\\|?*]', "_", name)
    return name.strip()[:120] or "trascrizione"


def numero_playlist(posizione: int, quanti: int) -> str:
    """Il numero da mettere davanti alla cartella di un video di una playlist.

    Gli zeri davanti non sono un vezzo. Windows ordina i nomi come parole, non
    come numeri: senza zeri, dopo «1» verrebbe «10», e una playlist di trenta
    lezioni si presenterebbe nell'ordine 1, 10, 11, 12, ... 2, 20, che e'
    esattamente il disordine che il numero doveva togliere.

    Quanti zeri servono lo dice la lunghezza della playlist e non un numero
    deciso qui: tre cifre su una playlist di otto video sarebbero brutte, due
    cifre su una di duecento riporterebbero il problema di prima fra il
    novantanove e il cento.
    """
    larghezza = max(2, len(str(max(quanti, 1))))
    return f"{posizione:0{larghezza}d}"


def nome_cartella_video(title: str, numero: str | None = None) -> str:
    """Il nome della cartella di un video, col numero davanti se ne ha uno.

    Il numero ce l'hanno solo i video presi da una playlist, e arriva gia'
    scritto (con i suoi zeri davanti) da ``numero_playlist``, perche' quanti
    zeri servano lo sa soltanto chi conosce la lunghezza della playlist, e qui
    dentro quella cosa non si sa.

    Il titolo viene accorciato PRIMA di ricevere il numero, cosi' il numero non
    rischia di essere lui la parte che sparisce quando il titolo e' lunghissimo.
    """
    safe = _safe_filename(title)
    return f"{numero} - {safe}" if numero else safe


# Una cartella di video che comincia col numero della playlist. Da una a quattro
# cifre, che copre qualunque playlist esista, e poi il titolo cosi' com'e'.
_CARTELLA_NUMERATA = re.compile(r"^\d{1,4} - (.+)$")


def cartella_video(out_root: str, title: str, numero: str | None = None) -> str:
    """Dove stanno (o dove andranno) i file di questo video dentro out_root.

    Perche' non basta incollare il titolo dopo la cartella
        Perche' la stessa cartella viene chiesta in due momenti molto diversi.
        Quando si SCRIVE, il numero della playlist lo si conosce, ed e' quello
        che decide il nome. Quando si RILEGGE, invece, il numero non lo si sa
        piu': «solo riassunto» fatto tre giorni dopo parte da un titolo e
        basta, e «l'ho gia' trascritto?» pure.

        Per questo in lettura la cartella non si calcola, si CERCA: prima come
        si chiamerebbe senza numero, e se non c'e' si guarda se ce n'e' una col
        numero davanti e lo stesso titolo dietro.

    Il vantaggio che viene da solo
        Le cartelle scritte prima che i numeri esistessero continuano a essere
        trovate, perche' il primo posto in cui si guarda e' proprio quello
        senza numero. Nessuno deve rinominare niente a mano.

    Se non si trova nulla si risponde col nome senza numero, che e' la risposta
    giusta per chi sta per creare la cartella adesso.
    """
    safe = _safe_filename(title)
    if numero:
        return os.path.join(out_root, nome_cartella_video(title, numero))
    diretta = os.path.join(out_root, safe)
    if os.path.isdir(_lp(diretta)):
        return diretta
    try:
        for nome in os.listdir(_lp(out_root)):
            trovato = _CARTELLA_NUMERATA.match(nome)
            if trovato and trovato.group(1) == safe:
                candidata = os.path.join(out_root, nome)
                if os.path.isdir(_lp(candidata)):
                    return candidata
    except OSError:
        pass
    return diretta


def _lp(path: str) -> str:
    """Restituisce il percorso in forma 'extended-length' (prefisso \\\\?\\) su
    Windows, così le operazioni su file non incappano nel vecchio limite di 260
    caratteri (MAX_PATH): con titoli lunghi il percorso completo può superarlo e
    open()/makedirs falliscono con FileNotFoundError. No-op su altri sistemi o se
    il prefisso è già presente. Richiede un percorso ASSOLUTO con backslash, che
    os.path.abspath garantisce su Windows."""
    if os.name != "nt":
        return path
    abs_path = os.path.abspath(path)
    if abs_path.startswith("\\\\?\\"):
        return abs_path
    if abs_path.startswith("\\\\"):          # percorso di rete \\server\share
        return "\\\\?\\UNC" + abs_path[1:]   # -> \\?\UNC\server\share
    return "\\\\?\\" + abs_path


def write_text_file(path: str, content: str, created: list[str] | None = None,
                    root: str | None = None) -> None:
    """Scrive un file UTF-8 con LE DUE protezioni che servono su questo sistema.

    Ogni scrittura dell'app passa di qui perché due guasti diversi, entrambi
    reali, colpiscono percorsi diversi:

    1. TITOLI LUNGHI (Windows): il percorso completo, che contiene il titolo del
       video, supera facilmente il vecchio limite di 260 caratteri. Senza il
       prefisso di `_lp()` open() fallisce con FileNotFoundError.
    2. ONEDRIVE: durante la sincronizzazione la cartella può essere
       rinominata/bloccata per un istante, e la scrittura fallisce con OSError
       anche se il percorso è giusto. Si ricrea la directory e si riprova una
       volta dopo una breve pausa.

    Se `created` e `root` sono dati, il percorso del file viene aggiunto alla
    lista in forma relativa a `root` (per l'elenco dei file prodotti)."""
    for attempt in (1, 2):
        try:
            parent = os.path.dirname(path)
            if parent:
                os.makedirs(_lp(parent), exist_ok=True)
            with open(_lp(path), "w", encoding="utf-8") as f:
                f.write(content)
            break
        except OSError:
            if attempt == 2:
                raise
            time.sleep(0.4)  # lascia finire OneDrive, poi riprova una volta
    if created is not None and root is not None:
        created.append(os.path.relpath(path, root).replace("\\", "/"))
