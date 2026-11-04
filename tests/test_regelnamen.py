"""Regelnamen (DESIGN: Regel "Sprechende Namen").

Eine Regel in docs/DESIGN.md heisst nach dem, was sie sagt, nicht nach einer
Nummer. Die Nummern, die es schon gab, stehen als Altbestand in ALTBESTAND; sie
werden schrittweise umbenannt und verlassen dabei die Liste.

* Eine Ueberschrift "### Architekturregel <Nummer>" mit einer Nummer, die nicht
  im Altbestand steht, macht den Test rot (keine neuen Nummern).
* Ein Eintrag im Altbestand, den es als Ueberschrift nicht mehr gibt, macht ihn
  ebenfalls rot (die Liste muss mit der Umbenennung kuerzer werden).
* Das Verzeichnis am Ende von DESIGN fuehrt nur Regeln, die es als
  Ueberschrift gibt.

Gegenprobe: `python3 tests/gegenprobe_regelnamen.py`.
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DESIGN = ROOT / "docs" / "DESIGN.md"

ALTBESTAND = [
    '1',
    '1a',
    '2',
    '3a',
    '3b',
    '4a',
    '4b',
    '4c',
    '5',
    '5a',
    '5b',
    '5h',
    '5c',
    '5d',
    '5i',
    '5s',
    '5e',
    '5f',
    '5g',
    '5j',
    '5n',
    '5k',
    '5l',
    '5m',
    '5t',
    '5u',
    '5v',
    '5o',
    '5p',
    '5q',
    '5r',
    '6',
    '6b',
    '6c',
    '6d',
    '6e',
    '7',
    '7c',
    '7d',
    '7a',
    '7b',
    '8',
    '8b',
    '8c',
    '8d',
    '8e',
    '8f',
    '8g',
    '8h',
    '8a',
    '9',
    '10',
    '10a',
    '10b',
    '10k',
    '10c',
    '10d',
    '10i',
    '10j',
    '10e',
    '10f',
    '10g',
    '10h',
    '10l',
    '10n',
    '10o',
    '10m',
    '10p',
    '10q',
    '10r',
    '10s',
    '10u',
    '13',
    '13a',
    '14',
    '15',
]

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
    ok(m) if got == want else bad(f"{m} -- erwartet {want!r}, bekam {got!r}")


def nummern(text):
    return re.findall(r"^#{3,4} Architekturregel (\S+) \u2014", text, re.M)


def pruefen(text, altbestand):
    gefunden = nummern(text)
    neu = sorted(set(gefunden) - set(altbestand))
    weg = sorted(set(altbestand) - set(gefunden))
    return neu, weg


if __name__ == "__main__":
    print("== Regelnamen ==")
    text = DESIGN.read_text(encoding="utf-8")
    neu, weg = pruefen(text, ALTBESTAND)
    check("keine neue nummerierte Regel", neu, [])
    check("kein Eintrag im Altbestand ohne Ueberschrift (umbenannt? dann aus der Liste nehmen)", weg, [])
    check("Altbestand ohne Doppelte", len(ALTBESTAND), len(set(ALTBESTAND)))
    check("Regel 'Sprechende Namen' steht in DESIGN", "### Regel \u201eSprechende Namen\u201c" in text, True)
    verz = text.split("## Verzeichnis der Architekturregeln", 1)[-1]
    ohne_ueberschrift = [m for m in re.findall(r"^- \*\*([0-9]+[a-z]?)\*\* \u2014", verz, re.M) if m not in set(nummern(text))]
    check("Verzeichnis nennt keine Nummer ohne Ueberschrift", ohne_ueberschrift, [])
    print(f"\nErgebnis: {PASS} ok, {FAIL} fehlgeschlagen")
    sys.exit(1 if FAIL else 0)
