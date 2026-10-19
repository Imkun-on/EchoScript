# -*- coding: utf-8 -*-
"""Il marchio di Mus auditor, montato una volta sola e messo nei posti in cui serve.

    python assets/marchio.py

Da dove viene
    Da ``assets/icona-originale.png``: un topo da biblioteca col tocco da
    laureato, seduto su una pila di libri, a incisione, inchiostro nero su
    fondo blu piatto (#318EE3, lo stesso blu della finestra: --tinta in
    client/styles/style.css). E' un quadrato pieno, senza angoli e senza
    bordo: quelli li mette questo file, cosi' sono identici a quelli di
    MediaFlow e per cambiarli non si rifa' il disegno.

Cosa gli si fa
    Lo si stringe attorno al disegno, lasciandogli un margine uguale su tutti i
    lati: nell'originale il topo e' piccolo in mezzo a molto fondo, e a sedici
    punti sulla barra delle applicazioni sparirebbe. Poi lo si ritaglia in un
    quadrato dagli angoli tondi e gli si passa attorno un filo scuro, che lo
    stacca tanto da un desktop chiaro quanto da uno scuro.

Dove finisce
    - ``assets/MusAuditor.ico``: l'eseguibile, la finestra e l'installatore.
    - ``assets/MusAuditor.png``: l'icona della pagina e il README.
    - ``client/marchio.png``: la testata e il velo di avvio. Qui non c'e' il
      quadrato: solo il topo coi suoi libri, scontornato, sul nero della
      finestra.

Come si toglie il fondo
    L'inchiostro e la carta sono grigi, cioe' hanno rosso, verde e blu uguali;
    il fondo no. Quanto fondo c'e' in un punto lo dice quindi la differenza fra
    il suo canale piu' forte e il piu' debole (nel blu: blu meno rosso), e una
    volta saputo lo si sottrae: sui bordi dei tratti, dove i due si mescolano,
    non resta nessun alone colorato. Quali siano i due canali lo si legge dal
    fondo stesso, quindi cambiare tinta non chiede di toccare questo file.

    Per questo il disegno deve restare in bianco e nero: un libro colorato
    verrebbe letto come «un po' di fondo» e uscirebbe mezzo trasparente.
"""
from __future__ import annotations

import os
import sys

import numpy as np
from PIL import Image, ImageDraw

QUI = os.path.dirname(os.path.abspath(__file__))
RADICE = os.path.dirname(QUI)
ORIGINALE = os.path.join(QUI, 'icona-originale.png')
ICO = os.path.join(QUI, 'MusAuditor.ico')
PNG = os.path.join(QUI, 'MusAuditor.png')
PAGINA = os.path.join(RADICE, 'client', 'marchio.png')

# Tutto e' pensato su 1024 punti di lato; le altre misure si ricavano
# rimpicciolendo.
LATO = 1024
RAGGIO = 228                          # degli angoli
BORDO = 10                            # lo spessore del filo scuro
INCHIOSTRO = (21, 21, 19, 255)

# Pillow non ammorbidisce i bordi delle forme che disegna: le si disegna
# quattro volte piu' grandi e le si rimpicciolisce.
LISCIO = 4

# Le misure che Windows si aspetta dentro un .ico. La piu' piccola e' quella
# della barra delle applicazioni, la piu' grande quella delle anteprime grandi
# di Esplora risorse.
MISURE_ICO = [16, 24, 32, 48, 64, 128, 256]
LATO_PNG = 512
LATO_PAGINA = 400                     # nella pagina non supera i 180 punti

# Lo scontorno. Sotto ALFA_VIA un punto e' fondo e sparisce, sopra ALFA_PIENO
# e' disegno pieno: la grana del fondo sta tutta sotto la prima soglia.
ANGOLO = 40                           # il lato dei riquadri da cui si legge il fondo
ALFA_VIA, ALFA_PIENO = .10, .88
SFUMA = 44                            # la fascia lungo i bordi in cui il disegno svanisce
MARGINE = .11                         # il fondo che resta attorno al disegno, per lato


def _scontornato() -> Image.Image:
    """L'originale intero, col fondo diventato trasparente."""
    a = np.asarray(Image.open(ORIGINALE).convert('RGB')).astype(np.float32)

    # Il colore del fondo: la mediana dei due angoli in alto. Quelli in basso
    # possono essere occupati dalla pila di libri.
    k = ANGOLO
    fondo = np.median(np.concatenate([a[:k, :k].reshape(-1, 3),
                                      a[:k, -k:].reshape(-1, 3)]), axis=0)

    forte, debole = int(np.argmax(fondo)), int(np.argmin(fondo))
    quota = np.clip((a[..., forte] - a[..., debole]) / (fondo[forte] - fondo[debole]), 0, 1)
    alfa = np.clip((1 - quota - ALFA_VIA) / (ALFA_PIENO - ALFA_VIA), 0, 1)
    colore = (a - quota[..., None] * fondo) / np.maximum(1 - quota[..., None], .05)

    # Se un libro o la coda escono dal riquadro, senza il quadrato attorno
    # finirebbero con un taglio netto: verso i bordi il disegno sfuma.
    alto, largo = alfa.shape
    y, x = np.mgrid[0:alto, 0:largo]
    dal_bordo = np.minimum(np.minimum(x, largo - 1 - x), np.minimum(y, alto - 1 - y))
    alfa *= np.clip(dal_bordo / SFUMA, 0, 1)

    return Image.fromarray(
        np.dstack([np.clip(colore, 0, 255), alfa * 255]).astype(np.uint8), 'RGBA')


def _disegno(img: Image.Image) -> tuple[int, int, int, int]:
    """Il rettangolo che il disegno occupa davvero."""
    return img.getchannel('A').point(lambda v: 255 if v > 8 else 0).getbbox()


def _inquadratura() -> tuple[int, int, int, int]:
    """Il quadrato dell'originale che finisce nell'icona: centrato sul disegno.

    Non esce mai dall'immagine: se il disegno e' gia' largo quanto il foglio,
    il quadrato e' il foglio intero.
    """
    img = _scontornato()
    x0, y0, x1, y1 = _disegno(img)
    lato = min(min(img.size), round(max(x1 - x0, y1 - y0) / (1 - 2 * MARGINE)))
    sx = min(max(0, (x0 + x1 - lato) // 2), img.width - lato)
    su = min(max(0, (y0 + y1 - lato) // 2), img.height - lato)
    return sx, su, sx + lato, su + lato


def icona() -> Image.Image:
    """L'originale dentro il quadrato dagli angoli tondi, col suo filo."""
    img = Image.open(ORIGINALE).convert('RGBA').crop(_inquadratura())
    img = img.resize((LATO, LATO), Image.LANCZOS)
    g = LATO * LISCIO

    sagoma = Image.new('L', (g, g), 0)
    ImageDraw.Draw(sagoma).rounded_rectangle((0, 0, g - 1, g - 1), RAGGIO * LISCIO, fill=255)

    filo = Image.new('RGBA', (g, g), (0, 0, 0, 0))
    meta = BORDO * LISCIO // 2
    ImageDraw.Draw(filo).rounded_rectangle(
        (meta, meta, g - 1 - meta, g - 1 - meta), RAGGIO * LISCIO - meta,
        outline=INCHIOSTRO, width=BORDO * LISCIO)

    img = Image.alpha_composite(img, filo.resize((LATO, LATO), Image.LANCZOS))
    img.putalpha(sagoma.resize((LATO, LATO), Image.LANCZOS))
    return img


def topo() -> Image.Image:
    """Il topo coi suoi libri senza il fondo, stretto sul disegno."""
    img = _scontornato()
    return img.crop(_disegno(img))


def scrivi() -> None:
    i = icona()
    t = topo()
    t.thumbnail((LATO_PAGINA, LATO_PAGINA), Image.LANCZOS)
    t.save(PAGINA)
    i.resize((LATO_PNG, LATO_PNG), Image.LANCZOS).save(PNG)
    # Pillow ricampiona da solo le misure richieste, partendo dalla piu' grande.
    i.save(ICO, sizes=[(m, m) for m in MISURE_ICO])
    print('  {}  {}x{}'.format(PAGINA, *t.size))
    print('  {}  {}x{}'.format(PNG, LATO_PNG, LATO_PNG))
    print('  {}  {}'.format(ICO, ', '.join(str(m) for m in MISURE_ICO)))


if __name__ == '__main__':
    if not os.path.isfile(ORIGINALE):
        sys.exit('Manca assets/icona-originale.png: e\' il disegno da cui si '
                 'ricava tutto il resto.')
    scrivi()
