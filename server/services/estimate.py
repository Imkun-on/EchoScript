"""Quanto costera' e quanto ci vorra', detto prima di cominciare.

A cosa serve davvero
    A non far cominciare alla cieca. Un video di tre ore su Groq costa dei
    crediti e su questo computer sono ore di ventola: sono due informazioni
    che cambiano la decisione, e arrivano quando c'e' ancora tempo per
    prenderla.

Come si fa a stimare il tempo in locale
    Con un numero misurato, non calcolato: quante volte piu' lento del tempo
    reale macina un modello su un processore normale. Non e' preciso, e non
    puo' esserlo, perche' dipende dal processore, dal modello scelto e da cosa
    altro sta girando. E' un ordine di grandezza, ed e' abbastanza: serve a
    distinguere «dieci minuti» da «tutto il pomeriggio».

Perche' il costo di Groq invece e' quasi esatto
    Perche' si paga a ore di audio, e le ore di audio si sanno gia': le ha
    lette il modulo dei metadati prima ancora di scaricare qualcosa.
"""
from __future__ import annotations

from server.config import settings
from server.transcription.local_whisper import _resolve_device
from server.utils.text import _format_duration


# === PRE-RUN ESTIMATE (cost for Groq, time for local) ========================
# Approximate Groq audio pricing ($ per hour of audio) and local processing-speed
# factors (processing time / audio time), used ONLY for the pre-run estimate so
# the user knows what to expect before committing. Figures are indicative.
GROQ_PRICE_PER_HOUR = {
    "whisper-large-v3-turbo": 0.04,
    "whisper-large-v3": 0.111,
    "distil-whisper-large-v3-en": 0.02,
}
_LOCAL_REALTIME_CPU = {
    "base": 0.10, "small": 0.18, "medium": 0.45,
    "large-v3": 0.90, "large-v3-turbo": 0.22,
}
def estimate_job(meta: dict, backend: str, model: str | None = None) -> dict:
    """Rough pre-run estimate for ONE source, BEFORE downloading/transcribing.

    Groq: estimated $ cost from the audio duration and the model's per-hour price.
    Local: estimated processing TIME from a per-model realtime factor, divided by
    ~8 on GPU. Returns a dict with a ready-to-show Italian 'detail' string."""
    duration = meta.get("duration") or 0
    hours = duration / 3600
    if backend == "groq":
        # 'model' (se passato) è il modello Groq scelto dall'utente; altrimenti il
        # default corrente. Il prezzo/ora dipende dal modello selezionato.
        gm = model or settings.GROQ_MODEL
        price = GROQ_PRICE_PER_HOUR.get(gm, 0.04)
        cost = hours * price
        return {"backend": "groq", "duration": duration, "cost_usd": cost,
                "model": gm,
                "detail": (f"costo stimato ~${cost:.3f} (Groq {gm}, "
                           f"{_format_duration(duration)} di audio)")}
    device, _ = _resolve_device()
    rt = _LOCAL_REALTIME_CPU.get(model or "small", 0.2)
    if device == "cuda":
        rt /= 8
    secs = duration * rt
    dev = "GPU" if device == "cuda" else "CPU"
    return {"backend": "local", "duration": duration, "device": device, "seconds": secs,
            "detail": (f"tempo stimato ~{_format_duration(secs)} su {dev} "
                       f"(modello {model or 'small'}); nessun costo (offline)")}
