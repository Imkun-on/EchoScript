"""Avvisare chi si e' allontanato che il lavoro e' finito (o si e' fermato).

Il problema
    Un video lungo dura mezz'ora, e nessuno la passa a guardare una barra. Si
    va a fare altro, e il programma finisce in silenzio dietro le altre
    finestre: ci si accorge che era pronto venti minuti dopo, o ci si accorge
    troppo tardi che si era fermato al terzo minuto per i crediti.

Cosa si fa
    Tre cose insieme, solo se la finestra del programma NON e' quella in primo
    piano (chi la sta guardando vede gia' tutto):

    - una notifica di Windows, quella che compare in basso a destra;
    - un suono, diverso se e' andata bene o se qualcosa si e' fermato;
    - l'icona nella barra delle applicazioni che lampeggia finche' non la si
      apre.

    Ognuna e' un tentativo: se una non riesce, le altre restano. Nessuna di
    queste puo' far cadere il programma, e fuori da Windows non fanno niente.

Da chi sembra arrivare la notifica
    Windows attribuisce le notifiche a un «AppUserModelID» registrato. Il
    programma installato ne ha uno suo (lo scrive l'installatore sul
    collegamento del menu Start), e la notifica arriva col nome EchoScript.
    Lanciando i sorgenti quel collegamento non c'e': la notifica si fa
    prestare l'identita' di PowerShell, che su ogni Windows e' registrata.
"""
from __future__ import annotations

import base64
import os
import subprocess
import sys
import threading

# L'identita' con cui il programma installato si presenta a Windows. Deve
# essere la stessa scritta dall'installatore sul collegamento del menu Start
# (installer/EchoScript.iss) e quella che il processo dichiara all'avvio
# (EchoScript.py): se le tre non coincidono, Windows non sa di chi e' la
# notifica e non la mostra.
APP_ID = "EchoScript.App"
_APP_ID_POWERSHELL = r"{1AC14E77-02E7-4E5D-B744-2EB1AE5198B7}\WindowsPowerShell\v1.0\powershell.exe"

_SCRIPT = r"""
$ErrorActionPreference = 'Stop'
[Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] > $null
$xml = [Windows.UI.Notifications.ToastNotificationManager]::GetTemplateContent([Windows.UI.Notifications.ToastTemplateType]::ToastText02)
$t = $xml.GetElementsByTagName('text')
$t.Item(0).AppendChild($xml.CreateTextNode($env:ECHO_TITOLO)) > $null
$t.Item(1).AppendChild($xml.CreateTextNode($env:ECHO_TESTO)) > $null
$toast = [Windows.UI.Notifications.ToastNotification]::new($xml)
[Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier($env:ECHO_APPID).Show($toast)
"""


def dichiara_identita() -> None:
    """Dice a Windows che questo processo e' EchoScript, e non python.exe.

    Va chiamata all'avvio, prima di aprire la finestra. Serve alla notifica,
    e anche a raggruppare la finestra sotto l'icona giusta nella barra.
    """
    if os.name != "nt":
        return
    try:
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(APP_ID)
    except Exception:
        pass


def _finestra_programma():
    """L'handle della finestra principale, cercata per titolo. 0 se non c'e'."""
    import ctypes
    return ctypes.windll.user32.FindWindowW(None, "EchoScript")


def _in_primo_piano(hwnd) -> bool:
    """True se chi usa il programma lo sta gia' guardando."""
    import ctypes
    return bool(hwnd) and ctypes.windll.user32.GetForegroundWindow() == hwnd


def _lampeggia(hwnd) -> None:
    """Fa lampeggiare l'icona nella barra finche' non si apre la finestra."""
    import ctypes
    from ctypes import wintypes

    class FLASHWINFO(ctypes.Structure):
        _fields_ = [("cbSize", wintypes.UINT), ("hwnd", wintypes.HWND),
                    ("dwFlags", wintypes.DWORD), ("uCount", wintypes.UINT),
                    ("dwTimeout", wintypes.DWORD)]

    FLASHW_ALL, FLASHW_TIMERNOFG = 0x3, 0xC
    info = FLASHWINFO(ctypes.sizeof(FLASHWINFO), hwnd, FLASHW_ALL | FLASHW_TIMERNOFG, 0, 0)
    ctypes.windll.user32.FlashWindowEx(ctypes.byref(info))


def _toast(titolo: str, testo: str) -> None:
    """La notifica vera, passando da PowerShell per non aggiungere librerie."""
    app_id = APP_ID if getattr(sys, "frozen", False) else _APP_ID_POWERSHELL
    ambiente = dict(os.environ, ECHO_TITOLO=titolo, ECHO_TESTO=testo, ECHO_APPID=app_id)
    codificato = base64.b64encode(_SCRIPT.encode("utf-16-le")).decode("ascii")
    subprocess.run(
        ["powershell", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
         "-EncodedCommand", codificato],
        env=ambiente, capture_output=True, timeout=20,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))


def avvisa(titolo: str, testo: str, andata_bene: bool = True) -> None:
    """Avvisa che un lavoro e' finito, se la finestra non e' in primo piano.

    Torna subito: il lavoro vero (PowerShell ci mette un secondo ad avviarsi)
    gira in un thread a parte, cosi' chi chiama non aspetta niente.
    """
    if os.name != "nt":
        return

    def _fai():
        """Suono, lampeggio e notifica: ognuno per conto suo."""
        try:
            hwnd = _finestra_programma()
            if _in_primo_piano(hwnd):
                return
        except Exception:
            hwnd = 0
        try:
            import winsound
            winsound.MessageBeep(winsound.MB_ICONASTERISK if andata_bene
                                 else winsound.MB_ICONEXCLAMATION)
        except Exception:
            pass
        if hwnd:
            try:
                _lampeggia(hwnd)
            except Exception:
                pass
        try:
            _toast(titolo, testo)
        except Exception:
            pass

    threading.Thread(target=_fai, daemon=True).start()
