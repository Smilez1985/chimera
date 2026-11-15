"""Das Ruhegesicht ist das Agentengesicht (DESIGN, Regel „Sprechgesicht" 6).

Fund am Pi (15.11.2026): `set_face CHAOS` meldete „Ausdruck gesetzt", die
nächste Nachricht trug trotzdem `[Gesicht: active=mood_idle]` — `wartet`
überschrieb am Turn-Ende jedes Gesicht mit IDLE. Auf dem Display war damit
nichts zu sehen, egal was der Agent setzte.

Geprüft wird der echte `Face` an der echten Bibliothek und einem echten
`State`; kein Nachbau der Entscheidung.

Aufruf: python3 tests/test_ruhegesicht.py [--gegenprobe]
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
# CHIMERA_SRC laesst die Gegenprobe eine veraenderte Kopie pruefen, ohne den
# echten Quellbaum anzufassen (Muster aus test_freigabe_erinnerung.py).
sys.path.insert(0, str(Path(os.environ.get("CHIMERA_SRC") or ROOT / "src")))

from chimera.agent.face import Face  # noqa: E402
from chimera.mood.registry import Registry  # noqa: E402
from chimera.render.avatar import State  # noqa: E402

GEGENPROBE = "--gegenprobe" in sys.argv
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
    ok(m) if got == want else bad(f"{m} — erwartet {want!r}, bekam {got!r}")

BIB = ROOT / "data" / "moods-builtin.json"

class Uhr:
    """Einsetzbare Uhr: die Haltezeit (HALT_S) wird ohne Warten geprüft."""
    def __init__(self) -> None:
        self.t = 100.0
    def __call__(self) -> float:
        return self.t
    def vor(self, sekunden: float) -> None:
        self.t += sekunden


def neues_face() -> tuple[Face, State, Uhr]:
    reg = Registry.load(BIB)
    st = State()
    uhr = Uhr()
    return Face(reg, st, clock=uhr), st, uhr

print("== ohne Agentenwahl bleibt die Ruhe IDLE ==")
face, st, uhr = neues_face()
face.show_state("wartet")
check("frisch: wartet -> IDLE", st.mood_name, "IDLE")

print("== ein gesetztes Gesicht überlebt den Turn ==")
face, st, uhr = neues_face()
# ``dauer=0`` heißt „bis zur Ablösung" — hier soll der Zustand aber wieder
# drankommen, also mit Frist setzen (smilez, 15.11.2026: die Dauer entscheidet
# der Aufruf oder der Ausdruck).
face.set_by_name("CHAOS", hard=True, dauer=1)
check("set_face zeigt CHAOS", st.mood_name, "CHAOS")
face.show_state("wartet")
check("nach wartet steht weiter CHAOS", st.mood_name, "CHAOS")

print("== der Zustand zeigt sich, die Ruhe kehrt zum Agenten zurück ==")
# Seit 15.11.2026 hält ein gesetztes Gesicht HALT_S Sekunden, bevor ein
# Zustand es übernimmt (sonst war der Befehl nicht zu sehen). Hier läuft
# die Frist ab, danach zeigt der Zustand wieder seinen eigenen Ausdruck.
uhr.vor(1.1)
face.show_state("denkt")
check("denkt zeigt seinen Ausdruck", st.mood_name, "CURIOUS")
face.show_state("wartet")
check("danach wieder CHAOS", st.mood_name, "CHAOS")
uhr.vor(1.1)
face.show_state("spricht")
check("spricht zeigt SPEAK", st.mood_name, "SPEAK")
face.show_state("wartet")
check("danach wieder CHAOS", st.mood_name, "CHAOS")

print("== ein neuer set_face ersetzt das alte ==")
face.set_by_name("ROCK", hard=True)
face.show_state("wartet")
check("Ruhe folgt dem letzten set_face", st.mood_name, "ROCK")

print("== ein gelöschter Ausdruck fällt auf IDLE zurück ==")
face, st, uhr = neues_face()
face.set_by_name("CHAOS", hard=True)
face.moods.remove("CHAOS")
face._last_state = None          # neuer Turn: der Zustand wird neu gemeldet
try:
    face.show_state("wartet")
    ergebnis = st.mood_name
except Exception as exc:         # noqa: BLE001 — ein Absturz ist ein Fehlschlag
    ergebnis = type(exc).__name__
check("gelöschter Ausdruck -> IDLE", ergebnis, "IDLE")

print("== die Meldung, die das Modell sieht, nennt das Agentengesicht ==")
face, st, uhr = neues_face()
face.set_by_name("CHAOS", hard=True)
face.show_state("wartet")
check("mood_name ist der Agentenausdruck", st.mood_name, "CHAOS")

if GEGENPROBE:
    # Die Gegenprobe verfälscht das Verhalten im Speicher: `wartet` fällt
    # wieder auf IDLE zurück, wie vor der Änderung.
    print("== Gegenprobe: altes Verhalten (wartet -> IDLE) muss rot werden ==")
    face, st, uhr = neues_face()
    face.set_by_name("CHAOS", hard=True)
    face._ruhegesicht = lambda: False        # das alte Verhalten
    face._last_state = None
    face.show_state("wartet")
    check("Gegenprobe: CHAOS bleibt", st.mood_name, "CHAOS")

print()
print(f"Ergebnis: {PASS} ok, {FAIL} fehlgeschlagen")
sys.exit(0 if FAIL == 0 else 1)
