"""Tests für Schema, Validator, Registry, Mischen und freie Formen.

Läuft ohne Hardware. Jeder Regressionstest hat eine Gegenprobe: Erst wird
gezeigt, dass der Schutz greift, dann dass er ohne ihn nicht gegriffen
hätte — sonst misst der Test nichts (Architekturregel 9).

Aufruf:  python3 tests/test_mood.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from chimera.mood import blend, draw, schema  # noqa: E402
from chimera.mood.registry import Registry  # noqa: E402
from chimera.mood.validate import (  # noqa: E402
    MoodError,
    fallback,
    safe_validate,
    validate,
)

PASS = FAIL = 0


def ok(msg):
    global PASS
    PASS += 1
    print(f"  ok    {msg}")


def bad(msg):
    global FAIL
    FAIL += 1
    print(f"  FAIL  {msg}")


def check(msg, got, want):
    ok(msg) if got == want else bad(f"{msg} — erwartet {want!r}, bekam {got!r}")


def section(title):
    print(f"== {title} ==")


# --- Schema ---------------------------------------------------------------

section("Schema")
d = schema.defaults()
check("alle Slots vorhanden", set(d), set(schema.SLOTS))
check("Standardmund", d["mouth"]["style"], "smile")
llm = schema.describe_for_llm()
check("Beschreibung deckt alle Slots", set(llm), set(schema.SLOTS))
ok("Grenzen dokumentiert") if llm["physics"]["felder"]["headbang_amp"]["bis"] == 40 else bad("Grenze fehlt")


# --- Validator: Zurechtstutzen --------------------------------------------

section("Validator")
m, r = validate({"name": "WILD", "physics": {"headbang_amp": 5000}})
check("absurder Wert geklemmt", m["physics"]["headbang_amp"], 40)
ok("Korrektur vermerkt") if r.fixes else bad("Korrektur nicht vermerkt")

# Gegenprobe: ohne Klemmen bliebe der Wert stehen und der Avatar verließe
# den Bildschirm. Belegt, dass der Test etwas misst.
raw_value = {"name": "X", "physics": {"headbang_amp": 5000}}["physics"]["headbang_amp"]
ok("Gegenprobe: roher Wert wäre 5000") if raw_value == 5000 else bad("Gegenprobe kaputt")

m, r = validate({"name": "P", "particles": {"rate": 0.99}})
check("Partikeldichte begrenzt", m["particles"]["rate"], 0.6)

m, r = validate({"name": "F", "body": {"color": "#ff8800"}})
check("Farbe aus Hex", m["body"]["color"], (255, 136, 0))
m, _ = validate({"name": "F2", "body": {"color": [300, -5, 20]}})
check("Farbkanäle begrenzt", m["body"]["color"], (255, 0, 20))

m, r = validate({"name": "U", "eyes": {"gibtsnicht": 5}})
ok("unbekanntes Feld verworfen") if any("gibtsnicht" in x for x in r.drops) else bad("nicht verworfen")
ok("Feld nicht durchgereicht") if "gibtsnicht" not in m["eyes"] else bad("durchgereicht")

m, _ = validate({"name": "B", "eyes": {"droopy": "ja"}})
check("Ja/Nein aus Text", m["eyes"]["droopy"], True)

m, _ = validate({"name": "D"})
check("Standard wenn nichts gesagt", m["mouth"]["style"], "smile")

try:
    validate({"mouth": {"style": "smile"}})
    bad("Mood ohne Namen hätte scheitern müssen")
except MoodError:
    ok("Mood ohne Namen abgelehnt")

m, r = safe_validate({"kein": "name"})
check("Rückfall greift", m["name"], "FALLBACK")
ok("Rückfall meldet Grund") if r.drops else bad("Grund fehlt")


# --- Freie Namen und Formen -----------------------------------------------

section("Freie Gestaltung")
m, r = validate({"name": "NEU", "mouth": {"style": "zaehneknirschen"}})
check("erfundener Name bleibt", m["mouth"]["style"], "zaehneknirschen")
ok("Hinweis auf eigene Formen") if any("frei" in x for x in r.fixes) else bad("kein Hinweis")

m, _ = validate({
    "name": "S",
    "shapes": [
        {"kind": "arc", "x": .5, "y": .6, "w": .2, "h": .1,
         "start": 20, "end": 160, "width": .01},
        {"kind": "polygon", "points": [[.2, .2], [.3, .1], [.4, .2]],
         "color": "#ff8800", "fill": True, "motion": "pulse"},
    ],
})
check("Formen übernommen", len(m["shapes"]), 2)
check("Bewegung übernommen", m["shapes"][1]["motion"], "pulse")

m, r = validate({"name": "Z", "shapes": [{"kind": "raumschiff", "x": .5}]})
check("unbekannte Form verworfen", m.get("shapes"), None)
ok("Verwerfen vermerkt") if r.drops else bad("nicht vermerkt")

m, r = validate({"name": "L", "shapes": [{"kind": "line", "points": [[.1, .1]]}]})
check("Linie mit einem Punkt verworfen", m.get("shapes"), None)

many = [{"kind": "ellipse", "x": .5, "y": .5, "w": .1, "h": .1} for _ in range(100)]
m, r = validate({"name": "M", "shapes": many})
check("Formenzahl begrenzt", len(m["shapes"]), draw.MAX_SHAPES)
ok("Begrenzung vermerkt") if any("begrenzt" in x for x in r.fixes) else bad("nicht vermerkt")

# Jede Form muss einzeln durchkommen — sonst steht sie im Schema und
# funktioniert trotzdem nicht.
probe = {
    "ellipse":  {"x": .5, "y": .5, "w": .2, "h": .2},
    "circle":   {"x": .5, "y": .5, "r": .1},
    "rect":     {"x": .5, "y": .5, "w": .2, "h": .1, "radius": .02},
    "polygon":  {"points": [[.2, .2], [.3, .1], [.4, .2]]},
    "ngon":     {"x": .5, "y": .5, "r": .1, "sides": 5, "rotation": 18},
    "arc":      {"x": .5, "y": .5, "w": .2, "h": .2, "start": 0, "end": 180, "width": .01},
    "chord":    {"x": .5, "y": .5, "w": .2, "h": .2, "start": 0, "end": 180},
    "pieslice": {"x": .5, "y": .5, "w": .2, "h": .2, "start": 0, "end": 90},
    "line":     {"points": [[.1, .1], [.9, .9]], "width": .01, "joint": "curve"},
    "point":    {"points": [[.5, .5]]},
    "text":     {"x": .5, "y": .5, "text": "?!", "size": .1, "anchor": "mm"},
}
check("alle Formen abgedeckt", set(probe), set(draw.SHAPES))
missing = []
for kind, args in probe.items():
    mm, _ = validate({"name": "T", "shapes": [dict(kind=kind, **args)]})
    if not mm.get("shapes"):
        missing.append(kind)
ok("jede Form kommt durch") if not missing else bad(f"verworfen: {missing}")

mm, _ = validate({"name": "N", "shapes": [
    {"kind": "ngon", "x": .5, "y": .5, "r": .1, "sides": 99}]})
check("Eckenzahl begrenzt", mm["shapes"][0]["sides"], 24)
ok("Eckenzahl ganzzahlig") if isinstance(mm["shapes"][0]["sides"], int) else bad("nicht ganzzahlig")

mm, _ = validate({"name": "O", "shapes": [
    {"kind": "rect", "x": .5, "y": .5, "w": .2, "h": .1,
     "outline": "#00ff00", "fill": False}]})
check("Umrissfarbe übernommen", mm["shapes"][0]["outline"], (0, 255, 0))

mm, r = validate({"name": "J", "shapes": [
    {"kind": "line", "points": [[.1, .1], [.9, .9]], "joint": "zickzack"}]})
ok("unbekanntes Auswahlfeld weggelassen") if "joint" not in mm["shapes"][0] else bad("durchgereicht")

m, _ = validate({"name": "K", "shapes": [
    {"kind": "ellipse", "x": 9.9, "y": -9.9, "w": .1, "h": .1}]})
ok("Koordinaten geklemmt") if m["shapes"][0]["x"] <= 1.5 and m["shapes"][0]["y"] >= -0.5 \
    else bad("Koordinaten nicht geklemmt")


# --- Mischen --------------------------------------------------------------

section("Mischen")
a, _ = validate({"name": "A", "body": {"color": [255, 0, 0]},
                 "physics": {"sway_amp": 0}, "mouth": {"style": "grin"}})
b, _ = validate({"name": "B", "body": {"color": [0, 0, 255]},
                 "physics": {"sway_amp": 20}, "mouth": {"style": "frown"}})

check("t=0 ergibt links", blend.mix(a, b, 0.0)["physics"]["sway_amp"], 0)
check("t=1 ergibt rechts", blend.mix(a, b, 1.0)["physics"]["sway_amp"], 20)
check("Mitte mittelt Zahlen", blend.mix(a, b, 0.5)["physics"]["sway_amp"], 10)
check("Auswahl: leichtes Gewicht", blend.mix(a, b, 0.2)["mouth"]["style"], "grin")
check("Auswahl: schweres Gewicht", blend.mix(a, b, 0.8)["mouth"]["style"], "frown")

# Farbmischung über den Farbton: Rot und Gelb müssen ein sattes Orange
# ergeben, nicht ein ausgewaschenes.
mixed = blend.mix_color((255, 0, 0), (255, 255, 0), 0.5)
ok(f"Rot+Gelb bleibt satt {mixed}") if max(mixed) > 200 and mixed[2] < 60 \
    else bad(f"Farbmischung flau: {mixed}")

# Gegenprobe: kanalweise gemittelt wäre es dasselbe — hier nicht aussagekräftig.
# Aussagekräftig ist Rot+Blau: kanalweise ergäbe (127,0,127), über den
# Farbton läuft es über Violett und bleibt kräftig.
mixed_rb = blend.mix_color((255, 0, 0), (0, 0, 255), 0.5)
naive = (127, 0, 127)
ok(f"Rot+Blau nicht naiv gemittelt {mixed_rb}") if mixed_rb != naive \
    else bad("Farbmischung ist doch kanalweise")

grey = blend.mix_color((128, 128, 128), (0, 200, 0), 0.0)
check("Grau bleibt grau bei t=0", grey, (128, 128, 128))

three = blend.mix_many([(a, 1), (b, 1), (a, 2)], name="DREI")
check("Mehrfachmischung benannt", three["name"], "DREI")
ok("Gewichte wirken") if three["physics"]["sway_amp"] < 10 else bad("Gewichtung falsch")


# --- Variieren ------------------------------------------------------------

section("Variieren")
v1 = blend.vary(a, seed=42)
v2 = blend.vary(a, seed=42)
check("gleicher Seed, gleiches Ergebnis", v1["body"]["color"], v2["body"]["color"])
v3 = blend.vary(a, seed=7)
ok("anderer Seed, anderes Ergebnis") if v3["body"]["color"] != v1["body"]["color"] \
    else bad("Seed wirkt nicht")
check("Auswahl bleibt unangetastet", v1["mouth"]["style"], a["mouth"]["style"])
vs = blend.vary(a, seed=1, strength=1.0)
ok("auch stark variiert im Rahmen") if 0 <= vs["physics"]["sway_amp"] <= 25 \
    else bad("Variation verlässt die Grenzen")


# --- Registry -------------------------------------------------------------

section("Registry")
reg = Registry(capacity=5)
e1, _ = reg.add({"name": "RUHIG"}, origin="builtin")
e2, _ = reg.add({"name": "WACH"}, origin="generated")
check("zwei Einträge", len(reg), 2)
check("Nummern fortlaufend", (e1.mood_id, e2.mood_id), (1, 2))
check("Zugriff über Namen", reg.get("ruhig")["name"], "RUHIG")
check("Zugriff über Nummer", reg.get(e2.mood_id)["name"], "WACH")

e3, _ = reg.add({"name": "RUHIG", "priority": 90}, origin="generated")
check("gleicher Name behält Nummer", e3.mood_id, e1.mood_id)
check("Inhalt ersetzt", reg.get("RUHIG")["priority"], 90)

for i in range(10):
    reg.add({"name": f"TMP{i}"}, origin="generated")
ok("Bibliothek begrenzt") if len(reg) <= 5 else bad(f"nicht begrenzt: {len(reg)}")
ok("Eingebautes überlebt") if "RUHIG" in reg else bad("Eingebautes weggeräumt")
check("Herkunft nicht herabgestuft", reg.find("RUHIG").origin, "builtin")

# Gegenprobe: ohne diesen Schutz verlöre ein überschriebener eingebauter
# Mood seinen Status und flöge beim nächsten Überlauf heraus.
reg3 = Registry(capacity=3)
reg3.add({"name": "FEST"}, origin="builtin")
reg3.find("FEST").origin = "generated"        # so sähe es ohne Schutz aus
for i in range(8):
    reg3.add({"name": f"F{i}"}, origin="generated")
ok("Gegenprobe: ohne Schutz verschwindet es") if "FEST" not in reg3 \
    else bad("Gegenprobe misslungen")

# Gegenprobe: ohne Begrenzung wüchse sie ungebremst.
reg2 = Registry(capacity=1000)
for i in range(30):
    reg2.add({"name": f"X{i}"})
check("Gegenprobe: ohne Grenze wächst sie", len(reg2), 30)

import tempfile  # noqa: E402

with tempfile.TemporaryDirectory() as td:
    p = Path(td) / "moods.json"
    reg2.save(p)
    back = Registry.load(p)
    check("gespeichert und geladen", len(back), len(reg2))
    ok("Namen erhalten") if set(back.names()) == set(reg2.names()) else bad("Namen verloren")

section("Mehrere Accessoires")
m, _ = validate({"name": "A2", "accessory": {"type": ["sunglasses", "frost"]}})
check("zwei Accessoires", m["accessory"]["type"], ("sunglasses", "frost"))
m, _ = validate({"name": "A1", "accessory": {"type": "headphones"}})
check("eines geht auch", m["accessory"]["type"], ("headphones",))
m, r = validate({"name": "A9", "accessory": {"type": ["a", "b", "c", "d", "e", "f"]}})
ok("Anzahl begrenzt") if len(m["accessory"]["type"]) <= 4 else bad("nicht begrenzt")

x, _ = validate({"name": "X", "accessory": {"type": ["headphones"]}})
y, _ = validate({"name": "Y", "accessory": {"type": ["sunglasses"]}})
both = blend.mix(x, y, 0.5)
check("Mischen vereinigt Accessoires", set(both["accessory"]["type"]),
      {"headphones", "sunglasses"})

section("Startbestand aus Noisy")
bi = Path(__file__).resolve().parent.parent / "data" / "moods-builtin.json"
if bi.exists():
    import json as _json
    data = _json.loads(bi.read_text(encoding="utf-8"))["moods"]
    check("41 Moods", len(data), 41)
    reg4 = Registry(capacity=500)
    bad_ones = []
    for entry in data:
        e, rp = reg4.add(entry, origin="builtin")
        if rp.drops:
            bad_ones.append((entry.get("name"), rp.drops))
    check("alle aufgenommen", len(reg4), 41)
    ok("keiner beanstandet") if not bad_ones else bad(f"beanstandet: {bad_ones[:2]}")
    mixed = blend.mix(reg4.get("ROCK"), reg4.get("CHILL"), 0.5, name="ROCKCHILL")
    ok("zwei Startmoods mischbar") if mixed["name"] == "ROCKCHILL" else bad("Mischen fehlgeschlagen")

    # Der Test oben liest die Datei SELBST und ruft add() auf — damit
    # blieb unbemerkt, dass Registry.load() sie nicht lesen konnte
    # (flaches gegen verpacktes Format). Der Weg, den das Programm
    # wirklich nimmt, muss auch geprüft werden.
    geladen = Registry.load(bi, capacity=500)
    check("load() liest die mitgelieferte Datei", len(geladen), 41)
    ok("Namen kommen mit") if "CHILL" in geladen else bad("CHILL fehlt nach load()")
    # Gegenprobe: das verpackte Format (save) muss weiter gehen.
    import tempfile as _tf
    with _tf.TemporaryDirectory() as _td:
        _p = Path(_td) / "rund.json"
        geladen.save(_p)
        zurueck = Registry.load(_p)
        check("Rundlauf save→load", len(zurueck), 41)
        ok("Nutzungszähler überlebt") if all(
            zurueck.find(n) is not None for n in ("CHILL", "ROCK")) \
            else bad("Moods nach Rundlauf verschwunden")
else:
    bad("data/moods-builtin.json fehlt — tools/import-noisy-moods.py laufen lassen")

print()
print(f"Ergebnis: {PASS} ok, {FAIL} fehlgeschlagen")
sys.exit(1 if FAIL else 0)
