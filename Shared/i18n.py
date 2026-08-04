"""Selezione della lingua e catalogo dei testi mostrati all'utente.

A cosa serve
    Tenere in un posto solo tutte le frasi che finiscono sotto gli occhi di chi
    usa il programma, in italiano e in inglese, e decidere quale delle due
    mostrare. Il codice chiama ``t('chiave')`` e non sa in che lingua sta
    scrivendo: la scelta e' fatta una volta all'avvio, e cambiarla non ricostruisce
    nulla.

Chi puo' cambiare lingua
    L'interfaccia. La riga di comando (``transcriber.py``) ha un suo catalogo di
    messaggi e non passa di qui: chi lavora nel terminale vuole vedere subito il
    banner e cominciare, non rispondere a una domanda sulla lingua.

Cosa NON viene tradotto
    I commenti, i docstring e i nomi delle funzioni restano in italiano.
    Servono a chi legge o mantiene il codice, non a chi lo usa.

Dove finisce la preferenza
    In ``settings.json``, nella cartella dei dati (accanto all'eseguibile
    quando e' impacchettato, accanto ai sorgenti altrimenti). E' un'impostazione
    di chi usa il programma, non del progetto, e infatti il file non viene
    versionato.
"""
from __future__ import annotations

import json

from Shared.percorsi import dati as _dati

# Lingue disponibili, nell'ordine in cui compaiono nel menu.
LANGUAGES = (('it', 'Italiano'), ('en', 'English'))
LANGUAGE_CODES = tuple(codice for codice, _ in LANGUAGES)

# Lingua di ripiego: e' quella in cui il programma ha sempre parlato, quindi un
# aggiornamento non cambia il comportamento a chi non fa nulla.
DEFAULT_LANG = 'it'

_SETTINGS_FILE = _dati('settings.json')

_lingua = DEFAULT_LANG
_catalogo: dict[str, dict[str, str]] = {}


# ── Catalogo e traduzione ────────────────────────────────────────────────────

def register(catalogo: dict[str, dict[str, str]]) -> None:
    """Aggiunge al catalogo comune un blocco di frasi.

    I testi stanno in moduli a parte (``strings_app``) e si registrano
    all'import: cosi' restano separati da leggere ma condividono la stessa
    macchina, e una frase comune si scrive una volta sola.
    """
    _catalogo.update(catalogo)


def catalogo() -> dict[str, dict[str, str]]:
    """Il catalogo intero, per chi deve spedirlo alla pagina in un colpo solo.

    L'interfaccia web traduce da se': riceve tutte le frasi all'avvio e
    riscrive gli elementi quando si cambia lingua, senza dover richiedere a
    Python una stringa alla volta.
    """
    return _catalogo


def t(chiave: str, **kwargs) -> str:
    """Restituisce la frase ``chiave`` nella lingua corrente, formattata.

    I segnaposto sono quelli di ``str.format`` (``{nome}``): passandoli come
    argomenti nominati la frase resta leggibile nel catalogo e ogni lingua puo'
    metterli nell'ordine che le serve, che fra italiano e inglese quasi mai
    coincide.

    Una chiave assente non fa cadere il programma: viene restituita cosi' com'e',
    in modo che un errore di battitura si veda a schermo come stringa strana
    invece di interrompere una trascrizione a meta'.
    """
    voce = _catalogo.get(chiave)
    if voce is None:
        return chiave
    testo = voce.get(_lingua) or voce.get(DEFAULT_LANG) or chiave
    try:
        return testo.format(**kwargs) if kwargs else testo
    except (KeyError, IndexError):
        # Una frase con un segnaposto sbagliato si mostra grezza: e' brutto, ma
        # e' meglio di un'eccezione in mezzo a un lavoro lungo.
        return testo


def set_language(codice: str) -> None:
    """Imposta la lingua corrente, ignorando i codici sconosciuti."""
    global _lingua
    if codice in LANGUAGE_CODES:
        _lingua = codice


def get_language() -> str:
    """Codice della lingua corrente ('it' o 'en')."""
    return _lingua


# ── Preferenza salvata ───────────────────────────────────────────────────────

def load_saved() -> str | None:
    """Legge la lingua salvata, o None se non c'e' o il file e' illeggibile.

    Qualsiasi problema — file assente, JSON rotto, permessi — vale come
    "nessuna preferenza": si riparte dall'italiano, che e' sempre recuperabile.
    Un'impostazione dell'interfaccia non deve mai impedire una trascrizione.
    """
    try:
        with open(_SETTINGS_FILE, encoding='utf-8') as fh:
            codice = json.load(fh).get('lang')
    except (OSError, ValueError):
        return None
    return codice if codice in LANGUAGE_CODES else None


def save(codice: str) -> None:
    """Salva la lingua scelta, conservando le altre chiavi del file.

    La rilettura preventiva serve a non cancellare impostazioni che versioni
    future potrebbero aggiungere accanto a questa. Un errore di scrittura viene
    ignorato: si perde solo la memoria della scelta, e il programma riparte in
    italiano al lancio successivo.
    """
    if codice not in LANGUAGE_CODES:
        return
    contenuto = {}
    try:
        with open(_SETTINGS_FILE, encoding='utf-8') as fh:
            letto = json.load(fh)
        if isinstance(letto, dict):
            contenuto = letto
    except (OSError, ValueError):
        pass

    contenuto['lang'] = codice
    try:
        with open(_SETTINGS_FILE, 'w', encoding='utf-8') as fh:
            json.dump(contenuto, fh, indent=2)
    except OSError:
        pass


# ── Preferenze non linguistiche ──────────────────────────────────────────────
#
# Nello stesso file finiscono anche le scelte che sarebbe scortese far rifare a
# ogni avvio: quale motore, quali modelli. Non sono impostazioni di progetto,
# sono abitudini di chi usa il programma.

def load_prefs() -> dict:
    """Legge le preferenze salvate. Un file mancante o rotto vale come vuoto."""
    try:
        with open(_SETTINGS_FILE, encoding='utf-8') as fh:
            letto = json.load(fh)
    except (OSError, ValueError):
        return {}
    return letto if isinstance(letto, dict) else {}


def save_prefs(**valori) -> None:
    """Scrive alcune preferenze, lasciando intatte le altre chiavi del file."""
    contenuto = load_prefs()
    contenuto.update({k: v for k, v in valori.items() if v is not None})
    try:
        with open(_SETTINGS_FILE, 'w', encoding='utf-8') as fh:
            json.dump(contenuto, fh, indent=2)
    except OSError:
        pass
