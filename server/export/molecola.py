"""Le molecole dei riassunti: dalla descrizione al disegno.

Due disegni, come nei libri
    Una molecola piccola (l'acqua, l'ammoniaca, il metano, l'anidride
    carbonica) si capisce dalla forma: l'acqua e' piegata, il metano e' un
    tetraedro. Per queste c'e' il modello a sfere e bastoncini, in 3D, con la
    geometria vera e i colori di sempre (ossigeno rosso, idrogeno bianco,
    carbonio grigio).

    Un composto organico invece si legge dallo scheletro: la formula a
    linee dei libri di chimica organica, con i carboni nei vertici, gli
    idrogeni sui carboni sottintesi e il cerchio dentro gli anelli aromatici.

    Chi sceglie e' la molecola stessa: con piu' di un carbonio lo scheletro,
    altrimenti il 3D. La riga «vista:» lo cambia.

    Il terzo disegno e' la struttura di Lewis («vista: lewis»): tutti gli
    atomi scritti, i legami come trattini, le coppie di elettroni non
    condivise come puntini e le cariche formali. I puntini non li scrive il
    modello: si contano dagli elettroni esterni di ogni atomo, tolti quelli
    impegnati nei legami, quindi non possono essere sbagliati.

Come lo scrive il modello
    In un blocco ```molecola, poche righe «chiave: valore»:

        nome: acido solforico
        formula: H2SO4                  facoltativa, ma se c'e' deve tornare
        smiles: OS(=O)(=O)O             la struttura, in SMILES
        vista: 3d                       3d, scheletro, entrambe o lewis (facoltativa)
        nota: due legami S=O e due S-OH una riga sotto il disegno

    Lo SMILES e' la struttura scritta come testo: «O» e' l'acqua, «c1ccccc1»
    il benzene, «CCO» l'etanolo. La formula serve da controllo: se gli atomi
    della formula e quelli dello SMILES non sono gli stessi, uno dei due e'
    sbagliato, e il blocco si toglie invece di disegnare una molecola che non
    e' quella del testo.

Il controllo col nome (OPSIN)
    La formula non basta: l'etanolo e il dimetiletere sono tutti e due
    C2H6O. Il nome IUPAC invece dice una molecola sola, ed e' la cosa che il
    modello riporta meglio, perche' la trova scritta nel testo. Per questo
    c'e' una riga in piu':

        iupac: 2-hydroxybenzoic acid    il nome IUPAC, in inglese

    OPSIN (Universita' di Cambridge, licenza MIT) legge il nome e ne ricava
    la struttura. Se e' la stessa dello SMILES, bene; se e' diversa, vince
    quella del nome, purche' torni con la formula; se non torna nemmeno con
    la formula, non si sa chi abbia ragione e il blocco si toglie. OPSIN e'
    scritto in Java: se Java non c'e', o il nome non e' IUPAC («aspirin»),
    resta il controllo con la formula e basta.

Chi disegna
    RDKit: legge lo SMILES, controlla che la molecola esista (valenze,
    cariche, anelli), calcola le coordinate 2D dello scheletro e quelle 3D
    della molecola vera (con un campo di forze, cosi' gli angoli sono quelli
    giusti). Lo scheletro lo disegna RDKit; le sfere e i bastoncini si
    disegnano qui, in SVG, perche' nel PDF serve un'immagine ferma e non un
    visualizzatore da girare col mouse. Senza RDKit i blocchi si tolgono e
    il riassunto resta com'e'.
"""
from __future__ import annotations

import glob
import hashlib
import html
import math
import os
import re
import shutil
import subprocess
import threading
from collections import Counter

import numpy as np

# I colori degli elementi, quelli dei modelli molecolari (CPK, come in Jmol).
COLORI = {
    "H": "#ffffff", "C": "#505050", "N": "#3050f8", "O": "#ff0d0d", "F": "#90e050",
    "Cl": "#1ff01f", "Br": "#a62929", "I": "#940094", "S": "#ffff30", "P": "#ff8000",
    "B": "#ffb5b5", "Si": "#f0c8a0", "Na": "#ab5cf2", "K": "#8f40d4", "Li": "#cc80ff",
    "Mg": "#8aff00", "Ca": "#3dff00", "Al": "#bfa6a6", "Fe": "#e06633", "Cu": "#c88033",
    "Zn": "#7d80b0", "Xe": "#429eb0", "He": "#d9ffff", "Ne": "#b3e3f5", "Ar": "#80d1e3",
}
_COLORE_ALTRO = "#ff1493"

# Quanto e' grande la sfera di ogni elemento, in angstrom: piu' piccola del
# raggio vero, o le sfere coprirebbero i bastoncini.
RAGGI = {"H": 0.26, "C": 0.38, "N": 0.37, "O": 0.36, "F": 0.34, "Cl": 0.46,
         "Br": 0.5, "I": 0.56, "S": 0.46, "P": 0.45, "B": 0.38, "Si": 0.48}
_RAGGIO_ALTRO = 0.5

NOMI = {
    "H": "idrogeno", "C": "carbonio", "N": "azoto", "O": "ossigeno", "F": "fluoro",
    "Cl": "cloro", "Br": "bromo", "I": "iodio", "S": "zolfo", "P": "fosforo",
    "B": "boro", "Si": "silicio", "Na": "sodio", "K": "potassio", "Li": "litio",
    "Mg": "magnesio", "Ca": "calcio", "Al": "alluminio", "Fe": "ferro", "Cu": "rame",
    "Zn": "zinco", "Xe": "xeno", "He": "elio", "Ne": "neon", "Ar": "argon",
}

# Oltre questi numeri il disegno non si legge piu', e il blocco si toglie.
MAX_ATOMI_PESANTI = 120
MAX_ATOMI_3D = 80

_CHIAVI = ("nome", "titolo", "formula", "smiles", "iupac", "vista", "nota")
_BLOCCO = re.compile(r"```molecola[^\n]*\n(.*?)```", re.S)


def disponibile() -> bool:
    """Vero se RDKit c'e': senza, le molecole non si possono disegnare."""
    try:
        import rdkit  # noqa: F401
    except ImportError:
        return False
    return True


# ── OPSIN: dal nome IUPAC alla struttura ────────────────────────────────────

# Le strutture gia' chieste, nome per nome (None: OPSIN non l'ha capito).
# Lo stesso blocco si legge piu' volte (pulizia, PDF, Word), e Java ci mette
# un paio di secondi a partire: ogni nome si chiede una volta sola.
_DA_NOME: dict[str, str | None] = {}
_LUCCHETTO = threading.Lock()


def _java() -> str | None:
    """Il programma java: quello di JAVA_HOME, o quello raggiungibile per nome."""
    casa = os.environ.get("JAVA_HOME", "")
    for candidato in (os.path.join(casa, "bin", "java.exe"), os.path.join(casa, "bin", "java")):
        if casa and os.path.isfile(candidato):
            return candidato
    return shutil.which("java")


def _jar_opsin() -> str | None:
    """Il file di OPSIN, quello che arriva col pacchetto py2opsin."""
    try:
        import py2opsin
    except ImportError:
        return None
    trovati = glob.glob(os.path.join(os.path.dirname(py2opsin.__file__), "opsin*.jar"))
    return sorted(trovati)[-1] if trovati else None


def opsin_disponibile() -> bool:
    """Vero se si puo' fare il controllo col nome: servono Java e OPSIN."""
    return bool(_java() and _jar_opsin())


def strutture_da_nomi(nomi: list[str]) -> dict[str, str | None]:
    """Lo SMILES di ogni nome IUPAC, o None dove OPSIN non l'ha capito.

    Tutti i nomi nuovi vanno a OPSIN in una volta sola, uno per riga: OPSIN
    risponde con una riga per nome, vuota se il nome non si capisce. Se Java
    manca o si guasta, ogni nome resta None e vale il controllo con la formula.
    """
    with _LUCCHETTO:
        mancanti = [n for n in dict.fromkeys(nomi) if n and n not in _DA_NOME]
        if mancanti:
            risposte: list[str] = []
            java, jar = _java(), _jar_opsin()
            if java and jar:
                try:
                    esito = subprocess.run(
                        [java, "-Dfile.encoding=UTF-8", "-jar", jar, "-osmi"],
                        input=("\n".join(mancanti) + "\n").encode("utf-8"),
                        capture_output=True, timeout=90,
                        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
                    risposte = esito.stdout.decode("utf-8", "replace").splitlines()
                except (OSError, subprocess.SubprocessError):
                    risposte = []
            # Una risposta per nome, o nessuna: righe in piu' o in meno
            # vorrebbero dire strutture attaccate al nome sbagliato.
            if len(risposte) != len(mancanti):
                risposte = [""] * len(mancanti)
            for nome, smiles in zip(mancanti, risposte):
                _DA_NOME[nome] = smiles.strip() or None
        return {n: _DA_NOME.get(n) for n in nomi}


def prepara(testo: str) -> None:
    """Chiede a OPSIN, in una volta sola, i nomi di tutte le molecole del testo.

    Si chiama prima di leggere i blocchi uno per uno: senza, ogni blocco
    farebbe partire Java per conto suo.
    """
    if not testo or "```molecola" not in testo or not opsin_disponibile():
        return
    nomi = [m.group(1).strip() for blocco in _BLOCCO.findall(testo)
            for m in re.finditer(r"(?im)^\s*iupac\s*:\s*(.+)$", blocco)]
    if nomi:
        strutture_da_nomi(nomi)


def _stessa(a, b) -> bool:
    """Vero se due molecole sono la stessa, stereochimica compresa."""
    from rdkit import Chem
    try:
        return Chem.MolToInchiKey(a) == Chem.MolToInchiKey(b)
    except Exception:
        return Chem.MolToSmiles(a) == Chem.MolToSmiles(b)


def _atomi(mol) -> Counter:
    """Gli atomi della molecola, idrogeni compresi."""
    from rdkit import Chem
    return Counter(a.GetSymbol() for a in Chem.AddHs(mol).GetAtoms())


# ── La descrizione ──────────────────────────────────────────────────────────

def _conta_formula(formula: str) -> Counter | None:
    """Gli atomi di una formula scritta: «Ca(OH)2» da' Ca 1, O 2, H 2.

    La carica in fondo («SO4^2-», «NH4+») non conta atomi e si toglie; i
    pedici possono essere anche quelli tipografici (H₂O). None se la formula
    non si legge.
    """
    t = formula.strip().translate(str.maketrans("₀₁₂₃₄₅₆₇₈₉", "0123456789"))
    t = re.sub(r"\s+", "", t)
    t = re.sub(r"(\^\{?\d*[+\-−]\}?|[+\-−]+)$", "", t)       # la carica
    pila: list[Counter] = [Counter()]
    i = 0
    while i < len(t):
        c = t[i]
        if c in "([":
            pila.append(Counter())
            i += 1
        elif c in ")]":
            if len(pila) < 2:
                return None
            m = re.match(r"\d+", t[i + 1:])
            volte = int(m.group()) if m else 1
            interno = pila.pop()
            for k, v in interno.items():
                pila[-1][k] += v * volte
            i += 1 + (len(m.group()) if m else 0)
        else:
            m = re.match(r"([A-Z][a-z]?)(\d*)", t[i:])
            if not m:
                return None
            pila[-1][m.group(1)] += int(m.group(2) or 1)
            i += len(m.group())
    return pila[0] if len(pila) == 1 and pila[0] else None


def leggi(testo: str) -> dict | None:
    """La descrizione di una molecola, o None se non si puo' disegnare.

    Come per il piano: basta una riga sbagliata, uno SMILES che non esiste o
    una formula che non torna per togliere tutto il blocco. Con il nome IUPAC
    e OPSIN la struttura si controlla anche col nome (vedi in cima al file);
    'verifica' nel risultato dice come e' andata: «nome» se nome e SMILES
    dicono la stessa molecola (o se c'era solo il nome), «corretta» se lo SMILES era sbagliato e si e'
    presa la struttura del nome, «formula» se c'e' stato solo il controllo
    con la formula.
    """
    if not disponibile():
        return None
    from rdkit import Chem, RDLogger
    RDLogger.DisableLog("rdApp.*")          # gli SMILES sbagliati non sporcano la console

    righe: dict[str, str] = {}
    note: list[str] = []
    for riga in (testo or "").splitlines():
        riga = riga.strip()
        if not riga:
            continue
        m = re.match(r"^([a-zA-Z]+)\s*:\s*(.+)$", riga)
        if not m or m.group(1).lower() not in _CHIAVI:
            return None
        chiave, valore = m.group(1).lower(), m.group(2).strip()
        if chiave == "nota":
            note.append(valore)
        else:
            righe["nome" if chiave == "titolo" else chiave] = valore
    formula = righe.get("formula", "")
    scritta = _conta_formula(formula) if formula else None
    if formula and scritta is None:
        return None

    def torna(m) -> bool:
        return scritta is None or _atomi(m) == scritta

    dal_testo = Chem.MolFromSmiles(righe["smiles"]) if "smiles" in righe else None
    dal_nome = None
    if righe.get("iupac"):
        trovata = strutture_da_nomi([righe["iupac"]])[righe["iupac"]]
        dal_nome = Chem.MolFromSmiles(trovata) if trovata else None
    if dal_nome is not None:
        if dal_testo is not None and _stessa(dal_nome, dal_testo):
            mol, verifica = dal_testo, "nome"
        elif torna(dal_nome):
            mol, verifica = dal_nome, ("corretta" if dal_testo is not None else "nome")
        else:
            return None                    # nome e formula non tornano: chi ha ragione?
    elif dal_testo is not None and torna(dal_testo):
        mol, verifica = dal_testo, "formula"
    else:
        return None
    if not 0 < mol.GetNumAtoms() <= MAX_ATOMI_PESANTI:
        return None
    atomi = _atomi(mol)
    vista = righe.get("vista", "").lower().replace(" ", "")
    if vista in ("", "auto"):
        vista = "scheletro" if atomi.get("C", 0) > 1 else "3d"
    elif vista in ("3d", "sfere", "sfereebastoncini"):
        vista = "3d"
    elif vista in ("scheletro", "2d", "linee"):
        vista = "scheletro"
    elif vista in ("lewis", "strutturadilewis", "puntini"):
        vista = "lewis"
    elif vista not in ("entrambe", "tutte"):
        return None
    if vista in ("3d", "entrambe", "tutte") and sum(atomi.values()) > MAX_ATOMI_3D:
        vista = "scheletro"
    return {"nome": righe.get("nome", ""), "formula": formula, "smiles": Chem.MolToSmiles(mol),
            "mol": mol, "atomi": atomi, "vista": vista, "note": note, "verifica": verifica}


# ── Lo scheletro ────────────────────────────────────────────────────────────

def _scheletro(mol) -> str:
    """La formula a linee dei libri di organica, in SVG."""
    return _scheletro_con_punti(mol)[0]


def _scheletro_con_punti(mol) -> tuple[str, int, int, list[tuple[float, float]]]:
    """Lo scheletro in SVG, la sua misura, e dove sta ogni atomo nel disegno.

    RDKit disegna gli anelli aromatici con i doppi legami alternati (la
    formula di Kekule') o col tratteggio; i libri di scuola ci mettono il
    cerchio. Quindi i legami aromatici si disegnano semplici, e il cerchio si
    aggiunge dopo, al centro di ogni anello aromatico.

    I punti degli atomi servono a chi ci disegna sopra: le frecce degli
    elettroni di un meccanismo di reazione partono da un atomo o da un legame
    e arrivano a un altro (vedi reazione.py).
    """
    from rdkit import Chem
    from rdkit.Chem import rdDepictor
    from rdkit.Chem.Draw import rdMolDraw2D

    rdDepictor.SetPreferCoordGen(True)
    disegno = Chem.RWMol(mol)
    rdDepictor.Compute2DCoords(disegno)
    anelli = [list(r) for r, legami in zip(mol.GetRingInfo().AtomRings(),
                                           mol.GetRingInfo().BondRings())
              if all(mol.GetBondWithIdx(b).GetIsAromatic() for b in legami)]
    # Gli idrogeni si fissano prima di togliere l'aromaticita': un «NH» del
    # pirrolo deve restare «NH» anche coi legami semplici.
    for a in disegno.GetAtoms():
        a.SetNumExplicitHs(a.GetTotalNumHs())
        a.SetNoImplicit(True)
        a.SetAtomMapNum(0)          # i numeri dei meccanismi non si disegnano
    for b in disegno.GetBonds():
        if b.GetIsAromatic():
            b.SetBondType(Chem.BondType.SINGLE)
            b.SetIsAromatic(False)
    for a in disegno.GetAtoms():
        a.SetIsAromatic(False)
    disegno.UpdatePropertyCache(strict=False)
    Chem.WedgeMolBonds(disegno, disegno.GetConformer())      # cunei della stereochimica

    # Il foglio si misura sulla molecola: ogni legame lungo circa 46 pixel,
    # come nei libri. Le coordinate di RDKit hanno legami lunghi 1,5 circa.
    xy = np.array(disegno.GetConformer().GetPositions())[:, :2]
    per_unita = 46 / 1.5
    larghezza = min(560, int(np.ptp(xy[:, 0]) * per_unita) + 90)
    altezza = min(420, int(np.ptp(xy[:, 1]) * per_unita) + 70)
    d = rdMolDraw2D.MolDraw2DSVG(larghezza, altezza)
    o = d.drawOptions()
    o.prepareMolsBeforeDrawing = False
    o.fixedBondLength = 46
    o.bondLineWidth = 2
    o.padding = 0.12
    o.minFontSize = 15
    o.clearBackground = False
    d.DrawMolecule(disegno)
    d.FinishDrawing()
    svg = d.GetDrawingText()
    cerchi = []
    for anello in anelli:
        punti = [d.GetDrawCoords(i) for i in anello]
        cx = sum(p.x for p in punti) / len(punti)
        cy = sum(p.y for p in punti) / len(punti)
        r = 0.6 * sum(math.hypot(p.x - cx, p.y - cy) for p in punti) / len(punti)
        cerchi.append(f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="{r:.1f}" fill="none" '
                      f'stroke="#000" stroke-width="2"/>')
    svg = re.sub(r"^<\?xml[^>]*>\s*", "", svg)
    punti = [(d.GetDrawCoords(i).x, d.GetDrawCoords(i).y) for i in range(disegno.GetNumAtoms())]
    return svg.replace("</svg>", "".join(cerchi) + "</svg>"), larghezza, altezza, punti


# ── La struttura di Lewis ───────────────────────────────────────────────────

# I metalli di transizione, i lantanidi e gli attinidi: per loro il conto
# degli elettroni esterni non e' quello della regola dell'ottetto, e una
# struttura di Lewis non si disegna.
_SENZA_LEWIS = set(range(21, 31)) | set(range(39, 49)) | set(range(57, 81)) | set(range(89, 113))


def _lewis(mol) -> str | None:
    """La struttura di Lewis in SVG, o None se per questa molecola non si fa.

    Si scrivono tutti gli atomi, idrogeni compresi. Per ognuno gli elettroni
    non condivisi sono quelli esterni dell'elemento, meno la carica formale,
    meno quelli messi nei legami: a coppie diventano due puntini vicini, e
    quello che avanza (un radicale) un puntino solo. I puntini vanno negli
    spazi lasciati liberi dai legami, il piu' largo per primo.
    """
    from rdkit import Chem
    from rdkit.Chem import rdDepictor

    mh = Chem.AddHs(mol)
    if not 0 < mh.GetNumAtoms() <= 40:
        return None
    try:
        Chem.Kekulize(mh, clearAromaticFlags=True)
    except Exception:
        return None
    tavola = Chem.GetPeriodicTable()
    liberi: list[int] = []
    for a in mh.GetAtoms():
        if a.GetAtomicNum() in _SENZA_LEWIS:
            return None
        impegnati = int(round(sum(b.GetBondTypeAsDouble() for b in a.GetBonds())))
        n = tavola.GetNOuterElecs(a.GetAtomicNum()) - a.GetFormalCharge() - impegnati
        if n < 0:
            return None
        liberi.append(n)
    rdDepictor.SetPreferCoordGen(False)
    rdDepictor.Compute2DCoords(mh)
    xy = np.array(mh.GetConformer().GetPositions())[:, :2] * (46 / 1.5)
    margine = 34
    x0, y1 = float(xy[:, 0].min()), float(xy[:, 1].max())
    W = float(np.ptp(xy[:, 0])) + 2 * margine
    H = float(np.ptp(xy[:, 1])) + 2 * margine
    punti = [(margine + x - x0, margine + (y1 - y)) for x, y in xy]

    parti = []
    for b in mh.GetBonds():
        (xa, ya), (xb, yb) = punti[b.GetBeginAtomIdx()], punti[b.GetEndAtomIdx()]
        lung = math.hypot(xb - xa, yb - ya) or 1
        ux, uy = (xb - xa) / lung, (yb - ya) / lung
        accorcia = min(12.0, lung * 0.3)
        xa, ya, xb, yb = xa + ux * accorcia, ya + uy * accorcia, xb - ux * accorcia, yb - uy * accorcia
        ordine = int(round(b.GetBondTypeAsDouble()))
        for s in {1: (0,), 2: (-3, 3), 3: (-4.5, 0, 4.5)}.get(ordine, (0,)):
            parti.append(f'<line x1="{xa - uy * s:.1f}" y1="{ya + ux * s:.1f}" '
                         f'x2="{xb - uy * s:.1f}" y2="{yb + ux * s:.1f}" stroke="#111" '
                         f'stroke-width="1.8" stroke-linecap="round"/>')
    for a in mh.GetAtoms():
        i = a.GetIdx()
        x, y = punti[i]
        parti.append(f'<text x="{x:.1f}" y="{y + 6:.1f}" text-anchor="middle" font-size="17" '
                     f'font-weight="600" fill="#111">{html.escape(a.GetSymbol())}</text>')
        carica = a.GetFormalCharge()
        if carica:
            segno = ("" if abs(carica) == 1 else str(abs(carica))) + ("+" if carica > 0 else "−")
            parti.append(f'<text x="{x + 9:.1f}" y="{y - 8:.1f}" font-size="13" '
                         f'font-weight="600" fill="#b91c1c">{segno}</text>')
        # Gli angoli gia' presi dai legami, e poi dai puntini messi via via.
        occupati = [math.atan2(punti[v.GetIdx()][1] - y, punti[v.GetIdx()][0] - x)
                    for v in a.GetNeighbors()]
        coppie, spaiati = divmod(liberi[i], 2)
        gruppi = coppie + spaiati
        angoli: list[float] = []
        if not occupati:
            angoli = [-math.pi / 2, math.pi / 2, math.pi, 0.0][:gruppi]
        elif gruppi:
            # Lo spazio piu' largo fra due legami: se ci stanno tutti, i
            # puntini si spartiscono quello, a distanze uguali. E' la
            # disposizione dei libri: le due coppie dell'acqua dalla parte
            # opposta agli idrogeni, le tre del cloro intorno al cloro.
            ordinati = sorted(occupati)
            vuoti = [(ordinati[(j + 1) % len(ordinati)] - ordinati[j]) % (2 * math.pi) or 2 * math.pi
                     for j in range(len(ordinati))]
            j = max(range(len(vuoti)), key=lambda q: vuoti[q])
            if vuoti[j] / (gruppi + 1) >= math.radians(50):
                angoli = [ordinati[j] + vuoti[j] * (k + 1) / (gruppi + 1) for k in range(gruppi)]
        while len(angoli) < gruppi:
            # Non ci stanno: uno alla volta, ognuno nel vuoto piu' largo rimasto.
            ordinati = sorted(occupati + angoli)
            vuoti = [(ordinati[(j + 1) % len(ordinati)] - ordinati[j]) % (2 * math.pi) or 2 * math.pi
                     for j in range(len(ordinati))]
            j = max(range(len(vuoti)), key=lambda q: vuoti[q])
            angoli.append(ordinati[j] + vuoti[j] / 2)
        for k, angolo in enumerate(angoli):
            cx, cy = x + 15.5 * math.cos(angolo), y + 15.5 * math.sin(angolo)
            for s in ((-3.3, 3.3) if k < coppie else (0.0,)):
                parti.append(f'<circle cx="{cx - math.sin(angolo) * s:.1f}" '
                             f'cy="{cy + math.cos(angolo) * s:.1f}" r="1.8" fill="#111"/>')
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W:.0f} {H:.0f}" '
            f'width="{W:.0f}" height="{H:.0f}" font-family="Segoe UI, Arial, sans-serif">'
            + "".join(parti) + "</svg>")


# ── Le sfere e i bastoncini ─────────────────────────────────────────────────

def _coordinate_3d(mol):
    """(simboli, posizioni in angstrom, legami) della molecola con gli idrogeni.

    Le coordinate si calcolano (ETKDG) e poi si rilassano con un campo di
    forze, MMFF o, per gli elementi che MMFF non conosce, UFF: e' quello che
    rende l'acqua piegata di circa 104° e il metano un tetraedro. None se la
    molecola non si riesce a costruire in 3D.
    """
    from rdkit import Chem
    from rdkit.Chem import AllChem

    mh = Chem.AddHs(mol)
    parametri = AllChem.ETKDGv3()
    parametri.randomSeed = 7              # sempre lo stesso disegno per la stessa molecola
    if AllChem.EmbedMolecule(mh, parametri) != 0:
        return None
    try:
        if AllChem.MMFFHasAllMoleculeParams(mh):
            AllChem.MMFFOptimizeMolecule(mh, maxIters=2000)
        elif AllChem.UFFHasAllMoleculeParams(mh):
            AllChem.UFFOptimizeMolecule(mh, maxIters=2000)
    except Exception:
        pass
    posizioni = np.array(mh.GetConformer().GetPositions(), dtype=float)
    simboli = [a.GetSymbol() for a in mh.GetAtoms()]
    legami = [(b.GetBeginAtomIdx(), b.GetEndAtomIdx(),
               {Chem.BondType.DOUBLE: 2, Chem.BondType.TRIPLE: 3}.get(b.GetBondType(), 1))
              for b in mh.GetBonds()]
    return simboli, posizioni, legami


def _rotazione(a: float, b: float) -> np.ndarray:
    """La rotazione di 'a' gradi attorno all'asse x e poi di 'b' attorno a y."""
    a, b = math.radians(a), math.radians(b)
    rx = np.array([[1, 0, 0], [0, math.cos(a), -math.sin(a)], [0, math.sin(a), math.cos(a)]])
    ry = np.array([[math.cos(b), 0, math.sin(b)], [0, 1, 0], [-math.sin(b), 0, math.cos(b)]])
    return ry @ rx


def _orienta(posizioni: np.ndarray, raggi: np.ndarray) -> np.ndarray:
    """La molecola girata perche' si veda bene.

    Si parte dalla posizione piu' naturale: la parte piu' larga in
    orizzontale, la seconda in verticale, la piu' sottile verso chi guarda.
    Una molecola piatta (l'acqua, il benzene) si vede cosi' di fronte, con i
    suoi angoli veri. Poi si provano tante inclinazioni e si tiene quella in
    cui gli atomi si coprono meno: guardato di fronte, il metano avrebbe un
    idrogeno proprio davanti al carbonio. A parita' vince l'inclinazione
    piu' piccola, che e' la piu' vicina alla posizione naturale.
    """
    centro = posizioni - posizioni.mean(axis=0)
    if len(centro) < 2:
        return centro
    valori, vettori = np.linalg.eigh(np.cov(centro.T) + np.eye(3) * 1e-9)
    base = centro @ vettori[:, np.argsort(valori)[::-1]]
    somme = raggi[:, None] + raggi[None, :]
    lontani = ~np.eye(len(base), dtype=bool)
    migliore, voto_migliore = base, -math.inf
    for a in range(0, 90, 10):
        for b in range(-80, 90, 10):
            girata = base @ _rotazione(a, b).T
            piano = girata[:, :2]
            distanze = np.linalg.norm(piano[:, None, :] - piano[None, :, :], axis=2)
            # Quanto si scostano gli atomi, in rapporto alla loro grandezza:
            # conta la coppia piu' sovrapposta.
            voto = float((distanze / somme)[lontani].min()) - 0.002 * (abs(a) + abs(b)) / 10
            if voto > voto_migliore + 1e-9:
                migliore, voto_migliore = girata, voto
    return migliore


def _sfere(mol, uid: str) -> tuple[str, list[str]] | None:
    """Il modello a sfere e bastoncini in SVG, e gli elementi che contiene."""
    costruita = _coordinate_3d(mol)
    if not costruita:
        return None
    simboli, posizioni, legami = costruita
    p = _orienta(posizioni, np.array([RAGGI.get(s, _RAGGIO_ALTRO) for s in simboli]))
    ampiezza_x = float(np.ptp(p[:, 0])) + 1.4
    ampiezza_y = float(np.ptp(p[:, 1])) + 1.4
    scala = min(400 / ampiezza_x, 280 / ampiezza_y, 120.0)
    W, H = ampiezza_x * scala + 20, ampiezza_y * scala + 20
    cx0, cy0 = float(p[:, 0].min()) - 0.7, float(p[:, 1].max()) + 0.7

    def px(v):
        return 10 + (v[0] - cx0) * scala, 10 + (cy0 - v[1]) * scala

    # Prima tutti i legami, poi le sfere dalla piu' lontana alla piu' vicina.
    # Un legame che va verso un atomo lontano ci entra dentro, ed e' giusto
    # che la sfera lo copra; disegnato dopo passerebbe sopra le lettere.
    legami_svg: list[tuple[float, str]] = []
    pezzi: list[tuple[float, str]] = []
    for i, j, ordine in legami:
        (x1, y1), (x2, y2) = px(p[i]), px(p[j])
        lung = math.hypot(x2 - x1, y2 - y1) or 1
        nx, ny = -(y2 - y1) / lung, (x2 - x1) / lung
        spessore = 7 if ordine == 1 else 4.2
        scarti = {1: (0,), 2: (-3.6, 3.6), 3: (-5.4, 0, 5.4)}[ordine]
        linee = "".join(
            f'<line x1="{x1 + nx * s:.1f}" y1="{y1 + ny * s:.1f}" x2="{x2 + nx * s:.1f}" '
            f'y2="{y2 + ny * s:.1f}" stroke="#6b7280" stroke-width="{spessore + 2:.1f}" '
            f'stroke-linecap="round"/>'
            f'<line x1="{x1 + nx * s:.1f}" y1="{y1 + ny * s:.1f}" x2="{x2 + nx * s:.1f}" '
            f'y2="{y2 + ny * s:.1f}" stroke="#d1d5db" stroke-width="{spessore:.1f}" '
            f'stroke-linecap="round"/>' for s in scarti)
        legami_svg.append(((p[i][2] + p[j][2]) / 2, linee))
    for k, simbolo in enumerate(simboli):
        x, y = px(p[k])
        r = RAGGI.get(simbolo, _RAGGIO_ALTRO) * scala
        chiaro = simbolo in ("H", "F", "Cl", "S", "Mg", "Ca", "He", "Ne", "B", "Si")
        lettera = (f'<text x="{x:.1f}" y="{y + r * 0.34:.1f}" text-anchor="middle" '
                   f'font-size="{max(9.0, r * 0.95):.1f}" font-weight="600" '
                   f'fill="{"#1f2937" if chiaro else "#fff"}">{html.escape(simbolo)}</text>')
        pezzi.append((p[k][2], f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{r:.1f}" '
                               f'fill="url(#{uid}{simbolo})" stroke="#374151" '
                               f'stroke-width="0.8"/>' + lettera))
    elementi = sorted(set(simboli), key=lambda s: (s != "C", s != "H", s))
    sfumature = "".join(
        f'<radialGradient id="{uid}{s}" cx="35%" cy="30%" r="75%">'
        f'<stop offset="0%" stop-color="#fff"/>'
        f'<stop offset="35%" stop-color="{COLORI.get(s, _COLORE_ALTRO)}"/>'
        f'<stop offset="100%" stop-color="{_scurisci(COLORI.get(s, _COLORE_ALTRO))}"/>'
        f'</radialGradient>' for s in elementi)
    corpo = "".join(t for _z, t in sorted(legami_svg, key=lambda v: v[0]))
    corpo += "".join(t for _z, t in sorted(pezzi, key=lambda v: v[0]))
    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W:.0f} {H:.0f}" '
           f'width="{W:.0f}" height="{H:.0f}" font-family="Segoe UI, Arial, sans-serif">'
           f'<defs>{sfumature}</defs>{corpo}</svg>')
    return svg, elementi


def _scurisci(colore: str, quota: float = 0.55) -> str:
    """Lo stesso colore piu' scuro, per il bordo in ombra della sfera."""
    r, g, b = (int(colore[i:i + 2], 16) for i in (1, 3, 5))
    return "#%02x%02x%02x" % tuple(int(c * quota) for c in (r, g, b))


# ── Il disegno ──────────────────────────────────────────────────────────────

def formula_bella(molecola: dict) -> str:
    """La formula in HTML, coi pedici: quella scritta, o quella calcolata.

    Quella calcolata e' in notazione di Hill (C, H, poi gli altri in ordine
    alfabetico), che e' quella dei libri per i composti organici; per gli
    inorganici e' piu' naturale quella scritta nel testo (H2SO4 e non H2O4S),
    ed e' per questo che la riga «formula:» c'e'.
    """
    if molecola["formula"]:
        testo = molecola["formula"].translate(str.maketrans("₀₁₂₃₄₅₆₇₈₉", "0123456789"))
    else:
        from rdkit.Chem import rdMolDescriptors
        testo = rdMolDescriptors.CalcMolFormula(molecola["mol"])
    carica = re.search(r"(\^\{?\d*[+\-−]\}?|[+\-−]+)$", testo)
    corpo = testo[:carica.start()] if carica else testo
    fuori = re.sub(r"(\d+)", r"<sub>\1</sub>", html.escape(corpo))
    if carica:
        fuori += "<sup>" + html.escape(re.sub(r"[\^{}]", "", carica.group(1))) + "</sup>"
    return fuori


def svg(molecola: dict) -> str:
    """La molecola disegnata: SVG, con titolo, formula e legenda in HTML."""
    uid = "m" + hashlib.sha1(molecola["smiles"].encode("utf-8")).hexdigest()[:8]
    disegni, legenda = [], []
    if molecola["vista"] == "lewis":
        # Se per questa molecola Lewis non si fa (un metallo di transizione),
        # resta il disegno di sempre.
        fatto = _lewis(molecola["mol"])
        if fatto:
            disegni.append(fatto)
    if molecola["vista"] in ("3d", "entrambe", "tutte"):
        fatto = _sfere(molecola["mol"], uid)
        if fatto:
            disegno, elementi = fatto
            disegni.append(disegno)
            legenda = [f'<span><i style="background:{COLORI.get(s, _COLORE_ALTRO)};'
                       f'width:12px;height:12px;border-radius:50%;border:1px solid #6b7280">'
                       f'</i>{html.escape(s)} {html.escape(NOMI.get(s, ""))}</span>'
                       for s in elementi]
    if molecola["vista"] not in ("3d", "lewis") or not disegni:
        disegni.insert(0, _scheletro(molecola["mol"]))
    fuori = ['<div class="piano molecola">']
    titolo = html.escape(molecola["nome"])
    formula = formula_bella(molecola)
    fuori.append(f'<div class="piano-titolo">{titolo + " · " if titolo else ""}{formula}</div>')
    fuori.append('<div style="display:flex;flex-wrap:wrap;justify-content:center;'
                 'align-items:center;gap:18px">' + "".join(disegni) + "</div>")
    if legenda:
        fuori.append('<div class="piano-legenda">' + "".join(legenda) + "</div>")
    for nota in molecola["note"]:
        fuori.append(f'<div class="piano-nota">{html.escape(nota)}</div>')
    fuori.append("</div>")
    return "".join(fuori)


def in_testo(testo: str) -> list[str]:
    """La molecola detta a parole, per il Word e il file di testo che non disegnano."""
    molecola = leggi(testo)
    if not molecola:
        return []
    formula = re.sub(r"<[^>]+>", "", formula_bella(molecola))
    fuori = [f"Molecola: {molecola['nome']} ({formula})" if molecola["nome"]
             else f"Molecola: {formula}"]
    fuori += [f"- {nota}" for nota in molecola["note"]]
    return fuori
