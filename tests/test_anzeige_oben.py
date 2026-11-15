"""Eigene Testdatei für die obere Leiste und das Verhalten des Modellnamens.

Prüft drei Zusagen von smilez (15.11.2026) an echten Bildern:
1. Temperatur mit Ampelfarbe oben.
2. Mikrofon/Lautsprecher durchgestrichen, solange aus.
3. Langer Modellname zentriert, umgebrochen, ohne Abschneiden links.

Aufruf: python3 tests/test_anzeige_oben.py
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(os.environ.get("CHIMERA_SRC") or ROOT / "src")))

from PIL import Image  # noqa: E402

from chimera.display.felder import oben as obenfeld  # noqa: E402
from chimera.display.statusline import StatusLine  # noqa: E402

PASS = FAIL = 0


def ok(m):
    global PASS
    PASS += 1
    print(f"  ok    {m}")


def bad(m):
    global FAIL
    FAIL += 1
    print(f"  FAIL  {m}")


def pruefe(ist, soll, was):
    if ist == soll:
        ok(f"{was}: {ist!r}")
    else:
        bad(f"{was}: {ist!r} (erwartet {soll!r})")


def bild(kontext: dict, hoehe: int = 40) -> Image.Image:
    img = Image.new("RGB", (240, 280), (0, 0, 0))
    StatusLine(hoehe=hoehe, grundtext=lambda: "IDLE").zeichnen(
        img, jetzt_ms=0, kontext=kontext)
    return img


def bunt(img: Image.Image, y: int) -> bool:
    for x in range(img.size[0]):
        if img.getpixel((x, y)) not in ((0, 0, 0), (20, 20, 20)):
            return True
    return False


print("== 1. Ampelfarben")
pruefe(obenfeld.farbe_fuer(40.0), obenfeld.GRUEN, "40 °C ist grün")
pruefe(obenfeld.farbe_fuer(55.0), obenfeld.GELB, "55 °C ist gelb")
pruefe(obenfeld.farbe_fuer(70.0), obenfeld.ROT, "70 °C ist rot")

print("== 2. Obere Leiste nur mit Inhalt")
pruefe(bunt(bild({"modell": "m"}), 4), False,
       "ohne Temperatur und ohne Schalter bleibt sie leer")
pruefe(bunt(bild({"modell": "m", "temperatur": 44.0,
                  "mikrofon_an": False, "lautsprecher_an": False}), 4), True,
       "mit Temperatur wird gezeichnet")

print("== 3. Durchgestrichen, solange aus")


def grau(an: bool) -> int:
    img = bild({"temperatur": 44.0, "mikrofon_an": an, "lautsprecher_an": an})
    n = 0
    for x in range(0, 60):
        for y in range(0, 13):
            r, g, b = img.getpixel((x, y))
            if abs(r - 110) < 14 and abs(g - 110) < 14 and abs(b - 110) < 14:
                n += 1
    return n


pruefe(grau(False) > grau(True), True,
       f"aus hat mehr graue Pixel als an ({grau(False)} > {grau(True)})")

print("== 4. Kurzer Name: eine Zeile, Band bleibt flach")
kurz = bild({"modell": "deepseek-flash"})
pruefe(bunt(kurz, 200), False, "kein Band über dem Statusbereich")
pruefe(bunt(kurz, 280 - 40 + 12), True, "Text im unteren Band")

print("== 5. Langer Name: zwei Zeilen, doppelte Höhe, zentriert")
lang = bild({"modell": "anthropic/claude-sonnet-4-5-20250929-experimental-preview"})
voll = [y for y in range(280 - 26, 280) if bunt(lang, y)]
pruefe(len(voll) >= 8, True,
       f"zwei Textzeilen im hohen Band ({len(voll)} gefüllte Bildzeilen)")
pruefe(bool(voll) and voll[0] < 280 - 26 + 13, True,
       "die erste Zeile liegt in der oberen Hälfte")


def links_rechts(img: Image.Image, oben: int, hoehe: int):
    links = rechts = None
    for x in range(img.size[0]):
        for y in range(oben, oben + hoehe):
            if img.getpixel((x, y)) not in ((0, 0, 0), (20, 20, 20)):
                if links is None:
                    links = x
                rechts = x
                break
    return links, rechts


li, re = links_rechts(lang, 280 - 26, 25)
pruefe(li is not None, True, "links steht Text (nichts abgeschnitten)")
pruefe(abs(li - (239 - re)) <= 8, True, f"zentriert (links {li}, rechts {re})")

print("== 6. Ein Wort ohne Leerzeichen wird geteilt, nicht gekürzt")
from chimera.display.feld import Flaeche  # noqa: E402

fl = Flaeche(Image.new("RGB", (240, 40)), 0, 26)
zeilen = fl.umbrechen("anbieter/modell-ohne-ein-einziges-leerzeichen-1234567890",
                      fl.schrift(11), zeilen=2)
pruefe(len(zeilen), 2, "zwei Zeilen")
pruefe(all("…" not in z for z in zeilen[:-1]), True,
       "die erste Zeile ist nicht gekürzt")

print("== 7. Die obere Leiste beginnt nicht am Gehaeuserand")
# Fund smilez (15.11.2026): *"von der Temperatur in der Infozeile sieht man
# nur das C"*. Gemessen wird am Bild: links von RAND_LINKS darf in der
# oberen Leiste kein Pixel gesetzt sein, und der Text muss vollstaendig
# innerhalb des Bildes stehen.
from chimera.display.felder.oben import RAND_LINKS  # noqa: E402
img = bild({"temperatur": 43.2, "mikrofon_an": False, "lautsprecher_an": False})
erste = None
for y in range(0, 13):
    for x in range(img.size[0]):
        if img.getpixel((x, y)) not in ((0, 0, 0), (20, 20, 20)):
            erste = x if erste is None else min(erste, x)
pruefe(erste is not None and erste >= RAND_LINKS, True,
       f"erster gesetzter Pixel in Spalte {erste} (Rand {RAND_LINKS})")
rechts = None
for y in range(0, 13):
    for x in range(img.size[0] - 1, -1, -1):
        if img.getpixel((x, y)) not in ((0, 0, 0), (20, 20, 20)):
            rechts = x if rechts is None else max(rechts, x)
pruefe(rechts is not None and rechts < img.size[0] - 2, True,
       f"letzter gesetzter Pixel in Spalte {rechts}")

print()
print(f"Ergebnis: {PASS} ok, {FAIL} fehlgeschlagen")
sys.exit(0 if FAIL == 0 else 1)
