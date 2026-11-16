"""Gegenprobe zu `tests/test_verdichten.py` (GLOBAL: jeder Regressionstest
braucht eine Gegenprobe, die rot wird).

Jede Zusage des Verdichtens wird in einer **Kopie** des Quellbaums
verfälscht; der Test muss an der erwarteten Stelle rot werden. Der echte
Baum bleibt unberührt (`CHIMERA_SRC` zeigt auf die Kopie).

Warum eine Verfälschung immer den **normalen** Erwartungen widersprechen
muss (Lehre vom 14.11.): Ein Test, der die Mutation nachbaut, ist auch mit
kaputtem Code grün — er prüft dann nur sich selbst.

Aufruf: python3 tests/gegenprobe_verdichten.py
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HIER = Path(__file__).resolve().parent
ROOT = HIER.parent
SRC = ROOT / "src"
TEST = HIER / "test_verdichten.py"

VERD = "chimera/agent/verdichten.py"
ABLAGE = "chimera/ablage.py"
TOOLS = "chimera/agent/tools.py"

# Je Mutation: Name, Datei, Muster, Ersatz, Prüfpunkt in der Testausgabe.
MUTATIONEN = [
    (
        "verweis-verschoben",
        VERD,
        "            a = von + i\n            b = von + i + len(teil) - 1",
        "            a = von + i + 1\n            b = von + i + len(teil)",
        "Kopfzeile nennt den Bereich",
    ),
    (
        "verweis-fehlt",
        VERD,
        '''              "Den vollen Wortlaut holt das Werkzeug nachlesen "''',
        '''              "Den vollen Wortlaut holt das Werkzeug "''',
        "Kopfzeile nennt nachlesen",
    ),
    (
        "offene-punkte-weg",
        VERD,
        "    if punkte:\n        zeilen += [\"\", f\"## Offene Punkte ({len(punkte)}, wörtlich)\"]",
        "    if False:\n        zeilen += [\"\", f\"## Offene Punkte ({len(punkte)}, wörtlich)\"]",
        "Punkt A wörtlich",
    ),
    (
        "entscheidungen-weg",
        VERD,
        "    if entscheide:\n        zeilen += [\"\", f\"## Entscheidungen ({len(entscheide)}, wörtlich)\"]",
        "    if False:\n        zeilen += [\"\", f\"## Entscheidungen ({len(entscheide)}, wörtlich)\"]",
        "Entscheidung wörtlich",
    ),
    (
        "runden-ignoriert",
        VERD,
        "    schnitt = schnittindex(nachrichten, runden)",
        "    schnitt = len(nachrichten)",
        "Bericht meldet die verdichteten Nachrichten",
    ),
    (
        # Der Schnitt muss auf einem Rundenbeginn liegen — sonst zerreißt
        # eine Werkzeugrunde (Papier OPENMINIS-MUSTER §2.3, Punkt 7).
        "schnitt-nach-nachrichten-statt-runden",
        VERD,
        "    schnitt = schnittindex(nachrichten, runden)",
        "    schnitt = max(0, len(nachrichten) - runden)",
        "Schnitt trifft eine echte Runde",
    ),
    (
        # Kein Rundenbeginn mehr erkennbar: Dann bleibt alles wörtlich.
        # Die sichere Richtung muss trotzdem sichtbar sein, sonst merkt
        # niemand, dass der Schnitt nie stattfindet.
        "rundenbeginn-nie-erkannt",
        VERD,
        '''    if m.get("role") != "user":
        return False''',
        '''    return False''',
        "Schnitt liegt im Verlauf",
    ),
    (
        "alter-verweis-geht-verloren",
        VERD,
        "    verweise = fruehere_verweise(kopf)",
        "    verweise = []",
        "neuer Text nennt die frühere Verdichtung",
    ),
    (
        "punkt-zaehlung-falsch",
        VERD,
        "                   len(kopf), len(punkte), len(entscheide), ausgelassen,\n                   schnitt)",
        "                   len(kopf), len(punkte) + 1, len(entscheide), ausgelassen,\n                   schnitt)",
        "Verdichtung zählt beide",
    ),
    (
        "protokoll-vergisst-nachricht",
        ABLAGE,
        '''        self.ablage.anhaengen(eintrag, self.sid)
        super().append(m)''',
        '''        super().append(m)''',
        "erste Nachricht noch da",
    ),
    (
        "fundstelle-nicht-vermerkt",
        ABLAGE,
        '''                               "zeilen_von": zeilen_von,
                               "zeilen_bis": zeilen_bis}, self.sid)''',
        '''                               "zeilen_von": 0,
                               "zeilen_bis": 0}, self.sid)''',
        "Verdichtung vermerkt die Fundstelle",
    ),
    (
        "nachlesen-ohne-grenze",
        TOOLS,
        "NACHLESEN_MAX = 60",
        "NACHLESEN_MAX = 10000",
        "zu großer Bereich wird gekappt",
    ),
    (
        "nachlesen-liest-nichts",
        TOOLS,
        '''            zeilen = self.ablage.lesen_zeilen(self.ablage.aktiv(), a, b)''',
        '''            zeilen = []''',
        "nachlesen liefert den Wortlaut",
    ),
    (
        # Die Marke hat **zwei** Wächter: die Kopfzeile in verdichten.py und
        # ``_mit_marke`` in der Ablage. Eine Mutation muss beide fallen
        # lassen, sonst misst sie nur einen (GLOBAL: Summe gegen Gesamtzahl).
        "verdichten-ohne-marke",
        [
            (VERD,
             '''    kopfzeile = (f"{MARKE} Zeilen {bloecke[0].von}–{bloecke[-1].bis} in "''',
             '''    kopfzeile = (f"Zeilen {bloecke[0].von}–{bloecke[-1].bis} in "'''),
            (ABLAGE,
             '''    return z if z.startswith("[Bisheriges Gespräch") else f"{MARKE}\\n{z}"''',
             '''    return z'''),
        ],
        "Fenster beginnt mit der Verdichtung",
    ),
]


def kopiere(ziel: Path) -> None:
    shutil.copytree(SRC, ziel, dirs_exist_ok=True)


def lauf(cwd: Path) -> tuple[int, str]:
    env = dict(os.environ, CHIMERA_SRC=str(cwd), PYTHONDONTWRITEBYTECODE="1")
    r = subprocess.run([sys.executable, str(TEST)], cwd=str(HIER),
                       env=env, capture_output=True, text=True, timeout=300)
    return r.returncode, r.stdout + r.stderr


def main() -> int:
    if not TEST.exists():
        print(f"FEHLT: {TEST}")
        return 2

    print("== Grundlauf (unverfälscht) muss grün sein")
    rc, out = lauf(SRC)
    if rc != 0:
        print(out[-2000:])
        print("ABBRUCH: Der unverfälschte Lauf ist schon rot — dann misst "
              "keine Mutation etwas.")
        return 2
    print("  ok    grün (rc=0)")

    gut = schlecht = 0
    for eintrag in MUTATIONEN:
        # Zwei Formen: (name, datei, alt, neu, punkt) — oder bei Zusagen mit
        # zwei Wächtern (name, [(datei, alt, neu), …], punkt).
        if len(eintrag) == 5:
            name, datei, alt, neu, punkt = eintrag
            teile = [(datei, alt, neu)]
        else:
            name, teile, punkt = eintrag
        td = Path(tempfile.mkdtemp(prefix="gegenprobe-verd-"))
        baum = td / "src"
        kopiere(baum)
        fehlt = False
        for d, a, n in teile:
            ziel = baum / d
            text = ziel.read_text(encoding="utf-8")
            if a not in text:
                print(f"  FAIL  {name}: Muster steht nicht in {d} — "
                      "Mutation wirkt nicht (Test prüft die Stelle dann nicht)")
                fehlt = True
                break
            ziel.write_text(text.replace(a, n, 1), encoding="utf-8")
        if fehlt:
            schlecht += 1
            shutil.rmtree(td, ignore_errors=True)
            continue
        rc, out = lauf(baum)
        getroffen = re.search(r"FAIL\s+" + re.escape(punkt), out) is not None
        if rc != 0 and getroffen:
            print(f"  ok    {name} → rot an „{punkt}“")
            gut += 1
        else:
            print(f"  FAIL  {name}: nicht rot an „{punkt}“ (rc={rc})")
            for z in out.splitlines():
                if "FAIL" in z:
                    print("        " + z.strip())
            schlecht += 1
        shutil.rmtree(td, ignore_errors=True)

    print()
    print(f"Gegenprobe: {gut}/{len(MUTATIONEN)} rot, {schlecht} grün geblieben")
    return 0 if schlecht == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
