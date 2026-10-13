"""Prova dei disegni dei riassunti: piano, spazio, molecole e chimica.

Scrive un documento con tanti esercizi e definizioni, ognuno col suo disegno,
lo trasforma in PDF con lo stesso codice che l'app usa per i riassunti, e lo
apre. Nel terminale dice, prova per prova, se il disegno e' stato accettato;
alcune prove sono scritte male apposta e devono essere scartate.

Uso:  python tests/prova.py           tutto, e apre il PDF
      python tests/prova.py --muto    solo il conto nel terminale, senza PDF

Esce con 1 se una prova non va come deve: si puo' usare come controllo prima
di pubblicare.
"""
import os
import sys
import tempfile

# Per trovare il codice dell'app anche lanciando lo script da un'altra cartella:
# questo file sta in tests/, il codice nella cartella sopra.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from server.export import chimica, molecola, piano, pdf_rich, spazio  # noqa: E402

# I nomi con le lettere greche e i pedici non stanno nella console di Windows.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# Ogni prova: (argomento, spiegazione, descrizione del piano).
PROVE = [
    # ── Geometria analitica ────────────────────────────────────────────────
    ("Geometria analitica", "Parabola e retta tangente nel punto T.", r"""
titolo: Parabola y = x^2 - 4x + 3 e tangente in T
x: -1, 5
y: -2, 6
curva: y = x^2 - 4x + 3
curva: y = 2x - 6
punto: V (2, -1)
punto: T (3, 0)
"""),
    ("Geometria analitica", "Circonferenza di centro C(1, 2) e raggio 3.", r"""
titolo: Circonferenza (x - 1)^2 + (y - 2)^2 = 9
x: -3, 5
y: -2, 6
curva: (x - 1)^2 + (y - 2)^2 = 9
punto: C (1, 2)
"""),
    ("Geometria analitica", "Ellisse con i fuochi.", r"""
titolo: Ellisse x^2/9 + y^2/4 = 1
x: -4, 4
y: -3, 3
curva: x^2/9 + y^2/4 = 1
punto: F1 (-sqrt(5), 0)
punto: F2 (sqrt(5), 0)
"""),
    ("Geometria analitica", "Iperbole con i suoi asintoti.", r"""
titolo: Iperbole x^2/4 - y^2 = 1
x: -6, 6
y: -4, 4
curva: x^2/4 - y^2 = 1
curva: y = x/2 | asintoto y = x/2
curva: y = -x/2 | asintoto y = −x/2
"""),

    # ── Definizioni con le lettere ─────────────────────────────────────────
    ("Definizioni", "La parabola come luogo dei punti equidistanti da fuoco e direttrice.", r"""
titolo: La parabola come luogo dei punti
numeri: no
x: -3, 3
y: -2, 4
curva: y = x^2/4 | parabola
curva d: y = -1 | direttrice
punto: F (0, 1)
punto: P (2, 1)
punto: H (2, -1)
segmento: P - F
segmento: P - H
nota: $\overline{PF} = \overline{PH}$ per ogni punto P della parabola
"""),
    ("Definizioni", "Il ruolo del parametro a in y = ax².", r"""
titolo: Come cambia la parabola al variare di a
numeri: no
x: -3, 3
y: -3, 4
curva: y = ax^2 per a = 0.25, 1, 3, -1 | $y = ax^2$
"""),

    # ── Analisi 1 ──────────────────────────────────────────────────────────
    ("Analisi 1", "Funzione fratta con asintoto verticale e orizzontale.", r"""
titolo: y = (x + 1)/(x - 2)
x: -4, 8
y: -5, 7
curva: y = (x + 1)/(x - 2)
curva: x = 2 | asintoto x = 2
curva: y = 1 | asintoto y = 1
"""),
    ("Analisi 1", "Studio di funzione: massimo, minimo e flesso.", r"""
titolo: y = x^3 - 3x
x: -3, 3
y: -4, 4
curva: y = x^3 - 3x
punto: M (-1, 2)
punto: m (1, -2)
punto: F (0, 0)
"""),
    ("Analisi 1", "Esponenziale e logaritmo, simmetrici rispetto a y = x.", r"""
titolo: y = e^x e y = ln x
x: -3, 5
y: -3, 5
curva: y = exp(x)
curva: y = log(x)
curva: y = x | bisettrice y = x
"""),
    ("Analisi 1", "Funzione definita a tratti, con pallini pieni e vuoti.", r"""
titolo: Funzione a tratti
x: -3, 3
y: -2, 5
curva: y = x + 1 se x < 0
curva: y = x^2 se 0 <= x <= 2
curva: y = 1 se x > 2
"""),
    ("Analisi 1", "Integrale definito come area sotto la curva.", r"""
titolo: Area sotto y = x^2 fra 0 e 2
x: -1, 3
y: -1, 5
curva: y = x^2
area: sotto y = x^2 da 0 a 2 | $\int_0^2 x^2\,dx = \frac{8}{3}$
"""),
    ("Analisi 1", "Area compresa fra due curve.", r"""
titolo: Area fra y = x e y = x^2
x: -0.5, 1.5
y: -0.5, 1.5
curva: y = x
curva: y = x^2
area: tra y = x e y = x^2 da 0 a 1 | $\int_0^1 (x - x^2)\,dx = \frac{1}{6}$
"""),

    # ── Algebra ────────────────────────────────────────────────────────────
    ("Algebra", "Disequazione di secondo grado: dove la parabola sta sopra l'asse x.", r"""
titolo: x^2 - 2x - 3 > 0
x: -3, 5
y: -5, 6
curva: y = x^2 - 2x - 3
area: x < -1 oppure x > 3 | soluzioni: x < −1 oppure x > 3
punto: (-1, 0)
punto: (3, 0)
"""),
    ("Algebra", "Sistema di due equazioni: la soluzione e' l'incrocio.", r"""
titolo: Sistema x + y = 4, x - y = 2
x: -1, 6
y: -3, 5
curva: y = 4 - x
curva: y = x - 2
punto: S (3, 1)
"""),

    # ── Trigonometria ──────────────────────────────────────────────────────
    ("Trigonometria", "Circonferenza goniometrica: seno e coseno di un angolo.", r"""
titolo: Circonferenza goniometrica
numeri: no
x: -1.4, 1.4
y: -1.4, 1.4
curva: x^2 + y^2 = 1
punto: P (cos(pi/3), sin(pi/3))
punto: H (cos(pi/3), 0)
segmento: P - H
vettore: (cos(pi/3), sin(pi/3))
angolo α: da 0° a 60°
nota: $\cos\alpha$ è l'ascissa di P, $\sin\alpha$ la sua ordinata
"""),
    ("Trigonometria", "Seno e coseno in un periodo, con le tacche a multipli di π.", r"""
titolo: y = sin x e y = cos x
x: -0.5, 7
y: -1.5, 1.5
tacche x: pi/2
curva: y = sin(x)
curva: y = cos(x)
"""),
    ("Trigonometria", "La tangente e i suoi asintoti verticali.", r"""
titolo: y = tan x
x: -4.8, 4.8
y: -4, 4
tacche x: pi/2
curva: y = tan(x)
"""),

    # ── Curve speciali ─────────────────────────────────────────────────────
    ("Curve parametriche e polari", "Cicloide, una curva parametrica.", r"""
titolo: Cicloide
x: -1, 14
y: -1, 3
tacche x: pi
curva: x = t - sin(t), y = 1 - cos(t) con t da 0 a 4*pi
"""),
    ("Curve parametriche e polari", "Cardioide, una curva polare.", r"""
titolo: Cardioide r = 1 + cos θ
x: -1, 2.5
y: -1.75, 1.75
curva: r = 1 + cos(θ)
"""),
    ("Curve parametriche e polari", "Rosa a quattro petali.", r"""
titolo: Rosa r = cos(2θ)
x: -1.2, 1.2
y: -1.2, 1.2
curva: r = cos(2θ)
"""),

    # ── Vettori e numeri complessi ─────────────────────────────────────────
    ("Vettori e numeri complessi", "Somma di vettori con la regola punta-coda.", r"""
titolo: u + v = w
x: -1, 5
y: -1, 5
punto: P (2, 1)
vettore u: (2, 1)
vettore v: (1, 2) da P
vettore w: (3, 3)
"""),
    ("Vettori e numeri complessi", "Un numero complesso nel piano di Gauss.", r"""
titolo: z = 3 + 2i
assi: Re, Im
x: -1, 4
y: -1, 3
punto: z (3, 2)
vettore: (3, 2)
angolo θ: da 0 a atan(2/3)
"""),

    # ── Analisi 2 ──────────────────────────────────────────────────────────
    ("Analisi 2", "Dominio di una funzione di due variabili.", r"""
titolo: Dominio di f(x, y) = sqrt(4 - x^2 - y^2)
x: -3, 3
y: -3, 3
curva: x^2 + y^2 = 4
area: x^2 + y^2 <= 4 | dominio: $x^2 + y^2 \le 4$
"""),
    ("Analisi 2", "Curve di livello di f(x, y) = x^2 + y^2.", r"""
titolo: Curve di livello x^2 + y^2 = c
x: -3, 3
y: -3, 3
curva: x^2 + y^2 = c per c = 1, 2, 4, 6 | $x^2 + y^2 = c$
"""),

    # ── Geometria: poligoni, lati, angoli ──────────────────────────────────
    ("Geometria", "Triangolo rettangolo: lati col nome e angolo retto col quadratino.", r"""
titolo: Teorema di Pitagora
numeri: no
x: -0.5, 4.5
y: -0.5, 3.5
punto: A (0, 0)
punto: B (4, 0)
punto: C (0, 3)
poligono: A, B, C
lato: A - B | b
lato: A - C | c
lato: B - C | a
angolo: in A tra B e C
angolo β: in B tra C e A
nota: $a^2 = b^2 + c^2$
"""),
    ("Geometria", "Altezza di un triangolo, tratteggiata.", r"""
titolo: Altezza CH del triangolo ABC
x: -1, 6
y: -1, 5
punto: A (0, 0)
punto: B (5, 0)
punto: C (2, 4)
punto: H (2, 0)
poligono: A, B, C | triangolo ABC
segmento: C - H | h
angolo: in H tra B e C
"""),
    ("Geometria", "Algebra lineare: l'immagine del quadrato unitario.", r"""
titolo: Il quadrato unitario trasformato da A = [[2, 1], [0, 1]]
x: -0.5, 3.5
y: -0.5, 1.5
poligono: (0, 0), (1, 0), (1, 1), (0, 1) | quadrato unitario
poligono: (0, 0), (2, 0), (3, 1), (1, 1) | la sua immagine
"""),

    # ── Campi ──────────────────────────────────────────────────────────────
    ("Campi vettoriali", "Campo rotazionale con due linee di campo.", r"""
titolo: F(x, y) = (-y, x)
x: -3, 3
y: -3, 3
campo: (-y, x)
linea: da (1, 0)
linea: da (2, 0)
"""),
    ("Campi vettoriali", "Il gradiente è perpendicolare alle curve di livello.", r"""
titolo: Gradiente di f = x^2 + y^2
x: -3, 3
y: -3, 3
campo: gradiente di x^2 + y^2
curva: x^2 + y^2 = c per c = 1, 4 | curve di livello
"""),
    ("Equazioni differenziali", "Campo di direzioni e soluzioni per tre dati iniziali.", r"""
titolo: y' = x - y
x: -3, 3
y: -3, 3
direzioni: y' = x - y
soluzione: da (0, 1)
soluzione: da (0, -2)
soluzione: da (-2, 2)
"""),
    ("Equazioni differenziali", "Crescita logistica: le soluzioni tendono all'equilibrio.", r"""
titolo: y' = y(1 - y)
x: 0, 8
y: -0.5, 1.5
direzioni: y' = y*(1 - y)
soluzione: da (0, 0.1)
soluzione: da (0, 1.4)
curva: y = 1 | equilibrio y = 1
"""),

    # ── Successioni, serie, somme di Riemann ───────────────────────────────
    ("Successioni e serie", "La successione 1/n tende a 0.", r"""
titolo: a_n = 1/n
successione: a_n = 1/n per n da 1 a 20
curva: y = 0 | limite 0
"""),
    ("Successioni e serie", "Una successione a segni alterni.", r"""
titolo: a_n = (-1)^n/n
x: 0, 21
y: -1.2, 0.7
successione: a_n = (-1)^n/n per n da 1 a 20
"""),
    ("Successioni e serie", "Le somme parziali di Σ 1/n² salgono verso π²/6.", r"""
titolo: Serie Σ 1/n^2
x: 0, 21
y: 0, 2
serie: a_n = 1/n^2 per n da 1 a 20
curva: y = pi^2/6 | $\pi^2/6$
"""),
    ("Integrali", "Somma di Riemann con l'estremo sinistro.", r"""
titolo: Somma di Riemann sinistra, n = 8
x: -0.5, 2.5
y: -0.5, 4.5
curva: y = x^2
rettangoli: y = x^2 da 0 a 2 con n = 8 sinistra
"""),
    ("Integrali", "Con più rettangoli e il punto medio ci si avvicina a 8/3.", r"""
titolo: Somma di Riemann nel punto medio, n = 16
x: -0.5, 2.5
y: -0.5, 4.5
curva: y = x^2
rettangoli: y = x^2 da 0 a 2 con n = 16 medio
"""),

    # ── Statistica e probabilità ───────────────────────────────────────────
    ("Statistica", "Istogramma con classi tutte larghe uguali: l'altezza è la frequenza.", r"""
titolo: Altezze degli studenti
assi: altezza (cm), frequenza
istogramma: [150, 160) 4; [160, 170) 9; [170, 180) 6; [180, 190) 1
"""),
    ("Statistica", "Classi di ampiezza diversa: si disegna la densità.", r"""
titolo: Redditi mensili
assi: reddito (€), densità
istogramma: [0, 1000) 10; [1000, 1500) 25; [1500, 2000) 30; [2000, 4000) 20
"""),
    ("Statistica", "Due gruppi a confronto con il boxplot, uno con un valore anomalo.", r"""
titolo: Voti delle due classi
assi: voto, classe
boxplot 3A: 4, 5.5, 6.5, 7, 9
boxplot 3B: 3, 5, 6, 8, 9.5 con anomali 1
"""),
    ("Statistica", "Dispersione e retta di regressione.", r"""
titolo: Ore di studio e voto
assi: ore, voto
dati: (1, 4.5), (2, 5), (3, 6), (4, 6), (5, 7.5), (6, 7), (7, 8.5), (8, 9)
curva: y = 0.61x + 3.9 | retta di regressione
"""),
    ("Probabilità", "Normale di media 170 e deviazione standard 8: la probabilità entro una σ.", r"""
titolo: Distribuzione normale N(170, 8^2)
x: 140, 200
y: 0, 0.055
assi: x, densità
curva: y = exp(-(x - 170)^2/(2*8^2))/(8*sqrt(2*pi))
area: sotto y = exp(-(x - 170)^2/(2*8^2))/(8*sqrt(2*pi)) da 162 a 178 | $P(162 \le X \le 178) \approx 0.68$
"""),
    # ── Fisica ──────────────────────────────────────────────────────────────
    ("Fisica", "Grafico v-t: lo spostamento è l'area sotto la curva.", r"""
titolo: Moto uniformemente accelerato
assi: t (s), v (m/s)
x: 0, 6
y: 0, 16
curva: y = 2 + 2x se 0 <= x <= 5 | $v = 2 + 2t$
area: sotto y = 2 + 2x da 0 a 5 | spostamento $\Delta s = 35\,\mathrm{m}$
"""),
    ("Fisica", "Diagramma di corpo libero, senza assi.", r"""
titolo: Forze su un blocco trascinato
numeri: no
assi: no
x: -3.5, 3.5
y: -3, 3
poligono: (-1, -0.7), (1, -0.7), (1, 0.7), (-1, 0.7)
punto: G (0, 0)
vettore P: (0, -2.2) da G
vettore N: (0, 2.2) da G
vettore F: (2.4, 0) da G
vettore Fa: (-1.4, 0) da G
nota: $\vec F + \vec F_a + \vec N + \vec P = m\vec a$
"""),
    ("Fisica", "Piano inclinato: peso e sua componente lungo il piano.", r"""
titolo: Corpo su un piano inclinato
numeri: no
assi: no
x: -0.5, 6
y: -0.5, 4
punto: A (0, 0)
punto: B (5, 0)
punto: C (5, 3)
poligono: A, B, C
angolo α: in A tra B e C
punto: G (2.5, 1.9)
vettore P: (0, -1.6) da G
vettore N: (-0.62, 1.03) da G
vettore Pt: (-1.18, -0.71) da G
"""),
    ("Fisica", "Moto parabolico: gittata e altezza massima.", r"""
titolo: Moto parabolico, v0 = 10 m/s a 45°
assi: x (m), y (m)
x: 0, 11
y: 0, 3.5
curva: y = x - 0.098x^2 se 0 <= x <= 10.2
punto: H (5.1, 2.55)
punto: G (10.2, 0)
"""),
    ("Fisica", "Il campo elettrico di una carica positiva.", r"""
titolo: Campo elettrico di una carica positiva
numeri: no
assi: no
x: -3, 3
y: -3, 3
campo: (x/(x^2+y^2)^1.5, y/(x^2+y^2)^1.5)
punto: q (0, 0)
"""),
    ("Probabilità", "Una distribuzione discreta: la somma di due dadi.", r"""
titolo: Somma di due dadi
assi: somma, probabilità
istogramma: [1.5, 2.5) 1/36; [2.5, 3.5) 2/36; [3.5, 4.5) 3/36; [4.5, 5.5) 4/36; [5.5, 6.5) 5/36; [6.5, 7.5) 6/36; [7.5, 8.5) 5/36; [8.5, 9.5) 4/36; [9.5, 10.5) 3/36; [10.5, 11.5) 2/36; [11.5, 12.5) 1/36
"""),
]

# Prove scritte male apposta: il piano NON deve essere disegnato.
DA_SCARTARE = [
    ("codice al posto della formula", 'curva: y = __import__("os").system("dir")'),
    ("segmento verso un punto che non c'è", "punto: A (0, 0)\nsegmento: A - B"),
    ("riga che non si capisce", "curva: y = x^2\ndisegna qualcosa di bello"),
    ("formula sbagliata", "curva: y = x^^2 +"),
    ("poligono con due vertici", "punto: A (0, 0)\npunto: B (1, 1)\npoligono: A, B"),
    ("soluzione senza equazione", "soluzione: da (0, 1)"),
    ("successione senza intervallo di n", "successione: a_n = 1/n"),
    ("rettangoli sotto una circonferenza", "rettangoli: x^2 + y^2 = 1 da 0 a 1 con n = 4"),
    ("boxplot con i quartili fuori ordine", "boxplot: 2, 7, 5, 9, 12"),
    ("boxplot con quattro numeri", "boxplot: 2, 5, 7, 9"),
    ("istogramma con classi sovrapposte", "istogramma: [0, 10) 4; [5, 15) 3"),
    ("istogramma con frequenza negativa", "istogramma: [0, 10) -4"),
    ("dati con un punto solo", "dati: (1, 2)"),
]

# Le prove nello spazio a tre dimensioni (blocco «spazio»).
PROVE_3D = [
    ("Analisi 2 in 3D", "Paraboloide: il grafico di f(x, y) = x² + y², col vertice.", r"""
titolo: Paraboloide z = x^2 + y^2
x: -2, 2
y: -2, 2
z: 0, 8
superficie: z = x^2 + y^2
punto: V (0, 0, 0)
"""),
    ("Analisi 2 in 3D", "Punto di sella: né massimo né minimo.", r"""
titolo: Sella z = x^2 - y^2
x: -2, 2
y: -2, 2
z: -4, 4
superficie: z = x^2 - y^2
punto: S (0, 0, 0)
"""),
    ("Analisi 2 in 3D", "Curve di livello disegnate sulla superficie.", r"""
titolo: Curve di livello sul paraboloide
x: -2, 2
y: -2, 2
z: 0, 4
superficie: z = x^2 + y^2
curva: x = cos(t), y = sin(t), z = 1 con t da 0 a 2*pi | livello z = 1
curva: x = 1.5*cos(t), y = 1.5*sin(t), z = 2.25 con t da 0 a 2*pi | livello z = 2.25
"""),
    ("Trigonometria in 3D", "Una superficie trigonometrica.", r"""
titolo: z = sin x · cos y
x: -pi, pi
y: -pi, pi
z: -1.5, 1.5
superficie: z = sin(x)*cos(y)
"""),
    ("Geometria nello spazio", "Il piano x + y + z = 3 e un suo punto.", r"""
titolo: Piano x + y + z = 3
x: 0, 3
y: 0, 3
z: 0, 3
vista: 30, 25
superficie: z = 3 - x - y
punto: P (1, 1, 1)
"""),
    ("Geometria nello spazio", "Elica circolare, una curva nello spazio.", r"""
titolo: Elica
x: -1.5, 1.5
y: -1.5, 1.5
z: 0, 4
curva: x = cos(t), y = sin(t), z = t/pi con t da 0 a 4*pi
"""),
    ("Vettori nello spazio", "Prodotto vettoriale: w è perpendicolare a u e v.", r"""
titolo: Prodotto vettoriale
x: 0, 2
y: 0, 2
z: 0, 2
vettore u: (1.5, 0, 0)
vettore v: (0, 1.5, 0)
vettore w: (0, 0, 1.5) | u × v
"""),
    ("Topologia", "Sfera, superficie parametrica.", r"""
titolo: Sfera di raggio 1
x: -1.2, 1.2
y: -1.2, 1.2
z: -1.2, 1.2
superficie: x = cos(u)*sin(v), y = sin(u)*sin(v), z = cos(v) con u da 0 a 2*pi, v da 0 a pi
"""),
    ("Topologia", "Toro.", r"""
titolo: Toro
x: -3.2, 3.2
y: -3.2, 3.2
z: -3.2, 3.2
vista: -60, 40
superficie: x = (2 + cos(v))*cos(u), y = (2 + cos(v))*sin(u), z = sin(v) con u da 0 a 2*pi, v da 0 a 2*pi
"""),
    ("Topologia", "Nastro di Möbius: una superficie con una faccia sola.", r"""
titolo: Nastro di Möbius
x: -1.6, 1.6
y: -1.6, 1.6
z: -1, 1
vista: -50, 35
superficie: x = (1 + v/2*cos(u/2))*cos(u), y = (1 + v/2*cos(u/2))*sin(u), z = v/2*sin(u/2) con u da 0 a 2*pi, v da -1 a 1
"""),

    # ── Quadriche scritte in forma implicita ───────────────────────────────
    ("Quadriche", "Ellissoide.", r"""
titolo: Ellissoide x^2/4 + y^2 + z^2/2 = 1
x: -2.2, 2.2
y: -2.2, 2.2
z: -2.2, 2.2
superficie: x^2/4 + y^2 + z^2/2 = 1
"""),
    ("Quadriche", "Iperboloide a una falda.", r"""
titolo: x^2 + y^2 - z^2 = 1
x: -2.5, 2.5
y: -2.5, 2.5
z: -2, 2
superficie: x^2 + y^2 - z^2 = 1
"""),
    ("Quadriche", "Iperboloide a due falde.", r"""
titolo: z^2 - x^2 - y^2 = 1
x: -2.5, 2.5
y: -2.5, 2.5
z: -2.5, 2.5
superficie: z^2 - x^2 - y^2 = 1
"""),
    ("Quadriche", "Cono.", r"""
titolo: Cono x^2 + y^2 = z^2
x: -2, 2
y: -2, 2
z: -2, 2
superficie: x^2 + y^2 = z^2
"""),
]

# Prove 3D scritte male apposta: lo spazio NON deve essere disegnato.
DA_SCARTARE_3D = [
    ("3D: codice al posto della superficie", 'superficie: z = __import__("os").getcwd()'),
    ("3D: superficie parametrica senza intervallo di v",
     "superficie: x = cos(u), y = sin(u), z = v con u da 0 a 2*pi"),
    ("3D: superficie con due uguali", "superficie: x^2 = y^2 = z^2"),
]


# Le molecole (blocco «molecola»): 3D per le piccole, scheletro per le organiche.
PROVE_MOLECOLE = [
    ("Chimica", "L'acqua è piegata: il modello 3D lo fa vedere.",
     "nome: acqua\nformula: H2O\nsmiles: O\nnota: angolo H–O–H di circa 104,5°"),
    ("Chimica", "L'ammoniaca è una piramide a base triangolare.", "nome: ammoniaca\nformula: NH3\nsmiles: N"),
    ("Chimica", "Il metano è un tetraedro.", "nome: metano\nformula: CH4\nsmiles: C"),
    ("Chimica", "L'anidride carbonica è lineare, con due doppi legami.",
     "nome: anidride carbonica\nformula: CO2\nsmiles: O=C=O"),
    ("Chimica", "Acido solforico, con la formula scritta come nei libri.",
     "nome: acido solforico\nformula: H2SO4\nsmiles: OS(=O)(=O)O"),
    ("Chimica", "Uno ione: l'ammonio.", "nome: ione ammonio\nformula: NH4^+\nsmiles: [NH4+]"),
    ("Chimica organica", "Il benzene, col cerchio dell'aromaticità.", "nome: benzene\nsmiles: c1ccccc1"),
    ("Chimica organica", "Acido acetilsalicilico (aspirina).",
     "nome: acido acetilsalicilico\nformula: C9H8O4\nsmiles: CC(=O)Oc1ccccc1C(=O)O"),
    ("Chimica organica", "Un centro stereogenico: (R)-butan-2-olo.",
     "nome: (R)-butan-2-olo\nformula: C4H10O\nsmiles: C[C@@H](O)CC"),
    ("Chimica organica", "Cicloesano: scheletro e sedia in 3D.",
     "nome: cicloesano\nformula: C6H12\nsmiles: C1CCCCC1\nvista: entrambe"),
    # Col nome IUPAC (serve Java: senza, vale solo la formula).
    ("Controllo col nome", "Nome e SMILES dicono la stessa molecola.",
     "nome: acido salicilico\niupac: 2-hydroxybenzoic acid\nformula: C7H6O3\nsmiles: OC(=O)c1ccccc1O"),
    ("Controllo col nome", "SMILES sbagliato (dimetiletere), il nome lo corregge in etanolo.",
     "nome: etanolo\niupac: ethanol\nformula: C2H6O\nsmiles: COC"),
    ("Controllo col nome", "Solo il nome, senza SMILES.",
     "nome: acetone\niupac: propan-2-one\nformula: C3H6O"),
    # La struttura di Lewis: i puntini li conta il programma.
    ("Strutture di Lewis", "L'acqua, con le due coppie non condivise.",
     "nome: acqua\nformula: H2O\nsmiles: O\nvista: lewis"),
    ("Strutture di Lewis", "L'anidride carbonica: due doppi legami.",
     "nome: anidride carbonica\nformula: CO2\nsmiles: O=C=O\nvista: lewis"),
    ("Strutture di Lewis", "Lo ione nitrato, con le cariche formali.",
     "nome: ione nitrato\nformula: NO3^-\nsmiles: [O-][N+](=O)[O-]\nvista: lewis"),
    ("Strutture di Lewis", "Il monossido di carbonio: triplo legame e una coppia per atomo.",
     "nome: monossido di carbonio\nformula: CO\nsmiles: [C-]#[O+]\nvista: lewis"),
]

# Molecole scritte male apposta: NON devono essere disegnate.
DA_SCARTARE_MOLECOLE = [
    ("molecola: formula che non torna con lo SMILES", "nome: acqua\nformula: H2O2\nsmiles: O"),
    ("molecola: anello non chiuso", "smiles: C1CC"),
    ("molecola: carbonio con cinque legami", "smiles: C(C)(C)(C)(C)C"),
    ("molecola: riga che non si capisce", "nome: acqua\nsmiles: O\ncolore: blu"),
    ("molecola: il nome dice un'altra formula",
     "nome: etanolo\niupac: propan-1-ol\nformula: C2H6O\nsmiles: CCO"),
]


# Gli altri disegni della chimica (export/chimica.py): (argomento, spiegazione,
# tipo di blocco, descrizione).
PROVE_CHIMICA = [
    ("Reazioni", "Uno schema con le condizioni sulla freccia e la doppia freccia.", "reazione",
     "titolo: Esterificazione di Fischer\nreagenti: CC(=O)O | acido acetico; CCO | etanolo\n"
     "prodotti: CC(=O)OCC | acetato di etile; O | acqua\nsopra: H2SO4\nsotto: calore\ntipo: equilibrio"),
    ("Reazioni", "Una reazione coi coefficienti.", "reazione",
     "titolo: Combustione del metano\nreagenti: C | metano; 2 O=O | ossigeno\n"
     "prodotti: O=C=O | anidride carbonica; 2 O | acqua"),
    ("Meccanismi", "SN2: l'ossidrile attacca il carbonio e il bromo se ne va.", "reazione",
     "titolo: Sostituzione nucleofila SN2\nreagenti: [OH-:1]; [CH3:2][Br:3]\n"
     "prodotti: CO | metanolo; [Br-] | ione bromuro\nfrecce: 1 -> 2; 2-3 -> 3"),
    ("Meccanismi", "Addizione elettrofila: il doppio legame prende l'idrogeno.", "reazione",
     "titolo: Addizione di HBr al propene, primo passo\nreagenti: [CH3:4][CH:1]=[CH2:2]; [H:5][Br:3]\n"
     "prodotti: C[CH+]C; [Br-]\nfrecce: 1-2 -> 2-5; 5-3 -> 3"),
    ("Orbitali", "La configurazione a caselle: la calcola il programma.", "orbitali",
     "titolo: Configurazione dell'ossigeno\nelemento: O"),
    ("Orbitali", "Uno ione di un metallo di transizione.", "orbitali",
     "elemento: Fe^3+\nnota: lo ione perde prima i due elettroni 4s"),
    ("Orbitali", "Uno stato eccitato, scritto dal testo.", "orbitali",
     "titolo: Il carbonio eccitato, prima dell'ibridazione\nelemento: C\nconfigurazione: 1s2 2s1 2p3"),
    ("Orbitali", "La forma degli orbitali s, p e d.", "orbitali",
     "titolo: La forma degli orbitali\nforme: s, p, d"),
    ("Orbitali", "Gli orbitali ibridi.", "orbitali", "titolo: Orbitali ibridi\nforme: sp, sp2, sp3"),
    ("Titolazioni", "Acido debole con base forte, con l'indicatore.", "titolazione",
     "analita: acido debole, 0,1 M, 25 mL, Ka = 1,8e-5 | acido acetico\n"
     "titolante: base forte, 0,1 M | NaOH\nindicatore: fenolftaleina, 8,2 - 10"),
    ("Titolazioni", "Acido forte con base forte.", "titolazione",
     "titolo: Acido forte con base forte\nanalita: acido forte, 0.1 M, 50 mL\n"
     "titolante: base forte, 0.2 M"),
    ("Titolazioni", "Base debole con acido forte.", "titolazione",
     "analita: base debole, 0.1 M, 20 mL, Kb = 1.8 × 10^-5 | ammoniaca\n"
     "titolante: acido forte, 0.1 M | HCl"),
    ("Profili di energia", "Coi valori del testo e il catalizzatore.", "energia",
     "titolo: Una reazione esotermica\nlivelli: reagenti 0; stato di transizione 85; prodotti -40\n"
     "catalizzatore: 50"),
    ("Profili di energia", "Senza numeri: resta la forma.", "energia",
     "tipo: endotermica\ncatalizzatore: sì"),
    ("Profili di energia", "Un meccanismo a due stadi, con l'intermedio.", "energia",
     "titolo: Meccanismo a due stadi\n"
     "livelli: reagenti 0; TS1 60; intermedio 20; TS2 45; prodotti -30"),
    ("Reticoli cristallini", "Cubico a corpo centrato.", "reticolo",
     "tipo: cubico a corpo centrato\natomi: Fe"),
    ("Reticoli cristallini", "Cubico a facce centrate.", "reticolo",
     "tipo: cubico a facce centrate\natomi: Cu"),
    ("Reticoli cristallini", "Il cloruro di sodio.", "reticolo", "tipo: cloruro di sodio"),
    ("Reticoli cristallini", "Il cloruro di cesio.", "reticolo", "tipo: cloruro di cesio"),
    ("Reticoli cristallini", "Il diamante, coi suoi legami.", "reticolo", "tipo: diamante"),
    ("Tavola periodica", "Un gruppo in evidenza, colorata per famiglie.", "tavola",
     "titolo: Gli alogeni\ngruppo: 17 | gli alogeni\ncolora: famiglie"),
    ("Tavola periodica", "Una proprieta' periodica.", "tavola",
     "titolo: Come cambia l'elettronegatività\ntendenza: elettronegatività"),
    ("Tavola periodica", "Due elementi in evidenza.", "tavola", "evidenzia: Na, Cl\ncolora: blocchi"),
]

# Disegni di chimica scritti male apposta: NON devono essere disegnati.
DA_SCARTARE_CHIMICA = [
    ("reazione non bilanciata", "reazione", "reagenti: C; O=O\nprodotti: O=C=O; O"),
    ("reazione con uno SMILES che non esiste", "reazione", "reagenti: C1CC\nprodotti: CCC"),
    ("reazione con le cariche che non tornano", "reazione", "reagenti: [OH-]; CBr\nprodotti: CO; Br"),
    ("freccia verso un atomo che non c'è", "reazione",
     "reagenti: [OH-:1]; [CH3:2][Br:3]\nprodotti: CO; [Br-]\nfrecce: 1 -> 7"),
    ("freccia da un legame che non c'è", "reazione",
     "reagenti: [OH-:1]; [CH3:2][Br:3]\nprodotti: CO; [Br-]\nfrecce: 1-3 -> 2"),
    ("elemento che non esiste", "orbitali", "elemento: Xx"),
    ("configurazione con gli elettroni sbagliati", "orbitali", "elemento: O\nconfigurazione: 1s2 2s2 2p6"),
    ("tre elettroni in un orbitale s", "orbitali", "configurazione: 1s3"),
    ("orbitale che non esiste", "orbitali", "forme: g"),
    ("acido debole senza la sua Ka", "titolazione",
     "analita: acido debole, 0.1 M, 25 mL\ntitolante: base forte, 0.1 M"),
    ("acido titolato con un acido", "titolazione",
     "analita: acido forte, 0.1 M, 25 mL\ntitolante: acido forte, 0.1 M"),
    ("titolazione senza il volume", "titolazione",
     "analita: acido forte, 0.1 M\ntitolante: base forte, 0.1 M"),
    ("stato di transizione piu' basso dei reagenti", "energia",
     "livelli: reagenti 0; stato di transizione -5; prodotti -40"),
    ("profilo senza stato di transizione", "energia", "livelli: reagenti 0; prodotti -40"),
    ("catalizzatore che alza la barriera", "energia",
     "livelli: reagenti 0; TS 80; prodotti -40\ncatalizzatore: 90"),
    ("catalizzatore senza valore in un profilo coi numeri", "energia",
     "livelli: reagenti 0; TS 80; prodotti -40\ncatalizzatore: sì"),
    ("reticolo che non esiste", "reticolo", "tipo: piramidale"),
    ("reticolo ionico con un elemento solo", "reticolo", "tipo: cloruro di sodio\natomi: Na"),
    ("tavola con un elemento che non esiste", "tavola", "evidenzia: Na, Zz"),
    ("tavola con un gruppo che non esiste", "tavola", "gruppo: 19"),
    ("tavola con una proprieta' sconosciuta", "tavola", "tendenza: simpatia"),
]


def main() -> None:
    righe = ["# Prova dei disegni dei riassunti", ""]
    argomento = None
    accettate = 0
    print("Prove che devono riuscire:")
    for tema, spiegazione, descrizione in PROVE:
        esito = piano.leggi(descrizione.strip())
        segno = "ok" if esito else "SCARTATA"
        accettate += bool(esito)
        print(f"  [{segno:8}] {tema}: {spiegazione}")
        if tema != argomento:
            righe += [f"## {tema}", ""]
            argomento = tema
        righe += [spiegazione, "", "```piano", descrizione.strip(), "```", ""]
    for tema, spiegazione, descrizione in PROVE_3D:
        esito = spazio.leggi(descrizione.strip())
        segno = "ok" if esito else "SCARTATA"
        accettate += bool(esito)
        print(f"  [{segno:8}] {tema}: {spiegazione}")
        if tema != argomento:
            righe += [f"## {tema}", ""]
            argomento = tema
        righe += [spiegazione, "", "```spazio", descrizione.strip(), "```", ""]
    for tema, spiegazione, descrizione in PROVE_MOLECOLE:
        esito = molecola.leggi(descrizione.strip())
        segno = "ok" if esito else "SCARTATA"
        accettate += bool(esito)
        controllo = f" (controllo: {esito['verifica']})" if esito else ""
        print(f"  [{segno:8}] {tema}: {spiegazione}{controllo}")
        if tema != argomento:
            righe += [f"## {tema}", ""]
            argomento = tema
        righe += [spiegazione, "", "```molecola", descrizione.strip(), "```", ""]
    for tema, spiegazione, tipo, descrizione in PROVE_CHIMICA:
        esito = chimica.leggi(tipo, descrizione)
        segno = "ok" if esito else "SCARTATA"
        accettate += bool(esito)
        print(f"  [{segno:8}] {tema}: {spiegazione}")
        if tema != argomento:
            righe += [f"## {tema}", ""]
            argomento = tema
        righe += [spiegazione, "", "```" + tipo, descrizione.strip(), "```", ""]

    print("\nProve che devono essere scartate:")
    scartate = 0
    for motivo, descrizione in DA_SCARTARE:
        esito = piano.leggi(descrizione)
        scartate += not esito
        print(f"  [{'ok' if not esito else 'ERRORE':8}] {motivo}: "
              f"{'scartata' if not esito else 'accettata, non doveva'}")
    for motivo, descrizione in DA_SCARTARE_3D:
        esito = spazio.leggi(descrizione)
        scartate += not esito
        print(f"  [{'ok' if not esito else 'ERRORE':8}] {motivo}: "
              f"{'scartata' if not esito else 'accettata, non doveva'}")

    for motivo, descrizione in DA_SCARTARE_MOLECOLE:
        esito = molecola.leggi(descrizione)
        scartate += not esito
        print(f"  [{'ok' if not esito else 'ERRORE':8}] {motivo}: "
              f"{'scartata' if not esito else 'accettata, non doveva'}")

    for motivo, tipo, descrizione in DA_SCARTARE_CHIMICA:
        esito = chimica.leggi(tipo, descrizione)
        scartate += not esito
        print(f"  [{'ok' if not esito else 'ERRORE':8}] {motivo}: "
              f"{'scartata' if not esito else 'accettata, non doveva'}")

    # La configurazione elettronica di ogni elemento deve avere tanti elettroni
    # quanti ne ha l'elemento, e sulla tavola ognuno ha la sua casella.
    for z, simbolo in enumerate(chimica.SIMBOLI, start=1):
        assert sum(n for _, n in chimica.configurazione(z)) == z, simbolo
    assert len({chimica.posto(z) for z in range(1, 119)}) == 118

    totale = len(PROVE) + len(PROVE_3D) + len(PROVE_MOLECOLE) + len(PROVE_CHIMICA)
    da_scartare = (len(DA_SCARTARE) + len(DA_SCARTARE_3D) + len(DA_SCARTARE_MOLECOLE)
                   + len(DA_SCARTARE_CHIMICA))
    print(f"\nRiuscite {accettate}/{totale}, scartate {scartate}/{da_scartare}.")
    tutto_bene = accettate == totale and scartate == da_scartare
    if "--muto" in sys.argv:
        sys.exit(0 if tutto_bene else 1)

    # Il PDF, con lo stesso codice dei riassunti.
    uscita = os.path.join(tempfile.gettempdir(), "prova_disegni_echoscript.pdf")
    print("\nCreo il PDF…")
    if pdf_rich.build_pdf_rich("\n".join(righe), uscita):
        print(f"PDF creato: {uscita}")
        os.startfile(uscita)
    else:
        print("Non sono riuscito a creare il PDF (serve Microsoft Edge o Google Chrome).")
    sys.exit(0 if tutto_bene else 1)


if __name__ == "__main__":
    main()
