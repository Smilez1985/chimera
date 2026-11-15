"""Ein Gähnen ist eine Bewegung, kein Dauerzustand.

Befund smilez (15.11.2026): *„die Animation ‚yawn' (gähnen) dauert zu lange,
sieht aus als wolle er mich fressen. er hat den Mund viel zu lange offen"*.
Nachgesehen: `mouth.style == "yawn"` zeichnete ein **festes** großes Oval —
ohne Bewegung, und weil YAWN keine `dauer_s` hatte, blieb es stehen, bis
etwas anderes kam.

Jetzt: Phase 0..1, einmal, gedeckelt wie der Zug-Zyklus; der Mund öffnet sich
und schließt wieder. YAWN bringt `dauer_s = 2.4` mit, damit es als endlicher
Ausdruck einmal läuft und dann zurückgeht (Regel „Sprechgesicht" Punkt 9).

Aufruf: python3 tests/test_gaehnen.py
"""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(os.environ.get("CHIMERA_SRC") or ROOT / "src")))

from chimera.mood.registry import Registry  # noqa: E402
from chimera.render.avatar import NoisyRenderer, State  # noqa: E402

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


class Panel:
    """Nimmt Bilder an und wirft sie weg (wie im Test von `render`)."""

    width = 240
    height = 280

    def show(self, img):
        pass

    def close(self):
        pass


print("== 1. YAWN ist ein endlicher Ausdruck")
reg = Registry.load(ROOT / "data" / "moods-builtin.json")
yawn = reg.get("YAWN")
pruefe(round(float(yawn.get("dauer_s") or 0), 1), 2.4, "dauer_s")

print("== 2. Die Phase läuft einmal und bleibt am Ende stehen")
r = NoisyRenderer(State(), Panel())
pruefe(r.einmal_phase, 0.0, "Start")
# Die Uhr wird eingesetzt: sonst haengt der Test an der Laufzeit der Schleife.
t = 100.0
werte = []
for _ in range(12):
    t += 0.1
    werte.append(r.einmal_zyklus("YAWN", 0.4, jetzt=t))
pruefe(werte == sorted(werte), True, "monoton steigend")
pruefe(werte[0] < 0.5, True, f"nach 0,1 s noch nicht fertig ({werte[0]:.2f})")
pruefe(r.einmal_phase, 1.0, "am Ende genau 1.0 (kein Modulo)")
t += 0.1
pruefe(r.einmal_zyklus("YAWN", 0.4, jetzt=t), 1.0, "bleibt dort")

print("== 3. Ein neuer Ausdruck fängt von vorn an")
t += 0.1
r.einmal_zyklus("STRETCH", 0.4, jetzt=t)
pruefe(r.einmal_phase, 0.0, "Moodwechsel setzt zurück")

print("== 4. Die Mundform: zu -> offen -> zu")
from chimera.render.avatar import gaehn_mund  # noqa: E402

b0, h0 = gaehn_mund(0.0)
b5, h5 = gaehn_mund(0.5)
b1, h1 = gaehn_mund(1.0)
pruefe(h5 > h0 * 3, True, f"in der Mitte deutlich offener ({h5} > {h0})")
pruefe(h1 <= h0 + 1, True, f"am Ende wieder zu ({h1} zu {h0})")
pruefe(b5 > b0, True, f"und breiter ({b5} > {b0})")
pruefe(gaehn_mund(-1.0) == gaehn_mund(0.0), True, "Phase unter 0 wie 0")
pruefe(gaehn_mund(2.0) == gaehn_mund(1.0), True, "Phase über 1 wie 1")

print()
print(f"Ergebnis: {PASS} ok, {FAIL} fehlgeschlagen")
sys.exit(0 if FAIL == 0 else 1)
