"""Il filo teso fra Python e la pagina, e chi lo tiene in mano.

Perche' esiste un modulo apposta per due funzioni
    Perche' la finestra e' una sola e serve a due padroni che non si conoscono.
    La crea il punto d'ingresso (``EchoScript.py``); a parlarci dentro sono i
    metodi che rispondono alla pagina (``api.py``) e i thread che lavorano in
    sottofondo. Se la tenesse uno dei due, l'altro dovrebbe importarlo, e
    siccome si importano gia' a vicenda si chiuderebbe un cerchio.

    Tenendola qui, in un modulo che non importa nessuno dei due, il cerchio non
    si chiude: tutti e due guardano in basso, verso questo file.

Le due direzioni, che non si somigliano
    Dalla pagina a Python si chiama un metodo e si aspetta la risposta, come
    una domanda normale. Da Python alla pagina no: si manda qualcosa che arriva
    quando vuole chi lo manda, e nessuno sta aspettando. Righe di diario,
    avanzamento, la fine di un lavoro. Per questo serve ``verso_pagina``, e per
    questo non torna indietro niente.
"""
from __future__ import annotations

import json

# La finestra. Nasce vuota e la riempie il punto d'ingresso appena l'ha creata.
#
# Si tiene dietro due funzioni invece di lasciarla nuda perche' chi la usa non
# deve mai copiarsela in una variabile propria: chiedendola ogni volta si ha
# sempre quella vera, anche se un giorno dovesse cambiare.
_finestra = None


def imposta(finestra) -> None:
    """Registra la finestra appena creata. La chiama il punto d'ingresso."""
    global _finestra
    _finestra = finestra


def attuale():
    """La finestra, o None se non e' ancora stata creata."""
    return _finestra


def json_per_js(valore) -> str:
    """JSON valido anche come pezzo di codice JavaScript.

    JSON e JavaScript non coincidono del tutto: U+2028 e U+2029 sono caratteri
    legittimi dentro una stringa JSON ma terminano una riga in JavaScript, quindi
    finirebbero dentro ``window.funzione(...)`` spezzando l'istruzione a meta'.
    Un titolo di video che li contiene farebbe fallire la chiamata in silenzio —
    l'errore lo vedrebbe solo la console della pagina, che qui non si apre. Si
    riscrivono nella loro forma con la barra rovesciata, che JSON accetta e
    JavaScript legge come lo stesso carattere.
    """
    return (json.dumps(valore, ensure_ascii=False, default=str)
            .replace('\u2028', '\\u2028').replace('\u2029', '\\u2029'))



def verso_pagina(funzione: str, *argomenti) -> None:
    """Esegue una funzione JavaScript della pagina, da qualunque thread.

    Gli argomenti passano per JSON: e' l'unico modo di trasportare un dizionario
    Python dentro la pagina senza inventarsi una codifica, e protegge da apici e
    accenti che altrimenti spezzerebbero la chiamata.
    """
    if _finestra is None:
        return
    try:
        args = ', '.join(json_per_js(a) for a in argomenti)
        _finestra.evaluate_js(f'window.{funzione}({args})')
    except Exception:
        # Una finestra chiusa mentre un thread stava ancora riferendo non e' un
        # errore: e' il normale ordine di spegnimento.
        pass
