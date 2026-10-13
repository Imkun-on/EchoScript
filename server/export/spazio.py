"""Lo spazio a tre dimensioni dei riassunti: superfici, curve, punti e vettori.

A che cosa serve
    Il piano cartesiano (piano.py) basta finche' si sta nel piano. L'analisi
    in due variabili, le superfici della geometria e le figure della topologia
    (sfera, toro, nastro di Möbius) vivono nello spazio: servono tre assi e una
    superficie che si veda come un oggetto solido.

Come lo scrive il modello
    In un blocco ```spazio, con le stesse regole del piano:

        titolo: Paraboloide
        x: -2, 2
        y: -2, 2
        z: 0, 8
        superficie: z = x^2 + y^2
        superficie: x = cos(u)*sin(v), y = sin(u)*sin(v), z = cos(v) con u da 0 a 2*pi, v da 0 a pi
        superficie: x^2 + y^2 - z^2 = 1       implicita: F(x, y, z) = 0
        curva: x = cos(t), y = sin(t), z = t/4 con t da 0 a 4*pi
        punto: P (1, 1, 2)
        vettore v: (1, 0, 1)         anche «da P» o «A -> B»
        segmento: A - B
        vista: -60, 30               da dove si guarda: azimut ed elevazione
        numeri: no
        nota: una riga sotto il disegno, anche con formule fra $

Come si disegna
    Una sola vista fissa, in SVG, come in un libro: niente da ruotare, e il PDF
    la stampa uguale. La superficie si divide in tanti quadrilateri; ognuno si
    proietta sul foglio, si colora (per altezza, o col suo colore) con una luce
    che fa vedere le pieghe, e si disegnano dal piu' lontano al piu' vicino
    (l'«algoritmo del pittore»): quelli davanti coprono quelli dietro. Curve,
    punti e vettori entrano nello stesso ordine, cosi' anche loro spariscono
    dietro una superficie quando ci passano dietro.

    Le espressioni si controllano come nel piano (vedi piano._Espressione):
    solo numeri, variabili, operazioni e poche funzioni note.
"""
from __future__ import annotations

import hashlib
import html
import math
import re

import numpy as np

from server.export.piano import (TINTE, _NOME, _Espressione, _equazione_bella, _intervallo,
                                 _numero, _numero_bello, _passo, _titolo_bello)

LARGHEZZA, ALTEZZA = 560, 440
MARGINE = 46

# La scala di colori per altezza (come «viridis»): dal viola in basso al
# giallo in alto, leggibile anche stampata in bianco e nero.
_SCALA = ((0.267, 0.005, 0.329), (0.231, 0.322, 0.545), (0.129, 0.569, 0.549),
          (0.369, 0.788, 0.384), (0.993, 0.906, 0.144))


# ── La descrizione ──────────────────────────────────────────────────────────

# I vertici di un cubetto e i sei tetraedri in cui lo si divide, tutti
# attorno alla diagonale 0-6: e' la divisione classica dei «tetraedri che
# marciano».
_ANGOLI = ((0, 0, 0), (1, 0, 0), (1, 1, 0), (0, 1, 0), (0, 0, 1), (1, 0, 1), (1, 1, 1), (0, 1, 1))
_TETRAEDRI = ((0, 5, 1, 6), (0, 1, 2, 6), (0, 2, 3, 6), (0, 3, 7, 6), (0, 7, 4, 6), (0, 4, 5, 6))


def _tetraedro(p, v) -> list:
    """Il pezzo di superficie F = 0 dentro un tetraedro: niente, un triangolo o
    un quadrilatero, coi vertici sugli spigoli dove F cambia segno."""
    dentro = [x > 0 for x in v]
    quanti = sum(dentro)
    if quanti in (0, 4):
        return []

    def taglio(a, b):
        t = v[a] / (v[a] - v[b])
        return tuple(p[a][i] + t * (p[b][i] - p[a][i]) for i in range(3))

    if quanti in (1, 3):
        solo = dentro.index(quanti == 1)
        altri = [i for i in range(4) if i != solo]
        return [[taglio(solo, a) for a in altri]]
    a, b = [i for i in range(4) if dentro[i]]
    c, d = [i for i in range(4) if not dentro[i]]
    return [[taglio(a, c), taglio(a, d), taglio(b, d), taglio(b, c)]]


class _Superficie:
    """z = f(x, y), oppure x(u, v), y(u, v), z(u, v), oppure F(x, y, z) = 0."""

    def __init__(self, valore: str, nome: str = ""):
        valore, _, self.etichetta = (p.strip() for p in valore.partition("|"))
        self.testo, self.nome = valore, nome
        m = re.match(r"^x\s*=\s*(.+?)\s*[,;]\s*y\s*=\s*(.+?)\s*[,;]\s*z\s*=\s*(.+?)\s+"
                     r"(?:con|per)\s+u\s+da\s+(.+?)\s+a\s+(.+?)\s*[,;]\s*v\s+da\s+(.+?)\s+a\s+(.+)$",
                     valore)
        if m:
            self.tipo = "parametrica"
            self.f = [_Espressione(m.group(k), ("u", "v")) for k in (1, 2, 3)]
            self.u = (_numero(m.group(4)), _numero(m.group(5)))
            self.v = (_numero(m.group(6)), _numero(m.group(7)))
            return
        m = re.match(r"^z\s*=\s*(.+)$", valore)
        if m:
            f = _Espressione(m.group(1), ("x", "y", "z"))
            if "z" not in f.usate:
                self.tipo, self.f = "esplicita", f     # in x e y
                return
        # Implicita: un'equazione qualsiasi in x, y e z, come x^2 + y^2 - z^2 = 1.
        if valore.count("=") != 1:
            raise ValueError("superficie")
        sinistra, destra = (_Espressione(t, ("x", "y", "z")) for t in valore.split("="))
        self.tipo = "implicita"
        self.F = lambda x, y, z: sinistra(x=x, y=y, z=z) - destra(x=x, y=y, z=z)

    def poligoni(self, xr, yr, zr, n: int = 18) -> list:
        """I pezzi di una superficie implicita: triangoli e quadrilateri.

        La scatola si divide in cubetti; si guardano solo quelli dove F cambia
        segno fra un vertice e l'altro (la superficie ci passa), e ognuno si
        divide in sei tetraedri, dove il pezzo di superficie si trova da solo.
        """
        xs, ys, zs = (np.linspace(*r, n) for r in (xr, yr, zr))
        X, Y, Z = np.meshgrid(xs, ys, zs, indexing="ij")
        V = np.array(np.broadcast_to(self.F(X, Y, Z), X.shape), dtype=float)
        valido = np.isfinite(V)
        positivo = V > 0
        angoli = [positivo[a:n - 1 + a, b:n - 1 + b, c:n - 1 + c] for a, b, c in _ANGOLI]
        validi = np.logical_and.reduce([valido[a:n - 1 + a, b:n - 1 + b, c:n - 1 + c]
                                        for a, b, c in _ANGOLI])
        misti = np.logical_or.reduce(angoli) & ~np.logical_and.reduce(angoli) & validi
        fuori = []
        for i, j, k in np.argwhere(misti):
            punti = [(xs[i + a], ys[j + b], zs[k + c]) for a, b, c in _ANGOLI]
            valori = [V[i + a, j + b, k + c] for a, b, c in _ANGOLI]
            for t in _TETRAEDRI:
                fuori += _tetraedro([punti[q] for q in t], [valori[q] for q in t])
        return fuori

    def griglia(self, xr, yr, zr):
        """I punti della superficie su una griglia: tre matrici X, Y, Z.

        Solo i punti dove la superficie non esiste diventano NaN. Quelli fuori
        dalla scatola restano: ogni quadrilatero si taglia poi esattamente sul
        bordo (vedi _taglia), e il bordo viene dritto invece che a denti di
        sega.
        """
        if self.tipo == "esplicita":
            X, Y = np.meshgrid(np.linspace(*xr, 40), np.linspace(*yr, 40))
            Z = np.array(np.broadcast_to(self.f(x=X, y=Y), X.shape), dtype=float)
            Z[~np.isfinite(Z)] = np.nan
            return X, Y, Z
        U, V = np.meshgrid(np.linspace(*self.u, 56), np.linspace(*self.v, 28))
        X, Y, Z = (np.array(np.broadcast_to(f(u=U, v=V), U.shape), dtype=float) for f in self.f)
        guasti = ~(np.isfinite(X) & np.isfinite(Y) & np.isfinite(Z))
        for M in (X, Y, Z):
            M[guasti] = np.nan
        return X, Y, Z


class _Curva3D:
    """x(t), y(t), z(t) con t in un intervallo."""

    def __init__(self, valore: str, nome: str = ""):
        valore, _, self.etichetta = (p.strip() for p in valore.partition("|"))
        self.testo, self.nome = valore, nome
        m = re.match(r"^x\s*=\s*(.+?)\s*[,;]\s*y\s*=\s*(.+?)\s*[,;]\s*z\s*=\s*(.+?)\s+"
                     r"(?:con|per)\s+t\s+da\s+(.+?)\s+a\s+(.+)$", valore)
        if not m:
            raise ValueError("curva nello spazio")
        self.f = [_Espressione(m.group(k), ("t",)) for k in (1, 2, 3)]
        self.t = (_numero(m.group(4)), _numero(m.group(5)))

    def punti(self):
        t = np.linspace(*self.t, 500)
        return [np.array(np.broadcast_to(f(t=t), t.shape), dtype=float) for f in self.f]


def _terna(testo: str, posto: dict) -> tuple[float, float, float]:
    """Un punto: il nome di un punto gia' scritto, o «(x, y, z)»."""
    testo = testo.strip()
    if testo in posto:
        return posto[testo]
    m = re.match(r"^\(\s*(.+?)\s*[,;]\s*(.+?)\s*[,;]\s*(.+?)\s*\)$", testo)
    if not m:
        raise KeyError(testo)
    return tuple(_numero(m.group(k)) for k in (1, 2, 3))


def leggi(testo: str) -> dict | None:
    """La descrizione di uno spazio, o None se non si puo' disegnare.

    Come nel piano, basta una riga sbagliata per buttare tutto.
    """
    sp = {"titolo": "", "x": None, "y": None, "z": None, "numeri": True, "vista": (-60.0, 28.0),
          "superfici": [], "curve": [], "punti": [], "vettori": [], "segmenti": [], "note": []}
    vettori, segmenti, etichette_vettori = [], [], []
    for riga in testo.splitlines():
        riga = riga.strip()
        if not riga:
            continue
        m = re.match(rf"^([a-zA-Zàèéìòù]+)(?:\s+({_NOME}))?\s*:\s*(.+)$", riga)
        if not m:
            return None
        chiave, nome, valore = m.group(1).lower(), m.group(2) or "", m.group(3).strip()
        try:
            if chiave == "titolo":
                sp["titolo"] = valore
            elif chiave in ("x", "y", "z"):
                sp[chiave] = _intervallo(valore)
            elif chiave == "numeri":
                sp["numeri"] = valore.lower() not in ("no", "nessuno", "false", "0")
            elif chiave == "vista":
                az, el = (float(_numero(p)) for p in re.split(r"[,;]", valore))
                sp["vista"] = (az, max(-89.0, min(89.0, el)))
            elif chiave in ("superficie", "piano", "sfera", "toro"):
                sp["superfici"].append(_Superficie(valore, nome))
            elif chiave in ("curva", "elica"):
                sp["curve"].append(_Curva3D(valore, nome))
            elif chiave == "punto":
                p = re.match(rf"^({_NOME})?\s*(\(.+\))$", valore)
                if not p:
                    return None
                sp["punti"].append((p.group(1) or "", *_terna(p.group(2), {})))
            elif chiave == "vettore":
                vettori.append((nome, valore))
            elif chiave == "segmento":
                p = re.match(rf"^({_NOME})\s*[-–,]\s*({_NOME})$", valore)
                if not p:
                    return None
                segmenti.append((p.group(1), p.group(2)))
            elif chiave == "nota":
                sp["note"].append(valore)
            else:
                return None
        except (ValueError, SyntaxError, TypeError, ZeroDivisionError, KeyError):
            return None
    posto = {n: (x, y, z) for n, x, y, z in sp["punti"] if n}
    try:
        for nome, valore in vettori:
            valore, _, etichetta = (p.strip() for p in valore.partition("|"))
            etichette_vettori.append(etichetta)
            freccia = re.match(r"^(.+?)\s*(?:->|→)\s*(.+)$", valore)
            if freccia:
                a, b = _terna(freccia.group(1), posto), _terna(freccia.group(2), posto)
                sp["vettori"].append((nome or freccia.group(1).strip() + freccia.group(2).strip(), a, b))
                continue
            m = re.match(r"^(\(.+?\))(?:\s+da\s+(.+))?$", valore)
            if not m:
                return None
            d = _terna(m.group(1), {})
            a = _terna(m.group(2), posto) if m.group(2) else (0.0, 0.0, 0.0)
            sp["vettori"].append((nome, a, tuple(a[k] + d[k] for k in range(3))))
        for a, b in segmenti:
            sp["segmenti"].append((posto[a], posto[b]))
    except (ValueError, SyntaxError, TypeError, ZeroDivisionError, KeyError):
        return None
    sp["etichette_vettori"] = etichette_vettori
    if not (sp["superfici"] or sp["curve"] or sp["punti"] or sp["vettori"]):
        return None
    return sp


# ── I conti del disegno ─────────────────────────────────────────────────────

def _intervalli(sp: dict):
    """Gli intervalli dei tre assi: quelli scritti, o presi dagli oggetti."""
    campioni = {k: [] for k in "xyz"}
    for _n, x, y, z in sp["punti"]:
        campioni["x"].append(x); campioni["y"].append(y); campioni["z"].append(z)
    for _n, a, b in sp["vettori"]:
        for p in (a, b):
            for k, v in zip("xyz", p):
                campioni[k].append(v)
    for c in sp["curve"]:
        for k, v in zip("xyz", c.punti()):
            v = v[np.isfinite(v)]
            if v.size:
                campioni[k] += [float(v.min()), float(v.max())]
    xr = sp["x"] or ((min(campioni["x"]) - 1, max(campioni["x"]) + 1) if campioni["x"] else (-3, 3))
    yr = sp["y"] or ((min(campioni["y"]) - 1, max(campioni["y"]) + 1) if campioni["y"] else (-3, 3))
    for s in sp["superfici"]:
        if s.tipo == "parametrica":
            X, Y, Z = s.griglia((-1e9, 1e9), (-1e9, 1e9), (-1e9, 1e9))
            for k, M in zip("xyz", (X, Y, Z)):
                M = M[np.isfinite(M)]
                if M.size:
                    campioni[k] += [float(M.min()), float(M.max())]
        elif s.tipo == "esplicita" and not sp["z"]:
            X, Y = np.meshgrid(np.linspace(*xr, 30), np.linspace(*yr, 30))
            Z = np.broadcast_to(s.f(x=X, y=Y), X.shape)
            Z = Z[np.isfinite(Z)]
            if Z.size:
                campioni["z"] += [float(np.percentile(Z, 2)), float(np.percentile(Z, 98))]
    if not sp["x"] and campioni["x"]:
        xr = (min(campioni["x"]), max(campioni["x"]))
    if not sp["y"] and campioni["y"]:
        yr = (min(campioni["y"]), max(campioni["y"]))
    zr = sp["z"] or ((min(campioni["z"]), max(campioni["z"])) if campioni["z"] else (-3, 3))
    allarga = lambda r: r if r[1] - r[0] > 1e-9 else (r[0] - 1, r[1] + 1)   # noqa: E731
    return allarga(xr), allarga(yr), allarga(zr)


def _colore_scala(t: float) -> tuple[float, float, float]:
    """Il colore della scala per un valore fra 0 e 1."""
    t = min(max(t, 0.0), 1.0) * (len(_SCALA) - 1)
    i = min(int(t), len(_SCALA) - 2)
    f = t - i
    return tuple(_SCALA[i][k] + (_SCALA[i + 1][k] - _SCALA[i][k]) * f for k in range(3))


def _esadecimale(rgb, luce: float = 1.0) -> str:
    return "#" + "".join(f"{int(max(0, min(1, c * luce)) * 255):02x}" for c in rgb)


def _rgb(esadecimale: str) -> tuple[float, float, float]:
    return tuple(int(esadecimale[k:k + 2], 16) / 255 for k in (1, 3, 5))


def _taglia(poligono: list, xr, yr, zr) -> list:
    """Il poligono tagliato alla scatola, parete per parete.

    E' il metodo di Sutherland e Hodgman: per ogni parete si tengono i
    vertici dalla parte giusta, e dove un lato attraversa la parete si
    aggiunge il punto esatto in cui la attraversa.
    """
    for asse, (basso, alto) in enumerate((xr, yr, zr)):
        for limite, dentro in ((basso, lambda v, l=basso: v >= l - 1e-12),
                               (alto, lambda v, l=alto: v <= l + 1e-12)):
            if not poligono:
                return []
            fuori, prima = [], poligono[-1]
            for p in poligono:
                if dentro(p[asse]):
                    if not dentro(prima[asse]):
                        fuori.append(_incrocio(prima, p, asse, limite))
                    fuori.append(p)
                elif dentro(prima[asse]):
                    fuori.append(_incrocio(prima, p, asse, limite))
                prima = p
            poligono = fuori
    return poligono


def _incrocio(a, b, asse: int, limite: float):
    """Il punto del segmento ab che sta sulla parete."""
    t = (limite - a[asse]) / (b[asse] - a[asse])
    return tuple(a[k] + t * (b[k] - a[k]) for k in range(3))


class _Vista:
    """La proiezione: dai punti dello spazio ai pixel del foglio.

    Ogni asse si porta fra -1 e 1 (una scatola cubica, come nei libri e in
    matplotlib), poi si guarda la scatola da una direzione: azimut attorno
    all'asse z, elevazione sopra il piano xy. La proiezione e' ortogonale:
    niente prospettiva, le parallele restano parallele.
    """

    def __init__(self, xr, yr, zr, az: float, el: float):
        self.r = (xr, yr, zr)
        a, e = math.radians(az), math.radians(el)
        self.verso = np.array([math.cos(e) * math.cos(a), math.cos(e) * math.sin(a), math.sin(e)])
        self.destra = np.array([-math.sin(a), math.cos(a), 0.0])
        self.su = np.cross(self.verso, self.destra)
        angoli = [self._piano(np.array(c, dtype=float))
                  for c in np.array(np.meshgrid([-1, 1], [-1, 1], [-1, 1])).T.reshape(-1, 3)]
        xs, ys = [p[0] for p in angoli], [p[1] for p in angoli]
        self.scala = min((LARGHEZZA - 2 * MARGINE) / (max(xs) - min(xs)),
                         (ALTEZZA - 2 * MARGINE) / (max(ys) - min(ys)))
        self.cx = LARGHEZZA / 2 - (max(xs) + min(xs)) / 2 * self.scala
        self.cy = ALTEZZA / 2 + (max(ys) + min(ys)) / 2 * self.scala

    def cubo(self, x, y, z):
        """Dalle coordinate vere a quelle della scatola, fra -1 e 1."""
        return np.stack([2 * (np.asarray(v, dtype=float) - r[0]) / (r[1] - r[0]) - 1
                         for v, r in zip((x, y, z), self.r)], axis=-1)

    def _piano(self, q):
        return q @ self.destra, q @ self.su

    def pixel(self, q):
        """Da un punto della scatola ai pixel, e la sua profondita' (piu' grande = piu' vicino)."""
        sx, sy = self._piano(q)
        return self.cx + sx * self.scala, self.cy - sy * self.scala, float(q @ self.verso)


def svg(sp: dict) -> str:
    """Lo spazio disegnato: SVG, con titolo, legenda e note in HTML intorno."""
    xr, yr, zr = _intervalli(sp)
    vista = _Vista(xr, yr, zr, *sp["vista"])
    uid = "s" + hashlib.sha1(repr((sp["titolo"], xr, yr, zr, [s.testo for s in sp["superfici"]],
                                   [c.testo for c in sp["curve"]], sp["punti"],
                                   sp["vettori"])).encode("utf-8")).hexdigest()[:8]
    fondo: list[str] = []            # la scatola: dietro a tutto
    oggetti: list[tuple[float, str]] = []   # (profondita', svg): dal lontano al vicino
    davanti: list[str] = []          # le etichette degli assi: sopra a tutto
    d = vista.verso

    # ── La scatola: le tre pareti dietro, con la griglia, e le tacche ───────
    lati = {k: (-1.0 if d[k] > 0 else 1.0) for k in range(3)}      # la parete lontana
    passi = [_passo((r[1] - r[0]) * 1.6) for r in (xr, yr, zr)]
    valori = []
    for (a, b), passo in zip((xr, yr, zr), passi):
        v0 = math.ceil(a / passo - 1e-9) * passo
        valori.append([v for v in np.arange(v0, b + passo * 1e-6, passo)])

    def punto(q):
        x, y, _p = vista.pixel(np.asarray(q, dtype=float))
        return x, y

    for asse in range(3):
        altri = [k for k in range(3) if k != asse]
        faccia = []
        for s1, s2 in ((-1, -1), (1, -1), (1, 1), (-1, 1)):
            q = [0.0, 0.0, 0.0]
            q[asse], q[altri[0]], q[altri[1]] = lati[asse], s1, s2
            faccia.append(punto(q))
        fondo.append('<path d="M' + " L".join(f"{x:.1f},{y:.1f}" for x, y in faccia)
                     + ' Z" fill="#f6f8f7" stroke="#c9d3ce" stroke-width="0.8"/>')
        if not sp["numeri"]:
            continue
        for k in altri:                          # la griglia della parete
            for v in valori[k]:
                c = 2 * (v - (xr, yr, zr)[k][0]) / ((xr, yr, zr)[k][1] - (xr, yr, zr)[k][0]) - 1
                altro = altri[0] if k == altri[1] else altri[1]
                q1, q2 = [0.0] * 3, [0.0] * 3
                q1[asse] = q2[asse] = lati[asse]
                q1[k] = q2[k] = c
                q1[altro], q2[altro] = -1, 1
                (x1, y1), (x2, y2) = punto(q1), punto(q2)
                fondo.append(f'<line x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}" '
                             f'stroke="#e3e9e6" stroke-width="0.7"/>')

    # Le tacche e i nomi, sugli spigoli piu' vicini a chi guarda: x e y sul
    # pavimento davanti, z su uno spigolo di lato.
    centro = punto((0, 0, 0))
    spigoli = {0: (None, -lati[1], lati[2]), 1: (-lati[0], None, lati[2]),
               2: (-lati[0], lati[1], None)}
    for asse, nome in enumerate("xyz"):
        fisso = spigoli[asse]

        def su_spigolo(c):
            return [c if k == asse else fisso[k] for k in range(3)]

        (ax1, ay1), (ax2, ay2) = punto(su_spigolo(-1)), punto(su_spigolo(1))
        mx, my = (ax1 + ax2) / 2, (ay1 + ay2) / 2
        ox, oy = mx - centro[0], my - centro[1]
        lung = math.hypot(ox, oy) or 1
        ox, oy = ox / lung, oy / lung
        if sp["numeri"]:
            r = (xr, yr, zr)[asse]
            for v in valori[asse]:
                x, y = punto(su_spigolo(2 * (v - r[0]) / (r[1] - r[0]) - 1))
                davanti.append(f'<text x="{x + ox * 14:.1f}" y="{y + oy * 14 + 4:.1f}" '
                               f'text-anchor="middle" fill="#555">{_numero_bello(v)}</text>')
        davanti.append(f'<text x="{mx + ox * (34 if sp["numeri"] else 16):.1f}" '
                       f'y="{my + oy * (34 if sp["numeri"] else 16) + 5:.1f}" text-anchor="middle" '
                       f'font-style="italic" font-size="14" fill="#333">{nome}</text>')

    # ── Le superfici ────────────────────────────────────────────────────────
    luce = vista.verso * 0.6 + np.array([0.0, 0.0, 0.8])
    luce /= np.linalg.norm(luce)
    legenda = []
    for k, s in enumerate(sp["superfici"]):
        if s.tipo == "implicita":
            tinta = _rgb(TINTE[k % len(TINTE)])
            for poligono in s.poligoni(xr, yr, zr):
                vertici = [vista.cubo(*p) for p in poligono]
                normale = np.cross(vertici[1] - vertici[0], vertici[-1] - vertici[0])
                n = np.linalg.norm(normale)
                # Piu' contrasto che per le altre superfici: una superficie
                # implicita non ha la griglia delle linee a disegnarne la forma,
                # la fa vedere solo la luce.
                intensita = 0.42 + 0.58 * (abs(normale @ luce) / n if n else 1.0)
                pixel = [vista.pixel(q) for q in vertici]
                colore = _esadecimale(tinta, intensita)
                # Coordinate intere: i pezzi sono migliaia, e un decimale in
                # piu' a vertice pesa centinaia di KB nel PDF senza vedersi.
                oggetti.append((sum(p[2] for p in pixel) / len(pixel), '<path d="M' + " L".join(
                    f"{x:.0f},{y:.0f}" for x, y, _p in pixel) + f' Z" fill="{colore}" '
                    f'stroke="{colore}" stroke-width="0.6" stroke-linejoin="round"/>'))
            legenda.append((TINTE[k % len(TINTE)], s.etichetta or ((f"{s.nome}: " if s.nome else "")
                                                                  + _equazione_bella(s.testo))))
            continue
        X, Y, Z = s.griglia(xr, yr, zr)
        Q = vista.cubo(X, Y, Z)
        per_altezza = s.tipo == "esplicita"
        tinta = _rgb(TINTE[k % len(TINTE)])
        righe, colonne = X.shape
        for i in range(righe - 1):
            for j in range(colonne - 1):
                indici = ((i, j), (i, j + 1), (i + 1, j + 1), (i + 1, j))
                quattro = [Q[a, b] for a, b in indici]
                if any(not np.isfinite(q).all() for q in quattro):
                    continue
                tagliato = _taglia([(X[a, b], Y[a, b], Z[a, b]) for a, b in indici], xr, yr, zr)
                if len(tagliato) < 3:
                    continue
                vertici = [vista.cubo(*p) for p in tagliato]
                normale = np.cross(quattro[2] - quattro[0], quattro[3] - quattro[1])
                n = np.linalg.norm(normale)
                intensita = 0.62 + 0.38 * (abs(normale @ luce) / n if n else 1.0)
                base = (_colore_scala((np.mean([q[2] for q in vertici]) + 1) / 2)
                        if per_altezza else tinta)
                pixel = [vista.pixel(q) for q in vertici]
                profondita = sum(p[2] for p in pixel) / len(pixel)
                colore = _esadecimale(base, intensita)
                bordo = _esadecimale(base, intensita * 0.72)
                oggetti.append((profondita, '<path d="M' + " L".join(
                    f"{x:.1f},{y:.1f}" for x, y, _p in pixel) + f' Z" fill="{colore}" '
                    f'stroke="{bordo}" stroke-width="0.4"/>'))
        testo = s.etichetta or ((f"{s.nome}: " if s.nome else "") + _equazione_bella(s.testo))
        if s.tipo == "parametrica" and not s.etichetta:
            testo = s.nome or "superficie parametrica"
        legenda.append(("scala" if per_altezza else TINTE[k % len(TINTE)], testo))

    # ── Le curve, a pezzetti: ognuno con la sua profondita' ─────────────────
    for k, c in enumerate(sp["curve"]):
        colore = TINTE[(len(sp["superfici"]) + k + 1) % len(TINTE)]
        xs, ys, zs = c.punti()
        dentro = ((xs >= xr[0]) & (xs <= xr[1]) & (ys >= yr[0]) & (ys <= yr[1])
                  & (zs >= zr[0]) & (zs <= zr[1]) & np.isfinite(xs + ys + zs))
        Q = vista.cubo(xs, ys, zs)
        for i in range(len(xs) - 1):
            if not (dentro[i] and dentro[i + 1]):
                continue
            (x1, y1, p1), (x2, y2, p2) = vista.pixel(Q[i]), vista.pixel(Q[i + 1])
            oggetti.append(((p1 + p2) / 2 + 0.08,
                            f'<line x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}" '
                            f'stroke="{colore}" stroke-width="2.6" stroke-linecap="round"/>'))
        testo = c.etichetta or ((f"{c.nome}: " if c.nome else "") + _equazione_bella(c.testo))
        legenda.append((colore, testo))

    # ── Segmenti, vettori, punti ────────────────────────────────────────────
    for a, b in sp["segmenti"]:
        (x1, y1, p1), (x2, y2, p2) = (vista.pixel(vista.cubo(*a)), vista.pixel(vista.cubo(*b)))
        oggetti.append(((p1 + p2) / 2 + 0.02,
                        f'<line x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}" '
                        f'stroke="#d97706" stroke-width="1.8" stroke-dasharray="6 4"/>'))
    for k, (nome, a, b) in enumerate(sp["vettori"]):
        colore = TINTE[(len(sp["superfici"]) + len(sp["curve"]) + k + 1) % len(TINTE)]
        (x1, y1, p1), (x2, y2, p2) = (vista.pixel(vista.cubo(*a)), vista.pixel(vista.cubo(*b)))
        lung = math.hypot(x2 - x1, y2 - y1) or 1
        ux, uy = (x2 - x1) / lung, (y2 - y1) / lung
        punta = f"{x2:.1f},{y2:.1f} {x2 - ux * 12 - uy * 5:.1f},{y2 - uy * 12 + ux * 5:.1f} " \
                f"{x2 - ux * 12 + uy * 5:.1f},{y2 - uy * 12 - ux * 5:.1f}"
        disegno = (f'<line x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2 - ux * 10:.1f}" y2="{y2 - uy * 10:.1f}" '
                   f'stroke="{colore}" stroke-width="2.6"/><polygon points="{punta}" fill="{colore}"/>')
        if nome:
            disegno += (f'<text x="{(x1 + x2) / 2 - uy * 13:.1f}" y="{(y1 + y2) / 2 + ux * 13 + 4:.1f}" '
                        f'text-anchor="middle" font-style="italic" font-weight="700" font-size="14" '
                        f'fill="{colore}" paint-order="stroke" stroke="#fff" stroke-width="3">'
                        f'{html.escape(nome)}</text>')
        oggetti.append(((p1 + p2) / 2 + 0.03, disegno))
        componenti = "(" + ", ".join(_numero_bello(b[i] - a[i]) for i in range(3)) + ")"
        etichetta = sp["etichette_vettori"][k]
        if etichetta:
            legenda.append((colore, f"{nome} = {etichetta}" if nome else etichetta))
        elif sp["numeri"]:
            legenda.append((colore, f"{nome} = {componenti}" if nome else componenti))
        elif nome:
            legenda.append((colore, nome))
    # I punti si disegnano sopra a tutto: un vertice o un punto di sella
    # nascosto dietro la superficie non servirebbe a niente.
    punti_sopra: list[str] = []
    for nome, x, y, z in sp["punti"]:
        if not (xr[0] <= x <= xr[1] and yr[0] <= y <= yr[1] and zr[0] <= z <= zr[1]):
            continue
        px, py, p = vista.pixel(vista.cubo(x, y, z))
        etichetta = (f"{nome}({_numero_bello(x)}, {_numero_bello(y)}, {_numero_bello(z)})"
                     if sp["numeri"] else nome)
        disegno = f'<circle cx="{px:.1f}" cy="{py:.1f}" r="4" fill="#1b1b1b"/>'
        if etichetta:
            disegno += (f'<text x="{px + 7:.1f}" y="{py - 7:.1f}" font-weight="600" '
                        f'font-size="{11 if sp["numeri"] else 13}" fill="#1b1b1b" paint-order="stroke" '
                        f'stroke="#fff" stroke-width="3">{html.escape(etichetta)}</text>')
        punti_sopra.append(disegno)

    oggetti.sort(key=lambda o: o[0])
    corpo = ("".join(fondo) + "".join(o[1] for o in oggetti) + "".join(punti_sopra)
             + "".join(davanti))
    disegno = (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {LARGHEZZA} {ALTEZZA}" '
               f'width="{LARGHEZZA}" height="{ALTEZZA}" font-family="Segoe UI, Arial, sans-serif" '
               f'font-size="11" id="{uid}">{corpo}</svg>')

    fuori = ['<div class="piano">']
    if sp["titolo"]:
        fuori.append(f'<div class="piano-titolo">{html.escape(_titolo_bello(sp["titolo"]))}</div>')
    fuori.append(disegno)
    if legenda:
        scala = "linear-gradient(90deg," + ",".join(_esadecimale(c) for c in _SCALA) + ")"
        fuori.append('<div class="piano-legenda">' + "".join(
            f'<span><i class="piano-area" style="background:{scala if c == "scala" else c};'
            f'opacity:1"></i>{html.escape(t)}</span>' if c == "scala" or not c.startswith("#")
            else f'<span><i style="background:{c}"></i>{html.escape(t)}</span>'
            for c, t in legenda) + "</div>")
    for nota in sp["note"]:
        fuori.append(f'<div class="piano-nota">{html.escape(nota)}</div>')
    fuori.append("</div>")
    return "".join(fuori)


def in_testo(testo: str) -> list[str]:
    """Lo spazio detto a parole, per il Word e il file di testo che non disegnano."""
    sp = leggi(testo)
    if not sp:
        return []
    fuori = [f"Grafico 3D: {_titolo_bello(sp['titolo'])}" if sp["titolo"] else "Grafico 3D:"]
    for s in sp["superfici"]:
        fuori.append(f"- Superficie {s.nome + ': ' if s.nome else ''}"
                     f"{s.etichetta or _equazione_bella(s.testo)}")
    for c in sp["curve"]:
        fuori.append(f"- Curva {c.nome + ': ' if c.nome else ''}{c.etichetta or _equazione_bella(c.testo)}")
    for nome, x, y, z in sp["punti"]:
        if sp["numeri"]:
            fuori.append(f"- Punto {nome}({_numero_bello(x)}, {_numero_bello(y)}, {_numero_bello(z)})")
        elif nome:
            fuori.append(f"- Punto {nome}")
    for nome, a, b in sp["vettori"]:
        componenti = "(" + ", ".join(_numero_bello(b[i] - a[i]) for i in range(3)) + ")"
        if sp["numeri"]:
            fuori.append(f"- Vettore {nome} = {componenti}" if nome else f"- Vettore {componenti}")
        elif nome:
            fuori.append(f"- Vettore {nome}")
    fuori += [f"- {nota}" for nota in sp["note"]]
    return fuori
