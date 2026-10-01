"""I disegni della chimica che non sono una molecola sola.

Che cosa c'e' qui
    Le molecole hanno il loro file (molecola.py). Qui stanno gli altri disegni
    che un libro di chimica mette accanto al testo, uno per tipo di blocco:

        ```reazione      uno schema di reazione, o un passo di un meccanismo
                         con le frecce degli elettroni (lo disegna reazione.py)
        ```orbitali      la configurazione elettronica a caselle e frecce, e
                         la forma degli orbitali
        ```titolazione   la curva del pH durante una titolazione
        ```energia       il profilo di energia di una reazione
        ```reticolo      la cella di un reticolo cristallino
        ```tavola        la tavola periodica, con qualcosa in evidenza

Il modello dice che cosa, i conti li fa il programma
    E' la regola di tutti questi blocchi, ed e' il motivo per cui si possono
    mostrare senza paura. Il modello scrive poche righe «chiave: valore» con
    quello che ha trovato nel testo: quale elemento, quale acido e a che
    concentrazione, quale reticolo. Tutto il resto esce da qui: come si
    riempiono gli orbitali, quanto vale il pH a ogni goccia, dove stanno gli
    atomi in una cella a facce centrate, in che casella sta il ferro. Sono
    cose che si calcolano, e un modello che le scrivesse a memoria ogni tanto
    le sbaglierebbe.

    Come per il piano e per le molecole, una riga che non si capisce o un
    dato che non torna toglie tutto il blocco: meglio nessun disegno che uno
    sbagliato.

Come si usa da fuori
    ``leggi(tipo, testo)`` da' la descrizione controllata o None;
    ``svg(tipo, descrizione)`` il disegno; ``in_testo(tipo, testo)`` le righe
    per il Word e il file di testo, che non disegnano.
"""
from __future__ import annotations

import hashlib
import html
import math
import re
import unicodedata

from server.export.piano import TINTE, _numero_bello, _passo

# I tipi di blocco di questo file, nell'ordine in cui si spiegano al modello.
BLOCCHI = ("reazione", "orbitali", "titolazione", "energia", "reticolo", "tavola")

_CARATTERE = 'font-family="Segoe UI, Arial, sans-serif"'
_APICI = str.maketrans("0123456789+-−", "⁰¹²³⁴⁵⁶⁷⁸⁹⁺⁻⁻")
_PEDICI = str.maketrans("0123456789", "₀₁₂₃₄₅₆₇₈₉")


# ── Gli attrezzi comuni ─────────────────────────────────────────────────────

def _senza_accenti(testo: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", testo) if not unicodedata.combining(c))


def _righe(testo: str, chiavi: tuple[str, ...]) -> list[tuple[str, str]] | None:
    """Le righe «chiave: valore» del blocco, o None se una non si capisce."""
    fuori = []
    for riga in (testo or "").splitlines():
        riga = riga.strip()
        if not riga:
            continue
        m = re.match(r"^([^:]{1,24}?)\s*:\s*(.+)$", riga)
        if not m:
            return None
        chiave = _senza_accenti(m.group(1)).strip().lower()
        if chiave not in chiavi:
            return None
        fuori.append((chiave, m.group(2).strip()))
    return fuori


def _numero(testo: str) -> float:
    """Un numero scritto come capita: «0,1», «1.8e-5», «1,8 × 10^-5», «10^-14»."""
    t = testo.strip().replace("−", "-").replace(",", ".").replace(" ", "")
    t = re.sub(r"[×·*x]10\^?\{?(-?\d+)\}?", r"e\1", t)
    m = re.fullmatch(r"10\^\{?(-?\d+)\}?", t)
    if m:
        return 10.0 ** int(m.group(1))
    return float(t)


def _formula(testo: str) -> str:
    """Una formula scritta in riga, coi pedici: H2SO4 diventa H₂SO₄."""
    return re.sub(r"(?<=[A-Za-z\)\]])(\d+)", lambda m: m.group(1).translate(_PEDICI), testo)


def _cornice(titolo: str, disegno: str, legenda=(), note=()) -> str:
    """Il disegno nella stessa cornice del piano: titolo, legenda e note in HTML."""
    fuori = ['<div class="piano">']
    if titolo:
        fuori.append(f'<div class="piano-titolo">{html.escape(titolo)}</div>')
    fuori.append(disegno)
    if legenda:
        fuori.append('<div class="piano-legenda">'
                     + "".join(f"<span>{voce}</span>" for voce in legenda) + "</div>")
    for nota in note:
        fuori.append(f'<div class="piano-nota">{html.escape(nota)}</div>')
    fuori.append("</div>")
    return "".join(fuori)


def _tassello(colore: str, testo: str, tondo: bool = False) -> str:
    """Una voce di legenda: il quadratino (o il pallino) del colore, e il suo nome."""
    return (f'<i style="background:{colore};width:12px;height:12px;'
            f'border-radius:{"50%" if tondo else "3px"};border:1px solid #9ca3af"></i>'
            f'{html.escape(testo)}')


def _uid(*cose) -> str:
    """Un nome proprio per le sfumature e le punte di freccia di QUESTO disegno."""
    return "c" + hashlib.sha1(repr(cose).encode("utf-8")).hexdigest()[:8]


def _apri_svg(W: float, H: float, dimensione: float = 11) -> str:
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W:.0f} {H:.0f}" '
            f'width="{W:.0f}" height="{H:.0f}" {_CARATTERE} font-size="{dimensione}">')


def _punta(uid: str, colore: str = "#333") -> str:
    return (f'<marker id="{uid}" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" '
            f'markerHeight="7" orient="auto-start-reverse">'
            f'<path d="M0,0 L10,5 L0,10 z" fill="{colore}"/></marker>')


# ═══════════════════════════════════════════════════════════════════════════
#  LA TAVOLA PERIODICA
# ═══════════════════════════════════════════════════════════════════════════

SIMBOLI = ("H He Li Be B C N O F Ne Na Mg Al Si P S Cl Ar K Ca Sc Ti V Cr Mn Fe Co Ni Cu Zn "
           "Ga Ge As Se Br Kr Rb Sr Y Zr Nb Mo Tc Ru Rh Pd Ag Cd In Sn Sb Te I Xe Cs Ba La Ce "
           "Pr Nd Pm Sm Eu Gd Tb Dy Ho Er Tm Yb Lu Hf Ta W Re Os Ir Pt Au Hg Tl Pb Bi Po At Rn "
           "Fr Ra Ac Th Pa U Np Pu Am Cm Bk Cf Es Fm Md No Lr Rf Db Sg Bh Hs Mt Ds Rg Cn Nh Fl "
           "Mc Lv Ts Og").split()
NUMERO = {simbolo: z for z, simbolo in enumerate(SIMBOLI, start=1)}

_PERIODI = ((3, 10), (11, 18), (19, 36), (37, 54), (55, 86), (87, 118))


def posto(z: int) -> tuple[int, int]:
    """(riga, colonna) dell'elemento sulla tavola. Lantanidi e attinidi stanno
    nelle righe 9 e 10, staccate sotto, come su ogni tavola appesa in aula."""
    if z == 1:
        return 1, 1
    if z == 2:
        return 1, 18
    for periodo, (inizio, fine) in enumerate(_PERIODI, start=2):
        if inizio <= z <= fine:
            k = z - inizio
            if periodo in (2, 3):
                return periodo, k + 1 if k < 2 else k + 11
            if periodo in (4, 5) or k < 2:
                return periodo, k + 1
            if k < 17:
                return periodo + 3, k + 1
            return periodo, k - 13
    raise ValueError(z)


def periodo(z: int) -> int:
    riga = posto(z)[0]
    return riga - 3 if riga > 7 else riga


def blocco(z: int) -> str:
    riga, colonna = posto(z)
    if riga > 7:
        return "f"
    if colonna <= 2 or z == 2:
        return "s"
    return "d" if colonna <= 12 else "p"


_SEMIMETALLI = {"B", "Si", "Ge", "As", "Sb", "Te"}
_NON_METALLI = {"H", "C", "N", "O", "P", "S", "Se"}


def famiglia(z: int) -> str:
    riga, colonna = posto(z)
    simbolo = SIMBOLI[z - 1]
    if riga == 9:
        return "lantanidi"
    if riga == 10:
        return "attinidi"
    if colonna == 18:
        return "gas nobili"
    if simbolo in _NON_METALLI:
        return "non metalli"
    if simbolo in _SEMIMETALLI:
        return "semimetalli"
    if colonna == 1:
        return "metalli alcalini"
    if colonna == 2:
        return "metalli alcalino-terrosi"
    if colonna <= 12:
        return "metalli di transizione"
    if colonna == 17:
        return "alogeni"
    return "altri metalli"


_COLORI_BLOCCO = {"s": "#fca5a5", "p": "#fcd34d", "d": "#93c5fd", "f": "#86efac"}
_COLORI_FAMIGLIA = {
    "metalli alcalini": "#fca5a5", "metalli alcalino-terrosi": "#fdba74",
    "metalli di transizione": "#93c5fd", "altri metalli": "#a5b4fc",
    "semimetalli": "#5eead4", "non metalli": "#fde047", "alogeni": "#bef264",
    "gas nobili": "#f0abfc", "lantanidi": "#86efac", "attinidi": "#d8b4fe",
}

# Le proprieta' periodiche, e da che parte crescono lungo un periodo e lungo
# un gruppo. Sono le sole due risposte possibili, e non si lasciano al modello.
_VERSO_ALTO_DESTRA = ("elettronegativita", "energia di ionizzazione", "affinita elettronica",
                      "carattere non metallico")
_VERSO_BASSO_SINISTRA = ("raggio atomico", "carattere metallico")


def _simboli(valore: str) -> list[str] | None:
    """Gli elementi di un elenco «Na, Cl, Fe», o None se uno non esiste."""
    fuori = []
    for pezzo in re.split(r"[,;\s]+", valore.strip()):
        if not pezzo:
            continue
        if pezzo not in NUMERO:
            return None
        fuori.append(pezzo)
    return fuori or None


def _leggi_tavola(testo: str) -> dict | None:
    righe = _righe(testo, ("titolo", "colora", "evidenzia", "gruppo", "periodo", "blocco",
                           "tendenza", "nota"))
    if righe is None:
        return None
    t = {"titolo": "", "colora": "blocchi", "evidenziati": [], "gruppi": [], "periodi": [],
         "blocchi": [], "tendenza": "", "etichette": [], "note": []}
    for chiave, valore in righe:
        etichetta = ""
        if chiave not in ("titolo", "nota"):
            valore, _, etichetta = (p.strip() for p in valore.partition("|"))
        if chiave == "titolo":
            t["titolo"] = valore
        elif chiave == "nota":
            t["note"].append(valore)
        elif chiave == "colora":
            scelta = _senza_accenti(valore).lower()
            scelta = {"blocco": "blocchi", "famiglia": "famiglie", "no": "niente"}.get(scelta, scelta)
            if scelta not in ("blocchi", "famiglie", "niente"):
                return None
            t["colora"] = scelta
        elif chiave == "evidenzia":
            simboli = _simboli(valore)
            if not simboli:
                return None
            t["evidenziati"] += simboli
        elif chiave in ("gruppo", "periodo"):
            try:
                numeri = [int(p) for p in re.split(r"[,;\s]+", valore) if p]
            except ValueError:
                return None
            tetto = 18 if chiave == "gruppo" else 7
            if not numeri or any(not 1 <= n <= tetto for n in numeri):
                return None
            t["gruppi" if chiave == "gruppo" else "periodi"] += numeri
        elif chiave == "blocco":
            lettere = [p for p in re.split(r"[,;\s]+", valore.lower()) if p]
            if not lettere or any(b not in "spdf" or len(b) != 1 for b in lettere):
                return None
            t["blocchi"] += lettere
        elif chiave == "tendenza":
            proprieta = _senza_accenti(valore).lower()
            if proprieta not in _VERSO_ALTO_DESTRA + _VERSO_BASSO_SINISTRA:
                return None
            t["tendenza"] = valore.lower()
        if etichetta:
            t["etichette"].append(etichetta)
    scelti = set()
    for z in range(1, 119):
        riga, colonna = posto(z)
        if (SIMBOLI[z - 1] in t["evidenziati"] or (riga <= 7 and colonna in t["gruppi"])
                or periodo(z) in t["periodi"] or blocco(z) in t["blocchi"]):
            scelti.add(z)
    t["scelti"] = scelti
    return t


def _svg_tavola(t: dict) -> str:
    lato = 30
    sinistra = 44 if t["tendenza"] else 22
    alto = 40 if t["tendenza"] else 18
    W = sinistra + 18 * lato + 8
    H = alto + 7 * lato + 12 + 2 * lato + 8
    uid = _uid("tavola", t["titolo"], sorted(t["scelti"]), t["tendenza"], t["colora"])

    def angolo(riga: int, colonna: int) -> tuple[float, float]:
        y = alto + (riga - 1) * lato if riga <= 7 else alto + 7 * lato + 12 + (riga - 9) * lato
        return sinistra + (colonna - 1) * lato, y

    parti = [_apri_svg(W, H), f"<defs>{_punta(uid + 'f', '#b45309')}</defs>"]
    for g in range(1, 19):
        x, _ = angolo(1, g)
        parti.append(f'<text x="{x + lato / 2:.1f}" y="{alto - 5}" text-anchor="middle" '
                     f'font-size="8.5" fill="#6b7280">{g}</text>')
    for p in range(1, 8):
        _, y = angolo(p, 1)
        parti.append(f'<text x="{sinistra - 5}" y="{y + lato / 2 + 3:.1f}" text-anchor="end" '
                     f'font-size="8.5" fill="#6b7280">{p}</text>')

    presenti: dict[str, str] = {}
    sopra = []
    for z in range(1, 119):
        riga, colonna = posto(z)
        x, y = angolo(riga, colonna)
        if t["colora"] == "blocchi":
            nome, colore = "blocco " + blocco(z), _COLORI_BLOCCO[blocco(z)]
        elif t["colora"] == "famiglie":
            nome, colore = famiglia(z), _COLORI_FAMIGLIA[famiglia(z)]
        else:
            nome, colore = "", "#f3f4f6"
        if nome:
            presenti.setdefault(nome, colore)
        spento = bool(t["scelti"]) and z not in t["scelti"]
        parti.append(f'<rect x="{x + 0.5:.1f}" y="{y + 0.5:.1f}" width="{lato - 1}" '
                     f'height="{lato - 1}" rx="3" fill="{colore}" '
                     f'fill-opacity="{0.22 if spento else 1}" stroke="#fff"/>')
        inchiostro = "#9ca3af" if spento else "#111827"
        parti.append(f'<text x="{x + 3:.1f}" y="{y + 9:.1f}" font-size="6.5" '
                     f'fill="{inchiostro}">{z}</text>')
        parti.append(f'<text x="{x + lato / 2:.1f}" y="{y + 22:.1f}" text-anchor="middle" '
                     f'font-size="12" font-weight="600" fill="{inchiostro}">{SIMBOLI[z - 1]}</text>')
        if z in t["scelti"]:
            sopra.append(f'<rect x="{x + 1:.1f}" y="{y + 1:.1f}" width="{lato - 2}" '
                         f'height="{lato - 2}" rx="3" fill="none" stroke="#111827" '
                         f'stroke-width="1.8"/>')
    # Le due caselle vuote che rimandano alle righe staccate sotto.
    for riga, scritta in ((6, "57–71"), (7, "89–103")):
        x, y = angolo(riga, 3)
        parti.append(f'<text x="{x + lato / 2:.1f}" y="{y + lato / 2 + 3:.1f}" '
                     f'text-anchor="middle" font-size="7" fill="#6b7280">{scritta}</text>')
    parti += sopra

    if t["tendenza"]:
        cresce_a_destra = _senza_accenti(t["tendenza"]) in _VERSO_ALTO_DESTRA
        x0, x1 = sinistra + 4, sinistra + 18 * lato - 4
        y0, y1 = alto + 4, alto + 7 * lato - 4
        if not cresce_a_destra:
            x0, x1 = x1, x0
        else:
            y0, y1 = y1, y0
        parti.append(f'<line x1="{x0}" y1="14" x2="{x1}" y2="14" stroke="#b45309" '
                     f'stroke-width="1.6" marker-end="url(#{uid}f)"/>')
        parti.append(f'<line x1="14" y1="{y0}" x2="14" y2="{y1}" stroke="#b45309" '
                     f'stroke-width="1.6" marker-end="url(#{uid}f)"/>')
    parti.append("</svg>")

    legenda = [_tassello(colore, nome) for nome, colore in presenti.items()]
    if t["tendenza"]:
        legenda.append(f'<b style="color:#b45309">→</b> cresce: {html.escape(t["tendenza"])}')
    legenda += [html.escape(e) for e in t["etichette"]]
    return _cornice(t["titolo"] or "Tavola periodica", "".join(parti), legenda, t["note"])


def _testo_tavola(t: dict) -> list[str]:
    fuori = ["Tavola periodica" + (f": {t['titolo']}" if t["titolo"] else "")]
    if t["evidenziati"]:
        fuori.append("- In evidenza: " + ", ".join(t["evidenziati"]))
    if t["gruppi"]:
        fuori.append("- Gruppo " + ", ".join(str(g) for g in t["gruppi"]))
    if t["periodi"]:
        fuori.append("- Periodo " + ", ".join(str(p) for p in t["periodi"]))
    if t["blocchi"]:
        fuori.append("- Blocco " + ", ".join(t["blocchi"]))
    if t["tendenza"]:
        verso = ("da sinistra a destra e dal basso verso l'alto"
                 if _senza_accenti(t["tendenza"]) in _VERSO_ALTO_DESTRA
                 else "da destra a sinistra e dall'alto verso il basso")
        fuori.append(f"- {t['tendenza'][0].upper()}{t['tendenza'][1:]}: cresce {verso}")
    fuori += [f"- {e}" for e in t["etichette"]] + [f"- {n}" for n in t["note"]]
    return fuori


# ═══════════════════════════════════════════════════════════════════════════
#  GLI ORBITALI
# ═══════════════════════════════════════════════════════════════════════════

# L'ordine in cui si riempiono (regola della diagonale) e quanti elettroni
# tiene ogni tipo.
AUFBAU = ("1s", "2s", "2p", "3s", "3p", "4s", "3d", "4p", "5s", "4d", "5p", "6s", "4f",
          "5d", "6p", "7s", "5f", "6d", "7p")
CAPIENZA = {"s": 2, "p": 6, "d": 10, "f": 14}

# Gli elementi che non seguono la regola della diagonale: il cromo e il rame
# dei libri di scuola, e gli altri che si incontrano piu' avanti.
_ECCEZIONI = {
    24: {"4s": 1, "3d": 5}, 29: {"4s": 1, "3d": 10}, 41: {"5s": 1, "4d": 4},
    42: {"5s": 1, "4d": 5}, 44: {"5s": 1, "4d": 7}, 45: {"5s": 1, "4d": 8},
    46: {"5s": 0, "4d": 10}, 47: {"5s": 1, "4d": 10}, 57: {"4f": 0, "5d": 1},
    58: {"4f": 1, "5d": 1}, 64: {"4f": 7, "5d": 1}, 78: {"6s": 1, "5d": 9},
    79: {"6s": 1, "5d": 10}, 89: {"5f": 0, "6d": 1}, 90: {"5f": 0, "6d": 2},
    91: {"5f": 2, "6d": 1}, 92: {"5f": 3, "6d": 1}, 93: {"5f": 4, "6d": 1},
    96: {"5f": 7, "6d": 1},
}
_GAS_NOBILI = {"He": 2, "Ne": 10, "Ar": 18, "Kr": 36, "Xe": 54, "Rn": 86}


def configurazione(z: int, carica: int = 0) -> list[tuple[str, int]]:
    """La configurazione elettronica dell'elemento (o del suo ione), nello
    stato fondamentale: una lista di (orbitale, elettroni), in ordine di
    riempimento."""
    occupati = {o: 0 for o in AUFBAU}
    rimasti = z
    for o in AUFBAU:
        occupati[o] = min(rimasti, CAPIENZA[o[1]])
        rimasti -= occupati[o]
    occupati.update(_ECCEZIONI.get(z, {}))
    # Uno ione positivo perde gli elettroni del guscio piu' esterno (il 4s
    # prima del 3d: Fe³⁺ e' [Ar] 3d⁵); uno negativo riempie il primo posto libero.
    for _ in range(max(carica, 0)):
        pieni = [o for o in AUFBAU if occupati[o]]
        if not pieni:
            break
        occupati[max(pieni, key=lambda o: (int(o[0]), "spdf".index(o[1])))] -= 1
    for _ in range(max(-carica, 0)):
        for o in AUFBAU:
            if occupati[o] < CAPIENZA[o[1]]:
                occupati[o] += 1
                break
    return [(o, n) for o in AUFBAU if (n := occupati[o])]


def _configurazione_scritta(valore: str) -> list[tuple[str, int]] | None:
    """Una configurazione scritta nel testo: «1s2 2s2 2p4», «[Ne] 3s² 3p⁴»."""
    t = valore.translate(str.maketrans("⁰¹²³⁴⁵⁶⁷⁸⁹", "0123456789"))
    fuori: list[tuple[str, int]] = []
    m = re.match(r"\s*\[(He|Ne|Ar|Kr|Xe|Rn)\]", t)
    if m:
        fuori = configurazione(_GAS_NOBILI[m.group(1)])
        t = t[m.end():]
    # Scritta tutta attaccata («1s22s22p4») non si sa dove finisce un numero
    # e comincia l'altro: uno spazio davanti a ogni «cifra e lettera» lo dice.
    t = re.sub(r"(?<=\d)(?=\d[spdf])", " ", t)
    for pezzo in re.split(r"[\s,;·]+", t.strip()):
        m = re.fullmatch(r"(\d)([spdf])\^?\{?(\d{1,2})\}?", pezzo)
        if not m:
            return None
        livello, tipo, n = int(m.group(1)), m.group(2), int(m.group(3))
        nome = f"{livello}{tipo}"
        if (not 1 <= n <= CAPIENZA[tipo] or livello <= "spdf".index(tipo)
                or nome in (o for o, _ in fuori)):
            return None
        fuori.append((nome, n))
    return fuori or None


_FORME = ("s", "px", "py", "pz", "dxy", "dxz", "dyz", "dx2-y2", "dz2", "sp", "sp2", "sp3")


def _leggi_orbitali(testo: str) -> dict | None:
    righe = _righe(testo, ("titolo", "elemento", "configurazione", "forme", "forma", "nota"))
    if righe is None:
        return None
    o = {"titolo": "", "simbolo": "", "carica": 0, "configurazione": [], "forme": [], "note": []}
    scritta = None
    for chiave, valore in righe:
        if chiave == "titolo":
            o["titolo"] = valore
        elif chiave == "nota":
            o["note"].append(valore)
        elif chiave == "elemento":
            from server.export.molecola import NOMI
            per_nome = {nome: simbolo for simbolo, nome in NOMI.items()}
            m = re.match(r"^([A-Za-zà-ù]+)\s*\^?\{?(\d*)([+\-−]?)\}?$", valore.strip())
            if not m:
                return None
            simbolo = per_nome.get(m.group(1).lower(), m.group(1))
            if simbolo not in NUMERO:
                return None
            carica = int(m.group(2) or 1) if m.group(3) else 0
            if m.group(2) and not m.group(3):
                return None
            o["simbolo"], o["carica"] = simbolo, carica if m.group(3) == "+" else -carica
        elif chiave == "configurazione":
            scritta = _configurazione_scritta(valore)
            if scritta is None:
                return None
        else:
            for pezzo in re.split(r"[,;]+", valore):
                nome = pezzo.strip().lower().replace(" ", "").replace("²", "2").replace("³", "3")
                nome = nome.replace("_", "").replace("^", "")
                gruppo = {"p": ["px", "py", "pz"], "d": ["dxy", "dxz", "dyz", "dx2-y2", "dz2"]}.get(nome, [nome])
                if any(g not in _FORME for g in gruppo):
                    return None
                o["forme"] += [g for g in gruppo if g not in o["forme"]]
    if o["simbolo"]:
        elettroni = NUMERO[o["simbolo"]] - o["carica"]
        if elettroni < 1:
            return None
        # Se il testo scrive una configurazione (uno stato eccitato, per
        # esempio), vale la sua, purche' gli elettroni siano quelli giusti.
        if scritta is not None and sum(n for _, n in scritta) != elettroni:
            return None
        o["configurazione"] = scritta or configurazione(NUMERO[o["simbolo"]], o["carica"])
    elif scritta is not None:
        o["configurazione"] = scritta
    if len(o["forme"]) > 10 or not (o["configurazione"] or o["forme"]):
        return None
    return o


def _in_riga(conf: list[tuple[str, int]], breve: bool = True) -> str:
    """La configurazione scritta in riga: «[Ar] 4s² 3d⁶»."""
    nucleo, resto = _nocciolo(conf) if breve else ("", conf)
    pezzi = [f"[{nucleo}]"] if nucleo else []
    return " ".join(pezzi + [o + str(n).translate(_APICI) for o, n in resto])


def _nocciolo(conf: list[tuple[str, int]]) -> tuple[str, list[tuple[str, int]]]:
    """Il gas nobile che fa da nocciolo, e gli orbitali che restano fuori.

    Si abbrevia solo quando conviene: una configurazione corta si scrive e si
    disegna tutta, che e' quello che serve a chi la sta imparando.
    """
    if sum(CAPIENZA[o[1]] // 2 for o, _ in conf) <= 9:
        return "", conf
    for nome, z in sorted(_GAS_NOBILI.items(), key=lambda v: -v[1]):
        dentro = configurazione(z)
        if len(conf) > len(dentro) and all(voce in conf for voce in dentro):
            return nome, [voce for voce in conf if voce not in dentro]
    return "", conf


def _spaiati(conf: list[tuple[str, int]]) -> int:
    return sum(n if n <= CAPIENZA[o[1]] // 2 else CAPIENZA[o[1]] - n for o, n in conf)


# Le direzioni dei tre assi sul foglio, come nei libri: z in alto, y a destra,
# x verso chi guarda (quindi in basso a sinistra, e accorciato).
_ASSI = {"x": (-0.5, 0.42), "y": (1.0, 0.0), "z": (0.0, -1.0)}
_FASI = ("#2563eb", "#f59e0b")
_R2 = 1 / math.sqrt(2)
_LOBI = {
    "px": [((1, 0, 0), 0), ((-1, 0, 0), 1)],
    "py": [((0, 1, 0), 0), ((0, -1, 0), 1)],
    "pz": [((0, 0, 1), 0), ((0, 0, -1), 1)],
    "dxy": [((_R2, _R2, 0), 0), ((-_R2, -_R2, 0), 0), ((_R2, -_R2, 0), 1), ((-_R2, _R2, 0), 1)],
    "dxz": [((_R2, 0, _R2), 0), ((-_R2, 0, -_R2), 0), ((_R2, 0, -_R2), 1), ((-_R2, 0, _R2), 1)],
    "dyz": [((0, _R2, _R2), 0), ((0, -_R2, -_R2), 0), ((0, _R2, -_R2), 1), ((0, -_R2, _R2), 1)],
    "dx2-y2": [((1, 0, 0), 0), ((-1, 0, 0), 0), ((0, 1, 0), 1), ((0, -1, 0), 1)],
    "dz2": [((0, 0, 1), 0), ((0, 0, -1), 0)],
    "sp": [((0, 1, 0), 0), ((0, -1, 0), 0)],
    "sp2": [((0, 0, 1), 0), ((0, 0.866, -0.5), 0), ((0, -0.866, -0.5), 0)],
    "sp3": [((0, 0, 1), 0), ((0, 0.943, -0.333), 0), ((0.816, -0.471, -0.333), 0),
            ((-0.816, -0.471, -0.333), 0)],
}
_NOME_FORMA = {"dx2-y2": ("d", "x²−y²"), "dz2": ("d", "z²"), "sp2": ("sp²", ""), "sp3": ("sp³", "")}


def _una_forma(nome: str, cx: float, cy: float) -> str:
    """Un orbitale disegnato sui suoi tre assi, in un riquadro di 120 pixel."""
    parti = []
    for asse, (dx, dy) in _ASSI.items():
        parti.append(f'<line x1="{cx - dx * 46:.1f}" y1="{cy - dy * 46:.1f}" x2="{cx + dx * 46:.1f}" '
                     f'y2="{cy + dy * 46:.1f}" stroke="#9ca3af" stroke-width="0.9"/>')
        parti.append(f'<text x="{cx + dx * 53:.1f}" y="{cy + dy * 53 + 3:.1f}" text-anchor="middle" '
                     f'font-size="9.5" font-style="italic" fill="#6b7280">{asse}</text>')
    if nome == "s":
        parti.append(f'<circle cx="{cx}" cy="{cy}" r="25" fill="{_FASI[0]}" fill-opacity="0.75" '
                     f'stroke="{_FASI[0]}"/>')
    lobi = []
    for (a, b, c), fase in _LOBI.get(nome, []):
        vx = a * _ASSI["x"][0] + b * _ASSI["y"][0] + c * _ASSI["z"][0]
        vy = a * _ASSI["x"][1] + b * _ASSI["y"][1] + c * _ASSI["z"][1]
        lung = math.hypot(vx, vy) or 1
        lobi.append((a, vx / lung, vy / lung, 40 * (0.55 + 0.45 * lung), fase))
    if nome == "dz2":
        # L'anello intorno all'asse z, nel piano xy: dietro i due lobi.
        parti.append(f'<ellipse cx="{cx}" cy="{cy}" rx="27" ry="10" fill="none" '
                     f'stroke="{_FASI[1]}" stroke-width="7" stroke-opacity="0.75"/>')
    # Dal piu' lontano al piu' vicino: quello che punta verso chi guarda sta sopra.
    for _a, ux, uy, lung, fase in sorted(lobi, key=lambda v: v[0]):
        mx, my = cx + ux * lung / 2, cy + uy * lung / 2
        parti.append(f'<ellipse cx="{mx:.1f}" cy="{my:.1f}" rx="{lung / 2:.1f}" ry="{lung / 3.6:.1f}" '
                     f'transform="rotate({math.degrees(math.atan2(uy, ux)):.1f} {mx:.1f} {my:.1f})" '
                     f'fill="{_FASI[fase]}" fill-opacity="0.75" stroke="{_FASI[fase]}"/>')
    base, pedice = _NOME_FORMA.get(nome, (nome[0], nome[1:]) if nome[0] in "pd" and len(nome) > 1
                                   else (nome, ""))
    parti.append(f'<text x="{cx}" y="{cy + 72}" text-anchor="middle" font-size="13" '
                 f'font-style="italic" fill="#111">{base}<tspan font-size="9" dy="3">{pedice}</tspan></text>')
    return "".join(parti)


def _svg_orbitali(o: dict) -> str:
    disegni, legenda = [], []
    conf = o["configurazione"]
    if conf:
        nucleo, fuori_nocciolo = _nocciolo(conf)
        lato, stacco = 26, 14
        x = 12.0
        parti = []
        if nucleo:
            parti.append(f'<text x="{x}" y="38" font-size="15" font-weight="600" '
                         f'fill="#374151">[{nucleo}]</text>')
            x += 44
        for nome, n in fuori_nocciolo:
            caselle = CAPIENZA[nome[1]] // 2
            for k in range(caselle):
                bx = x + k * lato
                parti.append(f'<rect x="{bx:.1f}" y="18" width="{lato}" height="{lato}" '
                             f'fill="#fff" stroke="#374151" stroke-width="1.2"/>')
                # Regola di Hund: prima una freccia in su per casella, poi si
                # torna indietro a metterci quella in giu'.
                if k < n:
                    parti.append(f'<path d="M{bx + 9:.1f},39 V23 m-3.2,4.5 l3.2,-4.5 l3.2,4.5" '
                                 f'fill="none" stroke="#dc2626" stroke-width="1.6" '
                                 f'stroke-linecap="round" stroke-linejoin="round"/>')
                if k < n - caselle:
                    parti.append(f'<path d="M{bx + 17:.1f},23 V39 m-3.2,-4.5 l3.2,4.5 l3.2,-4.5" '
                                 f'fill="none" stroke="#2563eb" stroke-width="1.6" '
                                 f'stroke-linecap="round" stroke-linejoin="round"/>')
            parti.append(f'<text x="{x + caselle * lato / 2:.1f}" y="60" text-anchor="middle" '
                         f'font-size="12.5" fill="#111">{nome}'
                         f'<tspan font-size="9" dy="-5">{n}</tspan></text>')
            x += caselle * lato + stacco
        W = x - stacco + 12
        disegni.append(_apri_svg(W, 70) + "".join(parti) + "</svg>")
        chi = f'{_specie_scritta(o)} (Z = {NUMERO[o["simbolo"]]}): ' if o["simbolo"] else ""
        legenda.append(html.escape(chi + _in_riga(conf)))
        legenda.append(f"elettroni spaiati: {_spaiati(conf)}")
    if o["forme"]:
        per_riga = min(len(o["forme"]), 5)
        file = math.ceil(len(o["forme"]) / per_riga)
        parti = []
        for k, nome in enumerate(o["forme"]):
            parti.append(_una_forma(nome, 60 + (k % per_riga) * 120, 58 + (k // per_riga) * 140))
        disegni.append(_apri_svg(per_riga * 120, file * 140) + "".join(parti) + "</svg>")
        if any(nome in _LOBI and len({f for _, f in _LOBI[nome]}) > 1 or nome == "dz2"
               for nome in o["forme"]):
            legenda.append(_tassello(_FASI[0], "fase +", True) + " " + _tassello(_FASI[1], "fase −", True))
    corpo = ('<div style="display:flex;flex-direction:column;align-items:center;gap:10px">'
             + "".join(disegni) + "</div>")
    return _cornice(o["titolo"], corpo, legenda, o["note"])


def _specie_scritta(o: dict) -> str:
    """L'elemento o lo ione come si scrive: «O», «Fe³⁺», «Cl⁻»."""
    carica = o["carica"]
    if not carica:
        return o["simbolo"]
    segno = ("" if abs(carica) == 1 else str(abs(carica))) + ("+" if carica > 0 else "−")
    return o["simbolo"] + segno.translate(_APICI)


def _testo_orbitali(o: dict) -> list[str]:
    fuori = [("Orbitali: " + o["titolo"]) if o["titolo"] else "Orbitali"]
    if o["configurazione"]:
        chi = f"{_specie_scritta(o)}: " if o["simbolo"] else ""
        fuori.append(f"- Configurazione elettronica {chi}{_in_riga(o['configurazione'])}")
        fuori.append(f"- Elettroni spaiati: {_spaiati(o['configurazione'])}")
    if o["forme"]:
        fuori.append("- Forma degli orbitali: " + ", ".join(o["forme"]))
    return fuori + [f"- {n}" for n in o["note"]]


# ═══════════════════════════════════════════════════════════════════════════
#  LA TITOLAZIONE
# ═══════════════════════════════════════════════════════════════════════════

KW = 1e-14


def _specie(valore: str) -> dict | None:
    """«acido debole, 0,1 M, 25 mL, Ka = 1,8e-5 | acido acetico» in un dizionario."""
    valore, _, nome = (p.strip() for p in valore.partition("|"))
    t = _senza_accenti(valore).lower()
    m = re.search(r"\b(acido|base)\s+(forte|debole)\b", t)
    if not m:
        return None
    s = {"tipo": m.group(1), "forte": m.group(2) == "forte", "nome": nome, "K": None,
         "volume": None, "M": None}
    numero = r"([0-9][0-9.,]*(?:\s*[×·*x]\s*10\^?\{?-?\d+\}?|e-?\d+)?|10\^\{?-?\d+\}?)"
    try:
        m = re.search(numero + r"\s*(?:m\b|mol/l|molare)", t)
        if m:
            s["M"] = _numero(m.group(1))
        m = re.search(numero + r"\s*(ml|l)\b", t)
        if m:
            s["volume"] = _numero(m.group(1)) * (1.0 if m.group(2) == "ml" else 1000.0)
        m = re.search(r"\b(p?)k([ab])\s*=\s*" + numero, t)
        if m:
            if m.group(2) != ("a" if s["tipo"] == "acido" else "b"):
                return None
            k = _numero(m.group(3))
            s["K"] = 10.0 ** -k if m.group(1) else k
    except ValueError:
        return None
    if s["M"] is None or not 1e-4 <= s["M"] <= 20:
        return None
    if s["forte"] != (s["K"] is None) or (s["K"] is not None and not 1e-13 < s["K"] < 1):
        return None
    return s


def _ph(analita: dict, titolante: dict, v: float) -> float:
    """Il pH dopo aver aggiunto 'v' millilitri di titolante.

    Non si usano le formule a pezzi dei libri (prima, al punto equivalente,
    dopo), che ai confini fra un pezzo e l'altro non si raccordano: si risolve
    l'equazione che vale sempre, il bilancio delle cariche, cercando per
    bisezione il pH a cui le cariche positive e le negative si pareggiano.
    """
    totale = analita["volume"] + v
    ca = analita["M"] * analita["volume"] / totale
    ct = titolante["M"] * v / totale
    acido = analita["tipo"] == "acido"
    k = analita["K"]
    ka = (k if acido else KW / k) if k is not None else None

    def sbilancio(ph: float) -> float:
        h = 10.0 ** -ph
        if acido:       # H⁺ + catione della base = OH⁻ + A⁻
            ionizzato = 1.0 if ka is None else ka / (ka + h)
            return h + ct - KW / h - ca * ionizzato
        protonata = 1.0 if ka is None else h / (h + ka)     # H⁺ + BH⁺ = OH⁻ + anione dell'acido
        return h + ca * protonata - KW / h - ct

    basso, alto = -1.0, 15.0            # a pH basso avanzano cariche positive
    for _ in range(60):
        mezzo = (basso + alto) / 2
        if sbilancio(mezzo) > 0:
            basso = mezzo
        else:
            alto = mezzo
    return (basso + alto) / 2


def _leggi_titolazione(testo: str) -> dict | None:
    righe = _righe(testo, ("titolo", "analita", "titolante", "indicatore", "nota"))
    if righe is None:
        return None
    t = {"titolo": "", "analita": None, "titolante": None, "indicatore": None, "note": []}
    for chiave, valore in righe:
        if chiave == "titolo":
            t["titolo"] = valore
        elif chiave == "nota":
            t["note"].append(valore)
        elif chiave in ("analita", "titolante"):
            t[chiave] = _specie(valore)
            if t[chiave] is None:
                return None
        else:
            m = re.match(r"^(.+?)[,:]?\s+(\d+(?:[.,]\d+)?)\s*[-–—a]\s*(\d+(?:[.,]\d+)?)\s*$", valore)
            if not m:
                return None
            da, a = _numero(m.group(2)), _numero(m.group(3))
            if not 0 <= da < a <= 14:
                return None
            t["indicatore"] = (m.group(1).strip(), da, a)
    a, b = t["analita"], t["titolante"]
    if not a or not b or a["volume"] is None or a["volume"] <= 0:
        return None
    # Si titola un acido con una base forte, o una base con un acido forte.
    if a["tipo"] == b["tipo"] or not b["forte"]:
        return None
    t["equivalente"] = a["M"] * a["volume"] / b["M"]
    if not 0.05 <= t["equivalente"] <= 1e5:
        return None
    t["ph_equivalente"] = _ph(a, b, t["equivalente"])
    t["ph_iniziale"] = _ph(a, b, 0.0)
    if a["K"] is not None:
        ka = a["K"] if a["tipo"] == "acido" else KW / a["K"]
        t["pka"] = -math.log10(ka)
    return t


def _svg_titolazione(t: dict) -> str:
    a, b = t["analita"], t["titolante"]
    ve = t["equivalente"]
    fine = 2 * ve
    sx, alto, w, h = 46, 16, 480, 300
    W, H = sx + w + 18, alto + h + 44

    def px(v):
        return sx + v / fine * w

    def py(ph):
        return alto + (14 - ph) / 14 * h

    parti = [_apri_svg(W, H)]
    for ph in range(0, 15, 2):
        parti.append(f'<line x1="{sx}" y1="{py(ph):.1f}" x2="{sx + w}" y2="{py(ph):.1f}" '
                     f'stroke="#e6ece8"/>')
        parti.append(f'<text x="{sx - 6}" y="{py(ph) + 4:.1f}" text-anchor="end" '
                     f'fill="#555">{ph}</text>')
    passo = _passo(fine)
    v = 0.0
    while v <= fine + 1e-9:
        parti.append(f'<line x1="{px(v):.1f}" y1="{alto}" x2="{px(v):.1f}" y2="{alto + h}" '
                     f'stroke="#e6ece8"/>')
        parti.append(f'<text x="{px(v):.1f}" y="{alto + h + 14}" text-anchor="middle" '
                     f'fill="#555">{_numero_bello(v)}</text>')
        v += passo
    if t["indicatore"]:
        _nome, da, fino = t["indicatore"]
        parti.append(f'<rect x="{sx}" y="{py(fino):.1f}" width="{w}" '
                     f'height="{py(da) - py(fino):.1f}" fill="#d946ef" fill-opacity="0.13"/>')
    parti.append(f'<line x1="{sx}" y1="{py(7):.1f}" x2="{sx + w}" y2="{py(7):.1f}" '
                 f'stroke="#9ca3af" stroke-dasharray="4 4"/>')
    parti.append(f'<rect x="{sx}" y="{alto}" width="{w}" height="{h}" fill="none" stroke="#333"/>')

    # Piu' punti dove la curva sale di colpo, intorno al punto equivalente.
    volumi = sorted({fine * k / 240 for k in range(241)}
                    | {ve * (1 + d) for k in range(1, 40) for d in (-0.02 * k / 40 * 5, 0.02 * k / 40 * 5)}
                    | {ve * (1 + s * 10.0 ** -e) for e in range(2, 7) for s in (-1, 1)} | {ve})
    punti = " ".join(f"{px(v):.1f},{py(_ph(a, b, v)):.1f}" for v in volumi if 0 <= v <= fine)
    parti.append(f'<polyline points="{punti}" fill="none" stroke="{TINTE[1]}" stroke-width="2.2" '
                 f'stroke-linejoin="round"/>')

    # Il punto equivalente, e per un acido o una base debole quello di mezzo.
    xe, ye = px(ve), py(t["ph_equivalente"])
    parti.append(f'<line x1="{xe:.1f}" y1="{ye:.1f}" x2="{xe:.1f}" y2="{alto + h}" '
                 f'stroke="{TINTE[4]}" stroke-dasharray="3 3"/>')
    parti.append(f'<circle cx="{xe:.1f}" cy="{ye:.1f}" r="4.2" fill="{TINTE[4]}"/>')
    if "pka" in t:
        xm, ym = px(ve / 2), py(_ph(a, b, ve / 2))
        parti.append(f'<circle cx="{xm:.1f}" cy="{ym:.1f}" r="4.2" fill="{TINTE[2]}"/>')
    parti.append(f'<text x="{sx + w / 2:.1f}" y="{H - 6}" text-anchor="middle" font-size="12" '
                 f'font-style="italic" fill="#333">volume di titolante aggiunto (mL)</text>')
    parti.append(f'<text x="14" y="{alto + h / 2:.1f}" text-anchor="middle" font-size="12" '
                 f'font-style="italic" fill="#333" '
                 f'transform="rotate(-90 14 {alto + h / 2:.1f})">pH</text>')
    parti.append("</svg>")

    legenda = [_tassello(TINTE[4], f"punto equivalente: {_virgola(ve)} mL, "
                                   f"pH {_virgola(t['ph_equivalente'])}", True)]
    if "pka" in t:
        nome_k = "pKa" if a["tipo"] == "acido" else "pKa dell'acido coniugato"
        legenda.append(_tassello(TINTE[2], f"metà titolazione: pH = {nome_k} = "
                                           f"{_virgola(t['pka'])}", True))
    legenda.append(html.escape(f"pH iniziale {_virgola(t['ph_iniziale'])}"))
    if t["indicatore"]:
        nome, da, fino = t["indicatore"]
        legenda.append(_tassello("#f0abfc", f"viraggio di {nome}: pH {_virgola(da)}–{_virgola(fino)}"))
    return _cornice(t["titolo"] or _titolo_titolazione(t), "".join(parti), legenda, t["note"])


def _virgola(v: float, cifre: int = 2) -> str:
    """Un numero con la virgola, come si scrive in italiano."""
    return _numero_bello(round(v, cifre)).replace(".", ",")


def _titolo_titolazione(t: dict) -> str:
    def chi(s):
        return s["nome"] or f"{s['tipo']} {'forte' if s['forte'] else 'debole'}"
    return f"Titolazione di {chi(t['analita'])} con {chi(t['titolante'])}"


def _testo_titolazione(t: dict) -> list[str]:
    fuori = [f"Curva di titolazione: {t['titolo'] or _titolo_titolazione(t)}",
             f"- pH iniziale: {_virgola(t['ph_iniziale'])}",
             f"- Punto equivalente: {_virgola(t['equivalente'])} mL di titolante, "
             f"pH {_virgola(t['ph_equivalente'])}"]
    if "pka" in t:
        fuori.append(f"- A metà titolazione il pH è uguale al pKa: {_virgola(t['pka'])}")
    if t["indicatore"]:
        nome, da, fino = t["indicatore"]
        fuori.append(f"- Indicatore: {nome}, viraggio fra pH {_virgola(da)} e {_virgola(fino)}")
    return fuori + [f"- {n}" for n in t["note"]]


# ═══════════════════════════════════════════════════════════════════════════
#  IL PROFILO DI ENERGIA
# ═══════════════════════════════════════════════════════════════════════════

def _leggi_energia(testo: str) -> dict | None:
    righe = _righe(testo, ("titolo", "livelli", "tipo", "catalizzatore", "unita", "asse",
                           "numeri", "nota"))
    if righe is None:
        return None
    e = {"titolo": "", "livelli": [], "catalizzatore": [], "unita": "kJ/mol", "asse": "energia",
         "numeri": True, "note": []}
    tipo = ""
    for chiave, valore in righe:
        if chiave == "titolo":
            e["titolo"] = valore
        elif chiave == "nota":
            e["note"].append(valore)
        elif chiave == "unita":
            e["unita"] = valore
        elif chiave == "asse":
            e["asse"] = valore
        elif chiave == "numeri":
            if valore.lower() not in ("si", "sì", "no"):
                return None
            e["numeri"] = valore.lower() != "no"
        elif chiave == "tipo":
            tipo = _senza_accenti(valore).lower()
            if tipo not in ("esotermica", "endotermica"):
                return None
        elif chiave == "livelli":
            for pezzo in valore.split(";"):
                m = re.match(r"^(.*?)\s*([+\-−]?\d+(?:[.,]\d+)?)\s*$", pezzo.strip())
                if not m or not m.group(1).strip():
                    return None
                e["livelli"].append((m.group(1).strip(" :="), _numero(m.group(2))))
        elif valore.strip().lower() in ("si", "sì"):
            e["catalizzatore"] = [None]        # c'e', ma il testo non dice quanto vale
        else:
            try:
                e["catalizzatore"] = [_numero(p) for p in valore.split(";") if p.strip()]
            except ValueError:
                return None
    if not e["livelli"]:
        # Senza numeri nel testo resta la forma: quella dei libri, e niente
        # valori scritti sopra, perche' sarebbero inventati.
        if not tipo:
            return None
        e["livelli"] = [("reagenti", 0.0), ("stato di transizione", 100.0),
                        ("prodotti", -55.0 if tipo == "esotermica" else 55.0)]
        e["numeri"] = False
        if e["catalizzatore"]:
            e["catalizzatore"] = [62.0 if tipo == "esotermica" else 80.0]
    valori = [v for _, v in e["livelli"]]
    n = len(valori)
    # Reagenti, stato di transizione, (intermedio, stato di transizione,)
    # prodotti: un numero dispari di livelli, coi dispari in cima a un colle.
    if n < 3 or n % 2 == 0 or n > 9:
        return None
    colli = list(range(1, n, 2))
    if any(valori[i] <= max(valori[i - 1], valori[i + 1]) for i in colli):
        return None
    if e["catalizzatore"]:
        if len(e["catalizzatore"]) != len(colli) or None in e["catalizzatore"]:
            return None
        for i, v in zip(colli, e["catalizzatore"]):
            if not max(valori[i - 1], valori[i + 1]) < v < valori[i]:
                return None
    if tipo and (tipo == "esotermica") != (valori[-1] < valori[0]):
        return None
    return e


def _svg_energia(e: dict) -> str:
    nomi = [n for n, _ in e["livelli"]]
    valori = [v for _, v in e["livelli"]]
    n = len(valori)
    W, H = 560, 340
    sx, dx, alto, basso = 52, 62, 30, 44
    tutti = valori + e["catalizzatore"]
    lo, hi = min(tutti), max(tutti)
    piano = 64 if n == 3 else 44                       # quanto e' largo un ripiano
    passo = (W - sx - dx - piano) / (n - 1)
    uid = _uid("energia", e["titolo"], e["livelli"], e["catalizzatore"])

    def x(i):
        return sx + piano / 2 + i * passo

    def y(v):
        return alto + (hi - v) / (hi - lo) * (H - alto - basso - 36) + 4

    def curva(cime: list[float]) -> str:
        """La curva: ripiani in basso, colli in cima, raccordati in piano."""
        d = f"M{x(0) - piano / 2:.1f},{y(cime[0]):.1f}"
        for i in range(n):
            if i % 2 == 0:
                d += f" L{x(i) + piano / 2:.1f},{y(cime[i]):.1f}"
            if i == n - 1:
                break
            x0 = x(i) + (piano / 2 if i % 2 == 0 else 0)
            x1 = x(i + 1) - (piano / 2 if (i + 1) % 2 == 0 else 0)
            mezzo = (x0 + x1) / 2
            d += (f" C{mezzo:.1f},{y(cime[i]):.1f} {mezzo:.1f},{y(cime[i + 1]):.1f} "
                  f"{x1:.1f},{y(cime[i + 1]):.1f}")
        return d

    parti = [_apri_svg(W, H, 11.5),
             f"<defs>{_punta(uid + 'a')}{_punta(uid + 'r', TINTE[4])}{_punta(uid + 'v', TINTE[0])}</defs>"]
    # Gli assi: senza tacche, perche' l'asse orizzontale non misura niente.
    parti.append(f'<line x1="{sx - 14}" y1="{H - basso}" x2="{sx - 14}" y2="{alto - 14}" '
                 f'stroke="#333" stroke-width="1.2" marker-end="url(#{uid}a)"/>')
    parti.append(f'<line x1="{sx - 14}" y1="{H - basso}" x2="{W - 14}" y2="{H - basso}" '
                 f'stroke="#333" stroke-width="1.2" marker-end="url(#{uid}a)"/>')
    asse = e["asse"] + (f" ({e['unita']})" if e["numeri"] else "")
    parti.append(f'<text x="{sx - 22}" y="{(H - basso + alto) / 2:.1f}" text-anchor="middle" '
                 f'font-style="italic" fill="#333" '
                 f'transform="rotate(-90 {sx - 22} {(H - basso + alto) / 2:.1f})">'
                 f'{html.escape(asse)}</text>')
    parti.append(f'<text x="{(sx + W) / 2:.1f}" y="{H - basso + 18}" text-anchor="middle" '
                 f'font-style="italic" fill="#333">coordinata di reazione</text>')

    # La linea del livello dei reagenti, fino in fondo: e' da li' che si misura ΔH.
    parti.append(f'<line x1="{x(0) + piano / 2:.1f}" y1="{y(valori[0]):.1f}" x2="{W - dx + 34:.1f}" '
                 f'y2="{y(valori[0]):.1f}" stroke="#9ca3af" stroke-dasharray="4 4"/>')
    if e["catalizzatore"]:
        cime = list(valori)
        for i, v in zip(range(1, n, 2), e["catalizzatore"]):
            cime[i] = v
        parti.append(f'<path d="{curva(cime)}" fill="none" stroke="{TINTE[2]}" stroke-width="2" '
                     f'stroke-dasharray="6 4"/>')
    parti.append(f'<path d="{curva(valori)}" fill="none" stroke="{TINTE[1]}" stroke-width="2.4"/>')

    def valore(v):
        return f" ({_numero_bello(v)})" if e["numeri"] else ""

    legenda = []
    for i in range(n):
        if i % 2 == 0:
            parti.append(f'<text x="{x(i):.1f}" y="{y(valori[i]) + 16:.1f}" text-anchor="middle" '
                         f'fill="#111">{html.escape(nomi[i] + valore(valori[i]))}</text>')
        else:
            parti.append(f'<text x="{x(i):.1f}" y="{y(valori[i]) - 8:.1f}" text-anchor="middle" '
                         f'fill="#111">{html.escape(nomi[i] + valore(valori[i]))}</text>')
            # L'energia di attivazione di questo stadio: dal ripiano prima al colle.
            numero = (str((i + 1) // 2).translate(_PEDICI)) if n > 3 else ""
            parti.append(f'<line x1="{x(i):.1f}" y1="{y(valori[i - 1]) - 2:.1f}" x2="{x(i):.1f}" '
                         f'y2="{y(valori[i]) + 5:.1f}" stroke="{TINTE[4]}" stroke-width="1.5" '
                         f'marker-end="url(#{uid}r)"/>')
            if i > 1:
                parti.append(f'<line x1="{x(i - 1) + piano / 2:.1f}" y1="{y(valori[i - 1]):.1f}" '
                             f'x2="{x(i) + 6:.1f}" y2="{y(valori[i - 1]):.1f}" stroke="#9ca3af" '
                             f'stroke-dasharray="4 4"/>')
            parti.append(f'<text x="{x(i) + 6:.1f}" y="{(y(valori[i - 1]) + y(valori[i])) / 2 + 4:.1f}" '
                         f'fill="{TINTE[4]}" font-weight="600">Eₐ{numero}</text>')
            ea = valori[i] - valori[i - 1]
            legenda.append(f'<b style="color:{TINTE[4]}">Eₐ{numero}</b> energia di attivazione'
                           + (f" = {_numero_bello(ea)} {html.escape(e['unita'])}" if e["numeri"] else ""))
    # ΔH: dal livello dei reagenti a quello dei prodotti, a destra.
    xd = W - dx + 26
    parti.append(f'<line x1="{xd:.1f}" y1="{y(valori[0]):.1f}" x2="{xd:.1f}" '
                 f'y2="{y(valori[-1]) + (-5 if valori[-1] < valori[0] else 5):.1f}" '
                 f'stroke="{TINTE[0]}" stroke-width="1.5" marker-end="url(#{uid}v)"/>')
    parti.append(f'<text x="{xd + 6:.1f}" y="{(y(valori[0]) + y(valori[-1])) / 2 + 4:.1f}" '
                 f'fill="{TINTE[0]}" font-weight="600">ΔH</text>')
    parti.append("</svg>")
    dh = valori[-1] - valori[0]
    legenda.append(f'<b style="color:{TINTE[0]}">ΔH</b>'
                   + (f" = {_numero_bello(dh)} {html.escape(e['unita'])}:" if e["numeri"] else ":")
                   + (" reazione esotermica" if dh < 0 else " reazione endotermica"))
    if e["catalizzatore"]:
        legenda.append(f'<i style="background:{TINTE[2]}"></i>con il catalizzatore'
                       + (": Eₐ = " + ", ".join(_numero_bello(v - valori[i - 1]) for i, v in
                                                zip(range(1, n, 2), e["catalizzatore"]))
                          + f" {html.escape(e['unita'])}" if e["numeri"] else ""))
    return _cornice(e["titolo"] or "Profilo di energia della reazione", "".join(parti),
                    legenda, e["note"])


def _testo_energia(e: dict) -> list[str]:
    valori = [v for _, v in e["livelli"]]
    fuori = [f"Profilo di energia: {e['titolo']}" if e["titolo"] else "Profilo di energia della reazione"]
    if e["numeri"]:
        fuori += [f"- {nome}: {_numero_bello(v)} {e['unita']}" for nome, v in e["livelli"]]
        fuori.append(f"- Energia di attivazione: {_numero_bello(valori[1] - valori[0])} {e['unita']}")
        fuori.append(f"- ΔH = {_numero_bello(valori[-1] - valori[0])} {e['unita']}")
    else:
        fuori.append("- " + " → ".join(nome for nome, _ in e["livelli"]))
    fuori.append("- Reazione " + ("esotermica" if valori[-1] < valori[0] else "endotermica"))
    if e["catalizzatore"]:
        fuori.append("- Con il catalizzatore l'energia di attivazione è più bassa")
    return fuori + [f"- {n}" for n in e["note"]]


# ═══════════════════════════════════════════════════════════════════════════
#  I RETICOLI CRISTALLINI
# ═══════════════════════════════════════════════════════════════════════════

_VERTICI = [(x, y, z) for x in (0, 1) for y in (0, 1) for z in (0, 1)]
_FACCE = [(0.5, 0.5, 0), (0.5, 0.5, 1), (0.5, 0, 0.5), (0.5, 1, 0.5), (0, 0.5, 0.5), (1, 0.5, 0.5)]
_SPIGOLI = [(a, b) for i, a in enumerate(_VERTICI) for b in _VERTICI[i + 1:]
            if sum(abs(p - q) for p, q in zip(a, b)) == 1]
_MEZZI_SPIGOLI = [tuple((p + q) / 2 for p, q in zip(a, b)) for a, b in _SPIGOLI]
_CENTRO = (0.5, 0.5, 0.5)
_DENTRO_DIAMANTE = [(0.25, 0.25, 0.25), (0.75, 0.75, 0.25), (0.75, 0.25, 0.75), (0.25, 0.75, 0.75)]

# Per ogni reticolo: i nomi con cui lo si puo' chiamare, gli atomi (posizione
# nella cella e specie, 0 o 1), quanti ce ne sono per cella, il numero di
# coordinazione, gli elementi di partenza e quanto dista un atomo dai vicini
# a cui va unito con una linea (0: nessuna linea).
_RETICOLI = {
    "cubico semplice": {
        "nomi": ("cubico semplice", "cubico primitivo", "cs"),
        "atomi": [(v, 0) for v in _VERTICI], "per_cella": "1", "coordinazione": "6",
        "elementi": [], "legame": 0.0, "raggi": (0.085,)},
    "cubico a corpo centrato": {
        "nomi": ("cubico a corpo centrato", "corpo centrato", "ccc", "bcc"),
        "atomi": [(v, 0) for v in _VERTICI] + [(_CENTRO, 0)], "per_cella": "2",
        "coordinazione": "8", "elementi": [], "legame": 0.866, "raggi": (0.085,)},
    "cubico a facce centrate": {
        "nomi": ("cubico a facce centrate", "facce centrate", "cfc", "fcc"),
        "atomi": [(v, 0) for v in _VERTICI + _FACCE], "per_cella": "4", "coordinazione": "12",
        "elementi": [], "legame": 0.0, "raggi": (0.085,)},
    "cloruro di sodio": {
        "nomi": ("cloruro di sodio", "salgemma", "nacl", "tipo nacl"),
        "atomi": [(v, 1) for v in _VERTICI + _FACCE] + [(v, 0) for v in _MEZZI_SPIGOLI + [_CENTRO]],
        "per_cella": "4 + 4", "coordinazione": "6 : 6", "elementi": ["Na", "Cl"], "legame": 0.5,
        "raggi": (0.06, 0.095)},
    "cloruro di cesio": {
        "nomi": ("cloruro di cesio", "cscl", "tipo cscl"),
        "atomi": [(v, 1) for v in _VERTICI] + [(_CENTRO, 0)], "per_cella": "1 + 1",
        "coordinazione": "8 : 8", "elementi": ["Cs", "Cl"], "legame": 0.866,
        "raggi": (0.13, 0.1)},
    "diamante": {
        "nomi": ("diamante", "tipo diamante"),
        "atomi": [(v, 0) for v in _VERTICI + _FACCE + _DENTRO_DIAMANTE], "per_cella": "8",
        "coordinazione": "4", "elementi": ["C"], "legame": 0.433, "raggi": (0.06,)},
}


def _leggi_reticolo(testo: str) -> dict | None:
    righe = _righe(testo, ("titolo", "tipo", "atomi", "atomo", "nota"))
    if righe is None:
        return None
    r = {"titolo": "", "tipo": "", "elementi": None, "note": []}
    for chiave, valore in righe:
        if chiave == "titolo":
            r["titolo"] = valore
        elif chiave == "nota":
            r["note"].append(valore)
        elif chiave == "tipo":
            cercato = re.sub(r"\s+", " ", _senza_accenti(valore).lower().strip())
            trovato = [nome for nome, dati in _RETICOLI.items() if cercato in dati["nomi"]]
            if not trovato:
                return None
            r["tipo"] = trovato[0]
        else:
            r["elementi"] = _simboli(valore)
            if not r["elementi"]:
                return None
    if not r["tipo"]:
        return None
    dati = _RETICOLI[r["tipo"]]
    specie = len(dati["raggi"])
    if r["elementi"] is None:
        r["elementi"] = list(dati["elementi"])
    if r["elementi"] and len(r["elementi"]) != specie:
        return None
    return r


def _svg_reticolo(r: dict) -> str:
    from server.export.molecola import COLORI, _scurisci
    dati = _RETICOLI[r["tipo"]]
    uid = _uid("reticolo", r["tipo"], r["elementi"], r["titolo"])
    W, H, scala = 400, 380, 205
    az, el = math.radians(-24), math.radians(17)

    def proietta(p):
        x, y, z = (c - 0.5 for c in p)
        xr = x * math.cos(az) - y * math.sin(az)
        fondo = x * math.sin(az) + y * math.cos(az)
        # Chi guarda sta davanti e un po' in alto: quello che e' in fondo
        # sale sul foglio, e quello che e' in alto e' piu' vicino.
        return (W / 2 + xr * scala, H / 2 - (z * math.cos(el) + fondo * math.sin(el)) * scala,
                z * math.sin(el) - fondo * math.cos(el))

    colori = []
    for k in range(len(dati["raggi"])):
        simbolo = r["elementi"][k] if r["elementi"] else ""
        colori.append(COLORI.get(simbolo) if COLORI.get(simbolo, "#ffffff") != "#ffffff"
                      else (TINTE[1], TINTE[2])[k])
    parti = [_apri_svg(W, H), "<defs>"]
    for k, colore in enumerate(colori):
        parti.append(f'<radialGradient id="{uid}{k}" cx="35%" cy="30%" r="75%">'
                     f'<stop offset="0%" stop-color="#fff"/><stop offset="35%" stop-color="{colore}"/>'
                     f'<stop offset="100%" stop-color="{_scurisci(colore)}"/></radialGradient>')
    parti.append("</defs>")

    # Gli spigoli della cella: tratteggiati i tre che partono dal vertice in fondo.
    lontano = min(_VERTICI, key=lambda v: proietta(v)[2])
    for a, b in _SPIGOLI:
        (x1, y1, _), (x2, y2, _) = proietta(a), proietta(b)
        dietro = lontano in (a, b)
        parti.append(f'<line x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}" '
                     f'stroke="{"#9ca3af" if dietro else "#4b5563"}" stroke-width="1.2"'
                     + (' stroke-dasharray="4 4"' if dietro else "") + "/>")
    pezzi = []
    atomi = dati["atomi"]
    if dati["legame"]:
        for i, (a, ka) in enumerate(atomi):
            for b, kb in atomi[i + 1:]:
                if abs(math.dist(a, b) - dati["legame"]) < 0.01 and (len(colori) == 1 or ka != kb):
                    (x1, y1, z1), (x2, y2, z2) = proietta(a), proietta(b)
                    pezzi.append(((z1 + z2) / 2 - 0.001,
                                  f'<line x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}" '
                                  f'stroke="#6b7280" stroke-width="{2.4 if r["tipo"] == "diamante" else 1.1}"'
                                  f' stroke-opacity="0.8"/>'))
    for p, k in atomi:
        x, y, z = proietta(p)
        pezzi.append((z, f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{dati["raggi"][k] * scala:.1f}" '
                         f'fill="url(#{uid}{k})" stroke="#374151" stroke-width="0.8"/>'))
    parti += [t for _z, t in sorted(pezzi, key=lambda v: v[0])]
    parti.append("</svg>")

    legenda = [_tassello(colori[k], r["elementi"][k], True) for k in range(len(colori))
               if r["elementi"]]
    legenda.append(f"atomi per cella: {dati['per_cella']}")
    legenda.append(f"numero di coordinazione: {dati['coordinazione']}")
    return _cornice(r["titolo"] or f"Reticolo {r['tipo']}", "".join(parti), legenda, r["note"])


def _testo_reticolo(r: dict) -> list[str]:
    dati = _RETICOLI[r["tipo"]]
    fuori = [f"Reticolo cristallino: {r['titolo'] or r['tipo']}"]
    if r["titolo"]:
        fuori.append(f"- Tipo: {r['tipo']}")
    if r["elementi"]:
        fuori.append("- Elementi: " + ", ".join(r["elementi"]))
    fuori.append(f"- Atomi per cella: {dati['per_cella']}")
    fuori.append(f"- Numero di coordinazione: {dati['coordinazione']}")
    return fuori + [f"- {n}" for n in r["note"]]


# ═══════════════════════════════════════════════════════════════════════════
#  LA PORTA: un tipo di blocco, tre domande
# ═══════════════════════════════════════════════════════════════════════════

_MESTIERI = {
    "orbitali": (_leggi_orbitali, _svg_orbitali, _testo_orbitali),
    "titolazione": (_leggi_titolazione, _svg_titolazione, _testo_titolazione),
    "energia": (_leggi_energia, _svg_energia, _testo_energia),
    "reticolo": (_leggi_reticolo, _svg_reticolo, _testo_reticolo),
    "tavola": (_leggi_tavola, _svg_tavola, _testo_tavola),
}


def _mestiere(tipo: str):
    if tipo == "reazione":
        from server.export import reazione
        return reazione.leggi, reazione.svg, reazione.a_parole
    return _MESTIERI[tipo]


def leggi(tipo: str, testo: str) -> dict | None:
    """La descrizione controllata di un blocco, o None se non si puo' disegnare."""
    if tipo not in BLOCCHI:
        return None
    try:
        return _mestiere(tipo)[0](testo)
    except (ValueError, ZeroDivisionError, OverflowError, KeyError, IndexError):
        return None


def svg(tipo: str, descrizione: dict) -> str:
    """Il disegno, nella stessa cornice del piano cartesiano."""
    return _mestiere(tipo)[1](descrizione)


def in_testo(tipo: str, testo: str) -> list[str]:
    """Il disegno detto a parole, per il Word e il file di testo."""
    descrizione = leggi(tipo, testo)
    return _mestiere(tipo)[2](descrizione) if descrizione else []
