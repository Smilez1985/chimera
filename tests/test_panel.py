"""Tests für die Bildausgabe. Ohne Panel lauffähig."""
import sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from PIL import Image  # noqa: E402
from chimera.display.panel import NullPanel, to_rgb565, open_panel  # noqa: E402

PASS = FAIL = 0
def ok(m):
    global PASS; PASS += 1; print(f"  ok    {m}")
def bad(m):
    global FAIL; FAIL += 1; print(f"  FAIL  {m}")
def check(m, got, want):
    ok(m) if got == want else bad(f"{m} — erwartet {want!r}, bekam {got!r}")

print("== RGB565 ==")
img = Image.new("RGB", (240, 280), (30, 180, 220))
data = to_rgb565(img)
check("zwei Byte je Bildpunkt", len(data), 240 * 280 * 2)

# Bekannte Werte: Weiss, Schwarz, reines Rot.
check("weiss",   to_rgb565(Image.new("RGB", (1, 1), (255, 255, 255))), b"\xff\xff")
check("schwarz", to_rgb565(Image.new("RGB", (1, 1), (0, 0, 0))),       b"\x00\x00")
check("rot",     to_rgb565(Image.new("RGB", (1, 1), (255, 0, 0))),     b"\xf8\x00")

# Gegenprobe: die bildpunktweise Fassung des Herstellers muss dasselbe
# liefern. Sonst misst der schnelle Weg etwas anderes als das Panel zeigt.
def naiv(im):
    out = bytearray()
    for r, g, b in im.convert("RGB").getdata():
        v = ((r & 0xF8) << 8) | ((g & 0xFC) << 3) | (b >> 3)
        out += bytes(((v >> 8) & 0xFF, v & 0xFF))
    return bytes(out)

probe = Image.new("RGB", (16, 16))
probe.putdata([((x * 16) % 256, (y * 16) % 256, (x * y) % 256)
               for y in range(16) for x in range(16)])
check("gleich wie bildpunktweise", to_rgb565(probe), naiv(probe))

print("== Panel ==")
p = NullPanel()
p.show(Image.new("RGB", (240, 280), (0, 0, 0)))
check("Bild gezählt", p.frames, 1)
check("Daten vorhanden", len(p.last or b""), 240 * 280 * 2)

try:
    p.show(Image.new("RGB", (240, 240)))
    bad("falsche Bildgröße hätte auffallen müssen")
except ValueError:
    ok("falsche Bildgröße wird gemeldet, nicht stillschweigend skaliert")

check("auto ohne Gerät", type(open_panel("auto")).__name__, "NullPanel")

# Die Einstellung haengt NICHT am Arbeitsverzeichnis (am Geraet 12.11.2026:
# der Installer-Zeichner startete aus /tmp und sah state/anzeige nie).
import os, tempfile  # noqa: E402
from pathlib import Path  # noqa: E402
from chimera.display.panel import _einstellung  # noqa: E402

_alt_cwd = os.getcwd()
_alt_env = {k: os.environ.get(k) for k in ("CHIMERA_ROOT", "CHIMERA_ANZEIGE")}
try:
    os.environ.pop("CHIMERA_ANZEIGE", None)
    os.environ.pop("CHIMERA_ROOT", None)
    with tempfile.TemporaryDirectory() as td:
        (Path(td) / "opt/chimera/state").mkdir(parents=True)
        os.chdir(td)
        typ, quelle = _einstellung()
        check("ohne CHIMERA_ROOT gilt / -- nicht das Arbeitsverzeichnis", typ, None)
        check("und der Grund nennt den Pfad", str(quelle).startswith("/opt/chimera/state/anzeige"), True)
        # Mit erfundener Wurzel (Tests) gilt die Wurzel.
        os.environ["CHIMERA_ROOT"] = td
        (Path(td) / "opt/chimera/state/anzeige").write_text("whisplay\n")
        check("CHIMERA_ROOT wird geehrt", _einstellung(), ("whisplay", "state/anzeige"))
finally:
    os.chdir(_alt_cwd)
    for k, v in _alt_env.items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v

print("== Tempo ==")
p2 = NullPanel()
frame = Image.new("RGB", (240, 280), (30, 180, 220))
t = time.perf_counter()
for _ in range(20):
    p2.show(frame)
ms = (time.perf_counter() - t) / 20 * 1000
budget = 1000 / 15
ok(f"Umrechnung {ms:.1f} ms je Bild (Budget {budget:.0f} ms, hier schnellere Hardware als der Pi)")
ok("deutlich unter dem Budget") if ms < budget / 4 else bad(f"zu langsam: {ms:.1f} ms")


print("== LED-Taktfrequenz kommt aus der Anzeigebeschreibung ==")
from chimera.displays.base import Profil  # noqa: E402
import json as _json, tempfile as _tf, os as _os  # noqa: E402
_basis = {"typ": "x", "name": "x", "breite": 240, "hoehe": 280,
          "farben": "rgb565", "bildrate": 15, "darstellung": "animiert"}
with _tf.NamedTemporaryFile("w", suffix=".json", delete=False) as _f:
    _json.dump(dict(_basis), _f)
    _pfad_ohne = _f.name
with _tf.NamedTemporaryFile("w", suffix=".json", delete=False) as _f:
    _json.dump(dict(_basis, led_frequenz_hz=60), _f)
    _pfad_mit = _f.name
try:
    check("ohne Angabe: 100 Hz", Profil.aus_datei(Path(_pfad_ohne)).led_frequenz_hz, 100.0)
    check("mit Angabe: 60 Hz", Profil.aus_datei(Path(_pfad_mit)).led_frequenz_hz, 60.0)
    _w = Profil.aus_datei(Path(__file__).resolve().parent.parent /
                          "src/chimera/displays/whisplay/display.json")
    check("Whisplay sagt 60 Hz", _w.led_frequenz_hz, 60.0)
finally:
    _os.unlink(_pfad_ohne); _os.unlink(_pfad_mit)

print()
print(f"Ergebnis: {PASS} ok, {FAIL} fehlgeschlagen")
sys.exit(1 if FAIL else 0)
