"""Tests fuer eigene Moods: ablegen, pruefen, behalten (DESIGN 3.3b).

Der Kern: Was der Agent erfindet, muss einen Neustart ueberstehen — und
darf dabei nicht die mitgelieferte Bibliothek umschreiben, aus dem
Verzeichnis ausbrechen oder die Obergrenze sprengen.
"""
import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
# CHIMERA_SRC laesst die Gegenprobe eine veraenderte Kopie pruefen.
sys.path.insert(0, str(Path(os.environ.get("CHIMERA_SRC") or ROOT / "src")))

from chimera.agent.face import Face                      # noqa: E402
from chimera.agent.tools import Toolbox                   # noqa: E402
from chimera.mood import ablage as A                      # noqa: E402
from chimera.mood.registry import Registry                # noqa: E402
from chimera.render.avatar import State                   # noqa: E402

BUILTIN = ROOT / "data" / "moods-builtin.json"
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


def wirft(m, fn, *a, **kw):
    try:
        fn(*a, **kw)
        bad(f"{m} — kein Fehler")
    except A.AblageFehler:
        ok(m)


with tempfile.TemporaryDirectory() as td:
    td = Path(td)
    eigene = td / "moods.json"

    print("== Name ==")
    check("gross geschrieben", A.pruefname(" chill "), "CHILL")
    check("Leerzeichen wird Unterstrich", A.pruefname("sehr wuetend"),
          "SEHR_WUETEND")
    for schlecht in ("", "x" * 25, "a/b", "../etc", "mood.json", "a b!"):
        wirft(f"Name abgelehnt: {schlecht!r}", A.pruefname, schlecht)

    print("== Bauen ==")
    reg, hinweise = A.lade(BUILTIN, td / "fehlt.json")
    check("nur mitgeliefert", len(reg), 43)
    check("kein Hinweis ohne eigene Datei", hinweise, [])
    roh = A.bauen(reg, "grummelig", von="CHILL",
                  felder={"mouth": {"style": "frown"}})
    check("Name gesetzt", roh["name"], "GRUMMELIG")
    check("Feld gemischt", roh["mouth"]["style"], "frown")
    check("uebrige Felder vom Vorbild", roh["mouth"]["width"],
          reg.get("CHILL")["mouth"]["width"])
    wirft("ohne Vorbild und Felder abgelehnt", A.bauen, reg, "X")
    wirft("unbekanntes Vorbild abgelehnt", A.bauen, reg, "X", von="GIBTSNICHT")
    wirft("zu tief abgelehnt", A.bauen, reg, "X",
          felder={"a": {"b": {"c": {"d": {"e": {"f": {"g": 1}}}}}}})

    print("== Anlegen und Behalten ==")
    eintrag, bericht = A.anlegen(reg, eigene, "grummelig", von="CHILL",
                                felder={"mouth": {"style": "frown"}})
    check("Nummer vergeben", eintrag.mood_id, 44)
    check("Herkunft", eintrag.origin, "generated")
    # Die Vorlage ist eine Referenz, keine Arbeitskopie: Wird sie veraendert,
    # heisst der eingebaute Ausdruck danach anders (Gegenprobe
    # "vorbild-wird-angefasst").
    check("Vorbild behaelt seinen Namen", reg.find("CHILL").mood["name"],
          "CHILL")
    check("Datei geschrieben", eigene.is_file(), True)
    roh_datei = json.loads(eigene.read_text(encoding="utf-8"))
    namen = [m["mood"]["name"] for m in roh_datei["moods"]]
    check("nur der eigene steht in der Datei", namen, ["GRUMMELIG"])
    check("next_id mitgeschrieben", roh_datei["next_id"], 45)

    reg2, hinweise2 = A.lade(BUILTIN, eigene)
    check("nach Neustart da", reg2.find("GRUMMELIG") is not None, True)
    check("Herkunft ueberlebt", reg2.find("GRUMMELIG").origin, "generated")
    check("Hinweis nennt die Zahl", hinweise2[0].startswith("Moods: 1"), True)
    check("eingebaute bleiben", len(reg2), 44)

    print("== Grenzen ==")
    wirft("eingebauter Name abgelehnt", A.anlegen, reg, eigene, "CHILL",
          von="CHILL")
    check("CHILL unveraendert", reg.find("CHILL").origin, "builtin")
    wirft("Loeschen eingebauter abgelehnt", A.entfernen, reg, eigene, "CHILL")
    wirft("Loeschen unbekannter abgelehnt", A.entfernen, reg, eigene, "NIX")

    # Validierung klemmt und sagt es (Regel 2).
    _, rep = A.anlegen(reg, eigene, "uebertrieben", von="CHILL",
                       felder={"physics": {"headbang_amp": 5000}})
    check("Korrektur gemeldet", bool(rep.fixes or rep.drops), True)
    amp = reg.find("UEBERTRIEBEN").mood["physics"]["headbang_amp"]
    check("Wert im Rahmen", amp <= 40, True)

    # Obergrenze: generierte fallen weg, eingebaute nie.
    klein = Registry(capacity=5)
    klein.add(reg.get("CHILL"), origin="builtin")
    for i in range(6):
        klein.add({"name": f"EIGEN{i}", "body": {"color": [1, 2, 3]}},
                  origin="generated")
    check("Obergrenze greift", len(klein), 5)
    check("Eingebautes bleibt", klein.find("CHILL") is not None, True)

    print("== Kaputte eigene Datei ==")
    kaputt = td / "kaputt.json"
    kaputt.write_text("{ das ist kein json", encoding="utf-8")
    regk, hinweisk = A.lade(BUILTIN, kaputt)
    check("mitgelieferte bleiben", len(regk), 43)
    check("Befund statt Absturz", "nicht lesbar" in hinweisk[0], True)

    print("== Face und Werkzeug ==")
    eigene3 = td / "face.json"
    face = Face(reg2, State(), ablage=eigene3)
    toolbox = Toolbox(td / "arbeit", face=face)
    text = toolbox.call("mood_anlegen",
                        {"name": "zorn", "von": "CHILL",
                         "felder": '{"mouth": {"style": "frown"}}'})
    check("Werkzeug legt an", text.startswith("Angelegt: ZORN"), True)
    check("Werkzeug schreibt Datei", eigene3.is_file(), True)
    check("Werkzeug meldet die Zahl",
          "Ausdruecke insgesamt" in text, True)

    text = toolbox.call("mood_anlegen", {"name": "ohne"})
    check("ohne Vorbild: Auskunft", text.startswith("Nicht angelegt:"), True)
    text = toolbox.call("mood_anlegen",
                        {"name": "kaputtf", "von": "CHILL", "felder": "nicht json"})
    check("kaputtes JSON: Auskunft", "kein gueltiges JSON" in text, True)
    text = toolbox.call("mood_anlegen", {"name": "CHILL", "von": "CHILL"})
    check("eingebauter Name: Auskunft", "ist eingebaut" in text, True)

    text = toolbox.call("set_face", {"mood": "ZORN"})
    check("neuer Ausdruck setzbar", text, "Ausdruck gesetzt: ZORN — gilt bis zur Ablösung")
    text = toolbox.call("mood_entfernen", {"name": "zorn"})
    check("Werkzeug loescht", text.startswith("Geloescht: ZORN"), True)
    check("nach Loeschen weg", reg2.find("ZORN") is None, True)

    # Das Vorbild wird beim Bauen nicht angefasst (deepcopy).
    check("Vorbild unveraendert", reg2.find("CHILL").mood["mouth"]["style"],
          reg.get("CHILL")["mouth"]["style"])

    print("== Ablage ohne Pfad ==")
    nackt = Face(reg2, State())
    try:
        nackt.anlegen("X", von="CHILL")
        bad("ohne Ablage angelegt")
    except A.AblageFehler:
        ok("ohne Ablage abgelehnt")

print("== Verdrahtung: app._try_face ==")
from chimera import app                                  # noqa: E402

with tempfile.TemporaryDirectory() as td:
    home = Path(td)
    notes = []
    face1, _r1, _p1 = app._try_face(notes, home)
    check("Gesicht aufgesetzt", face1 is not None, True)
    check("Ablage liegt im Heimverzeichnis", face1.ablage, home / "moods.json")
    face1.anlegen("drahtig", von="CHILL", felder={"mouth": {"style": "frown"}})

    notes2 = []
    face2, _r2, _p2 = app._try_face(notes2, home)
    check("nach dem Aufbau wieder da", face2.moods.find("DRAHTIG") is not None,
          True)
    check("Hinweis nennt den Bestand",
          any("eigene" in n for n in notes2), True)

print(f"\nErgebnis: {PASS} ok, {FAIL} fehlgeschlagen")
sys.exit(1 if FAIL else 0)
