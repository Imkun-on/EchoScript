"""Dove stanno le cose, dentro e fuori dall'eseguibile.

Il problema che risolve
    Ogni modulo del progetto calcola la propria cartella con
    ``os.path.dirname(os.path.abspath(__file__))``, e finche' si lancia
    ``python transcriber.py`` e' esattamente quello che serve.

    Dentro un eseguibile costruito con PyInstaller non lo e' piu'. In modalita'
    a file unico il contenuto viene riestratto a ogni avvio in una cartella
    temporanea, e ``__file__`` punta li'. Una trascrizione salvata in quella
    cartella, o la lingua scelta, sparirebbero alla chiusura del programma
    insieme alla cartella stessa.

Le due cartelle, che non coincidono
    risorse   cio' che e' stato impacchettato insieme al programma e non
              cambia mai: la pagina web, le icone. Dentro l'eseguibile sta
              nella cartella temporanea; fuori, accanto ai sorgenti.

    dati      cio' che appartiene a chi usa il programma e deve restare: le
              trascrizioni, i PDF, la lingua scelta. Dentro l'eseguibile sta
              accanto al file .exe, dove la si trova aprendo la cartella;
              fuori, accanto ai sorgenti.

    Fuori dall'eseguibile le due coincidono, ed e' il motivo per cui finora la
    distinzione non serviva a nessuno.
"""
from __future__ import annotations

import os
import sys

# La radice del progetto quando si lavora sui sorgenti.
#
# Questo file sta in  server/config/paths.py,  quindi per arrivare alla radice
# bisogna risalire di TRE cartelle: config, poi server, poi si e' arrivati.
# Il numero di risalite non e' decorativo e non va tirato a indovinare: e'
# esattamente la profondita' a cui sta questo file. Se un giorno paths.py si
# sposta, questa riga si sposta con lui, altrimenti il programma comincia a
# cercare la pagina e le icone in una cartella che non esiste.
#
# Il calcolo e' scritto per pezzi invece che con tre dirname incastrati uno
# dentro l'altro, cosi' chi legge conta le risalite invece di doverle dedurre
# dalle parentesi.
_QUESTO_FILE = os.path.abspath(__file__)
_CARTELLA_CONFIG = os.path.dirname(_QUESTO_FILE)          # server/config
_CARTELLA_SERVER = os.path.dirname(_CARTELLA_CONFIG)      # server
_SORGENTI = os.path.dirname(_CARTELLA_SERVER)             # la radice


def impacchettato() -> bool:
    """True se stiamo girando dentro un eseguibile costruito con PyInstaller."""
    return getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS')


def cartella_risorse() -> str:
    """Dove stanno i file impacchettati col programma (la pagina, le icone)."""
    return sys._MEIPASS if impacchettato() else _SORGENTI


def cartella_dati() -> str:
    """Dove stanno i file di chi usa il programma, e dove restano.

    Accanto all'eseguibile, non nella cartella temporanea: e' l'unico posto che
    chi lo ha lanciato sa ritrovare, ed e' l'unico che sopravvive alla
    chiusura.
    """
    if impacchettato():
        return os.path.dirname(os.path.abspath(sys.executable))
    return _SORGENTI


def dati(*parti: str) -> str:
    """Percorso dentro la cartella dei dati."""
    return os.path.join(cartella_dati(), *parti)


def risorsa(*parti: str) -> str:
    """Percorso dentro la cartella delle risorse impacchettate."""
    return os.path.join(cartella_risorse(), *parti)
