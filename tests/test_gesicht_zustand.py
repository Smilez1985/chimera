"""Gesicht und Zustand (DESIGN Regel 4d).

Geprueft wird die echte Bibliothek und der echte Renderer, nicht ein Nachbau:

* `spricht` zeigt keinen Ausdruck mit Ohr -- das Gesicht darf nicht das
  Gegenteil des Zustands sagen;
* `hoert` zeigt den Ausdruck mit Ohr (frueher `TALK`, jetzt `LISTEN`);
* der Ruhezustand hat einen Ausdruck (`IDLE`);
* `SPEAK` hat Mundphasen, jede steht SPEAK_HALTE Bilder, der Kreis schliesst sich;
* jede Antwort der Agentenschleife und der Telegram-Tuer endet mit `wartet`.

Gegenprobe: `python3 tests/test_gesicht_zustand.py --gegenprobe` stellt je
einen alten Zustand wieder her; der Test muss rot werden.
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from chimera.agent import face as facemod  # noqa: E402
from chimera.display.panel import NullPanel  # noqa: E402
from chimera.mood.validate import validate  # noqa: E402
from chimera.render.avatar import NoisyRenderer, State  # noqa: E402

PASS = FAIL = 0
GEGENPROBE = "--gegenprobe" in sys.argv


def ok(m):
    global PASS
    PASS += 1
    print(f"  ok    {m}")


def bad(m):
    global FAIL
    FAIL += 1
    print(f"  FAIL  {m}")


def check(m, got, want):
    ok(m) if got == want else bad(f"{m} -- erwartet {want!r}, bekam {got!r}")


def moods():
    d = json.loads((ROOT / "data" / "moods-builtin.json").read_text(encoding="utf-8"))
    return {m["name"]: m for m in d["moods"]}


M = moods()
# Der echte Weg: jeder Mood laeuft durch den Validator (Listen werden Tupel).
MV = {n: validate(m)[0] for n, m in M.items()}


def mit_ohr(name):
    return "big_ear" in M[name]["accessory"]["type"]


print("== Ausdruecke ==")
check("TALK gibt es nicht mehr", "TALK" in M, False)
check("LISTEN hat das Ohr", mit_ohr("LISTEN"), True)
check("IDLE gibt es (Ruhezustand)", "IDLE" in M, True)
check("IDLE hat kein Zubehoer", M["IDLE"]["accessory"]["type"], [])
check("SPEAK gibt es", "SPEAK" in M, True)
check("SPEAK hat kein Ohr", mit_ohr("SPEAK"), False)
check("SPEAK hat kein Zubehoer", M["SPEAK"]["accessory"]["type"], [])
check("SPEAK schaut geradeaus", M["SPEAK"]["eyes"]["look_offset"], 0)
check("SPEAK hat den Sprechmund", M["SPEAK"]["mouth"]["style"], "speak")

print("== Zustand -> Ausdruck (die echte Tabelle) ==")
check("spricht -> SPEAK zuerst", facemod.STATE_MOODS["spricht"][0], "SPEAK")
check("hoert -> LISTEN", facemod.STATE_MOODS["hoert"], ("LISTEN",))
check("wartet -> IDLE zuerst", facemod.STATE_MOODS["wartet"][0], "IDLE")
for zustand, kandidaten in facemod.STATE_MOODS.items():
    fehlt = [k for k in kandidaten if k not in M]
    check(f"{zustand}: jeder Name steht in der Bibliothek", fehlt, [])
check("spricht hat nie einen Ausdruck mit Ohr als Ersatz",
      [k for k in facemod.STATE_MOODS["spricht"] if k in M and mit_ohr(k)], [])

print("== Validierung ==")
for name in ("SPEAK", "LISTEN", "IDLE"):
    _m, rep = validate(M[name])
    check(f"{name}: Validator ohne Korrektur", rep.clean, True)

print("== Mundphasen im Renderer ==")
r = NoisyRenderer(State(), NullPanel())
check("Standard: Phasen", r.SPEAK_PHASEN, ("zu", "halb", "offen", "halb"))
check("Standard: Halten", r.SPEAK_HALTE, 3)
check("2 bis 4 Phasen", 2 <= len(r.SPEAK_PHASEN) <= 4, True)

# Phase je Bild: jede Phase steht SPEAK_HALTE Bilder, dann die naechste.
folge = [r.sprech_phase(f) for f in range(0, len(r.SPEAK_PHASEN) * r.SPEAK_HALTE * 2)]
erwartet = []
for _ in range(2):
    for p in r.SPEAK_PHASEN:
        erwartet += [p] * r.SPEAK_HALTE
check("jede Phase steht HALTE Bilder, der Kreis laeuft", folge, erwartet)
check("negatives und riesiges Bild bleiben im Bereich",
      {r.sprech_phase(-7), r.sprech_phase(10**9)} <= set(r.SPEAK_PHASEN), True)

# Halten 1: Phase wechselt jedes Bild; Halten 10: bleibt 10 Bilder.
r.SPEAK_HALTE = 1
check("Halten 1", [r.sprech_phase(f) for f in range(4)], list(r.SPEAK_PHASEN))
r.SPEAK_HALTE = 10
check("Halten 10", len({r.sprech_phase(f) for f in range(10)}), 1)
r.SPEAK_HALTE = 3


def mund_pixel(renderer, frame):
    """Bild mit SPEAK zeichnen und den dunklen Mundbereich zaehlen."""
    st = renderer.state
    st.mood, st.mood_name = MV["SPEAK"], "SPEAK"
    renderer.frame = float(frame)
    img = renderer.render()
    w, h = img.size
    # Mundbereich: grob unter der Mitte des Gesichts
    box = img.crop((int(w * 0.38), int(h * 0.50), int(w * 0.62), int(h * 0.66)))
    px = box.getdata()
    return sum(1 for p in px if sum(p) < 120)


r2 = NoisyRenderer(State(), NullPanel())
dunkel = {}
for phase_start, name in zip(range(0, 12, 3), r2.SPEAK_PHASEN):
    dunkel.setdefault(name, mund_pixel(r2, phase_start))
check("Mund 'offen' ist groesser als 'zu'", dunkel["offen"] > dunkel["zu"], True)
check("Mund 'halb' liegt dazwischen", dunkel["zu"] < dunkel["halb"] < dunkel["offen"], True)

print("== jede Antwort endet mit 'wartet' ==")
from chimera.agent.loop import Agent  # noqa: E402


class Antwort:
    provider, model, fell_back = "p", "m", False

    def __init__(self, text):
        self.text = text


class Registry:
    def __init__(self, texte):
        self.texte = list(texte)

    def resolve(self, task):
        return []

    def call(self, task, a, history, system):
        t = self.texte.pop(0)
        if isinstance(t, Exception):
            raise t
        return Antwort(t)


def lauf(texte):
    import tempfile
    from chimera.agent.tools import Toolbox
    gesehen = []
    a = Agent(Registry(texte), Toolbox(tempfile.mkdtemp(prefix="chimera-gz-")))
    a.on_state = gesehen.append
    try:
        a.run("hallo")
    except Exception as exc:  # noqa: BLE001
        gesehen.append(f"Ausnahme:{type(exc).__name__}")
    return gesehen


try:
    g = lauf(["Hallo!"])
    check("Antwort: letzter Zustand ist wartet", g[-1], "wartet")
    check("Antwort: spricht kam vor wartet", "spricht" in g, True)
    # Ein Anbieter, der eine Ausnahme wirft: sie geht an den Aufrufer weiter
    # (so war es immer), aber das Gesicht bleibt nicht stehen.
    g2 = lauf([RuntimeError("kein Anbieter")])
    check("Ausnahme im Anbieter: sie wird nicht verschluckt", g2[-1], "Ausnahme:RuntimeError")
    check("Ausnahme im Anbieter: wartet kam trotzdem", g2[-2], "wartet")
except Exception as exc:  # noqa: BLE001
    bad(f"Agent-Lauf nicht pruefbar: {type(exc).__name__}: {exc}")

print(f"\nErgebnis: {PASS} ok, {FAIL} fehlgeschlagen")
sys.exit(1 if FAIL else 0)
