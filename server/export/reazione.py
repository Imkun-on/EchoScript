"""Le reazioni dei riassunti: lo schema, e il meccanismo con le sue frecce.

Che cosa disegna
    Uno schema di reazione come nei libri di chimica organica: i reagenti
    disegnati a scheletro, i «+» fra uno e l'altro, la freccia con sopra e
    sotto le condizioni (il catalizzatore, il calore), i prodotti. Con una
    riga in piu' diventa un passo di meccanismo: le frecce curve rosse che
    dicono da dove partono gli elettroni e dove vanno.

Come lo scrive il modello
    In un blocco ```reazione, poche righe «chiave: valore»:

        titolo: Esterificazione di Fischer
        reagenti: CC(=O)O | acido acetico; CCO | etanolo
        prodotti: CC(=O)OCC | acetato di etile; O | acqua
        sopra: H2SO4                la scritta sopra la freccia
        sotto: calore               quella sotto
        tipo: equilibrio            la doppia freccia (di partenza e' semplice)

    Le molecole sono in SMILES, una dopo l'altra separate da «;»; dopo la
    barra il nome, e un numero davanti e' il coefficiente («2 [H][H]»).

    Per un meccanismo, gli atomi che contano prendono un numero dentro lo
    SMILES ([OH-:1], [CH3:2][Br:3]) e le frecce si scrivono con quei numeri:

        reagenti: [OH-:1]; [CH3:2][Br:3]
        prodotti: CO; [Br-]
        frecce: 1 -> 2; 2-3 -> 3

    «1 -> 2» parte dall'atomo 1 (una sua coppia di elettroni) e arriva
    all'atomo 2; «2-3 -> 3» parte dal legame fra 2 e 3 e finisce sull'atomo
    3, che si porta via gli elettroni; «1 -> 1-2» arriva in mezzo a due atomi,
    dove nasce un legame.

Il controllo
    Una reazione deve essere bilanciata: gli atomi dei reagenti, contati coi
    coefficienti, devono essere gli stessi dei prodotti, e cosi' le cariche.
    E' il controllo che toglie di mezzo quasi tutti gli errori di un modello:
    uno SMILES sbagliato, un prodotto dimenticato, un coefficiente che manca.
    Se non torna, il blocco si toglie. Le frecce devono partire e arrivare su
    atomi che esistono, e una che parte da un legame vuole che quel legame ci
    sia.

Chi disegna
    Le molecole le disegna RDKit, con lo stesso scheletro di molecola.py;
    tutto il resto (i «+», la freccia, le scritte, le frecce curve) si disegna
    qui, sapendo da RDKit dove ha messo ogni atomo.
"""
from __future__ import annotations

import html
import math
import re
from collections import Counter

from server.export import molecola
from server.export.chimica import _APICI, _cornice, _formula, _punta, _righe, _uid

_CARATTERE = 'font-family="Segoe UI, Arial, sans-serif"'
MAX_MOLECOLE = 6            # per parte: oltre, la riga non sta nella pagina
MAX_ATOMI = 40              # per molecola
_ROSSO = "#dc2626"

_SEMPLICE = ("", "->", "→", "semplice", "irreversibile", "freccia")
_EQUILIBRIO = ("<=>", "⇌", "<->", "equilibrio", "reversibile", "doppia freccia")


def _COME_SCRITTO():
    from rdkit import Chem
    parametri = Chem.SmilesParserParams()
    parametri.removeHs = False
    return parametri


def _parte(valore: str) -> list[dict] | None:
    """Le molecole di una parte della reazione, o None se una non esiste."""
    from rdkit import Chem
    fuori = []
    for pezzo in re.split(r"\s*;\s*|\s+\+\s+", valore.strip()):
        if not pezzo:
            continue
        smiles, _, nome = (p.strip() for p in pezzo.partition("|"))
        coefficiente = 1
        m = re.match(r"^(\d{1,2})\s+(\S+)$", smiles)
        if m:
            coefficiente, smiles = int(m.group(1)), m.group(2)
        # Gli idrogeni scritti apposta restano atomi veri: in un meccanismo
        # sono spesso proprio loro a portare il numero ([H:5][Br:3]).
        mol = Chem.MolFromSmiles(smiles, _COME_SCRITTO()) if smiles and " " not in smiles else None
        if mol is None or not 0 < mol.GetNumAtoms() <= MAX_ATOMI or coefficiente < 1:
            return None
        fuori.append({"mol": mol, "nome": nome, "coefficiente": coefficiente})
    return fuori if 0 < len(fuori) <= MAX_MOLECOLE else None


def _conto(parte: list[dict]) -> tuple[Counter, int]:
    """Gli atomi e la carica di una parte, coefficienti compresi."""
    from rdkit import Chem
    atomi: Counter = Counter()
    carica = 0
    for voce in parte:
        for a in Chem.AddHs(voce["mol"]).GetAtoms():
            atomi[a.GetSymbol()] += voce["coefficiente"]
            carica += a.GetFormalCharge() * voce["coefficiente"]
    return atomi, carica


def _estremo(testo: str) -> tuple[int, ...] | None:
    """Un capo di una freccia: un atomo («3») o un legame («2-3»)."""
    m = re.fullmatch(r"(\d+)(?:\s*[-–]\s*(\d+))?", testo.strip())
    if not m:
        return None
    numeri = tuple(int(g) for g in m.groups() if g)
    return None if len(numeri) == 2 and numeri[0] == numeri[1] else numeri


def leggi(testo: str) -> dict | None:
    """La reazione controllata, o None se non si puo' disegnare."""
    if not molecola.disponibile():
        return None
    from rdkit import RDLogger
    RDLogger.DisableLog("rdApp.*")
    righe = _righe(testo, ("titolo", "reagenti", "prodotti", "sopra", "sotto", "tipo",
                           "freccia", "frecce", "nota"))
    if righe is None:
        return None
    r = {"titolo": "", "reagenti": None, "prodotti": None, "sopra": "", "sotto": "",
         "equilibrio": False, "frecce": [], "note": []}
    frecce_scritte = []
    for chiave, valore in righe:
        if chiave == "titolo":
            r["titolo"] = valore
        elif chiave == "nota":
            r["note"].append(valore)
        elif chiave in ("reagenti", "prodotti"):
            r[chiave] = _parte(valore)
            if r[chiave] is None:
                return None
        elif chiave in ("sopra", "sotto"):
            r[chiave] = valore
        elif chiave == "frecce" or (chiave == "freccia" and re.search(r"\d", valore)):
            frecce_scritte += [p for p in valore.split(";") if p.strip()]
        else:
            scelta = valore.strip().lower()
            if scelta not in _SEMPLICE + _EQUILIBRIO:
                return None
            r["equilibrio"] = scelta in _EQUILIBRIO
    if not r["reagenti"] or not r["prodotti"]:
        return None
    if _conto(r["reagenti"]) != _conto(r["prodotti"]):
        return None

    # I numeri messi sugli atomi dei reagenti: dove sta ognuno.
    dove: dict[int, tuple[int, int]] = {}
    for k, voce in enumerate(r["reagenti"]):
        for a in voce["mol"].GetAtoms():
            numero = a.GetAtomMapNum()
            if numero:
                if numero in dove:
                    return None
                dove[numero] = (k, a.GetIdx())
    for scritta in frecce_scritte:
        capi = re.split(r"\s*(?:->|→|=>)\s*", scritta.strip())
        if len(capi) != 2:
            return None
        da, a = _estremo(capi[0]), _estremo(capi[1])
        if not da or not a or any(n not in dove for n in da + a):
            return None
        if len(da) == 2:
            (k1, i1), (k2, i2) = dove[da[0]], dove[da[1]]
            if k1 != k2 or r["reagenti"][k1]["mol"].GetBondBetweenAtoms(i1, i2) is None:
                return None
        r["frecce"].append((da, a))
    if len(r["frecce"]) > 6:
        return None
    r["dove"] = dove
    return r


def _disegna_parte(parte: list[dict], x: float, pezzi: list, misure: list) -> float:
    """Mette in fila le molecole di una parte; restituisce dove finisce."""
    for k, voce in enumerate(parte):
        if k:
            pezzi.append(("piu", x + 13, 0, 0, None))
            x += 26
        if voce["coefficiente"] > 1:
            pezzi.append(("numero", x + 8, 0, 0, str(voce["coefficiente"])))
            x += 18
        disegno, w, h, punti = molecola._scheletro_con_punti(voce["mol"])
        pezzi.append(("molecola", x, w, h, (disegno, voce["nome"])))
        misure.append((x, w, h, punti))
        x += w
    return x


def svg(r: dict) -> str:
    """La reazione disegnata: una riga di molecole, la freccia, e sopra le frecce curve."""
    uid = _uid("reazione", r["titolo"], [molecola._atomi(v["mol"]) for v in r["reagenti"] + r["prodotti"]],
               r["frecce"], r["sopra"], r["sotto"])
    pezzi: list = []
    misure_reagenti: list = []
    misure_prodotti: list = []
    x = _disegna_parte(r["reagenti"], 10.0, pezzi, misure_reagenti)
    sopra, sotto = _formula(r["sopra"]), _formula(r["sotto"])
    lunga = max(84.0, 7.0 * max(len(sopra), len(sotto)) + 26)
    freccia_da, freccia_a = x + 10, x + 10 + lunga
    x = _disegna_parte(r["prodotti"], freccia_a + 12, pezzi, misure_prodotti)

    alto = 40 if r["frecce"] else 12                # lo spazio per le frecce curve
    riga = max(h for _t, _x, _w, h, _d in pezzi if _t == "molecola")
    riga = max(riga, 70)
    nomi = any(d[1] for t, _x, _w, _h, d in pezzi if t == "molecola")
    W, H = x + 10, alto + riga + (22 if nomi else 6)
    mezzo = alto + riga / 2

    parti = [f"<defs>{_punta(uid + 'f')}{_punta(uid + 'e', _ROSSO)}</defs>"]
    for tipo, px, w, h, dato in pezzi:
        if tipo == "piu":
            parti.append(f'<text x="{px:.1f}" y="{mezzo + 7:.1f}" text-anchor="middle" '
                         f'font-size="21" fill="#111">+</text>')
        elif tipo == "numero":
            parti.append(f'<text x="{px:.1f}" y="{mezzo + 7:.1f}" text-anchor="middle" '
                         f'font-size="20" font-weight="600" fill="#111">{dato}</text>')
        else:
            disegno, nome = dato
            parti.append(disegno.replace("<svg ", f'<svg x="{px:.1f}" y="{mezzo - h / 2:.1f}" ', 1))
            if nome:
                parti.append(f'<text x="{px + w / 2:.1f}" y="{alto + riga + 15:.1f}" '
                             f'text-anchor="middle" font-size="11.5" fill="#374151">'
                             f'{html.escape(nome)}</text>')
    if r["equilibrio"]:
        parti.append(f'<line x1="{freccia_da:.1f}" y1="{mezzo - 3:.1f}" x2="{freccia_a:.1f}" '
                     f'y2="{mezzo - 3:.1f}" stroke="#333" stroke-width="1.5" marker-end="url(#{uid}f)"/>')
        parti.append(f'<line x1="{freccia_a:.1f}" y1="{mezzo + 3:.1f}" x2="{freccia_da:.1f}" '
                     f'y2="{mezzo + 3:.1f}" stroke="#333" stroke-width="1.5" marker-end="url(#{uid}f)"/>')
    else:
        parti.append(f'<line x1="{freccia_da:.1f}" y1="{mezzo:.1f}" x2="{freccia_a:.1f}" '
                     f'y2="{mezzo:.1f}" stroke="#333" stroke-width="1.6" marker-end="url(#{uid}f)"/>')
    centro = (freccia_da + freccia_a) / 2
    if sopra:
        parti.append(f'<text x="{centro:.1f}" y="{mezzo - 10:.1f}" text-anchor="middle" '
                     f'font-size="12" fill="#111">{html.escape(sopra)}</text>')
    if sotto:
        parti.append(f'<text x="{centro:.1f}" y="{mezzo + 20:.1f}" text-anchor="middle" '
                     f'font-size="12" fill="#111">{html.escape(sotto)}</text>')

    # Le frecce degli elettroni. Ogni atomo numerato ha il suo punto nel
    # disegno della sua molecola; spostato di dove la molecola e' finita nella
    # riga, e' il suo punto nel disegno intero.
    def punto(numero: int) -> tuple[float, float]:
        k, i = r["dove"][numero]
        mx, _w, h, punti = misure_reagenti[k]
        return mx + punti[i][0], mezzo - h / 2 + punti[i][1]

    def capo(numeri: tuple[int, ...]) -> tuple[float, float]:
        coordinate = [punto(n) for n in numeri]
        return (sum(c[0] for c in coordinate) / len(coordinate),
                sum(c[1] for c in coordinate) / len(coordinate))

    for n, (da, a) in enumerate(r["frecce"]):
        (x1, y1), (x2, y2) = capo(da), capo(a)
        lung = math.hypot(x2 - x1, y2 - y1)
        if lung < 4:
            continue
        nx, ny = -(y2 - y1) / lung, (x2 - x1) / lung
        # La pancia della curva va verso l'alto (dove c'e' lo spazio lasciato
        # apposta), alternando un po' l'altezza perche' due frecce non si coprano.
        if ny > 0:
            nx, ny = -nx, -ny
        gonfia = max(24.0, lung * 0.42) + (n % 2) * 8
        cx, cy = (x1 + x2) / 2 + nx * gonfia, (y1 + y2) / 2 + ny * gonfia

        def verso(x0, y0, quanto):
            d = math.hypot(cx - x0, cy - y0) or 1
            return x0 + (cx - x0) / d * quanto, y0 + (cy - y0) / d * quanto

        sx, sy = verso(x1, y1, 11 if len(da) == 1 else 4)
        ex, ey = verso(x2, y2, 12 if len(a) == 1 else 5)
        parti.append(f'<path d="M{sx:.1f},{sy:.1f} Q{cx:.1f},{cy:.1f} {ex:.1f},{ey:.1f}" '
                     f'fill="none" stroke="{_ROSSO}" stroke-width="1.7" '
                     f'marker-end="url(#{uid}e)"/>')

    larga = min(W, 660.0)
    disegno = (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W:.0f} {H:.0f}" '
               f'width="{larga:.0f}" height="{H * larga / W:.0f}" {_CARATTERE}>'
               + "".join(parti) + "</svg>")
    legenda = []
    if r["frecce"]:
        legenda.append(f'<b style="color:{_ROSSO}">↷</b> spostamento di una coppia di elettroni')
    return _cornice(r["titolo"], disegno, legenda, r["note"])


def _nome(voce: dict) -> str:
    """Come si chiama una molecola in una riga di testo: il suo nome, o la formula."""
    from rdkit.Chem import rdMolDescriptors
    testo = voce["nome"]
    if not testo:
        # RDKit scrive la carica in fondo alla formula («HO-», «O4S-2»): va in alto.
        m = re.fullmatch(r"(.*?)([+-])(\d*)", rdMolDescriptors.CalcMolFormula(voce["mol"]))
        testo = (_formula(m.group(1)) + (m.group(3) + m.group(2)).translate(_APICI) if m
                 else _formula(rdMolDescriptors.CalcMolFormula(voce["mol"])))
    return (f"{voce['coefficiente']} " if voce["coefficiente"] > 1 else "") + testo


def a_parole(r: dict) -> list[str]:
    """La reazione in una riga, per il Word e il file di testo."""
    freccia = " ⇌ " if r["equilibrio"] else " → "
    riga = (" + ".join(_nome(v) for v in r["reagenti"]) + freccia
            + " + ".join(_nome(v) for v in r["prodotti"]))
    fuori = [f"Reazione ({r['titolo']}): {riga}" if r["titolo"] else f"Reazione: {riga}"]
    condizioni = [c for c in (r["sopra"], r["sotto"]) if c]
    if condizioni:
        fuori.append("- Condizioni: " + ", ".join(_formula(c) for c in condizioni))
    if r["frecce"]:
        fuori.append("- Nel disegno le frecce mostrano lo spostamento degli elettroni")
    return fuori + [f"- {n}" for n in r["note"]]


def in_testo(testo: str) -> list[str]:
    descrizione = leggi(testo)
    return a_parole(descrizione) if descrizione else []
