"""Tests für die Sitzungsablage (Regel 8d).

Echte Dateien, echte Sitzung, echter Socket; nur der Agent ist ein Doppel.
Gegenprobe: ``--gegenprobe`` verfälscht die Ablage (Zeiger zeigt nach dem
Wechsel weiter auf die alte Sitzung, Alte bleibt beschreibbar); die Tests
müssen dann rot werden.
"""
import json
import os
import socket
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from chimera import ablage as ab, sitzung_socket  # noqa: E402
from chimera.agent.session import Session  # noqa: E402
from chimera.agent.loop import Agent  # noqa: E402

GEGENPROBE = "--gegenprobe" in sys.argv
PASS = FAIL = 0
def ok(m):
    global PASS; PASS += 1; print(f"  ok    {m}")
def bad(m):
    global FAIL; FAIL += 1; print(f"  FAIL  {m}")
def _kurz(x, n=160):
    r = repr(x)
    return r if len(r) <= n else r[:n] + f" … ({len(r)} Zeichen)"

def check(m, got, want):
    ok(m) if got == want else bad(f"{m} — erwartet {_kurz(want)}, bekam {_kurz(got)}")

if GEGENPROBE:
    _w = ab.Ablage.wechseln
    def kaputt(self, uebergabe):
        neu = _w(self, uebergabe)
        ab._atomar(self.wurzel / "haupt", self._wo + "\n")  # Zeiger zurück
        return neu
    def init_(self, *a, **k):
        ab.Ablage.__init__orig(self, *a, **k)
    ab.Ablage.__init__orig = ab.Ablage.__init__
    def wechseln_gp(self, u):
        self._wo = self.aktiv()
        return kaputt(self, u)
    ab.Ablage.wechseln = wechseln_gp

# Die Verfälschungen der Leseseite stehen einzeln, damit jede für sich
# laufen kann: ``python3 tests/test_ablage.py --gegenprobe=grenze``.
# Eine Mutation, die nur zufällig mit einer anderen zusammen rot wird,
# misst nicht die Zusage, die sie behauptet.
MUTATION = ""
for _a in sys.argv[1:]:
    if _a == "--gegenprobe":
        MUTATION = "wechsel"
    elif _a.startswith("--gegenprobe="):
        MUTATION = _a.split("=", 1)[1]
if MUTATION and MUTATION != "wechsel":
    GEGENPROBE = False            # die Wechsel-Verfälschung aus lassen
    _ls = ab.Ablage.lesen_seite
    _anz = ab.Ablage.anzahl
    if MUTATION == "grenze":
        # Die angeschnittene erste Zeile eines Blocks wird verworfen.
        def grenze(self, sid, max_n=200, vor=0):
            _echt = ab.LESE_BLOCK
            ab.LESE_BLOCK = _echt
            got = _ls(self, sid, max_n, vor)
            return got[1:] if len(got) > 1 else got
        ab.Ablage.lesen_seite = grenze
    elif MUTATION == "vor":
        # ``vor`` wird ignoriert: immer die letzten Einträge.
        def ohne_vor(self, sid, max_n=200, vor=0):
            return _ls(self, sid, max_n, 0)
        ab.Ablage.lesen_seite = ohne_vor
    elif MUTATION == "zaehlen":
        # Leere Zeilen werden mitgezählt.
        def zaehlen(self, sid):
            return _anz(self, sid) + 1
        ab.Ablage.anzahl = zaehlen
    elif MUTATION == "alles":
        # Die Seite wird gebaut, indem alles gelesen wird (der alte Weg).
        def alles(self, sid, max_n=200, vor=0):
            alle_ = self.lesen(sid)
            return sitzung_socket.seite(alle_, max_n, vor)
        ab.Ablage.lesen_seite = alles
    else:
        raise SystemExit(f"unbekannte Mutation {MUTATION!r} "
                         "(wechsel, grenze, vor, zaehlen, alles)")

class R:
    def __init__(self, t): self.text = t; self.provider = "p"; self.model = "m"

class Doppel:
    """Agent-Doppel mit echtem Verlauf wie der echte Loop (history.append)."""
    def __init__(self): self.history = []; self.n = 0
    def run(self, prompt):
        self.history.append({"role": "user", "content": prompt})
        self.n += 1
        t = f"antwort-{self.n}"
        self.history.append({"role": "assistant", "content": t})
        return R(t)

d = tempfile.mkdtemp()

print("== Verlauf überlebt einen Neustart ==")
a1 = ab.Ablage(d)
sid1 = a1.aktiv()
ag = Doppel(); ag.history = ab.Verlauf(a1, a1.laden())
s = Session(ag, ablage=a1)
s.ask("eins"); s.ask("zwei")
check("vier Nachrichten im Fenster", len(ag.history), 4)
a2 = ab.Ablage(d)                       # „Neustart“
check("gleiche Hauptsitzung", a2.aktiv(), sid1)
fenster = a2.laden()
check("Fenster aus der Platte = Fenster im RAM", fenster, list(ag.history))
check("Inhalt der letzten Antwort", fenster[-1]["content"], "antwort-2")

print("== Halb geschriebene letzte Zeile ==")
with open(Path(d) / "sitzungen" / sid1 / "verlauf.jsonl", "a") as f:
    f.write('{"art":"nachricht","rolle":"us')
check("Rest bleibt lesbar", len(ab.Ablage(d).laden()), 4)
# Aufräumen der kaputten Zeile für die Folgetests
p = Path(d) / "sitzungen" / sid1 / "verlauf.jsonl"
p.write_text("".join(l for l in p.read_text().splitlines(True) if l.endswith("}\n")))

print("== Verdichten behält das Protokoll ==")
ag.history.verdichten("Kurzfassung", 2)
check("Fenster: Zusammenfassung + 2", len(ag.history), 3)
check("Fenster beginnt mit Marke", ag.history[0]["content"].startswith(ab.MARKE), True)
roh = ab.Ablage(d).lesen(sid1)
check("Protokoll hat noch alle 4 Nachrichten",
      sum(1 for e in roh if e["art"] == "nachricht"), 4)
check("Abspielen ergibt dasselbe Fenster", ab.Ablage(d).laden(), list(ag.history))

print("== Wechsel: haupt zeigt auf die Neue, Alte nur lesbar ==")
alt_id = a1.aktiv()
neu_id = s.wechseln("ÜBERGABE: es läuft X", "test")
check("neue Sitzung ist Haupt", a1.aktiv(), neu_id)
check("alte ist alt", a1.alt(), alt_id)
check("Neue beginnt mit der Übergabe",
      [m["content"] for m in ag.history], ["ÜBERGABE: es läuft X"])
try:
    a1.anhaengen({"art": "nachricht", "rolle": "user", "inhalt": "x"}, sid=alt_id)
    bad("Schreiben auf die alte Sitzung abgelehnt")
except ab.AblageFehler:
    ok("Schreiben auf die alte Sitzung abgelehnt")
check("Alte unverändert lesbar", len(a1.lesen(alt_id)) >= 4, True)
check("Alte nicht schreibbar", a1.schreibbar(alt_id), False)
vorher = a1.lesen(alt_id)

print("== Socket: Eingabe an die alte ID landet in der neuen ==")
sock = os.path.join(d, "s.sock")
srv = sitzung_socket.SitzungsServer(s, pfad=sock).start()
time.sleep(0.1)
c = socket.socket(socket.AF_UNIX); c.connect(sock)
f = c.makefile("rwb", buffering=0)
def sende(**kw):
    f.write((json.dumps(kw) + "\n").encode())
def lies():
    while True:
        o = json.loads(f.readline())
        if "ereignis" not in o:
            return o
sende(op="frage", tuer="web", text="an die alte", sitzung=alt_id)
r = lies()
check("als umgeleitet gemeldet", r["umgeleitet"], True)
for _ in range(50):
    if any(m["content"] == "antwort-3" for m in a1.laden()):
        break
    time.sleep(0.1)
check("Eingabe steht in der neuen Sitzung",
      any(m["content"].endswith("an die alte") for m in a1.laden()), True)
check("alte Sitzung unverändert", a1.lesen(alt_id), vorher)

sende(op="frage", tuer="web", text="an haupt", sitzung="haupt")
check("„haupt“ wird nicht umgeleitet", lies()["umgeleitet"], False)
sende(op="sitzungen")
r = lies()
check("Socket meldet haupt/alt", (r["haupt"], r["alt"]), (neu_id, alt_id))
sende(op="lesen", sitzung=alt_id)
check("Socket liest die alte Sitzung", len(lies()["eintraege"]) >= 4, True)

print("== Zweiter Wechsel: Archiv, Prüfung, 3 Tage ==")
time.sleep(0.5)
dritte = s.wechseln("ÜBERGABE 2", "test")
check("erste Sitzung archiviert", (Path(d) / "archiv" / f"{alt_id}.tar.gz").exists(), True)
check("Verzeichnis der ersten weg", (Path(d) / "sitzungen" / alt_id).exists(), False)
check("Archiv noch lesbar", len(a1.lesen(alt_id)) >= 4, True)
check("alt ist jetzt die zweite", a1.alt(), neu_id)
p = Path(d) / "archiv" / f"{alt_id}.tar.gz"
check("frisches Archiv bleibt", a1.aufraeumen(), [])
old = time.time() - 4 * 24 * 3600
os.utime(p, (old, old))
check("4 Tage altes Archiv wird gelöscht", a1.aufraeumen(), [alt_id])
check("Datei ist weg", p.exists(), False)

print("== Ungültige IDs ==")
for bose in ("../x", "a/b", ""):
    try:
        a1.lesen(bose); bad(f"{bose!r} abgelehnt")
    except ab.AblageFehler:
        ok(f"{bose!r} abgelehnt")

print("== Seite statt allem: lesen_seite/anzahl (14.11.) ==")
# Ein eigener Baum mit einem langen Verlauf. Geschrieben wird direkt, nicht
# über anhaengen: 20 000 fsync wären Minuten für eine Eigenschaft, die hier
# nicht geprüft wird (anhaengen hat seine eigenen Tests).
lang = ab.Ablage(tempfile.mkdtemp())
sid = lang.aktiv()
pfad = Path(lang.wurzel) / "sitzungen" / sid / "verlauf.jsonl"
zeilen = []
for i in range(20000):
    # Unterschiedlich lange Zeilen: sonst lägen die Blockgrenzen zufällig
    # immer auf einer Zeilengrenze und die Zerlegung wäre nicht geprüft.
    inhalt = "zeile-%05d-" % i + ("x" * (i % 97))
    zeilen.append(json.dumps({"art": "nachricht", "rolle": "user",
                              "inhalt": inhalt}, ensure_ascii=False))
pfad.write_text("\n".join(zeilen) + "\n", encoding="utf-8")

# Die Blockgröße klein setzen: dann liegen viele Grenzen mitten in Zeilen,
# und derselbe Vergleich prüft die Zerlegung mit.
ab.LESE_BLOCK = 97
alle = lang.lesen(sid)
check("anzahl zählt die Einträge", lang.anzahl(sid), len(alle))
check("Verlauf vollständig gelesen", len(alle), 20000)

for max_n, vor in ((50, 0), (50, 50), (200, 0), (1, 0), (500, 19950),
                   (3, 19999), (200, 20000), (7, 1), (5000, 100)):
    want = sitzung_socket.seite(alle, max_n, vor)
    got = lang.lesen_seite(sid, max_n, vor)
    check(f"Seite max={max_n} vor={vor} gleich", got, want)

check("Seite über das Ende hinaus ist leer", lang.lesen_seite(sid, 200, 20000), [])
check("Unsinniges max verhält sich wie seite()",
      lang.lesen_seite(sid, 0, 0), sitzung_socket.seite(alle, 0, 0))
check("Unsinniges vor wird zu 0",
      lang.lesen_seite(sid, 3, "kaputt"), lang.lesen_seite(sid, 3, 0))

# Speicher: der Punkt der Übung. lesen() baut alle 20 000 Dicts, lesen_seite
# nur die Seite. Gemessen wird die Spitze, nicht die Dauer (Zeit wäre auf
# verschiedenen Geräten nicht vergleichbar).
import tracemalloc  # noqa: E402
tracemalloc.start()
lang.lesen_seite(sid, 50, 0)
spitze_seite = tracemalloc.get_traced_memory()[1]
tracemalloc.reset_peak()
lang.lesen(sid)
spitze_alle = tracemalloc.get_traced_memory()[1]
tracemalloc.stop()
check("eine Seite belegt deutlich weniger als alles",
      spitze_seite < spitze_alle / 20, True)
print(f"        (Spitze: Seite {spitze_seite // 1024} KiB, "
      f"alles {spitze_alle // 1024} KiB)")

# Eine halb geschriebene letzte Zeile (Absturz mitten im Schreiben) darf die
# Seite nicht verschieben. Sie zählt in ``anzahl`` mit — das ist die Zahl der
# Zeilen in der Datei, und sie wird im Protokoll gemeldet, nicht verschwiegen.
with open(pfad, "a", encoding="utf-8") as f:
    f.write('{"art":"nachricht","rolle":"ass')
letzte = lang.lesen_seite(sid, 5, 0)
check("halbe Zeile verschiebt die Seite nicht", len(letzte), 5)
check("halbe Zeile ist der letzte lesbare Eintrag",
      letzte[-1]["inhalt"].endswith("x" * (19999 % 97)), True)
check("anzahl zählt die Zeilen der Datei (inkl. kaputter)",
      lang.anzahl(sid), 20001)

print(f"\n{PASS} ok, {FAIL} FAIL")
sys.exit(1 if FAIL else 0)
