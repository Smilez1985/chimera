"""Avatar-Einstellungen (DESIGN, Regel „Avatar-Einstellungen").

Geprüft wird die **echte** Ablage und der **echte** Renderer, nicht ein
Nachbau:

* ungültige Werte ändern nichts — und sagen warum (Gegenprobe: nach dem
  Fehlversuch steht der alte Wert, nicht die Vorgabe);
* eine kaputte oder fehlende Datei ergibt Vorgaben **mit Hinweis**;
* Schreiben ist atomar (nie eine halbe Datei);
* die Vorschau-Rechnung: eigener Ablauf → einmal ganz, Dauerzustand → 30 s;
* der Renderer liest die Werte wirklich: zwei Frisuren und zwei Farben
  ergeben unterschiedliche Bilder (nicht nur unterschiedliche Aufrufe);
* die Positivliste der Frisuren deckt sich mit den `draw_hair_<name>` des
  Renderers — sonst zeigt die Auswahl Namen, die niemand zeichnen kann.

Aufruf: python3 tests/test_einstellungen.py
Gegenprobe: python3 tests/gegenprobe_einstellungen.py
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

# Eine Baumkopie, damit die Gegenprobe (tests/gegenprobe_einstellungen.py)
# Verfälschungen anlegen kann, ohne den echten Baum anzufassen.
ROOT = Path(os.environ.get("CHIMERA_ROOT_TEST") or
            Path(__file__).resolve().parent.parent)
sys.path.insert(0, str(ROOT / "src"))

from chimera.display.panel import NullPanel  # noqa: E402
from chimera.mood.ablage import lade as mood_laden  # noqa: E402
from chimera.render import einstellungen as E  # noqa: E402
from chimera.render.avatar import NoisyRenderer, State  # noqa: E402

PASS = 0
FAIL = 0
BUILTIN = ROOT / "data" / "moods-builtin.json"

def check(name, ist, soll):
    global PASS, FAIL
    if ist == soll:
        PASS += 1
        print(f"  ok    {name}")
    else:
        FAIL += 1
        print(f"  FAIL  {name} -- erwartet {soll!r}, bekam {ist!r}")

def ordner() -> Path:
    return Path(tempfile.mkdtemp(prefix="chimera-avatar-"))

# --- 1. Werte prüfen -------------------------------------------------------

print("== Werte ==")
check("Farbe: #RRGGBB wird groß geschrieben", E.farbe_pruefen("#8b5a2b"), "#8B5A2B")
for schlecht in ["8B5A2B", "#8B5A2", "#GGGGGG", "", None, 123, "#8B5A2B00"]:
    check(f"Farbe abgelehnt: {schlecht!r}", E.farbe_pruefen(schlecht), None)
check("Kontrast: 0 und 100 sind gültig",
      (E.kontrast_pruefen(0), E.kontrast_pruefen(100)), (0, 100))
for schlecht in [-1, 101, "viel", None, True, 3.7]:
    check(f"Kontrast abgelehnt: {schlecht!r}", E.kontrast_pruefen(schlecht), None)
for gut in E.FRISUREN:
    check(f"Frisur angenommen: {gut}", E.frisur_pruefen(gut), gut)
for schlecht in ["Mochi!", "", None, 7, "glatze"]:
    check(f"Frisur abgelehnt: {schlecht!r}", E.frisur_pruefen(schlecht), None)

# --- 2. Ablage: schreiben, lesen, ablehnen --------------------------------

print("== Ablage ==")
d = ordner()
a = E.Avatar(d / "avatar.json")
check("ohne Datei gelten die Vorgaben",
      (a.get_hair_style(), a.get_hair_color(), a.get_contrast()),
      (E.STANDARD_FRISUR, E.hex_zu_rgb(E.STANDARD_FARBE), E.STANDARD_KONTRAST))
check("ohne Datei kein Hinweis (nichts ist kaputt)",
      a.als_json()["hinweise"], [])

ok_setzen, meldung = a.setzen("frisur", "zopf")
check("gültige Frisur gesetzt", ok_setzen, True)
check("Frisur gilt sofort", a.get_hair_style(), "zopf")
check("Datei liegt mit 0644", oct((d / "avatar.json").stat().st_mode & 0o777), oct(0o644))

# Gegenprobe: ein ungültiger Wert darf NICHTS ändern.
ok_setzen, meldung = a.setzen("frisur", "glatze")
check("ungültige Frisur abgelehnt", ok_setzen, False)
check("Ablehnung nennt den Grund", "glatze" in meldung, True)
check("nach der Ablehnung steht der alte Wert", a.get_hair_style(), "zopf")
check("die Datei blieb unverändert",
      json.loads((d / "avatar.json").read_text())["frisur"], "zopf")

ok_setzen, _ = a.setzen("farbe", "#12Ab34")
check("Farbe gesetzt und normalisiert",
      (ok_setzen, a.get_hair_color()), (True, (0x12, 0xAB, 0x34)))
ok_setzen, _ = a.setzen("kontrast", "60")
check("Kontrast als Text gesetzt", (ok_setzen, a.get_contrast()), (True, 60))
ok_setzen, meldung = a.setzen("tempo", 3)
check("unbekanntes Feld abgelehnt", ok_setzen, False)
check("Grund nennt die erlaubten Felder", "frisur" in meldung, True)

# Eine neue Instanz liest, was die alte geschrieben hat (kein RAM-Zustand).
b = E.Avatar(d / "avatar.json")
check("die Datei trägt die Werte", (b.get_hair_style(), b.get_contrast()), ("zopf", 60))

# --- 3. Kaputte und fremde Dateien ---------------------------------------

print("== Kaputte Dateien ==")
d2 = ordner()
(d2 / "avatar.json").write_text("{ das ist kein JSON")
c = E.Avatar(d2 / "avatar.json")
check("kaputte Datei → Vorgabe", c.get_hair_style(), E.STANDARD_FRISUR)
check("kaputte Datei wird gemeldet", any("unlesbar" in h for h in c.als_json()["hinweise"]), True)

d3 = ordner()
(d3 / "avatar.json").write_text(json.dumps(["mochi"]))
check("Liste statt Objekt → Vorgabe und Hinweis",
      (E.Avatar(d3 / "avatar.json").get_hair_style(),
       any("Objekt" in h for h in E.Avatar(d3 / "avatar.json").als_json()["hinweise"])),
      (E.STANDARD_FRISUR, True))

d4 = ordner()
(d4 / "avatar.json").write_text(json.dumps({"frisur": "zopf", "farbe": "lila", "kontrast": 999}))
e = E.Avatar(d4 / "avatar.json")
check("einzelne kaputte Felder fallen auf die Vorgabe",
      (e.get_hair_style(), e.get_hair_color(), e.get_contrast()),
      ("zopf", E.hex_zu_rgb(E.STANDARD_FARBE), E.STANDARD_KONTRAST))
check("jedes kaputte Feld wird einzeln genannt",
      len([h for h in e.als_json()["hinweise"] if "ungültig" in h]), 2)

# --- 4. Vorschau-Rechnung ------------------------------------------------

print("== Vorschau ==")
check("eigene Dauer → einmal ganz (dauer None)",
      E.vorschau({"name": "BONG", "dauer_s": 13}), (None, "eigene Dauer — läuft einmal ganz (13 s)"))
check("Dauerzustand → 30 s",
      E.vorschau({"name": "ROCK"}), (30.0, "Dauerzustand — 30 s Vorschau"))
check("kaputtes dauer_s zählt als Dauerzustand",
      E.vorschau({"name": "X", "dauer_s": "viel"})[0], 30.0)
check("negative Dauer zählt nicht als eigene",
      E.vorschau({"name": "X", "dauer_s": -5})[0], 30.0)
# Die vertauschte Regel („max(30, 13)" = der BONG-Fehler vom 15.11.) prüft
# die Gegenprobe: tests/gegenprobe_einstellungen.py baut sie in eine
# Baumkopie ein, und dieser Test muss dann rot werden.

# --- 5. Der Renderer liest die Werte wirklich ----------------------------

print("== Renderer ==")
reg, _ = mood_laden(BUILTIN, ordner() / "eigene-moods.json")
mood = reg.get("IDLE")

def bild(frisur: str, farbe: str):
    abl = E.Avatar(ordner() / "avatar.json")
    abl.setzen("frisur", frisur)
    abl.setzen("farbe", farbe)
    st = State()
    st.rt = abl
    st.mood, st.mood_name = mood, "IDLE"
    r = NoisyRenderer(st, NullPanel())
    r.frame = 3.0
    return r.render().tobytes()

mochi = bild("mochi", "#8B5A2B")
zopf = bild("zopf", "#8B5A2B")
check("zwei Frisuren ergeben verschiedene Bilder", mochi != zopf, True)
braun = bild("mochi", "#8B5A2B")
rot = bild("mochi", "#FF0000")
check("zwei Haarfarben ergeben verschiedene Bilder", braun != rot, True)
# Ohne rt (der Zustand vor dieser Änderung) sind beide Frisuren gleich --
# die Gegenprobe nutzt das als Verfälschung.

# --- 6. Eine Liste, eine Stelle -----------------------------------------

print("== Frisurenliste gegen den Renderer ==")
quelle = (ROOT / "src/chimera/render/avatar.py").read_text(encoding="utf-8")
im_renderer = sorted(
    zeile.split("draw_hair_")[1].split("(")[0]
    for zeile in quelle.splitlines()
    if "def draw_hair_" in zeile
)
check("die Positivliste ist genau das, was der Renderer zeichnet",
      sorted(E.FRISUREN), im_renderer)

print(f"\n{PASS} ok, {FAIL} FAIL")
sys.exit(0 if FAIL == 0 else 1)
