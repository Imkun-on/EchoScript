# -*- coding: utf-8 -*-
"""Disegna il marchio di EchoScript e ne ricava icona e schermata di avvio.

Il marchio: tre barre di livello che diventano tre righe scritte. E' cio' che
il programma fa (del parlato entra, del testo esce) ed e' fatto di sei forme
spesse, che e' quanto sopravvive a un ridimensionamento a 16 pixel.

Si esegue a mano quando il disegno cambia, non durante la costruzione: quello
che finisce nel pacchetto sono i file gia' pronti dentro assets/.
"""
from __future__ import annotations

import os
import sys

from PIL import Image, ImageDraw, ImageFilter, ImageFont

# --- I colori, gli stessi di :root in web/style.css --------------------------
F0   = (0x04, 0x04, 0x0a)      # --f0   il nero di fondo
F2   = (0x12, 0x12, 0x2a)      # --f2   il fondo alto della piastrella
IRIS = (0x7c, 0x6c, 0xff)      # --iris il viola d'identita'
LUME = (0xa7, 0x8b, 0xfa)      # --lume viola chiaro
ONDA = (0x38, 0xd6, 0xee)      # --onda il ciano di cio' che lavora
T0   = (0xe9, 0xe7, 0xf7)      # --t0   il testo

# --- La geometria, su una griglia di 100 -------------------------------------
# (x, y, larghezza, altezza, colore). Le prime tre sono le barre, le altre tre
# le righe di testo. Il tutto sta fra 14 e 86, centrato sul 50 in entrambi i
# versi, cosi' regge sia dentro una piastrella sia da solo sul velo.
PIENO = [
    (14, 34,  8, 32, IRIS),
    (26, 22,  8, 56, LUME),
    (38, 30,  8, 40, IRIS),
    (54, 32, 32,  8, ONDA),
    (54, 46, 26,  8, ONDA),
    (54, 60, 20,  8, ONDA),
]

# Sotto i 32 pixel sei forme si impastano in una macchia: a quelle misure il
# marchio dice la stessa cosa con quattro forme piu' spesse. E' la stessa idea,
# non un altro disegno.
SEMPLICE = [
    (12, 18, 14, 64, IRIS),
    (30, 29, 14, 42, LUME),
    (50, 29, 38, 14, ONDA),
    (50, 55, 28, 14, ONDA),
]

SU = 8          # supercampionamento: si disegna otto volte piu' grande


def _forme(lato: int, semplice: bool) -> Image.Image:
    """Le sei (o quattro) forme, su fondo trasparente, in un quadrato di lato."""
    grande = lato * SU
    tela = Image.new('RGBA', (grande, grande), (0, 0, 0, 0))
    pennello = ImageDraw.Draw(tela)
    k = grande / 100
    for x, y, w, h, colore in (SEMPLICE if semplice else PIENO):
        raggio = min(w, h) / 2 * k
        pennello.rounded_rectangle(
            (x * k, y * k, (x + w) * k, (y + h) * k), radius=raggio, fill=colore + (255,))
    return tela.resize((lato, lato), Image.LANCZOS)


def marchio(lato: int, semplice: bool | None = None, alone: bool = True) -> Image.Image:
    """Il marchio da solo, con il suo alone viola. Fondo trasparente."""
    if semplice is None:
        semplice = lato < 32
    forme = _forme(lato, semplice)
    if not alone or lato < 48:
        # L'alone a misure piccole non si vede come luce, si vede come sporco
        # intorno alle forme: sotto i 48 pixel non si mette.
        return forme
    velo = Image.new('RGBA', (lato, lato), (0, 0, 0, 0))
    velo.paste(IRIS + (150,), mask=forme.getchannel('A'))
    velo = velo.filter(ImageFilter.GaussianBlur(lato * 0.055))
    return Image.alpha_composite(velo, forme)


def piastrella(lato: int) -> Image.Image:
    """Il marchio nella sua piastrella scura: e' l'icona del programma.

    La piastrella non e' decorazione. Nella barra delle applicazioni un'icona
    senza sagoma esterna si perde fra le altre; un quadrato arrotondato si
    riconosce di lato, prima ancora di distinguere cosa c'e' dentro.
    """
    grande = lato * SU
    tela = Image.new('RGBA', (grande, grande), (0, 0, 0, 0))

    # Il fondo, schiarito appena in alto: un piano illuminato da sopra.
    sfumatura = Image.new('RGBA', (1, grande))
    for y in range(grande):
        t = y / max(1, grande - 1)
        sfumatura.putpixel((0, y), tuple(
            round(F2[c] + (F0[c] - F2[c]) * t) for c in range(3)) + (255,))
    sfumatura = sfumatura.resize((grande, grande))

    maschera = Image.new('L', (grande, grande), 0)
    ImageDraw.Draw(maschera).rounded_rectangle(
        (0, 0, grande - 1, grande - 1), radius=grande * 0.225, fill=255)
    tela.paste(sfumatura, mask=maschera)

    # L'alone viola sotto il marchio, come il gradiente radiale del velo.
    fuoco = Image.new('RGBA', (grande, grande), (0, 0, 0, 0))
    r = grande * 0.34
    ImageDraw.Draw(fuoco).ellipse(
        (grande / 2 - r, grande * 0.42 - r, grande / 2 + r, grande * 0.42 + r),
        fill=(0x2a, 0x1f, 0x6b, 130))
    fuoco = fuoco.filter(ImageFilter.GaussianBlur(grande * 0.09))
    fuoco.putalpha(Image.composite(fuoco.getchannel('A'),
                                   Image.new('L', (grande, grande), 0), maschera))
    tela = Image.alpha_composite(tela, fuoco)

    # Il bordo: un filo di viola sul taglio, che stacca la piastrella dal nero
    # di una barra delle applicazioni scura.
    bordo = Image.new('RGBA', (grande, grande), (0, 0, 0, 0))
    ImageDraw.Draw(bordo).rounded_rectangle(
        (grande * 0.012, grande * 0.012, grande * 0.988, grande * 0.988),
        radius=grande * 0.213, outline=IRIS + (110,), width=max(1, round(grande * 0.016)))
    tela = Image.alpha_composite(tela, bordo)

    piccola = tela.resize((lato, lato), Image.LANCZOS)
    return Image.alpha_composite(piccola, marchio(lato))


def _carattere(dimensione: int, grassetto: bool = True):
    nomi = (['segoeuib.ttf', 'seguibl.ttf', 'arialbd.ttf'] if grassetto
            else ['segoeui.ttf', 'arial.ttf'])
    for nome in nomi:
        percorso = os.path.join(os.environ.get('WINDIR', r'C:\Windows'), 'Fonts', nome)
        if os.path.isfile(percorso):
            return ImageFont.truetype(percorso, dimensione)
    return ImageFont.load_default(dimensione)


def caricamento(larghezza: int = 440, altezza: int = 260) -> Image.Image:
    """La schermata che PyInstaller mostra mentre scompatta l'eseguibile.

    Stesso marchio, stesso viola, stesso nero del velo che le succede: chi
    guarda deve vedere un programma che si apre, non due schermate diverse che
    si passano il turno. Marchio e nome sono disposti come nel velo: segno
    sopra, nome sotto, stessa distanza, cosi' nell'istante dello scambio non
    si muove niente.

    Nessuna frase sotto il nome, di proposito: questa immagine e' disegnata una
    volta sola e non sa in che lingua girera' il programma, mentre il nome e'
    lo stesso in tutte e due. Nemmeno la barra: qui non c'e' ancora niente da
    misurare, e una barra ferma sembra un programma piantato. La barra comincia
    col velo, quando i passi da contare esistono davvero.
    """
    tela = Image.new('RGBA', (larghezza, altezza), F0 + (255,))

    lato_segno = 116
    tipo = _carattere(28)
    misura = ImageDraw.Draw(tela).textbbox((0, 0), 'EchoScript', font=tipo)
    alto_nome = misura[3] - misura[1]
    stacco = 16                                  # --s4, lo stesso gap del velo

    # Il blocco intero, un filo sopra la meta': centrato esatto sembra basso.
    alto_blocco = lato_segno + stacco + alto_nome
    cima = (altezza - alto_blocco) / 2 - altezza * 0.03
    cx = larghezza / 2

    # L'alone: lo stesso radial-gradient del velo, dietro il marchio.
    fuoco_y = cima + lato_segno / 2
    alone = Image.new('RGBA', (larghezza, altezza), (0, 0, 0, 0))
    rx, ry = larghezza * 0.32, altezza * 0.30
    ImageDraw.Draw(alone).ellipse((cx - rx, fuoco_y - ry, cx + rx, fuoco_y + ry),
                                  fill=(0x2a, 0x1f, 0x6b, 89))
    tela = Image.alpha_composite(tela, alone.filter(ImageFilter.GaussianBlur(40)))

    tela.alpha_composite(marchio(lato_segno, semplice=False),
                         (round(cx - lato_segno / 2), round(cima)))

    ImageDraw.Draw(tela).text(
        (round(cx - (misura[2] - misura[0]) / 2),
         round(cima + lato_segno + stacco - misura[1])),
        'EchoScript', font=tipo, fill=T0 + (255,))

    # Il filo del bordo: la finestra dello splash non ha cornice, e senza
    # questo su uno sfondo scuro non si capisce dove finisce. E' lo stesso
    # --bordo dell'interfaccia (#8b7cff1f), non uno piu' acceso: deve dire dove
    # finisce l'immagine, non farsi guardare.
    #
    # Su uno strato a parte, non direttamente sulla tela: ImageDraw scrive il
    # colore cosi' com'e' invece di fonderlo con quello che trova sotto, quindi
    # un bordo con alfa disegnato sul posto verrebbe fuori a piena tinta e la
    # trasparenza sparirebbe del tutto nella conversione a RGB.
    filo = Image.new('RGBA', (larghezza, altezza), (0, 0, 0, 0))
    ImageDraw.Draw(filo).rectangle((0, 0, larghezza - 1, altezza - 1),
                                   outline=(0x8b, 0x7c, 0xff, 0x1f))
    return Image.alpha_composite(tela, filo).convert('RGB')


def foglio_prova(percorso: str) -> None:
    """Le misure vere, affiancate, su due fondi: e' l'unico modo di giudicare."""
    misure = [16, 20, 24, 32, 48, 64, 128, 256]
    larghezza = sum(m + 24 for m in misure) + 24
    tela = Image.new('RGB', (larghezza, 256 + 256 + 96), (0x1a, 0x1a, 0x1a))
    pennello = ImageDraw.Draw(tela)
    pennello.rectangle((0, 0, larghezza, 300), fill=(0xf2, 0xf2, 0xf2))
    tipo = _carattere(13, grassetto=False)
    x = 24
    for m in misure:
        ico = piastrella(m)
        tela.paste(ico, (x, 300 - 24 - m), ico)          # su chiaro
        tela.paste(ico, (x, 300 + 40), ico)              # su scuro
        segno = marchio(m)
        tela.paste(segno, (x, 300 + 40 + 264 - m), segno)  # senza piastrella
        pennello.text((x, 300 + 8), str(m), font=tipo, fill=(0xa0, 0xa0, 0xa0))
        x += m + 24
    tela.save(percorso)


if __name__ == '__main__':
    dove = sys.argv[1] if len(sys.argv) > 1 else '.'
    os.makedirs(dove, exist_ok=True)

    # Ogni misura e' disegnata per conto suo, non rimpicciolita dalla piu'
    # grande: sotto i 32 pixel il marchio cambia forma, e un ridimensionamento
    # automatico ne farebbe una macchia. La base dev'essere la piu' grande,
    # perche' Pillow butta via le misure superiori a quella dell'immagine da
    # cui parte.
    misure = [16, 20, 24, 32, 48, 64, 128, 256]
    strati = {m: piastrella(m) for m in misure}
    strati[256].save(os.path.join(dove, 'EchoScript.ico'), format='ICO',
                     sizes=[(m, m) for m in misure],
                     append_images=[strati[m] for m in misure if m != 256])
    piastrella(512).save(os.path.join(dove, 'EchoScript.png'))
    caricamento().save(os.path.join(dove, 'caricamento.png'))
    print('fatti in', os.path.abspath(dove))
