"""Tests für das Lebenszeichen (DESIGN, Regel „Lebenszeichen", 14.11.2026).

Echter Unix-Socket, echter Faden, echte Zeit — nur die Uhr und die Adresse
sind einsetzbar. Geprüft wird, was an `$NOTIFY_SOCKET` ankommt; ein Test, der
nur `erlaubt()` nachrechnet, besteht auch mit einem Faden, der nie schlägt.

Gegenprobe: ``python3 tests/test_lebenszeichen.py --gegenprobe``
"""
import json
import os
import socket
import sys
import tempfile
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
# CHIMERA_SRC laesst die Gegenprobe eine veraenderte Kopie pruefen.
sys.path.insert(0, str(Path(os.environ.get("CHIMERA_SRC") or ROOT / "src")))

from chimera import lebenszeichen as lz  # noqa: E402

GEGENPROBE = any(a == "--gegenprobe" or a.startswith("--gegenprobe=") for a in sys.argv[1:])
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


# Verfälschungen, einzeln wählbar:
#   --gegenprobe           der Faden schlägt immer (Hänger bleibt unsichtbar)
#   --gegenprobe=busy      busy wird vergessen (langer Aufruf gilt als Hänger)
# Ein Test, der die Verfälschung nachbaut, besteht auch mit kaputtem Code --
# deshalb bleibt die Erwartung hier unverändert, und der Lauf MUSS rot werden.
MUTATION = next((a.split("=", 1)[1] for a in sys.argv[1:] if a.startswith("--gegenprobe=")), "")
if GEGENPROBE and MUTATION == "busy":
    lz.Melder.busy = lambda self, zweck, sekunden: None
elif GEGENPROBE:
    lz.Melder.erlaubt = lambda self: True


class Uhr:
    """Einsetzbare monotone Uhr."""

    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t


def sammler(pfad):
    """Datagram-Socket, der die Zeilen mitschreibt."""
    s = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
    s.bind(pfad)
    s.settimeout(5)
    return s


def lesen(s, n, frist=5.0):
    zeilen = []
    ende = time.time() + frist
    while len(zeilen) < n and time.time() < ende:
        try:
            s.settimeout(max(0.1, ende - time.time()))
            zeilen.append(s.recv(4096).decode())
        except socket.timeout:
            break
    return zeilen


d = tempfile.mkdtemp()

print("== Rechnung ohne Faden ==")
check("ohne busy gilt die Grundgeduld", lz.erlaubte_stille(90, 0), 90)
check("busy verlängert um Frist und Nachlass", lz.erlaubte_stille(90, 300, 30), 330)
check("eine kürzere busy-Frist kürzt nichts", lz.erlaubte_stille(90, 10, 30), 90)
check("eine abgelaufene Frist zählt als 0", lz.erlaubte_stille(90, -5, 30), 90)
check("Fortschritt vor der Grenze ist erlaubt", lz.beat_erlaubt(89, 90), True)
check("Fortschritt an der Grenze ist erlaubt", lz.beat_erlaubt(90, 90), True)
check("darüber ist es ein Hänger", lz.beat_erlaubt(90.5, 90), False)
check("busy deckt einen langen Aufruf", lz.beat_erlaubt(200, 90, 300), True)
check("busy ohne Frist hilft nicht", lz.beat_erlaubt(200, 90, 0), False)

print("== Faden: READY einmal, WATCHDOG im Takt ==")
pfad = os.path.join(d, "notify.sock")
s = sammler(pfad)
uhr = Uhr()
m = lz.Melder(pfad, takt_s=0.05, jetzt=uhr, grund=90)
check("start meldet Erfolg", m.start(), True)
zeit = lesen(s, 1)
check("READY kommt sofort", zeit, ["READY=1"])
m.fortschritt()
zeit = lesen(s, 2)
check("danach schlägt der Faden", [z for z in zeit if z == "WATCHDOG=1"][:1], ["WATCHDOG=1"])

print("== Hänger: der Faden schweigt ==")
# Uhr weit vorspulen, ohne Fortschritt zu melden: ab jetzt darf nichts mehr
# kommen -- sonst würde ein hängender Dienst als gesund gemeldet.
uhr.t += 200
zeit = lesen(s, 3, frist=1.0)
check("bei Stillstand kommt kein Schlag mehr", zeit, [])

print("== busy überbrückt einen langen Aufruf ==")
uhr.t += 1
m.fortschritt()
m.busy("Turn (web)", 300)
# 150 s Stille: 150 s Frist übrig + 30 s Nachlass = 180 s Geduld -> erlaubt.
# (Mit 200 s wäre die Geduld schon vorbei -- die Frist deckt genau die
# erwartete Dauer, sie ist keine Freikarte.)
uhr.t += 150
zeit = lesen(s, 2)
check("busy hält das Lebenszeichen am Leben", [z for z in zeit if z == "WATCHDOG=1"][:1], ["WATCHDOG=1"])

print("== Nach der Frist ist Schluss ==")
uhr.t += 100          # jetzt 250 s Stillstand gegen 80 s Geduld: vorbei
zeit = lesen(s, 3, frist=1.0)
check("abgelaufenes busy schützt nicht mehr", zeit, [])

print("== Zustandsdatei: nur zur Ansicht ==")
zustand = Path(d) / "lebenszeichen.json"
m2 = lz.Melder(None, jetzt=lambda: 500.0, zustandsdatei=zustand)
m2.busy("Werkzeug", 120)
daten = json.loads(zustand.read_text(encoding="utf-8"))
check("Zweck steht drin", daten["zweck"], "Werkzeug")
check("Sekunden stehen drin", daten["sekunden"], 120.0)
check("die Frist ist eine Unix-Zeit", daten["busy_bis"] > 1_700_000_000, True)
check("und die Entscheidung hängt nicht daran", m2.busy_rest(), 120.0)

print("== Ohne NOTIFY_SOCKET läuft alles weiter, aber mit Meldung ==")
m3 = lz.Melder("", jetzt=Uhr())
check("start sagt: kein Watchdog", m3.start(), False)
check("und es gibt keinen Faden", m3._faden, None)
check("fortschritt bleibt folgenlos", (m3.fortschritt(), True)[1], True)

print("== Ein nicht erreichbarer Socket tötet nichts ==")
m4 = lz.Melder(os.path.join(d, "gibtesnicht.sock"), takt_s=0.05, jetzt=Uhr())
check("start meldet trotzdem Erfolg", m4.start(), True)
time.sleep(0.2)
m4.stop()
ok("Faden beendet sich sauber")

print("== Die Verdrahtung im Dienst und im Turn ==")
quelle = (Path(os.environ.get("CHIMERA_SRC") or ROOT / "src")).resolve()
dienst = (quelle / "chimera" / "__main__.py").read_text(encoding="utf-8")
check("der Dienst startet den Melder", "waechter.start()" in dienst, True)
check("und meldet Fortschritt im Takt", "waechter.fortschritt()" in dienst, True)
check("und meldet ihn beim Beenden ab", "waechter.stop()" in dienst, True)
check("der Melder wird gesetzt (kein stiller No-Op)", "setze_melder(waechter)" in dienst, True)
session = (quelle / "chimera" / "agent" / "session.py").read_text(encoding="utf-8")
check("ein Turn meldet seine Frist an", "lebenszeichen.busy(f\"Turn" in session, True)
check("und danach einen Fortschritt", "lebenszeichen.fortschritt()" in session, True)
einheit = (ROOT / "installer" / "lib" / "service.sh").read_text(encoding="utf-8")
check("die Unit lauscht auf das Lebenszeichen", "Type=notify" in einheit, True)
check("und hat eine Watchdog-Frist", "WatchdogSec=30" in einheit, True)

m.stop() if m._faden else None
s.close()
print(f"\n{PASS} ok, {FAIL} FAIL")
sys.exit(1 if FAIL else 0)
