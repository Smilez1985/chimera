#!/usr/bin/env python3
"""Tests fuer das Treiberpaket `chimera.displays` und die Fassade
`chimera.display.panel` (DISPLAYS.md §4/§5, DESIGN Regel 6e/10g).

Geprueft wird, was am Geraet NICHT nachstellbar ist: die Entscheidungen.
Hardware wird nicht nachgebaut -- `erkennen.py` liest Attrappen unter
`$CHIMERA_ROOT/chimera-probe/<art>-<kennzeichen>`, und `CHIMERA_ROOT`
verschiebt alle Dateipfade. Was wirklich an Leitungen haengt (SPI, GPIO),
ist am 11.10.2026 am chimera-pi gemessen (shared/notes-chimera/analyse/
WHISPLAY-ABNAHME-1110.md); ein Test, der das nachbildet, bezeugte nur
sich selbst.

Jeder Test hat eine Gegenprobe in `tests/gegenprobe_displays.py`.
"""

import json
import os
import sys
import tempfile
from pathlib import Path

# Welcher Quellbaum geprueft wird, entscheidet CHIMERA_SRC -- so laeuft die
# Gegenprobe gegen eine verfaelschte Kopie. Ohne die Variable: das Repo.
# (Ein festes sys.path.insert(0, repo/src) gewaenne sonst immer, und die
# Gegenprobe maesse den echten Baum statt der Kopie.)
SRC = Path(os.environ.get("CHIMERA_SRC") or Path(__file__).resolve().parent.parent / "src")
sys.path.insert(0, str(SRC))

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


class Umgebung:
    """Erfundene Wurzel samt Attrappen; setzt die Umgebung zurueck."""

    def __init__(self, **attrappen):
        self.attrappen = attrappen
        self.vorher = {}

    def __enter__(self):
        self.tmp = tempfile.TemporaryDirectory()
        wurzel = Path(self.tmp.name)
        probe = wurzel / "chimera-probe"
        probe.mkdir()
        for name, wert in self.attrappen.items():
            (probe / name).write_text(str(wert))
        # Bus 1 vorhanden -- sonst meldet die I2C-Pruefung „Bus nicht aktiv"
        # und das Ergebnis haengt an einer anderen Ursache als gemeint.
        (wurzel / "sys/bus/i2c/devices/i2c-1").mkdir(parents=True)
        for k, v in (("CHIMERA_ROOT", str(wurzel)), ("CHIMERA_ANZEIGE", None)):
            self.vorher[k] = os.environ.get(k)
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        return wurzel

    def __exit__(self, *a):
        for k, v in self.vorher.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        self.tmp.cleanup()


def neu_laden():
    """Module frisch laden -- sie lesen die Umgebung beim Aufruf, aber die
    Registry haelt Pfade zur Paketwurzel; ein Neuimport schliesst aus, dass
    ein Zustand aus einem vorigen Test durchschlaegt."""
    for name in [n for n in list(sys.modules) if n.startswith("chimera.display")]:
        del sys.modules[name]
    from chimera.displays import erkennen, registry
    return erkennen, registry


print("== Registry: Ordner sind die Liste ==")
_, registry = neu_laden()
typen = registry.typen()
ok(f"gefundene Module: {', '.join(typen)}")
check("whisplay dabei", "whisplay" in typen, True)
check("keine dabei", "keine" in typen, True)
for typ in typen:
    p = registry.profil(typ)
    check(f"{typ}: typ == Ordnername", p.typ, typ)
    ok(f"{typ}: {p.breite}x{p.hoehe} {p.farben} {p.bildrate:g}/s")

try:
    registry.profil("gibtsnicht")
    bad("unbekannter Typ haette KeyError geben muessen")
except KeyError as exc:
    check("unbekannter Typ nennt die bekannten", "whisplay" in str(exc), True)

# Eine *Panel-Klasse je Modul, ohne Pflichtargumente konstruierbar: das ist
# die Zusage, auf die sich `oeffne` stuetzt. Geprueft wird sie am Modul
# „keine" -- das einzige, das ohne Hardware konstruierbar ist.
k = registry.oeffne("keine")
check("keine: Groesse aus display.json", (k.width, k.height), (240, 280))
check("keine: Profil haengt am Panel", k.profil.typ, "keine")
ok(f"keine: Klasse {type(k).__name__}")

# Ein Modul, dessen display.json einen anderen Typ nennt als sein Ordner,
# wird uebersprungen und benannt -- sonst zeigt state/anzeige auf einen
# Namen, den niemand findet. Geprueft an einer Kopie des Pakets in einem
# Unterprozess, damit der echte Baum und die uebrigen Tests unberuehrt bleiben.
import shutil
import subprocess
with tempfile.TemporaryDirectory() as d:
    kopie = Path(d) / "chimera"
    kopie.mkdir()
    (kopie / "__init__.py").write_text("")
    shutil.copytree(SRC / "chimera/displays",
                    kopie / "displays")
    falsch = kopie / "displays" / "falsch"
    falsch.mkdir()
    (falsch / "display.json").write_text(json.dumps({
        "typ": "anders", "name": "x", "breite": 1, "hoehe": 1, "farben": "mono",
        "bildrate": 0, "darstellung": "standbild"}))
    (falsch / "panel.py").write_text("")
    r = subprocess.run(
        [sys.executable, "-c",
         "import logging, sys; logging.basicConfig(stream=sys.stderr, level=logging.WARNING)\n"
         "from chimera.displays import registry\n"
         "print(','.join(registry.typen()), '|', ','.join(sorted(registry.profile())))"],
        env=dict(os.environ, PYTHONPATH=d), capture_output=True, text=True)
    ordner, _, profile = r.stdout.strip().partition("|")
    check("falscher typ: Ordner wird gesehen", "falsch" in ordner, True)
    check("falscher typ: Modul uebersprungen", "falsch" in profile or "anders" in profile, False)
    check("falscher typ: wird benannt", "falsch" in r.stderr and "typ=" in r.stderr, True)

print("== Erkennung: Klassen entscheiden, nicht Reihenfolge ==")
erk, _ = neu_laden()

# 1. Whisplay vollstaendig: Kennung (pflicht) + Codec (eindeutig)
with Umgebung(**{"st7789-dc27": "8181b3", "i2c-1-1a": "1"}):
    erk, _ = neu_laden()
    b = erk.erkennen()
    check("Whisplay: gewaehlt", b.gewaehlt, "whisplay")
    check("Whisplay: Grund", b.grund, "eindeutiger Treffer")

# 2. GamePi13-Fall: Kennung ja, Codec nein -> einziger Kandidat, aber
#    gemeldet. (Mit nur einem ST7789-Modul im Baum ist „whisplay ohne
#    Codec" genau dieser Fall.)
with Umgebung(**{"st7789-dc27": "8181b3", "i2c-1-1a": "0", "i2c-1-10": "0"}):
    erk, _ = neu_laden()
    b = erk.erkennen()
    check("ohne Codec: trotzdem gewaehlt", b.gewaehlt, "whisplay")
    check("ohne Codec: Grund benennt es", b.grund, "einziger Kandidat (Pflicht erfüllt)")

# 3. Kennung falsch -> Pflicht verletzt -> Rueckfall „keine"
with Umgebung(**{"st7789-dc27": "000000", "i2c-1-1a": "1"}):
    erk, _ = neu_laden()
    b = erk.erkennen()
    check("falsche Kennung: Rueckfall", b.gewaehlt, "keine")
    check("falsche Kennung: kein Kandidat", b.kandidaten, [])

# 4. Kennung nicht lesbar (leere Attrappe = „keine Antwort") und kein
#    Codec -> nichts entschieden, aber auch nicht geraten.
with Umgebung(**{"st7789-dc27": "", "i2c-1-1a": "0", "i2c-1-10": "0"}):
    erk, _ = neu_laden()
    b = erk.erkennen()
    check("nicht lesbar: Rueckfall statt Rateschluss", b.gewaehlt, "keine")
    belege = [x for x in b.belege if x.art == "st7789_kennung"]
    check("nicht lesbar: als nicht pruefbar vermerkt", belege[0].treffer, None)

# 5. „eingerichtet" waehlt NICHT (smilez, 11.10.): ALSA-Karte und Overlay
#    da (Karte war mal in einer Whisplay), Kennung aber nicht pruefbar und
#    kein Codec -> trotzdem keine Whisplay. Bewusst „nicht pruefbar" statt
#    „falsch": bei falscher Kennung scheitert schon die Pflicht, und ob
#    eingerichtet waehlen wuerde, kaeme gar nicht zur Entscheidung.
with Umgebung(**{"st7789-dc27": "", "i2c-1-1a": "0", "i2c-1-10": "0"}) as wurzel:
    (wurzel / "proc/asound").mkdir(parents=True)
    (wurzel / "proc/asound/cards").write_text(" 0 [whisplaysound ]: whisplaysound\n")
    (wurzel / "boot/firmware").mkdir(parents=True)
    (wurzel / "boot/firmware/config.txt").write_text("dtoverlay=whisplay-soundcard\n")
    erk, _ = neu_laden()
    b = erk.erkennen()
    check("eingerichtet waehlt nicht", b.gewaehlt, "keine")
    eingerichtet = [x.treffer for x in b.belege
                    if x.typ == "whisplay" and x.klasse == "eingerichtet"]
    check("eingerichtet: ALSA und Overlay trafen", eingerichtet.count(True), 2)

# 6. CHIMERA_ANZEIGE sticht die Erkennung -- und ein unbekannter Wert
#    waehlt nichts, statt das naechstbeste zu nehmen (Regel 10g).
with Umgebung(**{"st7789-dc27": "000000"}):
    erk, _ = neu_laden()
    b = erk.erkennen("whisplay")
    check("Einstellung sticht", (b.gewaehlt, b.einstellung), ("whisplay", "whisplay"))
    b2 = erk.erkennen("quatsch")
    check("unbekannte Einstellung waehlt nichts", b2.gewaehlt, None)
    check("unbekannte Einstellung nennt die bekannten", "whisplay" in b2.grund, True)

# 7. Befund als JSON -- das liest der Installer (Schritt 40).
with Umgebung(**{"st7789-dc27": "8181b3", "i2c-1-1a": "1"}):
    erk, _ = neu_laden()
    d = json.loads(erk.erkennen().als_json())
    check("JSON: gewaehlt", d["gewaehlt"], "whisplay")
    check("JSON: Belege mit Text", all(x["text"] for x in d["belege"]), True)
    check("JSON: rc-taugliches Feld belegt", d["belegt"], [])

print("== Fassade: display.panel folgt der Einstellung, erkennt nicht ==")

def fassade():
    for name in [n for n in list(sys.modules) if n.startswith("chimera.display")]:
        del sys.modules[name]
    from chimera.display import panel as modul
    return modul

with Umgebung():
    # a) nichts eingestellt -> blind, und zwar mit benanntem Grund
    m = fassade()
    p = m.open_panel()
    check("ohne Einstellung: NullPanel", type(p).__name__, "NullPanel")
    check("ohne Einstellung: kein falscher Defekt-Hinweis", p.hinweis, "")

    # b) state/anzeige wird gelesen (das schreibt Schritt 40)
    with Umgebung() as wurzel:
        (wurzel / "opt/chimera/state").mkdir(parents=True)
        (wurzel / "opt/chimera/state/anzeige").write_text("keine\n")
        m = fassade()
        p = m.open_panel()
        check("state/anzeige: Modul geoeffnet", getattr(p.profil, "typ", None), "keine")

    # c) Einstellung zeigt auf ein Modul, das sich nicht oeffnen laesst
    #    (whisplay ohne Hardware) -> blind, aber MIT Grund
    with Umgebung() as wurzel:
        (wurzel / "opt/chimera/state").mkdir(parents=True)
        (wurzel / "opt/chimera/state/anzeige").write_text("whisplay\n")
        m = fassade()
        p = m.open_panel()
        check("defekte Anzeige: NullPanel", type(p).__name__, "NullPanel")
        check("defekte Anzeige: Grund steht da", bool(p.hinweis), True)
        check("defekte Anzeige: Grund nennt den Typ", "whisplay" in p.hinweis, True)

    # d) ausdruecklich verlangtes Modul darf NICHT stillschweigend
    #    zum NullPanel werden -- das versteckte den Defekt
    m = fassade()
    try:
        m.open_panel("whisplay")
        bad("ausdruecklich verlangtes Modul: Fehler schlaegt durch — kam stattdessen ein Panel zurueck")
    except Exception:
        ok("ausdruecklich verlangtes Modul: Fehler schlaegt durch")

    # e) CHIMERA_ANZEIGE sticht state/anzeige
    with Umgebung() as wurzel:
        (wurzel / "opt/chimera/state").mkdir(parents=True)
        (wurzel / "opt/chimera/state/anzeige").write_text("whisplay\n")
        os.environ["CHIMERA_ANZEIGE"] = "keine"
        m = fassade()
        p = m.open_panel()
        check("CHIMERA_ANZEIGE sticht state/anzeige", getattr(p.profil, "typ", None), "keine")
        os.environ.pop("CHIMERA_ANZEIGE", None)

    # f) Die Fassade exportiert weiter, was app.py und die Tests importieren
    m = fassade()
    for name in ("NullPanel", "Panel", "to_rgb565", "open_panel"):
        check(f"Fassade exportiert {name}", hasattr(m, name), True)

print()
print(f"Ergebnis: {PASS} ok, {FAIL} fehlgeschlagen")
sys.exit(1 if FAIL else 0)
