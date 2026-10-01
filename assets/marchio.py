# -*- coding: utf-8 -*-
"""Ricava dal foglio del marchio l'icona del programma e il logo della pagina.

Il marchio non si disegna piu' qui: e' un'immagine fatta fuori, e sta intera in
assets/marchio-originale.png. Su quel foglio ci sono piu' cose di quelle che
servono (il nome, il motto, le icone delle funzioni); questo file ne ritaglia
tre pezzi e basta:

  - il simbolo grande, senza il suo fondo, per la barra laterale e per il velo
    di avvio (client/images/logo.png);
  - la piastrella «Icona principale», per l'icona del programma;
  - la piastrella «Versione semplificata», per le misure piu' piccole
    dell'icona, dove quella principale diventerebbe una macchia.

Si esegue a mano quando il foglio cambia, non durante la costruzione: quello
che finisce nel pacchetto sono i file gia' pronti.

    python assets/marchio.py            rifa' icona e logo
    python assets/marchio.py prova.png  in piu', un foglio con tutte le misure
"""
from __future__ import annotations

import os
import sys

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

QUI = os.path.dirname(os.path.abspath(__file__))
RADICE = os.path.dirname(QUI)
FOGLIO = os.path.join(QUI, 'marchio-originale.png')

# --- Dove stanno i pezzi sul foglio (1536 x 1024) ----------------------------
# Sono zone abbondanti: i bordi veri delle piastrelle li trova _piastrella()
# guardando dove finisce il loro colore. Se il foglio viene rifatto con
# un'altra impaginazione sono questi numeri da ritoccare, e nient'altro.
ZONA_SIMBOLO = (135, 53, 565, 483)       # un quadrato largo intorno al simbolo grande
ZONA_PRINCIPALE = (40, 650, 340, 925)    # «Icona principale (Desktop / App)»
ZONA_SEMPLICE = (575, 685, 810, 905)     # «Versione semplificata»

# Sotto il simbolo grande, a destra, comincia la fila delle icone delle
# funzioni: la prima (YouTube) entra nel quadrato del simbolo e va coperta.
FUORI_DAL_SIMBOLO = (428, 426, 565, 483)

# Il fondo del foglio intorno al simbolo: e' cio' che si toglie per averlo
# trasparente.
FONDO = (2, 12, 28)

# Sotto questa misura l'icona usa la versione semplificata.
SOGLIA_SEMPLICE = 32
MISURE_ICONA = [16, 20, 24, 32, 48, 64, 128, 256]

SU = 4          # le maschere si disegnano quattro volte piu' grandi, poi si riducono


def _foglio() -> Image.Image:
    return Image.open(FOGLIO).convert('RGB')


def simbolo() -> Image.Image:
    """Il simbolo grande senza il suo fondo, con l'alone che gli resta intorno.

    Il fondo del foglio e' quasi nero, e il simbolo ci sta sopra con una luce
    che sfuma: ritagliarlo lungo il bordo taglierebbe via la luce. Si toglie
    invece il fondo da ogni punto, e quello che avanza diventa quanto il punto
    e' opaco: dove c'era solo fondo non resta niente, dove c'era l'alone resta
    un velo, dove c'era il simbolo resta tutto. Posato sul nero della barra
    laterale torna com'era sul foglio, senza il rettangolo intorno.
    """
    x0, y0, x1, _ = ZONA_SIMBOLO
    pezzo = np.asarray(_foglio().crop(ZONA_SIMBOLO)).astype(np.float32)
    resto = np.clip(pezzo - np.array(FONDO, np.float32), 0, None)
    alfa = resto.max(axis=2) / (255.0 - min(FONDO))
    alfa = np.clip(alfa * 1.15, 0, 1)
    colore = np.where(alfa[..., None] > 0, resto / np.maximum(alfa[..., None], 1e-6), 0)
    colore = np.clip(colore, 0, 255)

    # La prima icona delle funzioni, che entra nell'angolo del ritaglio.
    lato = x1 - x0
    fx0, fy0, _, _ = FUORI_DAL_SIMBOLO
    alfa[fy0 - y0:, fx0 - x0:] = 0

    # L'alone sul foglio e' larghissimo e arriva fino al bordo del ritaglio:
    # tenuto tutto, intorno al simbolo si vedrebbe un quadrato di luce. Se ne
    # tiene solo la parte vicina: si prende la sagoma del simbolo, la si
    # allarga e la si sfuma, e l'alone resta solo li' dentro. Cosi' segue la
    # forma del simbolo e si spegne da solo prima del bordo.
    sagoma = Image.fromarray(((alfa > 0.5) * 255).astype(np.uint8), 'L')
    sagoma = sagoma.filter(ImageFilter.MaxFilter(41)).filter(ImageFilter.GaussianBlur(17))
    alfa = alfa * (np.asarray(sagoma).astype(np.float32) / 255.0)

    # Il riflesso sotto il simbolo e' piu' lungo del ritaglio, a sinistra e in
    # basso: una cornice sfumata lo porta a zero prima del bordo, altrimenti
    # finirebbe con un taglio netto.
    cornice = Image.new('L', (lato, lato), 0)
    ImageDraw.Draw(cornice).rectangle((22, 22, lato - 23, lato - 23), fill=255)
    cornice = cornice.filter(ImageFilter.GaussianBlur(11))
    alfa = alfa * (np.asarray(cornice).astype(np.float32) / 255.0)

    rgba = np.dstack([colore, alfa * 255]).round().astype(np.uint8)
    return Image.fromarray(rgba, 'RGBA')


def _piastrella(zona: tuple[int, int, int, int], soglia_blu: int, raggio: float) -> Image.Image:
    """Una piastrella del foglio, ritagliata lungo il suo bordo arrotondato.

    Il bordo si trova cercando dove il blu della piastrella si stacca dal
    fondo del foglio. La sagoma arrotondata invece si ridisegna: quella del
    foglio ha intorno il suo alone, e ritagliata a filo lascerebbe un orlo
    scuro che su una barra delle applicazioni chiara si vede.
    """
    foglio = _foglio()
    pezzo = np.asarray(foglio.crop(zona)).astype(int)
    pieno = pezzo[..., 2] > soglia_blu
    # Una riga o una colonna e' della piastrella se lo e' per piu' di un terzo:
    # cosi' una linea sottile del foglio che attraversa la zona non conta.
    righe = np.where(pieno.mean(axis=1) > 0.33)[0]
    colonne = np.where(pieno.mean(axis=0) > 0.33)[0]
    x0, x1 = zona[0] + colonne[0] + 1, zona[0] + colonne[-1]
    y0, y1 = zona[1] + righe[0] + 1, zona[1] + righe[-1]
    w, h = x1 - x0, y1 - y0

    maschera = Image.new('L', (w * SU, h * SU), 0)
    ImageDraw.Draw(maschera).rounded_rectangle(
        (0, 0, w * SU - 1, h * SU - 1), radius=min(w, h) * SU * raggio, fill=255)
    maschera = maschera.resize((w, h), Image.LANCZOS)
    ritaglio = foglio.crop((x0, y0, x1, y1)).convert('RGBA')
    ritaglio.putalpha(maschera)

    # Le piastrelle del foglio non sono quadrate al pixel: si centrano in un
    # quadrato, perche' un'icona lo e' sempre.
    lato = max(w, h)
    tela = Image.new('RGBA', (lato, lato), (0, 0, 0, 0))
    tela.paste(ritaglio, ((lato - w) // 2, (lato - h) // 2))
    return tela


def principale() -> Image.Image:
    return _piastrella(ZONA_PRINCIPALE, soglia_blu=52, raggio=0.235)


def semplice() -> Image.Image:
    return _piastrella(ZONA_SEMPLICE, soglia_blu=32, raggio=0.2)


def icona(lato: int) -> Image.Image:
    """L'icona del programma a una certa misura.

    Sotto i 32 pixel la piastrella principale, con i suoi vetri e le sue luci,
    si impasta: li' si usa la versione semplificata, che sul foglio c'e'
    apposta. E' lo stesso simbolo, non un altro disegno.
    """
    base = semplice() if lato < SOGLIA_SEMPLICE else principale()
    return base.resize((lato, lato), Image.LANCZOS)


def foglio_prova(percorso: str) -> None:
    """L'icona a tutte le misure vere, su fondo chiaro e su fondo scuro.

    Un'icona si giudica alla misura in cui verra' usata, non ingrandita, e su
    tutti e due i fondi perche' la barra delle applicazioni di Windows puo'
    essere chiara o scura.
    """
    larghezza = sum(m + 24 for m in MISURE_ICONA) + 24 + 404
    tela = Image.new('RGB', (larghezza, 600), (0x07, 0x07, 0x0f))
    ImageDraw.Draw(tela).rectangle((0, 0, larghezza - 404, 300), fill=(0xf2, 0xf2, 0xf2))
    x = 24
    for m in MISURE_ICONA:
        ico = icona(m)
        tela.paste(ico, (x, 300 - 24 - m), ico)          # su chiaro
        tela.paste(ico, (x, 300 + 24), ico)              # su scuro
        x += m + 24
    segno = simbolo()
    tela.paste(segno, (larghezza - 417, 85), segno)     # il logo, sul nero della barra
    tela.save(percorso)


if __name__ == '__main__':
    strati = {m: icona(m) for m in MISURE_ICONA}
    # La base dev'essere la piu' grande: Pillow butta via le misure superiori
    # a quella dell'immagine da cui parte.
    strati[256].save(os.path.join(QUI, 'EchoScript.ico'), format='ICO',
                     sizes=[(m, m) for m in MISURE_ICONA],
                     append_images=[strati[m] for m in MISURE_ICONA if m != 256])
    icona(512).save(os.path.join(QUI, 'EchoScript.png'))

    immagini = os.path.join(RADICE, 'client', 'images')
    os.makedirs(immagini, exist_ok=True)
    simbolo().save(os.path.join(immagini, 'logo.png'), optimize=True)

    if len(sys.argv) > 1:
        foglio_prova(sys.argv[1])
    print('fatti: assets/EchoScript.ico, assets/EchoScript.png, client/images/logo.png')
