"""Tests der Fortschrittsanzeige (installer/lib/py/fortschritt.py).

Geprüft wird die Rechnung und das Zeichnen -- nicht das Panel; das steht am
Gerät.
"""
import importlib.util
import io
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PY = ROOT / "installer" / "lib" / "py" / "fortschritt.py"

spec = importlib.util.spec_from_file_location("fortschritt", PY)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

PASS = FAIL = 0


def ok(m):
    global PASS
    PASS += 1
    print(f"  ok    {m}")


def bad(m):
    global FAIL
    FAIL += 1
    print(f"  FAIL  {m}")


def check(m, got, want):
    if got == want:
        ok(m)
    else:
        bad(f"{m} — erwartet {want!r}, bekam {got!r}")


print("== Anteil: jede Stufe gleich viel ==")
check("0 von 12", mod.anteil(0, 12), 0.0)
check("6 von 12", mod.anteil(6, 12), 0.5)
check("12 von 12", mod.anteil(12, 12), 1.0)
check("2 von 3", round(mod.anteil(2, 3), 4), 0.6667)
check("mehr als gesamt bleibt 1", mod.anteil(15, 12), 1.0)
check("negativ bleibt 0", mod.anteil(-3, 12), 0.0)
# Ohne Stufen ist nichts zu tun — und keine Division durch Null.
check("gesamt 0 heisst fertig", mod.anteil(0, 0), 1.0)

print("\n== Fortschrittsdatei lesen ==")
import tempfile  # noqa: E402

with tempfile.TemporaryDirectory() as d:
    f = Path(d) / "stand"
    f.write_text("7 12\n", encoding="utf-8")
    check("gelesen", mod.lies(f), (7, 12))
    f.write_text("kaputt\n", encoding="utf-8")
    check("kaputte Zeile wird verworfen", mod.lies(f), None)
    f.write_text("1 2 3\n", encoding="utf-8")
    check("zu viele Felder", mod.lies(f), None)
    check("fehlende Datei", mod.lies(Path(d) / "gibtsnicht"), None)

print("\n== Balken zeichnen ==")
from PIL import Image  # noqa: E402

for wert, erwartet in ((0.0, 0), (0.5, 1), (1.0, 1)):
    img = Image.new("RGB", (240, 280), (0, 0, 0))
    mod.zeichne_balken(img, wert)
    # Zeile in der Mitte des Balkens abtasten: Ist links Farbe, rechts Spur?
    px = img.load()
    rand = max(8, 240 // 20)
    hoehe = max(8, 280 // 24)
    y = 280 - hoehe - rand + hoehe // 2
    links = px[rand + 2, y]
    rechts = px[240 - rand - 3, y]
    if wert == 0.0:
        check(f"{int(wert*100)} %: links leer", links == (40, 32, 20), True)
    elif wert == 1.0:
        check(f"{int(wert*100)} %: rechts gefuellt", rechts == (235, 170, 60), True)
    else:
        check(f"{int(wert*100)} %: links gefuellt", links == (235, 170, 60), True)
        check(f"{int(wert*100)} %: rechts Spur", rechts == (40, 32, 20), True)
    check(f"{int(wert*100)} %: Spur vorhanden", rechts != (0, 0, 0) or wert == 1.0, True)

print()
print(f"Ergebnis: {PASS} ok, {FAIL} fehlgeschlagen")
sys.exit(1 if FAIL else 0)
