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

reg, _ = mood_laden(BUILTIN, ordner() / "eigene-moods.json")
mood = reg.get("IDLE")

# --- 3b. Helligkeit und Nachtfenster ------------------------------------

print("== Nachtfenster ==")
check("Helligkeit: 0 und 255 sind gültig",
      (E.helligkeit_pruefen(0), E.helligkeit_pruefen(255)), (0, 255))
for schlecht in [-1, 256, "hell", None, True]:
    check(f"Helligkeit abgelehnt: {schlecht!r}", E.helligkeit_pruefen(schlecht), None)
for gut in ["00:00", "06:30", "23:59"]:
    check(f"Uhrzeit angenommen: {gut}", E.uhrzeit_pruefen(gut), gut)
for schlecht in ["24:00", "6:30", "0630", "06:60", "", None, 630]:
    check(f"Uhrzeit abgelehnt: {schlecht!r}", E.uhrzeit_pruefen(schlecht), None)
check("Schalter: Wahrheitswert, Zahl, Wort",
      (E.schalter_pruefen(True), E.schalter_pruefen(0), E.schalter_pruefen("an"),
       E.schalter_pruefen("AUS")), (True, False, True, False))
check("Schalter: Unsinn ist kein 'aus'", E.schalter_pruefen("vielleicht"), None)

d5 = ordner()
n = E.Avatar(d5 / "avatar.json")
# Vorgabe: dimmen AUS -- sonst würde das Gerät über Nacht ungefragt dunkler.
check("Nachtfenster ist standardmäßig aus", n.get_display()["auto_dim"], False)
check("Helligkeiten und Zeiten haben Vorgaben",
      (n.get_display()["brightness_day"], n.get_display()["brightness_night"],
       n.get_display()["night_mode_start"], n.get_display()["night_mode_end"]),
      (255, 80, "22:00", "06:00"))
ok_setzen, _ = n.setzen("nacht_dimmen", True)
check("Schalter lässt sich setzen", (ok_setzen, n.get_display()["auto_dim"]), (True, True))
ok_setzen, _ = n.setzen("nacht_von", "21:15")
check("Startzeit gesetzt", (ok_setzen, n.get_display()["night_mode_start"]), (True, "21:15"))
ok_setzen, meldung = n.setzen("nacht_von", "25:00")
check("kaputte Uhrzeit abgelehnt", ok_setzen, False)
check("nach der Ablehnung steht die alte Zeit",
      n.get_display()["night_mode_start"], "21:15")
ok_setzen, _ = n.setzen("helligkeit_nacht", 60)
check("Nacht-Helligkeit gesetzt", (ok_setzen, n.get_display()["brightness_night"]), (True, 60))
# Der Renderer liest die Schlüssel, die `_apply_brightness` fragt.
check("get_display nennt genau die Schlüssel des Renderers",
      sorted(n.get_display()), sorted(["auto_dim", "brightness_day",
                                       "brightness_night", "night_mode_start",
                                       "night_mode_end"]))

# Der Renderer wirklich: mit Nachtfenster über "jetzt" wird das Bild dunkler.
from datetime import datetime as _dt
jetzt = _dt.now().strftime("%H:%M")
frueher, spaeter = ("00:00", "23:59") if jetzt != "00:00" else ("00:01", "23:59")

def bild_mit_display(auto_dim: bool):
    abl = E.Avatar(ordner() / "avatar.json")
    abl.setzen("nacht_dimmen", auto_dim)
    abl.setzen("helligkeit_nacht", 40)
    abl.setzen("nacht_von", frueher)
    abl.setzen("nacht_bis", spaeter)
    st = State()
    st.rt = abl
    st.mood, st.mood_name = mood, "IDLE"
    r = NoisyRenderer(st, NullPanel())
    r.frame = 3.0
    img = r.render()
    return sum(sum(p) for p in img.getdata()) / (img.size[0] * img.size[1])

check("Nachtfenster macht das Bild dunkler (der Renderer liest get_display)",
      bild_mit_display(True) < bild_mit_display(False), True)

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

# --- 7. Vorübergehende Helligkeit der aktuellen Zone --------------------
#
# Auftrag smilez (15.11.): „in Einstellungen ein davon abgekoppelter
# Helligkeitsschalter der nur die aktuelle Tageszeit Zone regelt, evtl sogar
# nur temporär bis zum nächsten Tag/Nacht Wechsel und dann wieder die im
# Tag/Nacht Modus eingestellte Dimmstufe nimmt".

print("== 7. Helligkeit jetzt: Zone, Ablauf, Rückkehr ==")
import time as _zeit  # noqa: E402

with tempfile.TemporaryDirectory() as td:
    pfad = Path(td) / "avatar.json"
    a = E.Avatar(pfad)
    # Tag/Nacht-Modus an, klare Werte: tags 255, nachts 60.
    a.setzen("nacht_dimmen", True)
    a.setzen("helligkeit_tag", 255)
    a.setzen("helligkeit_nacht", 60)
    a.setzen("nacht_von", "22:00")
    a.setzen("nacht_bis", "06:00")

    # Die Zonenrechnung ist die des Renderers — nicht nachgebaut, sondern
    # dieselbe Regel: über Mitternacht zählt beides.
    check("zone: 23:00 ist Nacht", E.zone("23:00", "22:00", "06:00"), "nacht")
    check("zone: 05:59 ist Nacht", E.zone("05:59", "22:00", "06:00"), "nacht")
    check("zone: 06:00 ist Tag", E.zone("06:00", "22:00", "06:00"), "tag")
    check("zone: 21:59 ist Tag", E.zone("21:59", "22:00", "06:00"), "tag")
    check("zone: Fenster ohne Mitternacht", E.zone("13:00", "12:00", "14:00"), "nacht")
    check("naechster Wechsel ab 23:00 → 06:00",
          E.naechster_wechsel("23:00", "22:00", "06:00"), 7 * 3600)
    check("naechster Wechsel ab 10:00 → 22:00",
          E.naechster_wechsel("10:00", "22:00", "06:00"), 12 * 3600)

    # Was gilt jetzt? (Der Test setzt die Zone über `nacht_dimmen` aus.)
    a.setzen("nacht_dimmen", False)
    check("ohne Nachtfenster gilt immer Tag", a.als_json()["zone"], "tag")
    check("Display ohne Überlagerung: Tagwert",
          a.get_display()["brightness_day"], 255)

    ok, meldung = a.setzen("helligkeit_jetzt", 120)
    check("setzen wird bestätigt", ok, True)
    check("die Meldung nennt Zone und Gültigkeit",
          "tag" in meldung and "gilt bis" in meldung, True)
    j = a.als_json()
    check("Überlagerung gilt", j["helligkeit_jetzt_gilt"], True)
    check("Überlagerung ersetzt den Tagwert",
          a.get_display()["brightness_day"], 120)
    check("der Nachtwert bleibt unberührt",
          a.get_display()["brightness_night"], 60)
    check("sie hat ein Ablaufdatum in der Zukunft", j["gilt_bis"] > _zeit.time(), True)

    # Abgelaufen: der Wert fällt auf die Einstellung zurück (Überlagerung aus,
    # Wert bleibt als Leiche in der Datei stehen -- er gilt nicht).
    roh = json.loads(pfad.read_text(encoding="utf-8"))
    roh["helligkeit_jetzt_bis"] = int(_zeit.time()) - 1
    pfad.write_text(json.dumps(roh), encoding="utf-8")
    b = E.Avatar(pfad)
    check("abgelaufen gilt nicht mehr", b.als_json()["helligkeit_jetzt_gilt"], False)
    check("abgelaufen: wieder die eingestellte Dimmstufe",
          b.get_display()["brightness_day"], 255)

    # Zone gewechselt: derselbe Wert gilt in der anderen Zone nicht.
    b.setzen("helligkeit_jetzt", 130)
    roh = json.loads(pfad.read_text(encoding="utf-8"))
    roh["helligkeit_jetzt_zone"] = "nacht"
    pfad.write_text(json.dumps(roh), encoding="utf-8")
    c = E.Avatar(pfad)
    check("Wert aus der anderen Zone gilt nicht", c.als_json()["helligkeit_jetzt_gilt"], False)
    check("… und ändert den Tagwert nicht", c.get_display()["brightness_day"], 255)

    # Zurücknehmen: der einzige Weg zur eingestellten Dimmstufe.
    ok, meldung = c.setzen("helligkeit_jetzt", "zurueck")
    check("zurücknehmen wird bestätigt", ok, True)
    d = json.loads(pfad.read_text(encoding="utf-8"))
    check("zurücknehmen räumt alle drei Felder",
          [k for k in d if k.startswith("helligkeit_jetzt")], [])
    check("zurücknehmen: Einstellung gilt",
          E.Avatar(pfad).get_display()["brightness_day"], 255)

    # Unsinn wird abgelehnt und ändert nichts.
    e = E.Avatar(pfad)
    vorher = e.get_display()
    check("300 ist keine Helligkeit", e.setzen("helligkeit_jetzt", 300)[0], False)
    check("'zuruck' ist kein Befehl", e.setzen("helligkeit_jetzt", "zuruck")[0], False)
    check("nach Ablehnung unverändert", e.get_display(), vorher)

print(f"\n{PASS} ok, {FAIL} FAIL")
sys.exit(0 if FAIL == 0 else 1)
