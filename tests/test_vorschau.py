"""Vorschau ohne Gerät: einen Ausdruck als Bild prüfen.

Zwei Dinge werden hier geprüft, und das zweite ist der eigentliche Grund für
diesen Test:

1. `tools/vorschau.py` zeichnet in Panelgröße, wiederholbar mit `--seed`, und
   ein Streifen ist genau `bilder × breite` breit.
2. **Erfundene Formen kommen wirklich ins Bild.** Bis 15.11.2026 wurden sie
   geprüft und im Mood abgelegt, aber nie gezeichnet — ein Zeichner ohne
   Aufrufer, und niemand hat es gesehen, weil es keinen Weg gab, das Ergebnis
   ohne Gerät anzusehen. Genau dieser Weg ist jetzt da, und dieser Test hält
   ihn fest: Ein Mood mit einer gelben Ellipse oben rechts muss an dieser
   Stelle auch gelb sein.

Aufruf: python3 tests/test_vorschau.py
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

HIER = Path(__file__).resolve().parent
ROOT = Path(os.environ.get("CHIMERA_ROOT_TEST") or HIER.parent)
sys.path.insert(0, str(ROOT / "src"))

from PIL import Image  # noqa: E402

WERKZEUG = ROOT / "tools" / "vorschau.py"

PASS = 0
FAIL = 0


def check(name, ist, soll) -> None:
    global PASS, FAIL
    if ist == soll:
        PASS += 1
        print(f"  ok    {name}")
    else:
        FAIL += 1
        print(f"  FAIL  {name} -- erwartet {soll!r}, bekam {ist!r}")


def lauf(*args: str, umgebung: dict | None = None) -> subprocess.CompletedProcess:
    env = dict(os.environ, **(umgebung or {}))
    return subprocess.run([sys.executable, str(WERKZEUG), *args],
                          capture_output=True, text=True, env=env, timeout=120)


def main() -> int:
    print("=== Vorschau ohne Gerät ===")
    tmp = Path(tempfile.mkdtemp(prefix="vorschau-"))

    # --- Ein Bild in Panelgröße ---
    ziel = tmp / "eins.png"
    p = lauf("--mood", "ROCK", "--out", str(ziel), "--seed", "1",
             umgebung={"CHIMERA_HOME": str(tmp / "home")})
    check("Lauf ohne Fehler", p.returncode, 0)
    check("Datei geschrieben", ziel.is_file(), True)
    bild = Image.open(ziel)
    check("Größe ist Panelgröße", bild.size, (240, 280))
    # Ein leeres Bild wäre auch „richtig groß" — es muss Inhalt haben.
    check("Bild ist nicht schwarz", bild.convert("L").getextrema()[1] > 40, True)

    # Andere Fläche, andere Größe (Regel 6c: das Panel ist eine Eigenschaft).
    # Ohne diesen Fall wäre „Größe kommt aus dem Aufruf" nur eine Behauptung.
    klein = tmp / "klein.png"
    p = lauf("--mood", "CHILL", "--breite", "240", "--hoehe", "240",
             "--out", str(klein), umgebung={"CHIMERA_HOME": str(tmp / "home")})
    check("240x240: Lauf ohne Fehler", p.returncode, 0)
    check("240x240 wird auch so gezeichnet", Image.open(klein).size, (240, 240))

    # --- Wiederholbar mit --seed ---
    ziel2 = tmp / "zwei.png"
    lauf("--mood", "ROCK", "--out", str(ziel2), "--seed", "1",
         umgebung={"CHIMERA_HOME": str(tmp / "home")})
    check("gleicher Seed, gleiches Bild",
          ziel.read_bytes() == ziel2.read_bytes(), True)
    # Ob zwei Seeds verschiedene Bilder ergeben, haengt am Ausdruck: Ein
    # Standbild ohne Partikel wuerfelt nicht. Geprueft wird deshalb an einem
    # Ausdruck MIT Partikeln ueber mehrere Bilder — dort muss der Seed wirken,
    # sonst waere "--seed" nur ein Wort in der Hilfe.
    for s in ("1", "2"):
        lauf("--mood", "PARTY", "--bilder", "8", "--abstand", "0.3",
             "--seed", s, "--out", str(tmp / f"party{s}.png"),
             umgebung={"CHIMERA_HOME": str(tmp / "home")})
    check("anderer Seed, anderes Bild (Partikel)",
          (tmp / "party1.png").read_bytes() != (tmp / "party2.png").read_bytes(),
          True)
    for n in ("a", "b"):
        lauf("--mood", "PARTY", "--bilder", "8", "--abstand", "0.3",
             "--seed", "1", "--out", str(tmp / f"party_{n}.png"),
             umgebung={"CHIMERA_HOME": str(tmp / "home")})
    check("gleicher Seed, zweimal gezeichnet, gleiches Bild",
          (tmp / "party_a.png").read_bytes() == (tmp / "party_b.png").read_bytes(),
          True)
    check("und verschieden vom anderen Seed",
          (tmp / "party_a.png").read_bytes() != (tmp / "party2.png").read_bytes(),
          True)

    # --- Streifen ---
    streifen = tmp / "streifen.png"
    p = lauf("--mood", "CHILL", "--bilder", "4", "--out", str(streifen),
             "--seed", "1", umgebung={"CHIMERA_HOME": str(tmp / "home")})
    check("Streifen: Lauf ohne Fehler", p.returncode, 0)
    check("Streifen ist 4 Bilder breit", Image.open(streifen).size, (960, 280))
    p = lauf("--mood", "CHILL", "--bilder", "0", "--out", str(tmp / "x.png"),
             umgebung={"CHIMERA_HOME": str(tmp / "home")})
    check("--bilder 0 wird abgelehnt", p.returncode, 1)
    check("und schreibt nichts", (tmp / "x.png").exists(), False)

    # --- Unbekannter Name: Grund statt Absturz ---
    p = lauf("--mood", "gibtsnicht", "--out", str(tmp / "nein.png"),
             umgebung={"CHIMERA_HOME": str(tmp / "home")})
    check("unbekannter Ausdruck: rc 1", p.returncode, 1)
    check("Grund nennt den Namen", "gibtsnicht" in p.stderr, True)
    check("keine Datei bei Fehler", (tmp / "nein.png").exists(), False)

    # --- Kaputte Datei: geprüft, nicht geraten ---
    kaputt = tmp / "kaputt.json"
    kaputt.write_text("{ das ist kein json")
    p = lauf("--datei", str(kaputt), "--out", str(tmp / "k.png"),
             umgebung={"CHIMERA_HOME": str(tmp / "home")})
    check("kaputte Datei: rc 1", p.returncode, 1)
    check("Grund nennt JSON", "JSON" in p.stderr, True)

    # --- Der eigentliche Punkt: erfundene Formen sind sichtbar ---
    ohne = tmp / "ohne.json"
    ohne.write_text(json.dumps({"name": "OHNE"}))
    mit = tmp / "mit.json"
    mit.write_text(json.dumps({
        "name": "MIT",
        "shapes": [{"kind": "ellipse", "x": 0.78, "y": 0.22, "w": 0.3, "h": 0.24,
                    "color": [255, 210, 0], "fill": True, "layer": "front"}],
    }))
    b_ohne = tmp / "b_ohne.png"
    b_mit = tmp / "b_mit.png"
    lauf("--datei", str(ohne), "--out", str(b_ohne), "--seed", "1",
         umgebung={"CHIMERA_HOME": str(tmp / "home")})
    lauf("--datei", str(mit), "--out", str(b_mit), "--seed", "1",
         umgebung={"CHIMERA_HOME": str(tmp / "home")})
    check("Form ändert das Bild", b_ohne.read_bytes() != b_mit.read_bytes(), True)
    if b_mit.is_file():
        px = Image.open(b_mit).convert("RGB").getpixel(
            (int(0.78 * 240), int(0.22 * 280)))     # Mitte der Ellipse
        # Gelb, wie im Mood angegeben — nicht „irgendein anderer Pixel".
        check("an der Stelle steht die Formfarbe", px, (255, 210, 0))
    else:
        check("Bild mit Form wurde geschrieben", False, True)

    # --- Man kann auch nachsehen, welche Namen es gibt ---
    p = lauf("--liste", umgebung={"CHIMERA_HOME": str(tmp / "home")})
    check("--liste läuft", p.returncode, 0)
    check("--liste nennt ROCK", "ROCK" in p.stdout, True)

    print(f"\nErgebnis: {PASS} ok, {FAIL} fehlgeschlagen")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
