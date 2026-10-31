"""docs/CLI.md gegen die echten Programme.

Zwei Richtungen, beide Pflicht:
  1. Was das Programm in --help nennt, muss in CLI.md stehen.
  2. Was CLI.md als Option nennt (ohne Marke "geplant / planned"), muss das
     Programm kennen.
Gegenprobe: ``--gegenprobe`` entfernt eine Option aus der Doku; der Test
muss dann rot werden.
"""
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
GEGENPROBE = "--gegenprobe" in sys.argv
PASS = FAIL = 0
def ok(m):
    global PASS; PASS += 1; print(f"  ok    {m}")
def bad(m):
    global FAIL; FAIL += 1; print(f"  FAIL  {m}")

doku = (ROOT / "docs" / "CLI.md").read_text(encoding="utf-8")
if GEGENPROBE:
    doku = doku.replace("`--offline`", "`--xxx`").replace("`--ruhig`", "`--yyy`")

def abschnitt(titel_re):
    """Text von der Überschrift bis zur nächsten gleich- oder höherrangigen."""
    m = re.search(rf"^(#+) {titel_re}.*$", doku, re.M)
    assert m, f"Abschnitt {titel_re} fehlt in CLI.md"
    ebene = len(m.group(1))
    rest = doku[m.end():]
    n = re.search(rf"^#{{1,{ebene}}} ", rest, re.M)
    return rest[: n.start()] if n else rest

def optionen_der_doku(text):
    """Optionen aus Tabellenzeilen; Zeilen mit 'geplant / planned' zählen nicht."""
    out = set()
    for zeile in text.splitlines():
        if not zeile.startswith("|") or "geplant / planned" in zeile:
            continue
        zelle = zeile.split("|")[1]
        for code in re.findall(r"`([^`]+)`", zelle):
            for opt in re.findall(r"(?<![\w-])(--?[A-Za-z][\w-]*)", code):
                out.add(opt)
    return out

def optionen_der_hilfe(text):
    return set(re.findall(r"(?<![\w-])(--?[A-Za-z][\w-]*)", text))

def lauf(cmd, env=None):
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=60,
                       cwd=ROOT, env=env)
    return r.stdout + r.stderr

import os
env = dict(os.environ, PYTHONPATH=str(ROOT / "src"))

# (Anzeigename, Abschnittsüberschrift, Hilfeaufruf, Optionen die in --help nur
#  als Beispiel/Text stehen und nicht zählen)
faelle = [
    ("chimera", r"`chimera`$", [sys.executable, "-m", "chimera", "--help"], set()),
    ("chimera-install", r"`chimera-install`", ["sh", "installer/chimera-install", "--help"], set()),
    ("chimera-uninstall", r"`chimera-uninstall`", ["sh", "uninstaller/chimera-uninstall", "--help"], set()),
]
tor = ROOT / "rust" / "target" / "release" / "chimera-tor"
for kand in (Path("/root/chimera-target/release/chimera-tor"), tor,
             Path("/root/chimera-target/debug/chimera-tor")):
    if kand.exists():
        faelle.append(("chimera-tor", r"`chimera-tor`", [str(kand), "--help"], set()))
        break
else:
    print("  (chimera-tor nicht gebaut -- Gateway-Abschnitt nur einseitig geprüft)")

print("== Hilfe -> Doku, Doku -> Hilfe ==")
for name, titel, cmd, ignor in faelle:
    h = optionen_der_hilfe(lauf(cmd, env)) - {"-h", "--help"} - ignor
    d = optionen_der_doku(abschnitt(titel)) - {"-h", "--help"}
    fehlt_in_doku = sorted(h - d)
    fehlt_im_prog = sorted(d - h)
    (ok if not fehlt_in_doku else bad)(
        f"{name}: alle Optionen der Hilfe stehen in CLI.md"
        + (f" -- fehlt: {fehlt_in_doku}" if fehlt_in_doku else ""))
    (ok if not fehlt_im_prog else bad)(
        f"{name}: CLI.md nennt nur Optionen, die es gibt"
        + (f" -- unbekannt: {fehlt_im_prog}" if fehlt_im_prog else ""))

print("== Anzeige-Werkzeug ==")
hilfe = lauf([sys.executable, "-m", "chimera.displays", "--help"], env)
befehle = set(re.findall(r"^\s{4}([a-z]+)\b", hilfe, re.M))
d = abschnitt(r"`python3 -m chimera.displays`")
dbefehle = {m for z in d.splitlines() if z.startswith("|")
            for m in re.findall(r"`([a-z]+)\b", z.split("|")[1])}
dbefehle -= {"python3"}
(ok if befehle <= dbefehle else bad)(f"displays: alle Befehle dokumentiert -- fehlt: {sorted(befehle - dbefehle)}")
(ok if dbefehle <= befehle else bad)(f"displays: nur echte Befehle -- unbekannt: {sorted(dbefehle - befehle)}")

print("== Betrieb ==")
src = (ROOT / "installer" / "bin" / "log-abgleich.sh").read_text()
echt = set(re.findall(r"--[a-z]+", src))
doc = optionen_der_doku(abschnitt(r"`installer/bin/log-abgleich.sh`"))
(ok if echt <= doc else bad)(f"log-abgleich: Optionen dokumentiert -- fehlt: {sorted(echt - doc)}")
(ok if doc <= echt else bad)(f"log-abgleich: nur echte Optionen -- unbekannt: {sorted(doc - echt)}")

print("== Umgebungsvariablen ==")
envdoku = set(re.findall(r"`((?:CHIMERA|OLLAMA|ANTHROPIC)_[A-Z_]+)`", abschnitt(r"7\. Umgebungsvariablen")))
beispiel = set(re.findall(r"^([A-Z][A-Z_]+)=", (ROOT / ".env.example").read_text(), re.M))
(ok if beispiel <= envdoku else bad)(f".env.example: jede Variable steht in CLI.md -- fehlt: {sorted(beispiel - envdoku)}")

print("== Verweise ==")
for datei in ("tools/check-globals.py", "tools/contact-sheet.py", "tools/import-noisy-moods.py",
              "installer/run-tests.sh", "rust/gegenprobe-web.sh", "rust/gegenprobe-telegram.sh"):
    (ok if (ROOT / datei).exists() and datei in doku else bad)(f"{datei}: existiert und ist genannt")

print(f"\nErgebnis: {PASS} ok, {FAIL} fehlgeschlagen")
sys.exit(1 if FAIL else 0)
