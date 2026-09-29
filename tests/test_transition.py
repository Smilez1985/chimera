"""Tests für Mood-Übergänge. Ohne Hardware, mit gestellter Uhr."""
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from chimera.mood.transition import Transition, ease  # noqa: E402
from chimera.mood.validate import validate  # noqa: E402

PASS = FAIL = 0
def ok(m):
    global PASS; PASS += 1; print(f"  ok    {m}")
def bad(m):
    global FAIL; FAIL += 1; print(f"  FAIL  {m}")
def check(m, got, want):
    ok(m) if got == want else bad(f"{m} — erwartet {want!r}, bekam {got!r}")


class Clock:
    """Gestellte Uhr — Tests dürfen nicht warten müssen."""
    def __init__(self): self.t = 0.0
    def __call__(self): return self.t
    def advance(self, dt): self.t += dt


A, _ = validate({"name": "A", "body": {"color": [255, 0, 0]},
                 "physics": {"sway_amp": 0}, "mouth": {"style": "grin"}})
B, _ = validate({"name": "B", "body": {"color": [0, 0, 255]},
                 "physics": {"sway_amp": 20}, "mouth": {"style": "frown"}})
SCHRECK, _ = validate({"name": "SCHRECK", "fast_track": True,
                       "body": {"color": [255, 255, 0]}})

print("== Verlauf ==")
check("Anfang", ease(0.0), 0.0)
check("Ende", ease(1.0), 1.0)
check("Mitte", ease(0.5), 0.5)
ok("startet sanft") if ease(0.1) < 0.1 else bad("startet nicht sanft")
ok("endet sanft") if ease(0.9) > 0.9 else bad("endet nicht sanft")

print("== Weicher Übergang ==")
c = Clock()
tr = Transition(A, duration=1.0, clock=c)
check("zu Beginn A", tr.current()["physics"]["sway_amp"], 0)
tr.to(B)
ok("läuft") if tr.active else bad("nicht aktiv")
c.advance(0.5)
mid = tr.current()["physics"]["sway_amp"]
ok(f"Mitte liegt dazwischen ({mid})") if 0 < mid < 20 else bad(f"kein Zwischenwert: {mid}")
c.advance(0.5)
check("Ende erreicht B", tr.current()["physics"]["sway_amp"], 20)
ok("beendet") if not tr.active else bad("noch aktiv")

# Gegenprobe: ohne Übergang gäbe es keinen Zwischenwert — der Test würde
# sonst nicht messen, ob überhaupt geblendet wird.
c2 = Clock()
tr2 = Transition(A, duration=1.0, clock=c2)
tr2.to(B, hard=True)
check("Gegenprobe: hart springt sofort", tr2.current()["physics"]["sway_amp"], 20)

print("== Harter Wechsel ==")
c = Clock()
tr = Transition(A, duration=1.0, clock=c)
tr.to(B, hard=True)
ok("sofort fertig") if not tr.active else bad("blendet trotz hard")

# fast_track schaltet von selbst hart — ein Schreck darf nicht einblenden.
c = Clock()
tr = Transition(A, duration=1.0, clock=c)
tr.to(SCHRECK)
check("fast_track springt", tr.current()["body"]["color"], (255, 255, 0))
ok("kein laufender Übergang") if not tr.active else bad("fast_track blendet")

# Gegenprobe: derselbe Mood ohne fast_track muss blenden.
ohne = dict(SCHRECK, fast_track=False)
c = Clock()
tr = Transition(A, duration=1.0, clock=c)
tr.to(ohne)
c.advance(0.5)
ok("Gegenprobe: ohne fast_track wird geblendet") if tr.active \
    else bad("blendet nicht")

print("== Sonderfälle ==")
c = Clock()
tr = Transition(A, duration=1.0, clock=c)
tr.to(B)
c.advance(0.5)
zwischen = tr.current()["physics"]["sway_amp"]
tr.to(A)          # zurück, mitten im Übergang
sofort = tr.current()["physics"]["sway_amp"]
ok(f"Wechsel setzt am Zwischenstand an ({zwischen} → {sofort})") \
    if abs(sofort - zwischen) < 3 else bad(f"springt: {zwischen} → {sofort}")

c = Clock()
tr = Transition(A, duration=1.0, clock=c)
tr.to(A)
ok("gleicher Mood löst nichts aus") if not tr.active else bad("startet grundlos")

tr.to(None)
check("None ändert nichts", tr.target["name"], "A")

c = Clock()
tr = Transition(A, duration=1.0, clock=c)
tr.to(B)
tr.snap()
check("snap beendet sofort", tr.current()["physics"]["sway_amp"], 20)

print("== Farben ==")
c = Clock()
tr = Transition(A, duration=1.0, clock=c)
tr.to(B)
c.advance(0.5)
col = tr.current()["body"]["color"]
check("Farbe ist ein Tupel", type(col), tuple)
# Rot nach Blau läuft über Violett, nicht über Grau.
ok(f"kein Graumatsch {col}") if max(col) > 150 else bad(f"ausgewaschen: {col}")

print()
print(f"Ergebnis: {PASS} ok, {FAIL} fehlgeschlagen")
sys.exit(1 if FAIL else 0)
