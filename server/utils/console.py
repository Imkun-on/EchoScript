"""Dove finisce quello che il programma dice mentre lavora.

Una sola console, per tutti e due i modi di usare il programma
    Sembra strano che il motore stampi su un terminale anche quando gira dentro
    una finestra, e invece e' proprio cosi' che funziona: la finestra dirotta
    l'uscita standard e raccoglie quelle righe una per una, le ripulisce dai
    codici colore e le mette nel diario che si vede a schermo (vedi la classe
    Diario in server/controllers/api.py).

    Quindi chi scrive il codice del motore non deve sapere chi lo sta
    guardando. Scrive, e basta. A decidere dove finisce quella riga e' chi ha
    avviato il programma, non chi la produce.

I nomi dei colori invece dei colori
    Nel resto del codice si scrive ``[info]...[/info]`` e non il nome di un
    colore. Serve a poter cambiare idea in un posto solo: se un giorno il
    ciano risultasse illeggibile su certi terminali, si cambia qui e cambia
    ovunque, invece di andarlo a cercare in duecento righe.

I quattro simboli
    Stanno qui per la stessa ragione. Sono caratteri che non tutti i terminali
    disegnano allo stesso modo, e il giorno in cui uno andasse sostituito
    conviene che sia scritto una volta sola.
"""
from __future__ import annotations

from rich.console import Console
from rich.theme import Theme


# We define a small palette of style names so that in the rest of the code we
# write [info]...[/info] instead of repeating the colors everywhere.
_theme = Theme({
    "info": "bright_cyan",
    "success": "bright_green",
    "warning": "yellow",
    "error": "bold red",
    "title": "bold bright_cyan",
    "phase": "bold bright_blue",
    "dim_label": "dim",
})
console = Console(theme=_theme)

# Symbols used in messages (✓ ✗ → •). Keeping them here makes them easy to change.
SYM_OK, SYM_FAIL, SYM_ARROW, SYM_DOT = "✓", "✗", "→", "•"
