"""Ollama: il programma che fa girare i modelli su questo computer.

Cosa c'e' qui
    Solo le tre domande che gli si fanno prima di cominciare: sei acceso? quali
    modelli hai gia' scaricato? hai questo qui?

    Il lavoro vero, cioe' mandargli un testo e farsi rispondere, non passa di
    qui: lo fanno i moduli che riassumono e traducono, ciascuno con le sue
    istruzioni.

Perche' "sei acceso?" e' una domanda che vale la pena fare
    Perche' Ollama e' un programma a parte, che va installato e avviato da chi
    usa il computer. Senza questo controllo, il primo segnale che non c'e'
    sarebbe un errore di rete in mezzo a una trascrizione gia' cominciata, dopo
    minuti di lavoro: incomprensibile, e per giunta al momento peggiore.

Perche' "quali hai gia'" e "hai questo" sono separate
    Perche' chiedere l'elenco costa una domanda a Ollama, e nei menu la
    verifica va fatta su una decina di modelli di fila. Si chiede l'elenco una
    volta e poi ci si cerca dentro, invece di bussare dieci volte.

    L'elenco vale None, e non la lista vuota, quando Ollama non risponde: sono
    due cose diverse. "Nessun modello scaricato" e "non so niente perche' non
    riesco a chiedere" portano a messaggi diversi.
"""
from __future__ import annotations

import json

from server.config import settings
from server.config.settings import OLLAMA_HOST


def _ollama_installed_models(timeout: float = 3) -> set[str] | None:
    """Nomi dei modelli GIÀ scaricati in Ollama (da /api/tags).

    None se Ollama non è raggiungibile (spento/non installato): chi chiama può
    così distinguere «nessun modello» da «nessuna informazione»."""
    import urllib.request
    try:
        with urllib.request.urlopen(OLLAMA_HOST + "/api/tags", timeout=timeout) as r:
            tags = json.loads(r.read().decode("utf-8"))
        return {m.get("name", "") for m in tags.get("models", [])}
    except Exception:
        return None

def _ollama_has_model(name: str, installed: set[str]) -> bool:
    """True se 'name' risulta scaricato. Con il tag esplicito (qwen2.5vl:3b) il
    confronto è esatto; senza tag (llama3.2-vision) basta lo stesso nome base
    (llama3.2-vision:latest conta)."""
    if ":" in name:
        return name in installed or name + ":latest" in installed
    return any(n.split(":")[0] == name for n in installed)

def _check_ollama() -> None:
    """Ollama e' acceso? Se no, si ferma spiegando cosa fare.

    Perche' si controlla prima invece di scoprirlo dopo
        Ollama e' un programma a parte, che va installato e avviato da chi usa
        il computer. Senza questo controllo il primo segnale che manca sarebbe
        un errore di rete in mezzo a un riassunto gia' cominciato, dopo minuti
        di lavoro: incomprensibile, e al momento peggiore.

    Perche' il messaggio d'errore e' lungo
        Perche' chi lo legge, quasi sempre, non sa nemmeno cos'e' Ollama: ha
        solo scelto «in locale» in un menu. Un messaggio tipo «connessione
        rifiutata» a quella persona non dice niente di utile. Qui invece c'e'
        l'indirizzo dove si e' provato, il sito da cui scaricarlo e il comando
        per prendersi un modello.
    """
    import urllib.request
    try:
        with urllib.request.urlopen(OLLAMA_HOST + "/api/tags", timeout=5) as r:
            r.read()
    except Exception:
        raise RuntimeError(
            f"Ollama non raggiungibile su {OLLAMA_HOST}. Per il riassunto in locale "
            "installa Ollama (https://ollama.com), avvialo e scarica un modello, "
            f"es:  ollama pull {settings.OLLAMA_MODEL}")
