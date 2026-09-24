"""Lo storico: che cosa e' stato trascritto, come, quando, e se e' finito.

Che cosa tiene
    Una riga per ogni video o file lavorato: il link, il canale, il titolo, la
    durata, i crediti Groq spesi, la playlist da cui veniva (o nessuna), se il
    lavoro e' completo o a meta', con quale motore e quando. E' quello che
    mostra la sezione «Storico».

I crediti
    Sono quello che Groq misura davvero: i secondi di audio trascritti e i
    token del riassunto. Riprendendo un lavoro si sommano a quelli della volta
    prima, perche' la riga racconta quanto e' costato quel video in tutto. In
    locale sono zero: non si paga niente. Per i lavori ricostruiti dai file
    salvati non si sanno, e restano vuoti invece di inventarli.

Una riga per video e per motore, non una per tentativo
    Riprendere un lavoro rimasto a meta' non aggiunge una riga: aggiorna quella
    che c'era, che passa da «a meta'» a «completo» con la data nuova. Un
    elenco che mostrasse ogni tentativo direbbe tre volte lo stesso video,
    una volta a meta' e due complete, e costringerebbe a indovinare quale
    delle tre e' vera. Lo stesso video trascritto una volta in locale e una in
    nuvola sono invece due righe, perche' sono due lavori diversi.

I lavori fatti prima che lo storico esistesse
    Alla prima apertura, se il file non c'e', lo si ricostruisce guardando le
    trascrizioni gia' salvate nella cartella dei risultati: nel .json di ognuna
    c'e' il titolo, il link, il canale e il motore. La data e' quella del file.

Dove sta
    In ``storico.json`` accanto agli altri dati del programma. Lo scrivono i
    thread di lavoro, anche due insieme (le postazioni sono due): un lucchetto
    evita che una scrittura cancelli l'altra.
"""
from __future__ import annotations

import hashlib
import json
import os
import threading
from datetime import datetime

from server.config import paths
from server.state import jobs
from server.utils.text import _lp

_FILE = paths.dati("storico.json")
_LUCCHETTO = threading.Lock()

COMPLETO = "completo"
A_META = "a metà"


def _id(url: str, modo: str) -> str:
    """La chiave di una riga: lo stesso video con lo stesso motore."""
    return hashlib.sha1(f"{url}|{modo}".encode("utf-8")).hexdigest()[:16]


def _leggi() -> list[dict] | None:
    """Il contenuto del file, o None se il file non c'e' (ancora)."""
    if not os.path.isfile(_FILE):
        return None
    try:
        with open(_FILE, encoding="utf-8") as fh:
            dati = json.load(fh)
        return dati if isinstance(dati, list) else []
    except (OSError, ValueError):
        return []


def _scrivi(voci: list[dict]) -> None:
    """Riscrive il file intero. Un errore di scrittura non ferma nessun lavoro."""
    try:
        os.makedirs(os.path.dirname(_FILE), exist_ok=True)
        tmp = _FILE + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(voci, fh, ensure_ascii=False, indent=2)
        os.replace(tmp, _FILE)
    except OSError:
        pass


def modo_da_etichetta(etichetta: str) -> str:
    """«Locale», «Cloud» o «Cloud + Locale», dall'etichetta del motore."""
    e = (etichetta or "").lower()
    if "groq" in e and "locale" in e:
        return "Cloud + Locale"
    return "Cloud" if "groq" in e else "Locale"


def registra(meta: dict, stato: str, modo: str, cartella: str = "",
             playlist: str = "", documento: str = "",
             consumo: dict | None = None, postazione: str = "") -> None:
    """Aggiunge o aggiorna la riga di un video.

    'meta' sono i metadati del video (servono titolo, canale e link, oppure il
    percorso per un file locale). 'playlist' e' il nome della playlist da cui
    viene, vuoto per un video singolo. 'documento' e' il .md da aprire con
    «Leggi»: il riassunto se c'e', altrimenti la trascrizione. 'consumo' e'
    quello che questo lavoro ha speso su Groq ({'audio_s', 'token'}).
    """
    if not meta:
        return
    url = meta.get("webpage_url") or meta.get("source_path") or ""
    voce = {
        # Una riga per video e per postazione: finire in locale un lavoro
        # cominciato in «Cloud» aggiorna la stessa riga, con il modo nuovo.
        "id": _id(url, postazione or modo),
        "url": url,
        "titolo": meta.get("title") or "?",
        "canale": meta.get("channel") or "",
        "locale": meta.get("source") == "local",
        "playlist": playlist or "",
        "stato": stato,
        "modo": modo,
        "data": datetime.now().isoformat(timespec="seconds"),
        "cartella": cartella or "",
        "documento": documento or "",
        "durata": meta.get("duration"),
        "audio_s": float((consumo or {}).get("audio_s") or 0.0),
        "token": int((consumo or {}).get("token") or 0),
    }
    with _LUCCHETTO:
        voci = _leggi() or []
        prima = next((v for v in voci if v.get("id") == voce["id"]), None)
        if prima:
            # Una ripresa: il costo del video e' quello di prima piu' questo.
            voce["audio_s"] += float(prima.get("audio_s") or 0.0)
            voce["token"] += int(prima.get("token") or 0)
            voce["durata"] = voce["durata"] or prima.get("durata")
        voci = [v for v in voci if v.get("id") != voce["id"]]
        voci.append(voce)
        _scrivi(voci)


def documento_da_leggere(cartella: str) -> str:
    """Il .md piu' utile da leggere in una cartella di video.

    Prima il riassunto, poi la traduzione, poi la trascrizione: e' l'ordine in
    cui una persona li vorrebbe aprire.
    """
    if not cartella:
        return ""
    for sotto in (jobs.SUMMARY_SUBDIR, jobs.TRANSL_SUBDIR, jobs.TRANS_SUBDIR,
                  jobs.NOMI_VECCHI[jobs.SUMMARY_SUBDIR],
                  jobs.NOMI_VECCHI[jobs.TRANSL_SUBDIR],
                  jobs.NOMI_VECCHI[jobs.TRANS_SUBDIR]):
        dove = os.path.join(cartella, sotto)
        try:
            nomi = sorted(n for n in os.listdir(_lp(dove)) if n.lower().endswith(".md"))
        except OSError:
            continue
        if nomi:
            return os.path.join(dove, nomi[0])
    return ""


def _ricostruisci(radice: str) -> list[dict]:
    """Lo storico dei lavori fatti prima che esistesse, dalle trascrizioni salvate.

    Una cartella di video sta o direttamente nella radice (video singolo) o
    dentro la cartella di una playlist: si riconosce dalla sottocartella delle
    trascrizioni, e il suo genitore dice se c'era una playlist in mezzo.
    """
    voci: list[dict] = []
    if not radice or not os.path.isdir(radice):
        return voci
    nomi_trascrizioni = {jobs.TRANS_SUBDIR, jobs.NOMI_VECCHI[jobs.TRANS_SUBDIR]}
    for cartella, sottocartelle, _file in os.walk(radice):
        if os.path.basename(cartella) not in nomi_trascrizioni:
            continue
        sottocartelle[:] = []
        video_dir = os.path.dirname(cartella)
        genitore = os.path.dirname(video_dir)
        playlist = "" if os.path.normcase(genitore) == os.path.normcase(radice) \
            else os.path.basename(genitore)
        for nome in os.listdir(cartella):
            if not nome.lower().endswith(".json"):
                continue
            percorso = os.path.join(cartella, nome)
            try:
                with open(percorso, encoding="utf-8") as fh:
                    d = json.load(fh)
            except (OSError, ValueError):
                continue
            if not isinstance(d, dict) or "segments" not in d:
                continue
            meta = {"title": d.get("title") or os.path.splitext(nome)[0],
                    "webpage_url": d.get("url", ""), "channel": d.get("channel") or "",
                    "source": d.get("source", "youtube")}
            modo = modo_da_etichetta(d.get("engine", ""))
            stato = A_META if jobs.has_resumable_state(meta) else COMPLETO
            voci.append({
                "id": _id(meta["webpage_url"], "locale" if modo == "Locale" else "cloud"),
                "url": meta["webpage_url"],
                "titolo": meta["title"], "canale": meta["channel"],
                "locale": meta["source"] == "local", "playlist": playlist,
                "stato": stato, "modo": modo,
                "data": datetime.fromtimestamp(os.path.getmtime(percorso))
                .isoformat(timespec="seconds"),
                "cartella": video_dir, "documento": documento_da_leggere(video_dir),
                "durata": d.get("duration_seconds"),
                # Quanto era costato non e' scritto da nessuna parte: si lascia
                # vuoto, e la tabella lo mostra come tale.
                "audio_s": None, "token": None,
            })
    return voci


def elenco(radice: str) -> list[dict]:
    """Tutte le righe, dalla piu' recente. Alla prima volta le ricostruisce."""
    with _LUCCHETTO:
        voci = _leggi()
        if voci is None:
            voci = _ricostruisci(radice)
            _scrivi(voci)
    return sorted(voci, key=lambda v: v.get("data", ""), reverse=True)


def trova(voce_id: str) -> dict | None:
    """La riga con questo identificativo, se c'e'."""
    with _LUCCHETTO:
        for v in _leggi() or []:
            if v.get("id") == voce_id:
                return v
    return None


def togli(voce_id: str) -> None:
    """Toglie una riga dallo storico. I file sul disco restano dove sono."""
    with _LUCCHETTO:
        voci = [v for v in (_leggi() or []) if v.get("id") != voce_id]
        _scrivi(voci)
