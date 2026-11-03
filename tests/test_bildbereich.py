#!/usr/bin/env python3
"""Tests für das Übertragen nur geänderter Bereiche (DESIGN Regel 7).

Warum: Am Pi gemessen (3.11.2026) schrieb der Dienst im Leerlauf 572-mal je
Sekunde auf `/dev/spidev0.0` — rund 17 volle Bilder je Sekunde für ein
stehendes Gesicht, 28 % eines Kerns. Der Panelspeicher behält seinen Inhalt,
also genügt ein Fenster auf das, was sich geändert hat.

Geprüft wird die echte Bibliothek. Das Panel selbst entsteht über
``object.__new__`` mit einer Attrappe statt ST7789 — die Hardware wird nicht
nachgebaut (siehe Kopf von ``test_displays.py``).
"""

import os
import sys
from pathlib import Path

# CHIMERA_SRC überstimmt den Quellbaum — sonst liefe die Gegenprobe immer
# gegen das Repo statt gegen die verfälschte Kopie und bliebe grün.
SRC = Path(os.environ.get("CHIMERA_SRC")
           or Path(__file__).resolve().parent.parent / "src")
sys.path.insert(0, str(SRC))

from PIL import Image  # noqa: E402

from chimera.displays.base import (  # noqa: E402
    aenderungsrechtecke, ausschnitt, to_rgb565,
)
from chimera.displays.whisplay.panel import WhisplayPanel  # noqa: E402

PASS = FAIL = 0

def ok(m):
    global PASS; PASS += 1; print(f"  ok    {m}")

def bad(m):
    global FAIL; FAIL += 1; print(f"  FAIL  {m}")

def check(m, got, want):
    ok(m) if got == want else bad(f"{m} — erwartet {want!r}, bekam {got!r}")


def bild(w, h, punkte=()):
    """Schwarzes Bild, einzelne Punkte ((x, y), Farbe) gesetzt."""
    im = Image.new("RGB", (w, h), (0, 0, 0))
    for (x, y), farbe in punkte:
        im.putpixel((x, y), farbe)
    return im


WEISS = (255, 255, 255)
ROT = (255, 0, 0)

print("== Rechtecke: unverändert ==")
w, h = 16, 12
a = to_rgb565(bild(w, h))
check("gleiche Bilder: kein Rechteck", aenderungsrechtecke(a, a, w, h), [])
b2 = to_rgb565(bild(w, h))
check("zwei gleiche Bilder, getrennt gerechnet: kein Rechteck",
      aenderungsrechtecke(a, b2, w, h), [])

print("== Rechtecke: ein Punkt ==")
neu = to_rgb565(bild(w, h, [((4, 7), WEISS)]))
check("ein Punkt: genau ein Rechteck, 1×1",
      aenderungsrechtecke(a, neu, w, h), [(4, 7, 1, 1)])

print("== Rechtecke: ein Block ==")
punkte = [((x, y), ROT) for y in range(3, 6) for x in range(2, 9)]
neu = to_rgb565(bild(w, h, punkte))
check("Block 7×3: ein Rechteck mit seinen Maßen",
      aenderungsrechtecke(a, neu, w, h), [(2, 3, 7, 3)])

print("== Rechtecke: zwei getrennte Streifen ==")
punkte = ([((1, y), WEISS) for y in (1, 2)] +
          [((10, y), ROT) for y in (8, 9)])
neu = to_rgb565(bild(w, h, punkte))
check("zwei Streifen: zwei Rechtecke, je eigener Spanne",
      aenderungsrechtecke(a, neu, w, h), [(1, 1, 1, 2), (10, 8, 1, 2)])

print("== Rechtecke: getrennte Zeilen in einem Streifen ==")
punkte = [((2, 1), WEISS), ((12, 2), ROT)]      # Zeilen 1 und 2, Lücke dazwischen
neu = to_rgb565(bild(w, h, punkte))
# Ein Streifen (Zeilen 1-2), Spanne von x=2 bis x=12: überträgt auch die
# unveränderte Mitte. Bewusst so -- je Bildpunkt ein Fenster wäre teurer.
check("benachbarte Zeilen: ein Streifen über die ganze Spanne",
      aenderungsrechtecke(a, neu, w, h), [(2, 1, 11, 2)])

print("== Rechtecke: 16-Bit-Grenzen ==")
# Ein Punkt ändert sich nur im niederwertigen Byte (Farbe 0x0001): Der
# Vergleich muss je Bildpunkt arbeiten, nicht je Byte-Paar-Grenze.
im_a = Image.new("RGB", (4, 2), (0, 0, 0))
im_b = Image.new("RGB", (4, 2), (0, 0, 0))
im_b.putpixel((3, 1), (0, 0, 8))                # 5-Bit-Blau: 1
check("nur niederwertiges Byte: trotzdem erkannt",
      aenderungsrechtecke(to_rgb565(im_a), to_rgb565(im_b), 4, 2), [(3, 1, 1, 1)])

print("== Ausschnitt ==")
voll = to_rgb565(bild(w, h, [((x, y), (x * 8 % 256, y * 16 % 256, 64))
                             for y in range(h) for x in range(w)]))

# Gegenrechnung: dasselbe Rechteck bildpunktweise aus dem Bild schneiden.
def naiv(im, x, y, bw, bh):
    aus = bytearray()
    for yy in range(y, y + bh):
        for xx in range(x, x + bw):
            r, g, b = im.getpixel((xx, yy))
            v = ((r & 0xF8) << 8) | ((g & 0xFC) << 3) | (b >> 3)
            aus += bytes(((v >> 8) & 0xFF, v & 0xFF))
    return bytes(aus)

quelle = bild(w, h, [((x, y), (x * 8 % 256, y * 16 % 256, 64))
                     for y in range(h) for x in range(w)])
check("Ausschnitt mitten im Bild", ausschnitt(voll, w, 3, 4, 5, 2),
      naiv(quelle, 3, 4, 5, 2))
check("Ausschnitt ganze Zeilen", ausschnitt(voll, w, 0, 2, w, 3),
      naiv(quelle, 0, 2, w, 3))
check("Ausschnitt ein Bildpunkt", ausschnitt(voll, w, 15, 11, 1, 1),
      naiv(quelle, 15, 11, 1, 1))

print("== Panel: nur Geändertes geht auf den Bus ==")


class StAttrappe:
    """Steht für den ST7789: sammelt, was geschrieben würde."""

    def __init__(self):
        self.aufrufe = []

    def schreibe_bild(self, rgb, x=0, y=0, breite=None, hoehe=None):
        self.aufrufe.append((x, y, breite, hoehe, len(rgb), bytes(rgb)))


def panel(w=16, h=12):
    p = object.__new__(WhisplayPanel)          # ohne SPI/GPIO
    p.width, p.height = w, h
    p._letztes_bild = None
    p.bilder = p.teilbilder = p.unveraendert = 0
    p._st = StAttrappe()
    return p

p = panel()
p.show(bild(16, 12))
check("erstes Bild: voll übertragen", (p._st.aufrufe[0][0], p._st.aufrufe[0][1],
                                       p._st.aufrufe[0][2], p._st.aufrufe[0][3]),
      (0, 0, 16, 12))
check("erstes Bild: ein Schreibaufruf", len(p._st.aufrufe), 1)

p.show(bild(16, 12))
check("gleiches Bild nochmal: KEIN Schreibaufruf", len(p._st.aufrufe), 1)
check("gleiches Bild: als unverändert gezählt", p.unveraendert, 1)

p.show(bild(16, 12, [((5, 6), WEISS)]))
check("ein Punkt geändert: ein Fenster von 1×1", p._st.aufrufe[-1][:4], (5, 6, 1, 1))
check("ein Punkt geändert: genau 2 Byte", p._st.aufrufe[-1][4], 2)

p.show(bild(16, 12, [((5, 6), WEISS), ((2, 9), ROT)]))
check("an einer zweiten Stelle geändert: ein weiteres Fenster",
      p._st.aufrufe[-1][:4], (2, 9, 1, 1))
check("Zähler: Bilder, Teilbilder, unverändert",
      (p.bilder, p.teilbilder, p.unveraendert), (4, 3, 1))

# Zwei Änderungen in Zeilen mit einer unveränderten Zeile dazwischen sind zwei
# Streifen -- ein Fenster über beide würde die unveränderte Zeile mitschicken.
p2 = panel()
p2.show(bild(16, 12, [((1, 1), WEISS)]))
p2.show(bild(16, 12, [((1, 1), ROT), ((3, 3), ROT)]))
check("voller Rahmen beim ersten Bild, danach zwei Fenster",
      [(a[0], a[1], a[2], a[3]) for a in p2._st.aufrufe],
      [(0, 0, 16, 12), (1, 1, 1, 1), (3, 3, 1, 1)])

print("== Rückfall ohne numpy ==")
# Derselbe Vergleich ohne numpy: andere Rechnung, gleiche Fläche. Der
# Rückfall darf sich nicht anders verhalten -- sonst zeigt das Gerät ohne
# numpy ein anderes Bild als das mit.
import chimera.displays.base as _basis  # noqa: E402

_probe = [
    ("gleiche Bilder", a, a),
    ("ein Punkt", a, to_rgb565(bild(w, h, [((4, 7), WEISS)]))),
    ("zwei Streifen", a, to_rgb565(bild(w, h, [((1, y), WEISS) for y in (1, 2)] +
                                            [((10, y), ROT) for y in (8, 9)]))),
]
_mit = [aenderungsrechtecke(x, y, w, h) for _, x, y in _probe]
_alt_np, _alt_versucht = _basis._np, _basis._np_versucht
_basis._np, _basis._np_versucht = None, True
try:
    _ohne = [aenderungsrechtecke(x, y, w, h) for _, x, y in _probe]
    # Der Rückfall kennt keine Spalten -- er nimmt je Streifen die ganze
    # Breite. Die ZEILEN müssen aber dieselben sein.
    _ohne_zeilen = [[(r[1], r[3]) for r in liste] for liste in _ohne]
    _mit_zeilen = [[(r[1], r[3]) for r in liste] for liste in _mit]
    check("ohne numpy: gleiche Zeilenstreifen wie mit numpy", _ohne_zeilen, _mit_zeilen)
    check("ohne numpy: je Streifen die ganze Breite",
          {(r[0], r[2]) for liste in _ohne for r in liste}, {(0, w)})
finally:
    _basis._np, _basis._np_versucht = _alt_np, _alt_versucht

print(f"\nErgebnis: {PASS} ok, {FAIL} fehlgeschlagen")
sys.exit(0 if FAIL == 0 else 1)
