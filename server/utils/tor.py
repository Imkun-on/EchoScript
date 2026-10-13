"""Nascondere l'IP: tutto quello che va verso YouTube passa da Tor.

Cosa fa
    YouTube non vede l'indirizzo di casa: vede quello di un nodo d'uscita di
    Tor, che cambia. Il programma avvia un ``tor.exe`` suo, in sottofondo,
    all'apertura della finestra, e ci fa passare yt-dlp (le informazioni sul
    video, l'elenco di una playlist, l'audio) e le copertine.

    E' sempre acceso, senza interruttore. Se Tor non parte, YouTube NON si
    raggiunge con la connessione diretta: ci si ferma con un messaggio. Un
    ripiego silenzioso mostrerebbe l'IP proprio nel momento in cui si crede
    di averlo nascosto.

Cosa non passa da Tor
    Groq, in «Cloud»: li' ci si presenta con la propria chiave, quindi non
    c'e' niente da nascondere, e l'audio da mandare e' tanto. Ollama, che e'
    su questo computer. Gli scaricamenti dei modelli e delle due librerie che
    disegnano formule e grafici: sono tanti megabyte da siti che non c'entrano
    con cosa si guarda, e su Tor ci metterebbero molto di piu'.

Da dove viene tor.exe
    Dal «Tor Expert Bundle» ufficiale, scaricato da torproject.org la prima
    volta (circa 22 MB), in ``%LOCALAPPDATA%\\EchoScript\\tor``. La versione
    la dice l'indice che usa anche Tor Browser per aggiornarsi. Sta li' e non
    accanto al programma perche' la cartella dei dati di Tor cambia di
    continuo, e dentro una cartella sincronizzata (OneDrive) darebbe guai.

YouTube e Tor
    A volte YouTube riconosce un nodo d'uscita e risponde «conferma di non
    essere un bot». Si chiede allora a Tor un'identita' nuova (``NEWNYM``, un
    altro nodo d'uscita) e si riprova: e' quello che fa ``nuova_identita``.
"""
from __future__ import annotations

import atexit
import json
import os
import socket
import subprocess
import tarfile
import tempfile
import threading
import time
import urllib.request

from server.config import paths

CARTELLA = os.path.join(os.environ.get('LOCALAPPDATA') or paths.dati(),
                        'EchoScript', 'tor')
ESEGUIBILE = os.path.join(CARTELLA, 'tor', 'tor.exe')
DATI = os.path.join(CARTELLA, 'dati')
DIARIO = os.path.join(CARTELLA, 'tor.log')
_INDICE = ('https://aus1.torproject.org/torbrowser/update_3/release/'
           'download-windows-x86_64.json')
_ARCHIVIO = ('https://dist.torproject.org/torbrowser/{v}/'
             'tor-expert-bundle-windows-x86_64-{v}.tar.gz')

# Quanto aspettare che Tor sia pronto prima di arrendersi. Il primo avvio
# scarica il programma e l'elenco dei nodi e ci mette di piu'; dopo, pochi
# secondi.
ATTESA = 120

# Quante volte si prova una richiesta a YouTube cambiando nodo d'uscita.
TENTATIVI = 3

# Con queste parole comincia l'errore quando Tor non c'e': e' da qui che
# contract.classifica_errore lo riconosce e lo spiega a parole.
SENZA_TOR = 'Tor non raggiungibile'

_pronto = threading.Event()
_serratura = threading.Lock()
_stato = {'fase': 'spento', 'errore': '', 'socks': 0, 'controllo': 0}
_processo: subprocess.Popen | None = None
_ultima_identita = 0.0


def _annota(riga: str) -> None:
    """Una riga nel diario di Tor, per capire dopo che cosa e' andato storto.

    Sta in un file e non a schermo: quello che Tor racconta mentre si collega
    serve a chi cerca un guasto, non a chi sta trascrivendo.
    """
    try:
        with open(DIARIO, 'a', encoding='utf-8') as f:
            f.write(time.strftime('%Y-%m-%d %H:%M:%S ') + riga.rstrip() + '\n')
    except OSError:
        pass


def stato() -> dict:
    """Per la pagina: 'spento', 'avvio', 'pronto' o 'errore', e il perche'."""
    return {'fase': _stato['fase'], 'errore': _stato['errore']}


def _porta_libera() -> int:
    with socket.socket() as s:
        s.bind(('127.0.0.1', 0))
        return s.getsockname()[1]


def installa() -> None:
    """Scarica e scompatta il Tor Expert Bundle, se non c'e' gia'."""
    if os.path.isfile(ESEGUIBILE):
        return
    os.makedirs(CARTELLA, exist_ok=True)
    with urllib.request.urlopen(_INDICE, timeout=30) as r:
        versione = json.load(r)['version']
    _annota(f'Scarico Tor {versione}')
    with tempfile.TemporaryFile() as f:
        with urllib.request.urlopen(_ARCHIVIO.format(v=versione), timeout=120) as r:
            while pezzo := r.read(1 << 16):
                f.write(pezzo)
        f.seek(0)
        with tarfile.open(fileobj=f, mode='r:gz') as tar:
            tar.extractall(CARTELLA, filter='data')
    if not os.path.isfile(ESEGUIBILE):
        raise RuntimeError('Tor scaricato, ma manca tor.exe')


def _avvia() -> None:
    global _processo
    try:
        _stato['fase'] = 'avvio'
        installa()
        os.makedirs(DATI, exist_ok=True)
        try:
            os.remove(DIARIO)               # un diario per avvio, non uno per sempre
        except OSError:
            pass
        socks, controllo = _porta_libera(), _porta_libera()
        geoip = os.path.join(CARTELLA, 'data')
        _processo = subprocess.Popen(
            [ESEGUIBILE,
             '--SocksPort', f'127.0.0.1:{socks}',
             '--ControlPort', f'127.0.0.1:{controllo}',
             '--CookieAuthentication', '1',
             '--DataDirectory', DATI,
             '--GeoIPFile', os.path.join(geoip, 'geoip'),
             '--GeoIPv6File', os.path.join(geoip, 'geoip6'),
             # Se il programma si chiude male, Tor se ne accorge e si chiude
             # anche lui, invece di restare appeso fra i processi.
             '__OwningControllerProcess', str(os.getpid())],
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
            encoding='utf-8', errors='replace',
            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        atexit.register(ferma)
        for riga in _processo.stdout:
            _annota(riga)
            if 'Bootstrapped 100%' in riga:
                _stato.update(socks=socks, controllo=controllo, fase='pronto')
                _pronto.set()
                _annota(f'Tor pronto sulla porta {socks}')
                break
        else:
            raise RuntimeError('Tor si e\' chiuso prima di collegarsi')
        # Il resto dei messaggi va letto comunque, o il tubo si riempie e
        # Tor si blocca.
        for riga in _processo.stdout:
            _annota(riga)
        # Arrivati qui Tor si e' chiuso da solo, a programma ancora aperto:
        # lo si dice, cosi' la prossima richiesta lo fa ripartire invece di
        # bussare a una porta dove non c'e' piu' nessuno.
        _stato.update(fase='errore', errore='Tor si e\' chiuso')
    except Exception as e:                  # noqa: BLE001
        _annota(f'Tor non avviato: {e}')
        _stato.update(fase='errore', errore=str(e)[:200])
        _pronto.set()


def avvia_in_sottofondo() -> None:
    """Avvia Tor una volta sola, senza aspettarlo."""
    with _serratura:
        if _stato['fase'] in ('spento', 'errore'):
            _pronto.clear()
            _stato.update(fase='avvio', errore='')
            threading.Thread(target=_avvia, daemon=True, name='tor').start()


def proxy() -> str:
    """L'indirizzo del proxy per yt-dlp; aspetta che Tor sia pronto.

    Se Tor non c'e', solleva un errore invece di restituire None: chi chiama
    non deve poter andare su internet a viso scoperto per distrazione.
    """
    avvia_in_sottofondo()
    if not _pronto.wait(ATTESA) or _stato['fase'] != 'pronto':
        raise RuntimeError(
            SENZA_TOR + ', quindi non contatto YouTube per non mostrare il tuo IP. '
            + (_stato['errore'] or 'Controlla la connessione e riprova.'))
    return f"socks5h://127.0.0.1:{_stato['socks']}"


def attraverso(ydl_opts: dict) -> dict:
    """Le stesse opzioni di yt-dlp, col proxy di Tor dentro.

    Le opzioni di yt-dlp si costruiscono in tre punti diversi (la scheda di un
    video, l'elenco di una playlist, lo scaricamento dell'audio) e tutti
    devono passare da qui: una chiamata che se ne dimenticasse mostrerebbe a
    YouTube l'IP di casa. Modifica e restituisce lo stesso dizionario, per
    potersi incastrare nell'espressione che lo crea.
    """
    ydl_opts['proxy'] = proxy()
    return ydl_opts


def riprovando(azione):
    """Esegue ``azione()``, con un nodo d'uscita nuovo se YouTube blocca questo.

    Ogni altro errore passa subito, cosi' com'e': cambiare nodo serve solo
    quando e' il nodo a non piacere a YouTube.
    """
    for tentativo in range(TENTATIVI):
        try:
            return azione()
        except Exception as e:              # noqa: BLE001
            if tentativo == TENTATIVI - 1 or not bloccato_da_youtube(e):
                raise
            _annota('YouTube blocca questo nodo, ne chiedo un altro')
            nuova_identita()


def bloccato_da_youtube(errore: object) -> bool:
    """True se YouTube ha riconosciuto il nodo d'uscita e chiede di accedere.

    La conferma dell'eta' comincia con le stesse parole ma e' un'altra cosa:
    riguarda il video e non il nodo, e cambiare nodo non la toglie.
    """
    testo = str(errore).lower()
    if 'confirm your age' in testo:
        return False
    return 'not a bot' in testo or 'sign in to confirm' in testo


def nuova_identita() -> None:
    """Chiede a Tor un altro nodo d'uscita. Tor ne concede uno ogni ~10 s."""
    global _ultima_identita
    if _stato['fase'] != 'pronto':
        return
    attesa = 10 - (time.monotonic() - _ultima_identita)
    if attesa > 0:
        time.sleep(attesa)
    try:
        with open(os.path.join(DATI, 'control_auth_cookie'), 'rb') as f:
            biscotto = f.read().hex()
        with socket.create_connection(('127.0.0.1', _stato['controllo']), timeout=10) as s:
            s.sendall(f'AUTHENTICATE {biscotto}\r\nSIGNAL NEWNYM\r\nQUIT\r\n'.encode())
            risposta = s.recv(256)
        _annota('Nuova identita\': ' + ' '.join(risposta.decode(errors='replace').split()[:2]))
    except OSError as e:
        _annota(f'Nuova identita\' non ottenuta: {e}')
    _ultima_identita = time.monotonic()


def ferma() -> None:
    if _processo and _processo.poll() is None:
        _processo.terminate()
