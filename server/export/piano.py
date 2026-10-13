"""Il piano cartesiano dei riassunti: dalla descrizione al disegno.

Perche' non basta Mermaid
    I grafici di Mermaid sono fatti per i dati: barre, linee che uniscono dei
    valori, torte. Una funzione disegnata cosi' non e' un grafico di
    matematica: gli assi non passano per l'origine, i punti si uniscono con
    segmenti dritti (una parabola con tre punti diventa una «V»), e una
    circonferenza non si puo' proprio fare. Per la matematica serve un piano
    cartesiano vero.

Come lo scrive il modello
    In un blocco ```piano, poche righe «chiave: valore»:

        titolo: Parabola e retta tangente
        x: -2, 6
        y: -3, 8
        curva: y = x^2 - 4x + 3
        curva: (x - 1)^2 + (y - 2)^2 = 9
        punto: V (2, -1)

    Le curve sono equazioni in x e y: y = f(x), x = g(y), oppure implicite
    (circonferenze, ellissi, iperboli).

    Per le definizioni, dove si ragiona con le lettere e non coi numeri:

        numeri: no                          assi e punti senza numeri
        curva d: y = -1 | direttrice        una curva col suo nome, e cosa
                                            scrivere nella legenda
        curva: y = a*x^2 per a = 1, 2, -1   una famiglia: una curva per valore
        segmento: P - F                     un segmento tratteggiato
        nota: $\\overline{PF} = \\overline{PH}$   una riga sotto il grafico

    Per l'analisi e le disequazioni:

        curva: y = x + 1 se x < 0           solo dove vale la condizione (a
                                            tratti); agli estremi il pallino
                                            pieno (<=) o vuoto (<)
        area: sotto y = x^2 da 0 a 2        fra la curva e l'asse x (integrale)
        area: tra y = x e y = x^2 da 0 a 1  fra due curve
        area: x^2 + y^2 <= 4                dove vale una disuguaglianza

    Per la trigonometria, l'algebra lineare e i numeri complessi:

        curva: x = cos(t), y = sin(t) con t da 0 a 2*pi    parametrica
        curva: r = 1 + cos(θ)               polare (θ da 0 a 2π, se non detto)
        vettore v: (2, 1)                   una freccia dall'origine
        vettore w: (1, 2) da P              da un punto; «vettore: A -> B»
        angolo α: da 0 a pi/3               l'arco dell'angolo (anche in gradi,
                                            «da 0° a 60°»), vertice «in P»
        tacche x: pi/2                      tacche a multipli di π: π/2, π…
        assi: Re, Im                        i nomi degli assi
        assi: no                            nessun asse (le forze su un corpo,
                                            un piano inclinato: disegni di
                                            fisica che non misurano niente)

    Per la geometria e per i campi:

        poligono: A, B, C | etichetta       un poligono colorato, coi lati
        lato: A - B | c                     un lato pieno col suo nome
        segmento: P - H | h                 tratteggiato, anche col nome
        angolo α: in A tra B e C            l'angolo fra due lati (retto: il
                                            quadratino)
        campo: (-y, x)                      un campo vettoriale: frecce
        campo: gradiente di x^2 + y^2       il gradiente di una funzione
        linea: da (1, 0)                    la linea di campo da un punto
        direzioni: y' = x - y               il campo di direzioni di un'equazione
        soluzione: da (0, 1)                la soluzione da un punto (Runge-Kutta)

    Per successioni, serie e integrali:

        successione: a_n = 1/n per n da 1 a 20     i termini, come punti
        serie: a_n = 1/n^2 per n da 1 a 20         le somme parziali S_n
        rettangoli: y = x^2 da 0 a 2 con n = 8 sinistra
                                            la somma di Riemann (sinistra,
                                            destra o medio), col suo valore

    Per la statistica:

        dati: (1, 2), (2, 3.5), (4, 4)      una nuvola di punti (dispersione),
                                            senza nomi ne' coordinate scritte
        istogramma: [0, 10) 4; [10, 20) 7   le classi e le loro frequenze; con
                                            classi di ampiezza diversa si
                                            disegna la densita' (frequenza /
                                            ampiezza), come va fatto
        boxplot A: 2, 5, 7, 9, 12           minimo, Q1, mediana, Q3, massimo;
                                            «con anomali 20, 25» per gli outlier

    I numeri servono comunque per disegnare: con «numeri: no» non si vedono,
    e restano solo i nomi. Qui si disegnano in SVG, dentro la
    pagina del PDF: nessuna libreria, nessuna rete. Chi legge vede il grafico
    e mai la descrizione; se la descrizione non si capisce il blocco si toglie
    (vedi leggi), non si mostra.

Le espressioni
    Si calcolano con numpy, ma non con eval libero: prima si controlla che
    l'espressione contenga solo numeri, x e y, le quattro operazioni, le
    potenze e poche funzioni note (vedi _controlla). Il testo viene da un
    modello, e non deve poter eseguire niente.
"""
from __future__ import annotations

import ast
import hashlib
import html
import math
import re

import numpy as np

# I colori delle curve: gli stessi dei grafici del PDF, verde in testa.
TINTE = ("#128a4b", "#2563eb", "#d97706", "#9333ea", "#dc2626", "#0891b2")

# Le funzioni che un'espressione puo' usare, e il loro corrispondente numpy.
_FUNZIONI = {
    "sqrt": np.sqrt, "sin": np.sin, "cos": np.cos, "tan": np.tan,
    "exp": np.exp, "log": np.log, "ln": np.log, "abs": np.abs,
    "asin": np.arcsin, "acos": np.arccos, "atan": np.arctan,
}
_COSTANTI = {"pi": math.pi, "e": math.e}

# Le chiavi che il modello potrebbe usare al posto di «curva».
_NOMI_CURVA = ("curva", "funzione", "retta", "parabola", "circonferenza",
               "ellisse", "iperbole", "asintoto")

# Il riquadro del disegno, in pixel: il massimo, e i margini per le etichette.
LARGHEZZA, ALTEZZA = 560, 420
MARGINE = 28


# ── Le espressioni ──────────────────────────────────────────────────────────

def _normalizza(testo: str) -> str:
    """Un'espressione scritta da una persona, in sintassi Python.

    «x^2 - 4x + 3» diventa «x**2 - 4*x + 3»: potenze col cappelletto, prodotti
    sottintesi fra un numero e una lettera o una parentesi, simboli tipografici
    al posto degli operatori.
    """
    t = testo.strip()
    for da, a in (("−", "-"), ("·", "*"), ("×", "*"), ("÷", "/"), ("√", "sqrt"),
                  ("π", "pi"), ("²", "^2"), ("³", "^3"), ("θ", "theta"),
                  ("°", "*pi/180")):
        t = t.replace(da, a)
    t = re.sub(r"(\d),(\d)", r"\1.\2", t)                    # 0,5 → 0.5
    t = t.replace("^", "**")
    t = re.sub(r"(\d)\s*([a-zA-Z(])", r"\1*\2", t)           # 4x, 2(x+1)
    t = re.sub(r"\)\s*([a-zA-Z0-9(])", r")*\1", t)           # (x+1)(x-1), (x)2
    t = re.sub(r"(?<![a-zA-Z_])([xy])\s*\(", r"\1*(", t)       # x(x-1)
    while re.search(r"(?<![a-zA-Z_])([xy])([xy])(?![a-zA-Z_(])", t):
        t = re.sub(r"(?<![a-zA-Z_])([xy])([xy])(?![a-zA-Z_(])", r"\1*\2", t)   # xy
    return t


_NODI = (ast.Expression, ast.BinOp, ast.UnaryOp, ast.Add, ast.Sub, ast.Mult,
         ast.Div, ast.Pow, ast.USub, ast.UAdd, ast.Constant, ast.Name, ast.Load,
         ast.Call)


def _controlla(albero: ast.AST, variabili: tuple[str, ...] = ("x", "y")) -> set[str]:
    """Le variabili usate, dopo aver controllato che l'espressione sia innocua.

    Solleva ValueError se c'e' qualcosa che non e' un numero, x, y, una
    costante nota, un'operazione o una delle funzioni ammesse.
    """
    usate: set[str] = set()
    for nodo in ast.walk(albero):
        if not isinstance(nodo, _NODI):
            raise ValueError(type(nodo).__name__)
        if isinstance(nodo, ast.Constant) and not isinstance(nodo.value, (int, float)):
            raise ValueError("costante")
        if isinstance(nodo, ast.Call):
            if not (isinstance(nodo.func, ast.Name) and nodo.func.id in _FUNZIONI) \
                    or nodo.keywords or len(nodo.args) != 1:
                raise ValueError("funzione")
        if isinstance(nodo, ast.Name):
            if nodo.id in variabili:
                usate.add(nodo.id)
            elif nodo.id not in _FUNZIONI and nodo.id not in _COSTANTI:
                raise ValueError(nodo.id)
    return usate


class _Espressione:
    """Un'espressione in x e y, controllata e pronta da calcolare."""

    def __init__(self, testo: str, variabili: tuple[str, ...] = ("x", "y")):
        albero = ast.parse(_normalizza(testo), mode="eval")
        self.usate = _controlla(albero, variabili)
        self._codice = compile(albero, "<piano>", "eval")

    def __call__(self, x=0.0, y=0.0, **altre):
        with np.errstate(all="ignore"):
            valore = eval(self._codice, {"__builtins__": {}},        # noqa: S307
                          {**_FUNZIONI, **_COSTANTI, "x": x, "y": y, **altre})
        return np.asarray(valore, dtype=float)


_CONFRONTI = {ast.Lt: np.less, ast.LtE: np.less_equal,
              ast.Gt: np.greater, ast.GtE: np.greater_equal}


class _Condizione:
    """Una condizione su x e y: «x < 0», «-1 <= x < 2», «x^2 + y^2 <= 4 e y > 0».

    Si scrive come in matematica: confronti anche in catena, uniti da «e» /
    «oppure». Ogni lato di un confronto e' un'espressione controllata come
    tutte le altre (vedi _Espressione).
    """

    def __init__(self, testo: str):
        t = testo.strip().replace("≤", "<=").replace("≥", ">=").replace("⩽", "<=").replace("⩾", ">=")
        # Ogni pezzo fra «e» e «oppure» e' una catena di confronti: i lati si
        # normalizzano uno per uno, cosi' le parole «and»/«or» non finiscono
        # dentro le regole dei prodotti sottintesi.
        pezzi = re.split(r"\s+(e|and|oppure|o|or)\s+", t)
        fuori = []
        for i, pezzo in enumerate(pezzi):
            if i % 2:
                fuori.append(" and " if pezzo in ("e", "and") else " or ")
                continue
            catena = re.split(r"(<=|>=|<|>)", pezzo)
            if len(catena) < 3:
                raise ValueError("condizione senza confronto")
            fuori.append("".join(c if k % 2 else "(" + _normalizza(c) + ")"
                                 for k, c in enumerate(catena)))
        self.albero = ast.parse("".join(fuori), mode="eval").body
        self.usate: set[str] = set()
        self._codici: dict[int, object] = {}
        self._prepara(self.albero)

    def _prepara(self, nodo):
        """Controlla la struttura e compila ogni lato dei confronti."""
        if isinstance(nodo, ast.BoolOp):
            for v in nodo.values:
                self._prepara(v)
        elif isinstance(nodo, ast.Compare):
            if not all(type(op) in _CONFRONTI for op in nodo.ops):
                raise ValueError("confronto")
            for lato in (nodo.left, *nodo.comparators):
                espressione = ast.Expression(body=lato)
                self.usate |= _controlla(espressione)
                self._codici[id(lato)] = compile(ast.fix_missing_locations(espressione),
                                                 "<piano>", "eval")
        else:
            raise ValueError("condizione")

    def _lato(self, nodo, x, y):
        with np.errstate(all="ignore"):
            return np.asarray(eval(self._codici[id(nodo)], {"__builtins__": {}},   # noqa: S307
                                   {**_FUNZIONI, **_COSTANTI, "x": x, "y": y}), dtype=float)

    def _valuta(self, nodo, x, y):
        if isinstance(nodo, ast.BoolOp):
            unisci = np.logical_and if isinstance(nodo.op, ast.And) else np.logical_or
            esito = self._valuta(nodo.values[0], x, y)
            for v in nodo.values[1:]:
                esito = unisci(esito, self._valuta(v, x, y))
            return esito
        esito = True
        sinistra = self._lato(nodo.left, x, y)
        for op, lato in zip(nodo.ops, nodo.comparators):
            destra = self._lato(lato, x, y)
            with np.errstate(all="ignore"):
                esito = np.logical_and(esito, _CONFRONTI[type(op)](sinistra, destra))
            sinistra = destra
        return esito

    def __call__(self, x=0.0, y=0.0):
        return self._valuta(self.albero, x, y)

    def estremi_x(self) -> list[tuple[float, bool]]:
        """I valori di x dove la condizione comincia o finisce, e se sono inclusi.

        «-1 <= x < 2» da' [(-1, True), (2, False)]: servono per i pallini
        pieni e vuoti agli estremi di una funzione a tratti.
        """
        fuori = []
        for nodo in ast.walk(self.albero):
            if not isinstance(nodo, ast.Compare):
                continue
            lati = [nodo.left, *nodo.comparators]
            for op, a, b in zip(nodo.ops, lati, lati[1:]):
                incluso = type(op) in (ast.LtE, ast.GtE)
                for var, valore in ((a, b), (b, a)):
                    if isinstance(var, ast.Name) and var.id == "x":
                        try:
                            v = float(self._lato(valore, 0.0, 0.0))
                        except (TypeError, ValueError):
                            continue
                        if math.isfinite(v) and not _usa_variabili(valore):
                            fuori.append((v, incluso))
        return fuori


def _usa_variabili(nodo) -> bool:
    """Vero se l'espressione contiene x o y."""
    return any(isinstance(n, ast.Name) and n.id in ("x", "y") for n in ast.walk(nodo))


# ── La descrizione ──────────────────────────────────────────────────────────

class _Curva:
    """Una curva: y = f(x), x = g(y), oppure F(x, y) = 0."""

    def __init__(self, testo: str, nome: str = "", etichetta: str = "",
                 parametro: str = "", condizione: str = ""):
        self.testo = testo.strip()
        # «se x < 0»: la curva c'e' solo dove vale, per le funzioni a tratti.
        self.condizione_testo = condizione.strip()
        self.condizione = _Condizione(condizione) if condizione.strip() else None
        self.nome = nome              # «d»: si scrive accanto alla curva
        self.etichetta = etichetta    # cosa dire nella legenda, se non l'equazione
        self.parametro = parametro    # «a = 2», per una curva di una famiglia
        if "=" in self.testo:
            if self.testo.count("=") != 1:
                raise ValueError("uguali")
            sinistra, destra = (s.strip() for s in self.testo.split("="))
        else:
            sinistra, destra = "y", self.testo
        a, b = _Espressione(sinistra), _Espressione(destra)
        if sinistra == "y" and "y" not in b.usate:
            self.tipo, self.f = "y", b
        elif destra == "y" and "y" not in a.usate:
            self.tipo, self.f = "y", a
        elif sinistra == "x" and "x" not in b.usate:
            self.tipo, self.f = "x", b
        elif destra == "x" and "x" not in a.usate:
            self.tipo, self.f = "x", a
        else:
            self.tipo = "implicita"
            self.f = lambda x=0.0, y=0.0: a(x, y) - b(x, y)


class _Parametrica:
    """Una curva data come x(t), y(t): parametrica, o polare r(θ).

    Ha gli stessi campi di _Curva che servono al disegno e alla legenda, cosi'
    il resto del codice la tratta come le altre.
    """

    def __init__(self, fx: str, fy: str, variabile: str, da: float, a: float,
                 testo: str, nome: str = "", etichetta: str = ""):
        self.fx = _Espressione(fx, ("x", "y", variabile))
        self.fy = _Espressione(fy, ("x", "y", variabile))
        if (self.fx.usate | self.fy.usate) - {variabile}:
            raise ValueError("una parametrica dipende solo dal suo parametro")
        self.variabile, self.da, self.a = variabile, da, a
        self.testo, self.nome, self.etichetta = testo.strip(), nome, etichetta
        self.tipo, self.parametro, self.condizione, self.condizione_testo = "parametrica", "", None, ""

    def tratti(self, xr, yr, n: int = 1500):
        """I tratti della curva, spezzata dove non esiste o dove salta."""
        t = np.linspace(self.da, self.a, n)
        xs = np.broadcast_to(self.fx(**{self.variabile: t}), t.shape)
        ys = np.broadcast_to(self.fy(**{self.variabile: t}), t.shape)
        salto = max(xr[1] - xr[0], yr[1] - yr[0]) * 2
        fuori, corrente = [], []
        for x, y in zip(xs, ys):
            buono = math.isfinite(x) and math.isfinite(y) and abs(x) < 1e9 and abs(y) < 1e9
            if buono and corrente and math.hypot(x - corrente[-1][0], y - corrente[-1][1]) > salto:
                buono = False
            if buono:
                corrente.append((float(x), float(y)))
            elif corrente:
                fuori.append(corrente)
                corrente = []
        if corrente:
            fuori.append(corrente)
        return fuori


def _parametrica(valore: str, nome: str, etichetta: str) -> _Parametrica | None:
    """La curva, se la riga e' una parametrica o una polare; None se no."""
    m = re.match(r"^x\s*=\s*(.+?)\s*[,;]\s*y\s*=\s*(.+?)\s+(?:con|per)\s+(t|theta|θ)"
                 r"\s+da\s+(.+?)\s+a\s+(.+)$", valore.strip())
    if m:
        var = "theta" if m.group(3) in ("theta", "θ") else "t"
        return _Parametrica(m.group(1), m.group(2), var, _numero(m.group(4)),
                            _numero(m.group(5)), valore, nome, etichetta)
    m = re.match(r"^r\s*=\s*(.+?)(?:\s+(?:con|per)\s+(t|theta|θ)\s+da\s+(.+?)\s+a\s+(.+))?$",
                 valore.strip())
    if m:
        var = "t" if m.group(2) == "t" else "theta"
        r = m.group(1)
        da, a = (_numero(m.group(3)), _numero(m.group(4))) if m.group(2) else (0.0, 2 * math.pi)
        return _Parametrica(f"({r})*cos({var})", f"({r})*sin({var})", var, da, a,
                            valore, nome, etichetta)
    return None


def _numero(testo: str) -> float:
    """Una coordinata: un numero, una frazione, sqrt(20)…"""
    e = _Espressione(testo)
    if e.usate:
        raise ValueError("variabile in una coordinata")
    valore = float(e())
    if not math.isfinite(valore):
        raise ValueError("coordinata")
    return valore


def _intervallo(testo: str) -> tuple[float, float] | None:
    """«-2, 6» → (-2.0, 6.0); None se non si legge o e' vuoto."""
    parti = re.split(r"[,;]|\.\.|\s+a\s+", testo)
    if len(parti) != 2:
        return None
    try:
        da, a = sorted((_numero(parti[0]), _numero(parti[1])))
    except (ValueError, SyntaxError):
        return None
    return (da, a) if a - da > 1e-9 else None


_NOME = r"[A-Za-zα-ωΑ-Ω][\w']*"


def _curve(valore: str, nome: str) -> list[_Curva]:
    """Le curve di una riga «curva:»: una sola, o una per valore del parametro.

    «y = a*x^2 per a = 1, 2, -1 | etichetta» diventa tre curve, con a
    sostituito dal suo valore. Il parametro si riconosce anche attaccato a x
    o y («ax^2»), come lo si scrive a mano.
    """
    valore, _, etichetta = valore.partition("|")
    parametrica = _parametrica(valore, nome, etichetta.strip())
    if parametrica:
        return [parametrica]
    parti = re.split(r"\s+se\s+", valore.strip(), maxsplit=1)
    valore, condizione = parti[0], (parti[1] if len(parti) > 1 else "")
    famiglia = re.match(r"^(.*?)\s+per\s+([a-df-wzA-Z])\s*=\s*(.+)$", valore.strip())
    if not famiglia:
        return [_Curva(valore, nome, etichetta.strip(), condizione=condizione)]
    equazione, lettera = famiglia.group(1), famiglia.group(2)
    dove = re.compile(rf"(?<![A-Za-z_]){lettera}(?=[xy]?(?![A-Za-z_(]))")
    fuori = []
    for testo in famiglia.group(3).split(","):
        v = _numero(testo)
        fuori.append(_Curva(dove.sub(f"({v!r})", equazione), nome, etichetta.strip(),
                            f"{lettera} = {_numero_bello(v)}", condizione))
        fuori[-1].testo_generale = equazione.strip()
    return fuori


class _Area:
    """Una zona da colorare: fra una curva e l'asse x, fra due curve, o dove
    vale una disuguaglianza."""

    def __init__(self, valore: str):
        valore, _, self.etichetta = (p.strip() for p in valore.partition("|"))
        self.testo = valore
        m = re.match(r"^(sotto|tra|fra)\s+(.+?)\s+da\s+(.+?)\s+a\s+(.+)$", valore, re.I)
        if m:
            if m.group(1).lower() == "sotto":
                curve = [_Curva(m.group(2)), _Curva("y = 0")]
            else:
                due = re.split(r"\s+e\s+", m.group(2), maxsplit=1)
                if len(due) != 2:
                    raise ValueError("area fra due curve")
                curve = [_Curva(due[0]), _Curva(due[1])]
            if any(c.tipo != "y" for c in curve):
                raise ValueError("area fra curve che non sono y = f(x)")
            self.tipo, self.curve = "fra", curve
            self.da, self.a = sorted((_numero(m.group(3)), _numero(m.group(4))))
        else:
            self.tipo, self.condizione = "zona", _Condizione(valore)

    def descrizione(self) -> str:
        """L'area detta a parole, per la legenda e per il testo."""
        if self.etichetta:
            return self.etichetta
        if self.tipo == "zona":
            return "dove " + _equazione_bella(self.testo)
        a, b = _numero_bello(self.da), _numero_bello(self.a)
        if self.curve[1].testo == "y = 0":
            return f"area sotto {_equazione_bella(self.curve[0].testo)} per x da {a} a {b}"
        return (f"area fra {_equazione_bella(self.curve[0].testo)} e "
                f"{_equazione_bella(self.curve[1].testo)} per x da {a} a {b}")


def leggi(testo: str) -> dict | None:
    """La descrizione di un piano, o None se non si puo' disegnare.

    Basta una riga sbagliata per buttare tutto: un grafico con una curva in
    meno direbbe una cosa diversa da quella che il testo spiega.
    """
    piano = {"titolo": "", "x": None, "y": None, "numeri": True, "curve": [],
             "punti": [], "segmenti": [], "note": [], "aree": [], "vettori": [],
             "angoli": [], "tacche": {}, "assi": ("x", "y")}
    # Vettori e angoli possono nominare punti scritti piu' sotto: si
    # risolvono alla fine.
    vettori_da_fare, angoli_da_fare = [], []
    poligoni_da_fare, traiettorie_da_fare = [], []
    piano["poligoni"], piano["campi"] = [], []
    piano["successioni"], piano["rettangoli"] = [], []
    piano["dati"], piano["istogrammi"], piano["boxplot"] = [], [], []
    for riga in testo.splitlines():
        riga = riga.strip()
        if not riga:
            continue
        # «chiave: valore», oppure «curva d: valore» con il nome della curva.
        # Il nome puo' anche cominciare con una cifra: «boxplot 3A».
        m = re.match(r"^([a-zA-Zàèéìòù]+)(?:\s+([\wα-ωΑ-Ω][\w']*))?\s*:\s*(.+)$", riga)
        if not m:
            return None
        chiave, nome, valore = m.group(1).lower(), m.group(2) or "", m.group(3).strip()
        try:
            if chiave == "titolo":
                piano["titolo"] = valore
            elif chiave in ("x", "y"):
                piano[chiave] = _intervallo(valore)
            elif chiave == "numeri":
                piano["numeri"] = valore.lower() not in ("no", "nessuno", "false", "0")
            elif chiave in _NOMI_CURVA:
                piano["curve"] += _curve(valore, nome)
            elif chiave == "punto":
                p = re.match(rf"^({_NOME})?\s*\(\s*(.+?)\s*[,;]\s*(.+?)\s*\)$", valore)
                if not p:
                    return None
                piano["punti"].append((p.group(1) or "", _numero(p.group(2)), _numero(p.group(3))))
            elif chiave in ("segmento", "lato"):
                # «segmento» e' tratteggiato (una proiezione, una distanza),
                # «lato» e' pieno (il lato di una figura). Dopo «|» il nome.
                estremi, _, etichetta = (t.strip() for t in valore.partition("|"))
                p = re.match(rf"^({_NOME})\s*[-–,]\s*({_NOME})$", estremi) \
                    or re.match(r"^([A-Z])([A-Z])$", estremi)
                if not p:
                    return None
                piano["segmenti"].append((p.group(1), p.group(2), etichetta, chiave == "lato"))
            elif chiave in ("poligono", "triangolo", "quadrilatero"):
                poligoni_da_fare.append((nome, valore))
            elif chiave in ("campo", "direzioni"):
                piano["campi"].append(_Campo(valore))
            elif chiave in ("successione", "serie"):
                piano["successioni"].append(_Successione(valore, chiave == "serie"))
            elif chiave in ("rettangoli", "riemann"):
                piano["rettangoli"].append(_Rettangoli(valore))
            elif chiave in ("dati", "dispersione"):
                piano["dati"].append(_Dati(valore))
            elif chiave == "istogramma":
                piano["istogrammi"].append(_Istogramma(valore))
            elif chiave in ("boxplot", "box"):
                piano["boxplot"].append(_Boxplot(valore, nome))
            elif chiave in ("soluzione", "linea"):
                traiettorie_da_fare.append((chiave, nome, valore))
            elif chiave == "nota":
                piano["note"].append(valore)
            elif chiave in ("area", "zona", "regione"):
                piano["aree"].append(_Area(valore))
            elif chiave == "vettore":
                vettori_da_fare.append((nome, valore))
            elif chiave == "angolo":
                angoli_da_fare.append((nome, valore))
            elif chiave == "tacche":
                if nome not in ("x", "y"):
                    return None
                passo = _numero(valore)
                if passo <= 0:
                    return None
                piano["tacche"][nome] = (passo, "pi" in valore or "π" in valore)
            elif chiave == "assi" and valore.lower() in ("no", "nessuno", "senza"):
                # Un disegno di fisica (le forze su un corpo, un piano
                # inclinato) non misura niente: gli assi confonderebbero.
                piano["senza_assi"] = True
            elif chiave == "assi":
                nomi_assi = [n.strip() for n in re.split(r"[,;]", valore)]
                if len(nomi_assi) != 2 or not all(nomi_assi):
                    return None
                piano["assi"] = tuple(nomi_assi)
            else:
                return None
        except (ValueError, SyntaxError, TypeError, ZeroDivisionError):
            return None
    # Un segmento fra punti che non ci sono non si sa dove disegnarlo.
    nomi = {n for n, _x, _y in piano["punti"] if n}
    if any(a not in nomi or b not in nomi for a, b, *_resto in piano["segmenti"]):
        return None
    posto = {n: (x, y) for n, x, y in piano["punti"] if n}
    try:
        piano["vettori"] = [_vettore(n, v, posto) for n, v in vettori_da_fare]
        piano["angoli"] = [_angolo(n, v, posto) for n, v in angoli_da_fare]
        piano["poligoni"] = [_poligono(n, v, posto) for n, v in poligoni_da_fare]
        piano["curve"] += [_traiettoria(c, n, v, piano["campi"], posto)
                           for c, n, v in traiettorie_da_fare]
    except (ValueError, SyntaxError, TypeError, ZeroDivisionError, KeyError):
        return None
    if not (piano["curve"] or piano["punti"] or piano["aree"] or piano["vettori"]
            or piano["poligoni"] or piano["campi"] or piano["successioni"]
            or piano["rettangoli"] or _statistica(piano)):
        return None
    return piano


def _statistica(piano: dict) -> bool:
    """Vero se nel piano ci sono dati, istogrammi o boxplot."""
    return bool(piano.get("dati") or piano.get("istogrammi") or piano.get("boxplot"))


class _Dati:
    """Una nuvola di punti: i dati di un grafico di dispersione."""

    def __init__(self, valore: str):
        valore, _, self.etichetta = (t.strip() for t in valore.partition("|"))
        punti = [_dove(p, {}) for p in _dividi(valore)]
        if not 2 <= len(punti) <= 2000:
            raise ValueError("dati")
        self.xs, self.ys = [p[0] for p in punti], [p[1] for p in punti]
        self.testo = valore

    def descrizione(self) -> str:
        return self.etichetta or f"dati ({len(self.xs)} osservazioni)"


class _Istogramma:
    """Le classi di un istogramma e le loro frequenze.

    L'area di ogni barra dev'essere proporzionale alla frequenza: con classi
    tutte larghe uguali l'altezza e' la frequenza, con classi diverse e' la
    densita' (frequenza / ampiezza). Il conto si fa qui e non lo si chiede al
    modello, che le divisioni le sbaglia.
    """

    _CLASSE = re.compile(r"^[\[(]\s*([^,\])]+?)\s*,\s*([^\])]+?)\s*[\])]\s*[:=]?\s*(.+)$")

    def __init__(self, valore: str):
        valore, _, self.etichetta = (t.strip() for t in valore.partition("|"))
        classi = []
        for pezzo in (p.strip() for p in valore.split(";")):
            if not pezzo:
                continue
            m = self._CLASSE.match(pezzo)
            if not m:
                raise ValueError("classe")
            a, b, f = _numero(m.group(1)), _numero(m.group(2)), _numero(m.group(3))
            if b <= a or f < 0:
                raise ValueError("classe")
            classi.append((a, b, f))
        if not 1 <= len(classi) <= 60:
            raise ValueError("istogramma")
        classi.sort()
        if any(c[0] < p[1] - 1e-9 for p, c in zip(classi, classi[1:])):
            raise ValueError("classi sovrapposte")
        ampiezze = [b - a for a, b, _f in classi]
        self.densita = max(ampiezze) - min(ampiezze) > 1e-9 * max(ampiezze)
        self.classi = classi
        self.altezze = [f / (b - a) if self.densita else f for a, b, f in classi]
        self.testo = valore

    def descrizione(self) -> str:
        if self.etichetta:
            return self.etichetta
        return ("istogramma: altezza = frequenza / ampiezza della classe" if self.densita
                else "istogramma delle frequenze")


class _Boxplot:
    """Un diagramma a scatola: minimo, Q1, mediana, Q3, massimo, e gli anomali."""

    def __init__(self, valore: str, nome: str = ""):
        valore, _, self.etichetta = (t.strip() for t in valore.partition("|"))
        m = re.match(r"^(.+?)(?:\s+(?:con\s+)?(?:anomali|outlier)\s*:?\s*(.+))?$", valore, re.I)
        numeri = [_numero(v) for v in _dividi(m.group(1))]
        if len(numeri) != 5 or any(a > b for a, b in zip(numeri, numeri[1:])):
            raise ValueError("boxplot: servono minimo, Q1, mediana, Q3 e massimo in ordine")
        self.minimo, self.q1, self.mediana, self.q3, self.massimo = numeri
        self.anomali = [_numero(v) for v in _dividi(m.group(2))] if m.group(2) else []
        self.nome, self.testo = nome, valore

    def descrizione(self) -> str:
        if self.etichetta:
            return self.etichetta
        n = _numero_bello
        testa = f"{self.nome}: " if self.nome else ""
        fuori = (f"{testa}min {n(self.minimo)} · Q1 {n(self.q1)} · Me {n(self.mediana)} · "
                 f"Q3 {n(self.q3)} · max {n(self.massimo)}")
        if self.anomali:
            fuori += " · anomali " + ", ".join(n(v) for v in self.anomali)
        return fuori


class _Successione:
    """I termini a_n per n da n0 a n1, oppure le somme parziali S_n di una serie."""

    def __init__(self, valore: str, serie: bool):
        valore, _, self.etichetta = (t.strip() for t in valore.partition("|"))
        m = re.match(r"^(?:([a-zA-Z])_?n\s*=\s*)?(.+?)\s+per\s+n\s+da\s+(.+?)\s+a\s+(.+)$", valore)
        if not m:
            raise ValueError("successione")
        self.nome = m.group(1) or "a"
        self.espressione = m.group(2)
        f = _Espressione(self.espressione, ("n",))
        n0, n1 = int(round(_numero(m.group(3)))), int(round(_numero(m.group(4))))
        if not 0 <= n1 - n0 <= 500:
            raise ValueError("troppi termini")
        self.n = np.arange(n0, n1 + 1, dtype=float)
        valori = np.array(np.broadcast_to(f(n=self.n), self.n.shape), dtype=float)
        self.serie = serie
        self.valori = np.cumsum(valori) if serie else valori
        self.testo = valore

    def descrizione(self) -> str:
        if self.etichetta:
            return self.etichetta
        a = f"{self.nome}ₙ = {_equazione_bella(self.espressione)}"
        return f"somme parziali di Σ {a}" if self.serie else a


class _Rettangoli:
    """La somma di Riemann di y = f(x) fra a e b, con n rettangoli."""

    def __init__(self, valore: str):
        valore, _, self.etichetta = (t.strip() for t in valore.partition("|"))
        m = re.match(r"^(?:sotto\s+)?(.+?)\s+da\s+(.+?)\s+a\s+(.+?)\s+con\s+(?:n\s*=\s*)?(\d+)"
                     r"(?:\s+rettangoli)?(?:\s+(sinistr[ao]|destr[ao]|medi[ao]|centr[ao]))?$",
                     valore, re.I)
        if not m:
            raise ValueError("rettangoli")
        self.curva = _Curva(m.group(1))
        if self.curva.tipo != "y":
            raise ValueError("rettangoli sotto una curva che non e' y = f(x)")
        self.a, self.b = _numero(m.group(2)), _numero(m.group(3))
        self.n = int(m.group(4))
        if not 1 <= self.n <= 200 or self.b <= self.a:
            raise ValueError("rettangoli")
        self.metodo = {"s": "sinistra", "d": "destra"}.get((m.group(5) or "m")[0].lower(), "medio")
        larghezza = (self.b - self.a) / self.n
        sinistri = self.a + np.arange(self.n) * larghezza
        dove = sinistri + {"sinistra": 0, "destra": larghezza, "medio": larghezza / 2}[self.metodo]
        self.sinistri, self.larghezza = sinistri, larghezza
        self.altezze = np.array(np.broadcast_to(self.curva.f(x=dove), dove.shape), dtype=float)
        if not np.isfinite(self.altezze).all():
            raise ValueError("la funzione non esiste in un punto dei rettangoli")
        self.somma = float(self.altezze.sum() * larghezza)
        self.testo = valore

    def descrizione(self) -> str:
        if self.etichetta:
            return self.etichetta
        punto = {"sinistra": "estremo sinistro", "destra": "estremo destro", "medio": "punto medio"}
        return (f"somma di Riemann con n = {self.n} ({punto[self.metodo]}) ≈ "
                f"{_numero_bello(round(self.somma, 3))}")


def _dividi(testo: str) -> list[str]:
    """Le parti di un elenco separate da virgole, senza spezzare le parentesi:
    «A, (1, 2), C» da' tre parti."""
    parti, livello, corrente = [], 0, ""
    for c in testo:
        if c == "," and livello == 0:
            parti.append(corrente.strip())
            corrente = ""
            continue
        livello += (c == "(") - (c == ")")
        corrente += c
    parti.append(corrente.strip())
    return [p for p in parti if p]


def _poligono(nome: str, valore: str, posto: dict) -> tuple:
    """(nome, vertici, etichetta) da «A, B, C» o da coordinate."""
    vertici, _, etichetta = (t.strip() for t in valore.partition("|"))
    lista = _dividi(vertici)
    if len(lista) == 1 and re.fullmatch(r"[A-Z]{3,}", lista[0]):
        lista = list(lista[0])                           # «ABC»
    if len(lista) < 3:
        raise ValueError("poligono con meno di tre vertici")
    return (nome, [_dove(v, posto) for v in lista], etichetta, lista)


class _Campo:
    """Un campo vettoriale (P, Q), il gradiente di una funzione, o il campo di
    direzioni di un'equazione differenziale y' = f(x, y)."""

    def __init__(self, valore: str):
        valore, _, self.etichetta = (t.strip() for t in valore.partition("|"))
        self.testo = valore
        m = re.match(r"^(?:y'|dy/dx)\s*=\s*(.+)$", valore)
        if m:
            self.tipo, self.f = "direzioni", _Espressione(m.group(1))
            return
        m = re.match(r"^gradiente\s+di\s+(.+)$", valore, re.I)
        if m:
            f = _Espressione(m.group(1))

            def derivata(x, y, dx, dy):
                h = 1e-4 * (1 + np.abs(x) + np.abs(y))
                return (f(x=x + dx * h, y=y + dy * h) - f(x=x - dx * h, y=y - dy * h)) / (2 * h)
            self.tipo = "vettori"
            self.P = lambda x, y: derivata(x, y, 1, 0)
            self.Q = lambda x, y: derivata(x, y, 0, 1)
            return
        m = re.match(r"^(?:F\s*=\s*)?\((.+)\)$", valore)
        parti = _dividi(m.group(1)) if m else []
        if len(parti) != 2:
            raise ValueError("campo")
        p, q = _Espressione(parti[0]), _Espressione(parti[1])
        self.tipo = "vettori"
        self.P = lambda x, y: p(x=x, y=y)
        self.Q = lambda x, y: q(x=x, y=y)

    def descrizione(self) -> str:
        if self.etichetta:
            return self.etichetta
        if self.tipo == "direzioni":
            return "direzioni di " + _equazione_bella(self.testo)
        return "campo " + _equazione_bella(self.testo)


class _Traiettoria:
    """Una soluzione di y' = f(x, y), o una linea di un campo, da un punto.

    Si calcola col metodo di Runge-Kutta del quarto ordine, in avanti e
    all'indietro dal punto di partenza, finche' resta vicino al riquadro.
    Per il disegno e la legenda e' una curva come le altre.
    """

    def __init__(self, campo: _Campo, x0: float, y0: float, testo: str, nome: str,
                 etichetta: str):
        self.campo, self.x0, self.y0 = campo, x0, y0
        self.testo, self.nome, self.etichetta = testo, nome, etichetta
        self.tipo, self.parametro, self.condizione, self.condizione_testo = "parametrica", "", None, ""

    def tratti(self, xr, yr):
        ax, ay = xr[1] - xr[0], yr[1] - yr[0]

        def lontano(x, y):
            return (not (math.isfinite(x) and math.isfinite(y))
                    or not (xr[0] - ax <= x <= xr[1] + ax and yr[0] - 2 * ay <= y <= yr[1] + 2 * ay))

        if self.campo.tipo == "direzioni":
            f = lambda x, y: float(self.campo.f(x=x, y=y))                   # noqa: E731
            h = ax / 600
            rami = []
            for verso in (1, -1):
                x, y, ramo = self.x0, self.y0, [(self.x0, self.y0)]
                while xr[0] <= x <= xr[1] and len(ramo) < 2000:
                    k1 = f(x, y)
                    k2 = f(x + verso * h / 2, y + verso * h / 2 * k1)
                    k3 = f(x + verso * h / 2, y + verso * h / 2 * k2)
                    k4 = f(x + verso * h, y + verso * h * k3)
                    y += verso * h / 6 * (k1 + 2 * k2 + 2 * k3 + k4)
                    x += verso * h
                    if lontano(x, y):
                        break
                    ramo.append((x, y))
                rami.append(ramo)
            return [rami[1][::-1] + rami[0][1:]]
        # Una linea di campo: si segue la direzione del campo, a passi uguali.
        passo = math.hypot(ax, ay) / 500

        def direzione(x, y):
            p, q = float(self.campo.P(x, y)), float(self.campo.Q(x, y))
            n = math.hypot(p, q)
            return (p / n, q / n) if n > 1e-12 and math.isfinite(n) else None

        rami = []
        for verso in (1, -1):
            x, y, ramo = self.x0, self.y0, [(self.x0, self.y0)]
            for i in range(3000):
                d1 = direzione(x, y)
                if not d1:
                    break
                d2 = direzione(x + verso * passo / 2 * d1[0], y + verso * passo / 2 * d1[1])
                if not d2:
                    break
                x += verso * passo * d2[0]
                y += verso * passo * d2[1]
                if lontano(x, y):
                    break
                ramo.append((x, y))
                # Una linea chiusa (un'orbita) torna al punto di partenza.
                if i > 30 and math.hypot(x - self.x0, y - self.y0) < passo * 1.5:
                    ramo.append((self.x0, self.y0))
                    return [ramo]
            rami.append(ramo)
        return [rami[1][::-1] + rami[0][1:]]


def _traiettoria(chiave: str, nome: str, valore: str, campi: list, posto: dict) -> _Traiettoria:
    """La soluzione o la linea di campo di una riga «soluzione:» / «linea:»."""
    valore, _, etichetta = (t.strip() for t in valore.partition("|"))
    m = re.match(r"^(?:(.+?)\s+)?da\s+(.+)$", valore)
    if not m:
        raise ValueError("traiettoria")
    x0, y0 = _dove(m.group(2), posto)
    if m.group(1):
        campo = _Campo(m.group(1))
    else:
        adatti = [c for c in campi if (c.tipo == "direzioni") == (chiave == "soluzione")]
        if not adatti:
            raise ValueError("soluzione senza equazione")
        campo = adatti[-1]
    punto = f"({_numero_bello(x0)}, {_numero_bello(y0)})"
    testo = (f"soluzione per {punto}" if chiave == "soluzione" else f"linea di campo per {punto}")
    return _Traiettoria(campo, x0, y0, testo, nome, etichetta)


def _dove(testo: str, posto: dict) -> tuple[float, float]:
    """Un punto: il nome di un punto gia' scritto, o le coordinate «(x, y)»."""
    testo = testo.strip()
    if testo in posto:
        return posto[testo]
    m = re.match(r"^\(\s*(.+?)\s*[,;]\s*(.+?)\s*\)$", testo)
    if not m:
        raise KeyError(testo)
    return _numero(m.group(1)), _numero(m.group(2))


def _vettore(nome: str, valore: str, posto: dict) -> tuple:
    """(nome, x0, y0, x1, y1) da «A -> B», «(2, 1)» o «(2, 1) da P»."""
    freccia = re.match(r"^(.+?)\s*(?:->|→)\s*(.+)$", valore)
    if freccia:
        (x0, y0), (x1, y1) = _dove(freccia.group(1), posto), _dove(freccia.group(2), posto)
        return (nome or f"{freccia.group(1).strip()}{freccia.group(2).strip()}", x0, y0, x1, y1)
    m = re.match(r"^(\(.+?\))(?:\s+da\s+(.+))?$", valore)
    if not m:
        raise ValueError("vettore")
    dx, dy = _dove(m.group(1), {})
    x0, y0 = _dove(m.group(2), posto) if m.group(2) else (0.0, 0.0)
    return (nome, x0, y0, x0 + dx, y0 + dy)


def _angolo(nome: str, valore: str, posto: dict) -> tuple:
    """(nome, xv, yv, da, a): l'angolo da «da» ad «a», in radianti, col vertice.

    «in A tra B e C» e' l'angolo nel vertice A fra i lati AB e AC: quello
    minore di un angolo piatto, come in un triangolo.
    """
    tra = re.match(r"^in\s+(.+?)\s+tra\s+(.+?)\s+e\s+(.+)$", valore)
    if tra:
        (xv, yv), (xb, yb), (xc, yc) = (_dove(tra.group(k), posto) for k in (1, 2, 3))
        a1, a2 = math.atan2(yb - yv, xb - xv), math.atan2(yc - yv, xc - xv)
        if (a2 - a1) % (2 * math.pi) > math.pi:
            a1, a2 = a2, a1
        return (nome, xv, yv, a1, a2)
    m = re.match(r"^da\s+(.+?)\s+a\s+(.+?)(?:\s+in\s+(.+))?$", valore)
    if not m:
        raise ValueError("angolo")
    xv, yv = _dove(m.group(3), posto) if m.group(3) else (0.0, 0.0)
    return (nome, xv, yv, _numero(m.group(1)), _numero(m.group(2)))


# ── I conti del disegno ─────────────────────────────────────────────────────

def _passo(ampiezza: float) -> float:
    """Il passo delle tacche: 1, 2 o 5 per una potenza di dieci, circa 8 tacche."""
    grezzo = ampiezza / 8
    potenza = 10 ** math.floor(math.log10(grezzo))
    for fattore in (1, 2, 5, 10):
        if grezzo <= fattore * potenza:
            return fattore * potenza
    return 10 * potenza


def _campiona(curva: _Curva, xr, yr, n: int = 700):
    """I tratti di una curva: liste di punti (x, y) da unire con una linea.

    Una funzione si spezza dove non esiste o dove salta (un asintoto), per non
    tirare una riga verticale da +infinito a -infinito.
    """
    if curva.tipo == "parametrica":
        return curva.tratti(xr, yr)
    tratti: list[list[tuple[float, float]]] = []
    if curva.tipo in ("y", "x"):
        lungo = xr if curva.tipo == "y" else yr
        altro = yr if curva.tipo == "y" else xr
        t = np.linspace(lungo[0], lungo[1], n)
        if curva.condizione and curva.tipo == "y":
            # Campioni anche proprio sugli estremi dei tratti, un soffio dentro
            # e fuori: senza, un tratto finirebbe un po' prima del suo estremo.
            eps = (lungo[1] - lungo[0]) * 1e-6
            extra = [v + d for v, _i in curva.condizione.estremi_x() for d in (-eps, 0, eps)]
            t = np.unique(np.concatenate([t, [e for e in extra if lungo[0] <= e <= lungo[1]]]))
            n = len(t)
        v = curva.f(x=t) if curva.tipo == "y" else curva.f(y=t)
        v = np.array(np.broadcast_to(v, t.shape), dtype=float)
        if curva.condizione:
            vale = curva.condizione(x=t, y=v) if curva.tipo == "y" else curva.condizione(x=v, y=t)
            v[~np.broadcast_to(vale, t.shape)] = np.nan
        salto = (altro[1] - altro[0]) * 2
        corrente: list[tuple[float, float]] = []
        for i in range(n):
            buono = math.isfinite(v[i]) and abs(v[i]) < 1e9
            if buono and corrente and abs(v[i] - corrente[-1][1 if curva.tipo == "y" else 0]) > salto:
                buono = False
            if buono:
                corrente.append((t[i], v[i]) if curva.tipo == "y" else (v[i], t[i]))
            elif corrente:
                tratti.append(corrente)
                corrente = []
        if corrente:
            tratti.append(corrente)
        return tratti
    return _contorno(curva.f, xr, yr, condizione=curva.condizione)


def _contorno(f, xr, yr, n: int = 260, condizione=None):
    """I segmenti dove F(x, y) = 0, col metodo dei quadratini (marching squares).

    Si divide il riquadro in una griglia fitta e, in ogni quadratino dove F
    cambia segno, si traccia il pezzetto di curva che lo attraversa,
    interpolando sui lati. Ne escono tanti segmenti corti: disegnati insieme
    fanno la curva.
    """
    xs = np.linspace(xr[0], xr[1], n)
    ys = np.linspace(yr[0], yr[1], n)
    gx, gy = np.meshgrid(xs, ys)
    v = np.broadcast_to(f(x=gx, y=gy), gx.shape).astype(float)
    if condizione:
        v = v.copy()
        v[~np.broadcast_to(condizione(x=gx, y=gy), gx.shape)] = np.nan
    segmenti = []

    def taglio(i1, j1, i2, j2):
        a, b = v[i1, j1], v[i2, j2]
        t = a / (a - b) if a != b else 0.5
        return (xs[j1] + t * (xs[j2] - xs[j1]), ys[i1] + t * (ys[i2] - ys[i1]))

    for i in range(n - 1):
        for j in range(n - 1):
            angoli = (v[i, j], v[i, j + 1], v[i + 1, j + 1], v[i + 1, j])
            if not all(map(math.isfinite, angoli)):
                continue
            segni = [a > 0 for a in angoli]
            if all(segni) or not any(segni):
                continue
            lati = []
            for (i1, j1), (i2, j2) in (((i, j), (i, j + 1)), ((i, j + 1), (i + 1, j + 1)),
                                       ((i + 1, j + 1), (i + 1, j)), ((i + 1, j), (i, j))):
                if (v[i1, j1] > 0) != (v[i2, j2] > 0):
                    lati.append(taglio(i1, j1, i2, j2))
            # Due lati tagliati: un segmento. Quattro (un punto di sella): due.
            for k in range(0, len(lati) - 1, 2):
                segmenti.append([lati[k], lati[k + 1]])
    return segmenti


def _solo_boxplot(piano: dict) -> bool:
    """Vero se il piano ha soltanto boxplot: l'asse verticale non misura niente."""
    altro = ("curve", "punti", "aree", "vettori", "poligoni", "campi", "successioni",
             "rettangoli", "dati", "istogrammi")
    return bool(piano.get("boxplot")) and not any(piano.get(k) for k in altro)


def _intervalli_statistici(piano: dict) -> tuple[tuple, tuple]:
    """Gli intervalli attorno ai dati, per un piano di statistica.

    Qui lo zero non si include per forza: le altezze di una classe vanno da
    150 a 190 cm, e un asse da 0 schiaccerebbe tutto in un angolo. Lo zero
    resta sull'asse verticale di un istogramma, perche' le barre partono da li'.
    """
    xs = [p[1] for p in piano["punti"]]
    ys = [p[2] for p in piano["punti"]]
    for d in piano["dati"]:
        xs += d.xs
        ys += d.ys
    for ist in piano["istogrammi"]:
        xs += [ist.classi[0][0], ist.classi[-1][1]]
        ys += [0.0, max(ist.altezze)]
    for k, b in enumerate(piano["boxplot"]):
        xs += [b.minimo, b.massimo, *b.anomali]
        ys += [k + 0.4, k + 1.6]

    def largo(valori, quota):
        da, a = min(valori), max(valori)
        margine = (a - da) * quota or abs(da) * 0.1 or 1.0
        return da - margine, a + margine

    xr = piano["x"] or largo(xs, 0.06)
    if piano["y"]:
        return xr, piano["y"]
    for c in piano["curve"]:
        if c.tipo == "y":
            v = np.broadcast_to(c.f(x=np.linspace(xr[0], xr[1], 200)), (200,))
            ys += [float(t) for t in v[np.isfinite(v)]]
    if _solo_boxplot(piano):
        return xr, (0.0, len(piano["boxplot"]) + 1.0)
    da, a = largo(ys, 0.1)
    if piano["istogrammi"] and min(ys) >= 0:
        da = -(a - da) * 0.03
    return xr, (da, a)


def _intervalli_automatici(piano: dict) -> tuple[tuple, tuple]:
    """Gli intervalli da mostrare, quando il modello non li ha scritti."""
    if _statistica(piano) and not (piano["x"] and piano["y"]):
        return _intervalli_statistici(piano)
    xs = [p[1] for p in piano["punti"]] + [0.0]
    ys = [p[2] for p in piano["punti"]] + [0.0]
    for succ in piano.get("successioni", []):
        buoni = np.isfinite(succ.valori)
        xs += [float(succ.n[0]) - 1, float(succ.n[-1]) + 1]
        ys += [float(v) for v in succ.valori[buoni]]
    for r in piano.get("rettangoli", []):
        xs += [r.a, r.b]
        ys += [float(v) for v in r.altezze]
    if piano.get("successioni") and not piano["x"]:
        return ((min(xs), max(xs)), piano["y"] or (min(ys) - 0.1 * (max(ys) - min(ys) or 1),
                                                   max(ys) + 0.1 * (max(ys) - min(ys) or 1)))
    xr = piano["x"] or (min(xs) - 3, max(xs) + 3)
    if piano["y"]:
        return xr, piano["y"]
    valori = list(ys)
    for c in piano["curve"]:
        if c.tipo == "y":
            v = np.broadcast_to(c.f(x=np.linspace(xr[0], xr[1], 200)), (200,))
            v = v[np.isfinite(v)]
            if v.size:
                valori += [float(np.percentile(v, 5)), float(np.percentile(v, 95))]
    return xr, (min(valori) - 1, max(valori) + 1)


# ── Il disegno ──────────────────────────────────────────────────────────────

def _numero_bello(v: float) -> str:
    """Un numero per un'etichetta: 2 e non 2.0, −1 col meno tipografico."""
    testo = f"{v:.2f}".rstrip("0").rstrip(".") if abs(v - round(v)) > 1e-9 else str(int(round(v)))
    return testo.replace("-", "−")


def _equazione_bella(testo: str) -> str:
    """L'equazione come la si legge: x² e non x^2, il meno tipografico."""
    apici = str.maketrans("0123456789", "⁰¹²³⁴⁵⁶⁷⁸⁹")
    # «^2» e «^(2)»: la parentesi di chiusura si toglie solo se c'era quella
    # di apertura, o «√(4 - y^2)» perderebbe la sua.
    t = re.sub(r"\^(?:\((\d+)\)|(\d+))",
               lambda m: (m.group(1) or m.group(2)).translate(apici), testo)
    t = t.replace("sqrt", "√").replace("<=", "≤").replace(">=", "≥").replace("theta", "θ")
    t = re.sub(r"(?<![A-Za-z])pi(?![A-Za-z])", "π", t)
    t = re.sub(r"\^n(?![A-Za-z])", "ⁿ", t)                   # (−1)^n
    t = re.sub(r"(?<=[A-Za-z])_n(?![A-Za-z])", "ₙ", t)       # a_n
    t = re.sub(r"(\d)\s*\*\s*π", r"\1π", t).replace("*", "·")
    return re.sub(r"(?<=[\s(])-|^-", "−", t).replace(" - ", " − ")


def svg(piano: dict) -> str:
    """Il piano disegnato: SVG, con titolo e legenda in HTML intorno."""
    xr, yr = _intervalli_automatici(piano)
    ax, ay = xr[1] - xr[0], yr[1] - yr[0]
    # Stessa scala sui due assi quando si puo': una circonferenza deve restare
    # rotonda. Se gli intervalli sono troppo diversi si rinuncia, o il disegno
    # diventerebbe una striscia.
    if 1 / 2.5 <= ax / ay <= 2.5:
        scala = min(LARGHEZZA / ax, ALTEZZA / ay)
        sx = sy = scala
    else:
        sx, sy = LARGHEZZA / ax, ALTEZZA * 0.8 / ay
    w, h = ax * sx, ay * sy
    W, H = w + 2 * MARGINE, h + 2 * MARGINE

    def px(x):
        return MARGINE + (x - xr[0]) * sx

    def py(y):
        return MARGINE + (yr[1] - y) * sy

    # Nomi propri per il riquadro e la freccia: in una pagina con piu' piani,
    # nomi uguali farebbero tagliare ogni curva al riquadro del primo.
    uid = "p" + hashlib.sha1(repr((piano["titolo"], xr, yr, [c.testo for c in piano["curve"]],
                                   piano["punti"], piano["segmenti"], piano["vettori"],
                                   [c.testo for c in piano["campi"]],
                                   [p[1] for p in piano["poligoni"]],
                                   [a.testo for a in piano["aree"]],
                                   [s.testo for s in piano["dati"] + piano["istogrammi"]
                                    + piano["boxplot"]])).encode("utf-8")).hexdigest()[:8]
    solo_boxplot = _solo_boxplot(piano)
    senza_assi = piano.get("senza_assi", False)

    parti = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W:.0f} {H:.0f}" '
             f'width="{W:.0f}" height="{H:.0f}" font-family="Segoe UI, Arial, sans-serif" '
             f'font-size="11">',
             f'<defs><clipPath id="{uid}r"><rect x="{MARGINE}" y="{MARGINE}" '
             f'width="{w:.1f}" height="{h:.1f}"/></clipPath>'
             f'<marker id="{uid}f" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" '
             'markerHeight="7" orient="auto"><path d="M0,0 L10,5 L0,10 z" fill="#333"/></marker>'
             '</defs>']

    # La griglia e le tacche. Senza numeri niente griglia: in una definizione
    # conta la forma, e una quadrettatura farebbe cercare dei valori.
    ox = min(max(0.0, xr[0]), xr[1])            # dove passano gli assi
    oy = min(max(0.0, yr[0]), yr[1])
    tacche = piano["tacche"]
    griglia = (("x", xr, tacche.get("x", (_passo(ax), False))[0]),
               ("y", yr, tacche.get("y", (_passo(ay), False))[0])) if piano["numeri"] else ()
    if solo_boxplot:
        # I boxplot stanno uno sopra l'altro: in verticale non c'e' niente da misurare.
        griglia = griglia[:1]
    if senza_assi:
        griglia = ()
    for asse, (da, a), passo in griglia:
        v = math.ceil(da / passo) * passo
        while v <= a + 1e-9:
            if asse == "x":
                parti.append(f'<line x1="{px(v):.1f}" y1="{MARGINE}" x2="{px(v):.1f}" '
                             f'y2="{MARGINE + h:.1f}" stroke="#e6ece8"/>')
                if abs(v) > 1e-9:
                    parti.append(f'<text x="{px(v):.1f}" y="{py(oy) + 14:.1f}" '
                                 f'text-anchor="middle" fill="#555">{_tacca(v, asse, tacche)}</text>')
            else:
                parti.append(f'<line x1="{MARGINE}" y1="{py(v):.1f}" x2="{MARGINE + w:.1f}" '
                             f'y2="{py(v):.1f}" stroke="#e6ece8"/>')
                if abs(v) > 1e-9:
                    parti.append(f'<text x="{px(ox) - 5:.1f}" y="{py(v) + 4:.1f}" '
                                 f'text-anchor="end" fill="#555">{_tacca(v, asse, tacche)}</text>')
            v += passo
    # Le aree, sotto assi e curve: colore pieno ma trasparente.
    legenda_aree = []
    for k, area in enumerate(piano["aree"]):
        colore = TINTE[(k + 1) % len(TINTE)] if piano["curve"] else TINTE[k % len(TINTE)]
        d = _area_path(area, xr, yr, px, py, w, h)
        if d:
            parti.append(f'<path d="{d}" fill="{colore}" fill-opacity="0.22" stroke="none" '
                         f'clip-path="url(#{uid}r)"/>')
        legenda_aree.append((colore, area.descrizione(), "area"))

    # I campi: frecce o trattini su una griglia, grigi, sotto a tutto il resto.
    legenda_campi = []
    for campo in piano["campi"]:
        parti.append(_disegna_campo(campo, xr, yr, px, py, sx, sy, w, h, uid))
        if campo.etichetta or piano["numeri"]:
            legenda_campi.append(("#64748b", campo.descrizione()))

    # I rettangoli di Riemann: sotto la curva, sopra le aree.
    for k, r in enumerate(piano["rettangoli"]):
        colore = TINTE[(k + 1) % len(TINTE)]
        pezzi = []
        for x0, altezza in zip(r.sinistri, r.altezze):
            alto, basso = max(altezza, 0.0), min(altezza, 0.0)
            pezzi.append(f"M{px(x0):.1f},{py(alto):.1f}H{px(x0 + r.larghezza):.1f}"
                         f"V{py(basso):.1f}H{px(x0):.1f}Z")
        parti.append(f'<path d="{"".join(pezzi)}" fill="{colore}" fill-opacity="0.25" '
                     f'stroke="{colore}" stroke-width="1.2" clip-path="url(#{uid}r)"/>')
        legenda_aree.append((colore, r.descrizione(), "area"))

    # Gli istogrammi: barre attaccate, con la frequenza scritta sopra.
    for k, ist in enumerate(piano["istogrammi"]):
        colore = TINTE[k % len(TINTE)]
        pezzi, scritte = [], []
        for (a, b, f), alto in zip(ist.classi, ist.altezze):
            pezzi.append(f"M{px(a):.1f},{py(alto):.1f}H{px(b):.1f}V{py(0):.1f}H{px(a):.1f}Z")
            if piano["numeri"] and px(b) - px(a) >= 16:
                scritte.append(f'<text x="{(px(a) + px(b)) / 2:.1f}" y="{py(alto) - 4:.1f}" '
                               f'text-anchor="middle" font-size="10.5" fill="#333">'
                               f'{_numero_bello(f)}</text>')
        parti.append(f'<path d="{"".join(pezzi)}" fill="{colore}" fill-opacity="0.35" '
                     f'stroke="{colore}" stroke-width="1.4" clip-path="url(#{uid}r)"/>')
        parti += scritte
        legenda_aree.append((colore, ist.descrizione(), "area"))

    # Gli assi, con la freccia e il nome.
    if not senza_assi:
        parti.append(f'<line x1="{MARGINE - 6}" y1="{py(oy):.1f}" x2="{MARGINE + w + 10:.1f}" '
                     f'y2="{py(oy):.1f}" stroke="#333" stroke-width="1.2" marker-end="url(#{uid}f)"/>')
        if len(piano["assi"][0]) <= 3:
            parti.append(f'<text x="{MARGINE + w + 12:.1f}" y="{py(oy) - 6:.1f}" font-style="italic" '
                         f'font-size="13" fill="#333">{html.escape(piano["assi"][0])}</text>')
        else:
            # Un nome lungo («altezza (cm)») oltre la freccia uscirebbe dal
            # disegno: va sotto la fine dell'asse, sotto i numeri delle tacche.
            parti.append(f'<text x="{MARGINE + w:.1f}" y="{py(oy) + 27:.1f}" text-anchor="end" '
                         f'font-style="italic" font-size="12" fill="#333">'
                         f'{html.escape(piano["assi"][0])}</text>')
    if not (solo_boxplot or senza_assi):
        parti.append(f'<line x1="{px(ox):.1f}" y1="{MARGINE + h + 6:.1f}" x2="{px(ox):.1f}" '
                     f'y2="{MARGINE - 10}" stroke="#333" stroke-width="1.2" marker-end="url(#{uid}f)"/>')
        parti.append(f'<text x="{px(ox) + 7:.1f}" y="{MARGINE - 8}" font-style="italic" '
                     f'font-size="13" fill="#333">{html.escape(piano["assi"][1])}</text>')
    # La «O» dell'origine, se nessun punto ci sta sopra col suo nome.
    occupata = any(abs(x) < 1e-9 and abs(y) < 1e-9 for _n, x, y in piano["punti"])
    if xr[0] < 0 < xr[1] and yr[0] < 0 < yr[1] and not occupata and not senza_assi:
        parti.append(f'<text x="{px(0) - 5:.1f}" y="{py(0) + 14:.1f}" text-anchor="end" '
                     f'fill="#555">O</text>')

    # Le curve, tagliate al riquadro, col nome accanto se ce l'hanno.
    legenda: list[tuple[str, str]] = list(legenda_campi)
    famiglie_dette: set[str] = set()
    pallini: list[tuple[float, float, str, bool]] = []
    for k, curva in enumerate(piano["curve"]):
        colore = TINTE[k % len(TINTE)]
        tratti = [t for t in _campiona(curva, xr, yr) if len(t) > 1]
        d = " ".join("M" + " L".join(f"{px(x):.1f},{py(y):.1f}" for x, y in t) for t in tratti)
        if d:
            parti.append(f'<path d="{d}" fill="none" stroke="{colore}" stroke-width="2.2" '
                         f'stroke-linejoin="round" stroke-linecap="round" clip-path="url(#{uid}r)"/>')
        # Agli estremi di un tratto: pallino pieno se l'estremo e' incluso,
        # vuoto se no.
        if curva.condizione and curva.tipo == "y":
            for xe, incluso in curva.condizione.estremi_x():
                ye = float(np.asarray(curva.f(x=xe)))
                if xr[0] <= xe <= xr[1] and math.isfinite(ye) and yr[0] <= ye <= yr[1]:
                    pallini.append((xe, ye, colore, incluso))
        if curva.nome and tratti:
            x, y = _dove_scrivere(tratti, xr, yr)
            parti.append(f'<text x="{px(x) + 6:.1f}" y="{py(y) - 7:.1f}" font-style="italic" '
                         f'font-weight="600" font-size="13" fill="{colore}" paint-order="stroke" '
                         f'stroke="#fff" stroke-width="3">{html.escape(curva.nome)}</text>')
        if curva.parametro:
            # Una famiglia: in legenda l'equazione generale una volta sola, poi
            # un colore per ogni valore del parametro.
            generale = curva.etichetta or _equazione_bella(curva.testo_generale)
            if generale not in famiglie_dette:
                famiglie_dette.add(generale)
                legenda.append(("", generale))
            legenda.append((colore, curva.parametro))
        elif curva.etichetta:
            legenda.append((colore, (f"{curva.nome}: " if curva.nome else "") + curva.etichetta))
        elif piano["numeri"]:
            dove = f" per {_equazione_bella(curva.condizione_testo)}" if curva.condizione_testo else ""
            legenda.append((colore, (f"{curva.nome}: " if curva.nome else "")
                            + _equazione_bella(curva.testo) + dove))
        elif curva.nome:
            legenda.append((colore, curva.nome))

    # I termini di una successione: un pallino per termine, niente linea che
    # li unisca (una successione non e' una funzione continua).
    for k, succ in enumerate(piano["successioni"]):
        colore = TINTE[(len(piano["curve"]) + k) % len(TINTE)]
        pallini_succ = "".join(
            f'<circle cx="{px(n):.1f}" cy="{py(v):.1f}" r="3.4" fill="{colore}"/>'
            for n, v in zip(succ.n, succ.valori)
            if math.isfinite(v) and xr[0] <= n <= xr[1] and yr[0] <= v <= yr[1])
        parti.append(f'<g clip-path="url(#{uid}r)">{pallini_succ}</g>')
        legenda.append((colore, succ.descrizione()))

    # I dati di una dispersione: pallini senza nome, un po' trasparenti, cosi'
    # dove si accumulano si vede.
    for k, dati in enumerate(piano["dati"]):
        colore = TINTE[(len(piano["curve"]) + k + 1) % len(TINTE)]
        pallini_dati = "".join(f'<circle cx="{px(x):.1f}" cy="{py(y):.1f}" r="3.6"/>'
                               for x, y in zip(dati.xs, dati.ys))
        parti.append(f'<g fill="{colore}" fill-opacity="0.75" stroke="#fff" stroke-width="0.8" '
                     f'clip-path="url(#{uid}r)">{pallini_dati}</g>')
        legenda.append((colore, dati.descrizione()))

    # I boxplot: la scatola da Q1 a Q3, la mediana, i baffi fino al minimo e al
    # massimo, gli anomali come cerchietti vuoti. Uno sopra l'altro.
    for k, b in enumerate(piano["boxplot"]):
        colore = TINTE[k % len(TINTE)]
        yc = py(k + 1)
        mezza = min(18.0, sy * 0.3)
        parti.append(
            f'<g stroke="{colore}" stroke-width="1.8" fill="none">'
            f'<line x1="{px(b.minimo):.1f}" y1="{yc:.1f}" x2="{px(b.q1):.1f}" y2="{yc:.1f}"/>'
            f'<line x1="{px(b.q3):.1f}" y1="{yc:.1f}" x2="{px(b.massimo):.1f}" y2="{yc:.1f}"/>'
            f'<line x1="{px(b.minimo):.1f}" y1="{yc - mezza / 2:.1f}" x2="{px(b.minimo):.1f}" '
            f'y2="{yc + mezza / 2:.1f}"/>'
            f'<line x1="{px(b.massimo):.1f}" y1="{yc - mezza / 2:.1f}" x2="{px(b.massimo):.1f}" '
            f'y2="{yc + mezza / 2:.1f}"/>'
            f'<rect x="{px(b.q1):.1f}" y="{yc - mezza:.1f}" width="{px(b.q3) - px(b.q1):.1f}" '
            f'height="{2 * mezza:.1f}" fill="{colore}" fill-opacity="0.2"/>'
            f'<line x1="{px(b.mediana):.1f}" y1="{yc - mezza:.1f}" x2="{px(b.mediana):.1f}" '
            f'y2="{yc + mezza:.1f}" stroke-width="3"/>'
            + "".join(f'<circle cx="{px(v):.1f}" cy="{yc:.1f}" r="3.6" fill="#fff"/>'
                      for v in b.anomali)
            + "</g>")
        if b.nome:
            parti.append(f'<text x="{px(b.q1):.1f}" y="{yc - mezza - 5:.1f}" font-weight="600" '
                         f'font-size="12" fill="{colore}">{html.escape(b.nome)}</text>')
        if piano["numeri"] or b.etichetta:
            legenda.append((colore, b.descrizione()))

    # I vuoti prima dei pieni: dove due tratti si toccano, il pieno resta
    # sopra e si vede quale dei due prende il punto.
    for xe, ye, colore, incluso in sorted(pallini, key=lambda p: p[3]):
        parti.append(f'<circle cx="{px(xe):.1f}" cy="{py(ye):.1f}" r="4.2" '
                     f'fill="{colore if incluso else "#fff"}" stroke="{colore}" stroke-width="2"/>')

    # I poligoni: colore chiaro dentro, lati pieni del loro colore.
    for k, (nome, vertici, etichetta, _nomi) in enumerate(piano["poligoni"]):
        colore = TINTE[(len(piano["curve"]) + k + 2) % len(TINTE)]
        d = "M" + " L".join(f"{px(x):.1f},{py(y):.1f}" for x, y in vertici) + " Z"
        parti.append(f'<path d="{d}" fill="{colore}" fill-opacity="0.16" stroke="{colore}" '
                     f'stroke-width="2.2" stroke-linejoin="round" clip-path="url(#{uid}r)"/>')
        if etichetta or nome:
            legenda_aree.append((colore, etichetta or nome, "area"))

    # Gli angoli: uno spicchio chiaro con il suo arco, e il nome a meta'.
    for nome, xv, yv, da, a in piano["angoli"]:
        parti.append(_arco(nome, px(xv), py(yv), da, a, sx, sy))

    # I vettori: frecce del loro colore, col nome vicino a meta'.
    for k, (nome, x0, y0, x1, y1) in enumerate(piano["vettori"]):
        colore = TINTE[(len(piano["curve"]) + k) % len(TINTE)]
        parti.append(f'<defs><marker id="{uid}v{k}" viewBox="0 0 10 10" refX="9" refY="5" '
                     f'markerWidth="12" markerHeight="12" markerUnits="userSpaceOnUse" '
                     f'orient="auto"><path d="M0,0 L10,5 L0,10 z" fill="{colore}"/></marker></defs>')
        a0, b0, a1, b1 = px(x0), py(y0), px(x1), py(y1)
        parti.append(f'<line x1="{a0:.1f}" y1="{b0:.1f}" x2="{a1:.1f}" y2="{b1:.1f}" '
                     f'stroke="{colore}" stroke-width="2.4" marker-end="url(#{uid}v{k})"/>')
        if nome:
            lung = math.hypot(a1 - a0, b1 - b0) or 1
            nx, ny = -(b1 - b0) / lung, (a1 - a0) / lung       # perpendicolare
            mx, my = (a0 + a1) / 2 + nx * 12, (b0 + b1) / 2 + ny * 12
            parti.append(f'<text x="{mx:.1f}" y="{my + 4:.1f}" text-anchor="middle" '
                         f'font-style="italic" font-weight="700" font-size="14" fill="{colore}" '
                         f'paint-order="stroke" stroke="#fff" stroke-width="3">'
                         f'{html.escape(nome)}</text>')
        # In legenda: nome e componenti; senza numeri solo il nome, e un
        # vettore senza nome ne' numeri non ha niente da dire.
        componenti = f"({_numero_bello(x1 - x0)}, {_numero_bello(y1 - y0)})"
        if piano["numeri"]:
            legenda.append((colore, f"{nome} = {componenti}" if nome else componenti))
        elif nome:
            legenda.append((colore, nome))

    # I segmenti (tratteggiati) e i lati (pieni), col nome a meta' se ce
    # l'hanno, dalla parte opposta al centro della figura. Sotto i punti.
    posto = {n: (x, y) for n, x, y in piano["punti"] if n}
    if posto:
        cxm = sum(px(x) for x, _y in posto.values()) / len(posto)
        cym = sum(py(y) for _x, y in posto.values()) / len(posto)
    for a, b, etichetta, pieno in piano["segmenti"]:
        (x1, y1), (x2, y2) = posto[a], posto[b]
        stile = ('stroke="#1f2937" stroke-width="2.2"' if pieno
                 else 'stroke="#d97706" stroke-width="1.8" stroke-dasharray="6 4"')
        parti.append(f'<line x1="{px(x1):.1f}" y1="{py(y1):.1f}" x2="{px(x2):.1f}" '
                     f'y2="{py(y2):.1f}" {stile} stroke-linecap="round" clip-path="url(#{uid}r)"/>')
        if etichetta:
            mx, my = (px(x1) + px(x2)) / 2, (py(y1) + py(y2)) / 2
            lung = math.hypot(px(x2) - px(x1), py(y2) - py(y1)) or 1
            nx, ny = -(py(y2) - py(y1)) / lung, (px(x2) - px(x1)) / lung
            if (mx - cxm) * nx + (my - cym) * ny < 0:
                nx, ny = -nx, -ny
            parti.append(f'<text x="{mx + nx * 13:.1f}" y="{my + ny * 13 + 4:.1f}" text-anchor="middle" '
                         f'font-style="italic" font-size="13" fill="{"#1f2937" if pieno else "#b45309"}" '
                         f'paint-order="stroke" stroke="#fff" stroke-width="3">{html.escape(etichetta)}</text>')

    # I punti: col nome e le coordinate, o solo col nome se i numeri non si
    # mostrano.
    centri = {}
    for _n, vertici, _e, nomi in piano["poligoni"]:
        cx = sum(px(vx) for vx, _vy in vertici) / len(vertici)
        cy = sum(py(vy) for _vx, vy in vertici) / len(vertici)
        for v in nomi:
            centri.setdefault(v, (cx, cy))
    for nome, x, y in piano["punti"]:
        if not (xr[0] <= x <= xr[1] and yr[0] <= y <= yr[1]):
            continue
        if piano["numeri"]:
            etichetta = f"{nome}({_numero_bello(x)}, {_numero_bello(y)})"
        else:
            etichetta = nome
        a_sinistra = px(x) > MARGINE + w - 90
        parti.append(f'<circle cx="{px(x):.1f}" cy="{py(y):.1f}" r="3.8" fill="#1b1b1b"/>')
        # Il vertice di un poligono ha il nome fuori dalla figura, dalla parte
        # opposta al suo centro: dentro ci sono gli angoli segnati.
        tx, ty, ancora = px(x) + (-7 if a_sinistra else 7), py(y) - 7, "end" if a_sinistra else "start"
        if nome in centri:
            dx, dy = px(x) - centri[nome][0], py(y) - centri[nome][1]
            n = math.hypot(dx, dy) or 1
            tx, ty = px(x) + dx / n * 13, py(y) + dy / n * 13 + 4
            ancora = "middle"
        if etichetta:
            parti.append(f'<text x="{tx:.1f}" y="{ty:.1f}" '
                         f'text-anchor="{ancora}" font-weight="600" '
                         f'font-size="{11 if piano["numeri"] else 13}" '
                         f'fill="#1b1b1b" paint-order="stroke" stroke="#fff" stroke-width="3">'
                         f'{html.escape(etichetta)}</text>')
    parti.append("</svg>")

    fuori = ['<div class="piano">']
    if piano["titolo"]:
        fuori.append(f'<div class="piano-titolo">{html.escape(_titolo_bello(piano["titolo"]))}</div>')
    fuori.append("".join(parti))
    if legenda or legenda_aree:
        # Le voci senza colore sono i titoli delle famiglie; quelle delle aree
        # hanno un quadratino. Il testo passa dall'escape ma i $ restano: le
        # formule le disegna MathJax.
        voci = [f'<span><i style="background:{c}"></i>{html.escape(t)}</span>' if c
                else f'<span class="piano-famiglia">{html.escape(t)}</span>' for c, t in legenda]
        voci += [f'<span><i class="piano-area" style="background:{c}"></i>{html.escape(t)}</span>'
                 for c, t, _f in legenda_aree]
        fuori.append('<div class="piano-legenda">' + "".join(voci) + "</div>")
    for nota in piano["note"]:
        fuori.append(f'<div class="piano-nota">{html.escape(nota)}</div>')
    fuori.append("</div>")
    return "".join(fuori)


def _area_path(area: _Area, xr, yr, px, py, w: float, h: float) -> str:
    """Il contorno SVG di un'area.

    Fra due curve: un poligono che va avanti lungo la prima e torna indietro
    lungo la seconda, liscio come le curve. Per una disuguaglianza: la zona
    si calcola su una griglia fitta, riga per riga, e ogni tratto di riga
    dove vale diventa un rettangolino; insieme fanno la zona.
    """
    if area.tipo == "fra":
        t = np.linspace(max(area.da, xr[0]), min(area.a, xr[1]), 400)
        if t[0] >= t[-1]:
            return ""
        y1 = np.broadcast_to(area.curve[0].f(x=t), t.shape)
        y2 = np.broadcast_to(area.curve[1].f(x=t), t.shape)
        buoni = np.isfinite(y1) & np.isfinite(y2)
        if not buoni.all():
            return ""
        # Tenuti poco oltre il riquadro, che poi taglia: niente numeri enormi.
        alto, basso = yr[1] + (yr[1] - yr[0]), yr[0] - (yr[1] - yr[0])
        y1, y2 = np.clip(y1, basso, alto), np.clip(y2, basso, alto)
        andata = [f"{px(a):.1f},{py(b):.1f}" for a, b in zip(t, y1)]
        ritorno = [f"{px(a):.1f},{py(b):.1f}" for a, b in zip(t[::-1], y2[::-1])]
        return "M" + " L".join(andata + ritorno) + " Z"
    colonne, righe = max(int(w), 2), max(int(h / 2), 2)
    xs = xr[0] + (np.arange(colonne) + 0.5) * (xr[1] - xr[0]) / colonne
    ys = yr[1] - (np.arange(righe) + 0.5) * (yr[1] - yr[0]) / righe
    gx, gy = np.meshgrid(xs, ys)
    dentro = np.broadcast_to(area.condizione(x=gx, y=gy), gx.shape)
    passo_x, passo_y = w / colonne, h / righe
    pezzi = []
    for i in range(righe):
        riga = np.concatenate([[False], dentro[i], [False]]).astype(np.int8)
        cambi = np.flatnonzero(np.diff(riga))
        for inizio, fine in zip(cambi[::2], cambi[1::2]):
            x0 = MARGINE + inizio * passo_x
            pezzi.append(f"M{x0:.1f},{MARGINE + i * passo_y:.1f}h{(fine - inizio) * passo_x:.1f}"
                         f"v{passo_y + 0.05:.2f}h{-(fine - inizio) * passo_x:.1f}z")
    return "".join(pezzi)


def _titolo_bello(titolo: str) -> str:
    """Il titolo con x² e √ al posto di x^2 e sqrt, fuori dalle formule fra $."""
    pezzi = re.split(r"(\$[^$]*\$)", titolo)
    return "".join(p if p.startswith("$") else _equazione_bella(p) for p in pezzi)


def _tacca(v: float, asse: str, tacche: dict) -> str:
    """Il numero di una tacca: 1.5, oppure π/2 se l'asse va a multipli di π."""
    if not tacche.get(asse, (0, False))[1]:
        return _numero_bello(v)
    from fractions import Fraction
    q = Fraction(v / math.pi).limit_denominator(24)
    if q == 0:
        return "0"
    segno = "−" if q < 0 else ""
    num, den = abs(q.numerator), q.denominator
    testa = "π" if num == 1 else f"{num}π"
    return segno + (testa if den == 1 else f"{testa}/{den}")


def _arco(nome: str, cx: float, cy: float, da: float, a: float, sx: float, sy: float) -> str:
    """Lo spicchio di un angolo col vertice in (cx, cy), gia' in pixel.

    Le direzioni si prendono in pixel: se le due scale sono diverse l'arco
    resta attaccato ai lati disegnati. Il raggio e' fisso sullo schermo, cosi'
    l'angolo si legge anche in un piano molto grande o molto piccolo.
    """
    raggio = 26

    def direzione(angolo):
        dx, dy = math.cos(angolo) * sx, -math.sin(angolo) * sy
        lung = math.hypot(dx, dy) or 1
        return dx / lung, dy / lung

    (u0, v0), (u1, v1) = direzione(da), direzione(a)
    ampiezza = (a - da) % (2 * math.pi)
    grande = 1 if ampiezza > math.pi else 0
    p0 = (cx + u0 * raggio, cy + v0 * raggio)
    p1 = (cx + u1 * raggio, cy + v1 * raggio)
    um, vm = direzione(da + ampiezza / 2)
    if abs(ampiezza - math.pi / 2) < 1e-3:
        # L'angolo retto si segna col quadratino, come sul quaderno.
        q = 13
        angolo_q = (cx + (u0 + u1) * q, cy + (v0 + v1) * q)
        fuori = (f'<path d="M{cx + u0 * q:.1f},{cy + v0 * q:.1f} L{angolo_q[0]:.1f},{angolo_q[1]:.1f} '
                 f'L{cx + u1 * q:.1f},{cy + v1 * q:.1f}" fill="none" stroke="#d97706" '
                 f'stroke-width="1.6"/>')
        if nome:
            fuori += (f'<text x="{cx + um * (q * 1.41 + 12):.1f}" y="{cy + vm * (q * 1.41 + 12) + 4:.1f}" '
                      f'text-anchor="middle" font-style="italic" font-size="13" fill="#b45309" '
                      f'paint-order="stroke" stroke="#fff" stroke-width="3">{html.escape(nome)}</text>')
        return fuori
    fuori = (f'<path d="M{cx:.1f},{cy:.1f} L{p0[0]:.1f},{p0[1]:.1f} A{raggio},{raggio} 0 '
             f'{grande} 0 {p1[0]:.1f},{p1[1]:.1f} Z" fill="#d97706" fill-opacity="0.15" '
             f'stroke="none"/>'
             f'<path d="M{p0[0]:.1f},{p0[1]:.1f} A{raggio},{raggio} 0 {grande} 0 '
             f'{p1[0]:.1f},{p1[1]:.1f}" fill="none" stroke="#d97706" stroke-width="1.6"/>')
    if nome:
        fuori += (f'<text x="{cx + um * (raggio + 12):.1f}" y="{cy + vm * (raggio + 12) + 4:.1f}" '
                  f'text-anchor="middle" font-style="italic" font-size="13" fill="#b45309" '
                  f'paint-order="stroke" stroke="#fff" stroke-width="3">{html.escape(nome)}</text>')
    return fuori


def _disegna_campo(campo: _Campo, xr, yr, px, py, sx, sy, w, h, uid) -> str:
    """Un campo su una griglia: frecce (lunghe quanto e' forte il campo) per un
    campo vettoriale, trattini tutti uguali per un campo di direzioni."""
    cella = max(w, h) / 17
    colonne, righe = max(int(w / cella), 3), max(int(h / cella), 3)
    xs = xr[0] + (np.arange(colonne) + 0.5) * (xr[1] - xr[0]) / colonne
    ys = yr[0] + (np.arange(righe) + 0.5) * (yr[1] - yr[0]) / righe
    gx, gy = np.meshgrid(xs, ys)
    pezzi = []
    if campo.tipo == "direzioni":
        pendenza = np.broadcast_to(campo.f(x=gx, y=gy), gx.shape)
        for x, y, m in zip(gx.ravel(), gy.ravel(), pendenza.ravel()):
            if not math.isfinite(m):
                continue
            dx, dy = sx, -m * sy
            n = math.hypot(dx, dy)
            dx, dy = dx / n * cella * 0.36, dy / n * cella * 0.36
            pezzi.append(f"M{px(x) - dx:.1f},{py(y) - dy:.1f}L{px(x) + dx:.1f},{py(y) + dy:.1f}")
        return (f'<path d="{"".join(pezzi)}" stroke="#64748b" stroke-width="1.3" '
                f'stroke-linecap="round" clip-path="url(#{uid}r)"/>')
    P = np.array(np.broadcast_to(campo.P(gx, gy), gx.shape), dtype=float)
    Q = np.array(np.broadcast_to(campo.Q(gx, gy), gx.shape), dtype=float)
    forza = np.hypot(P, Q)
    # La lunghezza delle frecce si misura sul 90° percentile e non sul
    # massimo: il campo di una carica vicino alla carica e' enorme, e col
    # massimo tutte le altre frecce diventavano puntini.
    finite = forza[np.isfinite(forza)]
    massimo = float(np.percentile(finite, 90)) if finite.size else 0
    forza = np.minimum(forza, massimo) if massimo else forza
    punte = []
    for x, y, p, q, f in zip(gx.ravel(), gy.ravel(), P.ravel(), Q.ravel(), forza.ravel()):
        if not (math.isfinite(f) and f > 1e-12 and massimo):
            continue
        dx, dy = p * sx, -q * sy
        n = math.hypot(dx, dy)
        lung = cella * 0.85 * (0.3 + 0.7 * f / massimo)
        ux, uy = dx / n, dy / n
        x0, y0 = px(x) - ux * lung / 2, py(y) - uy * lung / 2
        x1, y1 = px(x) + ux * lung / 2, py(y) + uy * lung / 2
        pezzi.append(f"M{x0:.1f},{y0:.1f}L{x1 - ux * 4:.1f},{y1 - uy * 4:.1f}")
        punte.append(f"M{x1:.1f},{y1:.1f}L{x1 - ux * 6 - uy * 3:.1f},{y1 - uy * 6 + ux * 3:.1f}"
                     f"L{x1 - ux * 6 + uy * 3:.1f},{y1 - uy * 6 - ux * 3:.1f}Z")
    return (f'<g clip-path="url(#{uid}r)"><path d="{"".join(pezzi)}" stroke="#64748b" '
            f'stroke-width="1.3" fill="none"/><path d="{"".join(punte)}" fill="#64748b"/></g>')


def _dove_scrivere(tratti, xr, yr) -> tuple[float, float]:
    """Il punto della curva dove scriverne il nome: il piu' a sinistra fra
    quelli ben dentro il riquadro (per una retta verticale, il piu' in alto)."""
    dx, dy = (xr[1] - xr[0]) * 0.04, (yr[1] - yr[0]) * 0.08
    dentro = [(x, y) for t in tratti for x, y in t
              if xr[0] + dx <= x <= xr[1] - dx and yr[0] + dy <= y <= yr[1] - dy]
    return min(dentro or [p for t in tratti for p in t], key=lambda p: (round(p[0], 6), -p[1]))


def in_testo(testo: str) -> list[str]:
    """Il piano detto a parole, per il Word e il file di testo che non disegnano."""
    piano = leggi(testo)
    if not piano:
        return []
    fuori = [f"Grafico: {piano['titolo']}" if piano["titolo"] else "Grafico:"]
    for c in piano["curve"]:
        nome = f"{c.nome}: " if c.nome else ""
        dove = f" per {_equazione_bella(c.condizione_testo)}" if c.condizione_testo else ""
        if c.parametro:
            fuori.append(f"- {nome}{_equazione_bella(c.testo_generale)} con {c.parametro}{dove}")
        else:
            fuori.append(f"- {nome}{c.etichetta or _equazione_bella(c.testo)}{dove}")
    for n, x, y in piano["punti"]:
        if piano["numeri"]:
            fuori.append(f"- Punto {n}({_numero_bello(x)}, {_numero_bello(y)})")
        elif n:
            fuori.append(f"- Punto {n}")
    for a, b, etichetta, pieno in piano["segmenti"]:
        fuori.append(f"- {'Lato' if pieno else 'Segmento'} {a}{b}" + (f" ({etichetta})" if etichetta else ""))
    for nome, _vertici, etichetta, nomi in piano["poligoni"]:
        vertici_nominati = "".join(n for n in nomi if not n.startswith("("))
        fuori.append(f"- Poligono {nome or vertici_nominati}".rstrip()
                     + (f": {etichetta}" if etichetta else ""))
    fuori += [f"- {c.descrizione()[0].upper()}{c.descrizione()[1:]}" for c in piano["campi"]]
    for succ in piano["successioni"]:
        primi = ", ".join(_numero_bello(round(float(v), 4)) for v in succ.valori[:5])
        fuori.append(f"- {succ.descrizione()} (primi valori: {primi}…)")
    fuori += [f"- {r.descrizione()[0].upper()}{r.descrizione()[1:]}" for r in piano["rettangoli"]]
    for d in piano["dati"]:
        coppie = "; ".join(f"({_numero_bello(x)}, {_numero_bello(y)})"
                           for x, y in list(zip(d.xs, d.ys))[:12])
        fuori.append(f"- {d.descrizione()}: {coppie}" + ("…" if len(d.xs) > 12 else ""))
    for ist in piano["istogrammi"]:
        classi = "; ".join(f"[{_numero_bello(a)}, {_numero_bello(b)}): {_numero_bello(f)}"
                           for a, b, f in ist.classi)
        fuori.append(f"- {ist.descrizione()[0].upper()}{ist.descrizione()[1:]}: {classi}")
    fuori += [f"- Boxplot {b.descrizione()}" for b in piano["boxplot"]]
    for nome, x0, y0, x1, y1 in piano["vettori"]:
        componenti = f"({_numero_bello(x1 - x0)}, {_numero_bello(y1 - y0)})"
        if piano["numeri"]:
            fuori.append(f"- Vettore {nome} = {componenti}" if nome else f"- Vettore {componenti}")
        elif nome:
            fuori.append(f"- Vettore {nome}")
    fuori += [f"- Angolo {nome}" for nome, *_resto in piano["angoli"] if nome]
    for a in piano["aree"]:
        if a.etichetta:
            fuori.append(f"- Area colorata: {a.etichetta}")
        elif a.tipo == "fra":
            fuori.append(f"- Colorata l'{a.descrizione()}")
        else:
            fuori.append(f"- Colorata la zona {a.descrizione()}")
    fuori += [f"- {nota}" for nota in piano["note"]]
    return fuori
