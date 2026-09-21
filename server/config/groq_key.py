"""La chiave di Groq: da dove si prende e come si capisce che manca.

Tre posti, in ordine di precedenza
    Una vera variabile d'ambiente del sistema vince su tutto. Poi il file
    ``.env`` accanto al programma. Poi niente, e allora il backend in nuvola
    non si puo' usare (quello locale si', e non ha bisogno di nessuna chiave).

Il segnaposto, che e' la parte meno ovvia
    Il file ``.env`` di esempio contiene una riga con scritto
    ``gsk_la-tua-chiave-qui``. Chi lo copia e si dimentica di sostituirla si
    ritrova una chiave che esiste ma non funziona, e l'errore che Groq
    restituisce a quel punto non aiuta: parla di autenticazione, non di
    segnaposti.

    Per questo quel valore viene riconosciuto e trattato come "chiave
    assente", che e' l'unico messaggio che porta alla cosa giusta da fare.
"""
from __future__ import annotations

from server.config.settings import _load_env_file


def load_dotenv() -> None:
    """Load the variables from a '.env' file next to the script, if present.

    Thin public wrapper around _load_env_file() (the same loader used at import
    time): kept for backward compatibility, since the engine and the GUI call
    tx.load_dotenv() before reading the Groq/DeepL keys. It reads KEY=value lines
    (ignoring comments/blank lines, tolerating an 'export ' prefix), strips any
    surrounding quotes, and sets each variable ONLY if not already defined, so a
    real environment variable always wins over the .env file.

    The .env file must NOT be committed (it is already in .gitignore): keep it
    only locally, it contains your secret keys."""
    _load_env_file()
# Placeholder value of the .env file: it must be treated as "key not entered".
_GROQ_KEY_PLACEHOLDER = "gsk_la-tua-chiave-qui"
