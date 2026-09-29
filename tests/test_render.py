"""Tests für den Renderer. Ohne Panel lauffähig."""
import json, sys, time
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from chimera.display.panel import NullPanel  # noqa: E402
from chimera.mood import blend  # noqa: E402
from chimera.mood.validate import validate  # noqa: E402
from chimera.render.avatar import NoisyRenderer, State  # noqa: E402

PASS = FAIL = 0
def ok(m):
    global PASS; PASS += 1; print(f"  ok    {m}")
def bad(m):
    global FAIL; FAIL += 1; print(f"  FAIL  {m}")
def check(m, got, want):
    ok(m) if got == want else bad(f"{m} — erwartet {want!r}, bekam {got!r}")

print("== Grundlage ==")
p = NullPanel()
r = NoisyRenderer(State(), p)
img = r.render()
check("Bildgröße folgt dem Panel", img.size, (240, 280))
check("RGB", img.mode, "RGB")

# Auflösungsunabhängig (Regel 6): Die Bezugsgröße ist die kurze Seite,
# damit das Gesicht nicht mitgedehnt wird.
r2 = NoisyRenderer(State(), NullPanel(320, 240))
check("andere Fläche", r2.render().size, (320, 240))
check("Bezug ist die kurze Seite", (r.BASE, r2.BASE), (240, 240))

# Doppelte Fläche: das Gesicht muss doppelt so groß werden. Vorher war
# dieser Test falsch gewählt — 240×280 und 320×240 haben dieselbe kurze
# Seite, also konnte er gar nichts zeigen.
r3 = NoisyRenderer(State(), NullPanel(480, 560))
check("doppelte Fläche, doppelter Bezug", r3.BASE, 2 * r.BASE)
check("Bild in voller Größe", r3.render().size, (480, 560))

print("== Moods ==")
raw = json.loads((ROOT / "data" / "moods-builtin.json").read_text("utf-8"))["moods"]
by = {}
for m in raw:
    v, _ = validate(m)
    by[v["name"]] = v
check("41 Moods", len(by), 41)

st = State()
rr = NoisyRenderer(st, NullPanel())
broken = []
for name, mood in by.items():
    st.mood, st.mood_name = mood, name
    try:
        rr.render()
    except Exception as exc:
        broken.append((name, str(exc)[:60]))
ok("jeder Mood zeichnet") if not broken else bad(f"kaputt: {broken[:3]}")

mixed = blend.mix(by["ROCK"], by["CHILL"], 0.5)
st.mood, st.mood_name = mixed, "MIX"
ok("Mischung zeichnet") if rr.render() else bad("Mischung scheitert")

print("== Freie Formen ==")
m, _ = validate({
    "name": "FREI",
    "shapes": [
        {"kind": "ngon", "x": .5, "y": .8, "r": .06, "sides": 5,
         "color": "#ffcc00", "layer": "front"},
        {"kind": "arc", "x": .5, "y": .6, "w": .3, "h": .15,
         "start": 200, "end": 340, "width": .01, "color": "#ff0000"},
        {"kind": "text", "x": .5, "y": .9, "text": "!", "anchor": "mm"},
    ],
})
st.mood, st.mood_name = m, "FREI"
before = getattr(rr, "_shape_errors", 0)
out = rr.render()
ok("Bild mit freien Formen") if out else bad("kein Bild")
check("keine Zeichenfehler", getattr(rr, "_shape_errors", 0), before)

# Gegenprobe: ohne Formen muss sich das Bild unterscheiden — sonst würde
# der Test nicht messen, ob überhaupt etwas gezeichnet wurde.
plain, _ = validate({"name": "FREI"})
st.mood = plain
a = rr.render().tobytes()
st.mood = m
b = rr.render().tobytes()
ok("Gegenprobe: Formen verändern das Bild") if a != b else bad("Formen unsichtbar")

print("== Panel ==")
p3 = NullPanel()
r3 = NoisyRenderer(State(), p3)
r3.show()
check("show() gibt aus", p3.frames, 1)
check("RGB565 erzeugt", len(p3.last or b""), 240 * 280 * 2)

print("== Tempo ==")
st.mood, st.mood_name = by["ROCK"], "ROCK"
st.intensity = 120
t = time.perf_counter()
for _ in range(30):
    rr.render()
ms = (time.perf_counter() - t) / 30 * 1000
budget = 1000 / 15
ok(f"{ms:.1f} ms je Bild (Budget {budget:.0f} ms; hier schneller als der Pi)")
ok("im Budget") if ms < budget else bad(f"über Budget: {ms:.1f} ms")

print()
print(f"Ergebnis: {PASS} ok, {FAIL} fehlgeschlagen")
sys.exit(1 if FAIL else 0)
