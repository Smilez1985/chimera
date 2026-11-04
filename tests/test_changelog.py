"""CHANGELOG.md gegen die Projektregeln (Keep a Changelog, ohne Unreleased).

Warum ein eigener Waechter: Die Datei hat sich zweimal unbemerkt zerlegt --
ein doppelter Abschnitt ("### Hinzugefuegt" nach "### Entfernt") und zwei
Bullets, die ohne Ueberschrift direkt nach dem Vorspann standen. Beides faellt
beim Lesen nicht auf, beim Auswerten (Release-Notizen, Abgleich Changelog ->
Modul, docs/INSTALLER.md `docs/INSTALLER.md`, Abschnitt „Was welches Modul aus dem Changelog einspielt") sehr wohl.

Geprueft wird der TEXT, nicht die Datei -- damit die Gegenprobe mit einer
veraenderten Kopie arbeiten kann, statt die echte Datei anzufassen.

Aufruf:  python3 tests/test_changelog.py [--gegenprobe]
Exitcode 0 = in Ordnung, 1 = Befund.
"""
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
# Uebersteuerbar, damit sich der Waechter gegen eine Kopie richten laesst
# (Beleg: der alte, kaputte Stand wird rot).
DATEI = Path(os.environ.get("CHIMELOG_DATEI") or (ROOT / "CHANGELOG.md"))
# Die Roadmap wird mitgeprueft: sie darf keine Haken tragen.
ROADMAP = Path(os.environ.get("CHIMERA_ROADMAP") or (ROOT / "docs/ROADMAP.md"))
GEGENPROBE = "--gegenprobe" in sys.argv
PASS = FAIL = 0


def ok(m):
    global PASS
    PASS += 1
    print(f"  ok    {m}")


def bad(m):
    global FAIL
    FAIL += 1
    print(f"  FAIL  {m}")


# Keep a Changelog, deutsche Fassung; das Projekt hat "Bekannte
# Einschraenkungen" und "Geprueft" ergaenzt (Abschnitt "Abweichungen" im Kopf).
ERLAUBT = ["Hinzugefügt", "Geändert", "Veraltet", "Entfernt", "Behoben",
           "Sicherheit", "Bekannte Einschränkungen", "Geprüft"]
VORSPANN_ERLAUBT = re.compile(r"^(#|\*\*|>|\s*$|Alles hier Genannte|zählt als)")


def pruefe(text):
    """Alle Verstoesse als Liste von Texten (leer = in Ordnung)."""
    fehler = []

    # 1. Versionskopf
    if not re.search(r"^## \[[^\]]+\]", text, re.M):
        fehler.append("kein Versionskopf '## [x.y.z]'")
    # 2. kein Unreleased (Projektregel: offen ist die ROADMAP)
    if re.search(r"^## *\[?Unreleased", text, re.M | re.I):
        fehler.append("Unreleased-Block (gehoert in docs/ROADMAP.md)")

    zeilen = text.split("\n")
    gesehen = []
    aktuell = None
    bullets_je_abschnitt = {}
    vor_erstem_abschnitt = []

    for nr, z in enumerate(zeilen, 1):
        if z.startswith("### "):
            name = z[4:].strip()
            if name not in ERLAUBT:
                fehler.append(f"Zeile {nr}: unbekannter Abschnitt '{name}'")
            if name in gesehen:
                fehler.append(f"Zeile {nr}: Abschnitt '{name}' kommt doppelt")
            else:
                gesehen.append(name)
            aktuell = name
            bullets_je_abschnitt.setdefault(name, 0)
            continue
        if z.startswith("## "):
            aktuell = None
            continue
        if z.startswith("- "):
            if aktuell is None:
                vor_erstem_abschnitt.append(nr)
            else:
                bullets_je_abschnitt[aktuell] += 1
        elif aktuell is None and z.strip() and not VORSPANN_ERLAUBT.match(z):
            # Freitext ausserhalb eines Abschnitts: erlaubt nur der Vorspann,
            # und der steht vor dem ersten Bullet.
            if any(x.startswith("- ") for x in zeilen[:nr]):
                fehler.append(f"Zeile {nr}: Text ausserhalb eines Abschnitts")

    if vor_erstem_abschnitt:
        fehler.append("Zeilen %s: Bullets ohne Abschnittsueberschrift"
                      % ", ".join(map(str, vor_erstem_abschnitt)))

    # 4. Reihenfolge wie in der Liste ERLAUBT
    rang = [ERLAUBT.index(n) for n in gesehen if n in ERLAUBT]
    if rang != sorted(rang):
        fehler.append("Abschnitte stehen nicht in der Reihenfolge von Keep a "
                      "Changelog: " + ", ".join(gesehen))

    # 5. Jeder Abschnitt hat Inhalt
    for name, n in bullets_je_abschnitt.items():
        if n == 0:
            fehler.append(f"Abschnitt '{name}' hat keinen einzigen Punkt")

    return fehler


def lauf(text, was):
    fehler = pruefe(text)
    if fehler:
        for f in fehler:
            bad(f"{was}: {f}")
    else:
        ok(was)


def pruefe_roadmap(text):
    """docs/ROADMAP.md enthaelt nur, was aussteht.

    Projektregel: Erledigtes steht im CHANGELOG, die Roadmap traegt keine
    Haken. Anlass: 96 erledigte Punkte sammelten sich dort an, waehrend
    dieselbe Arbeit im Changelog stand -- zwei Staende, die auseinanderliefen.
    """
    fehler = []
    for nr, z in enumerate(text.split("\n"), 1):
        if "[x]" in z.lower():
            fehler.append(f"Zeile {nr}: Haken '[x]' -- Erledigtes gehoert ins "
                          "CHANGELOG")
    if not re.search(r"^## ", text, re.M):
        fehler.append("keine Abschnitte")
    return fehler


print("=== Changelog (Keep a Changelog, ohne Unreleased) ===")

if not DATEI.is_file():
    bad("CHANGELOG.md fehlt")
    print("\nErgebnis: %d ok, %d fehlgeschlagen" % (PASS, FAIL))
    sys.exit(1)

gut = DATEI.read_text(encoding="utf-8")
lauf(gut, "CHANGELOG.md")

if not ROADMAP.is_file():
    bad("docs/ROADMAP.md fehlt")
else:
    roadmap = ROADMAP.read_text(encoding="utf-8")
    fehler = pruefe_roadmap(roadmap)
    if fehler:
        for f in fehler:
            bad("docs/ROADMAP.md: " + f)
    else:
        ok("docs/ROADMAP.md ohne Haken")

if GEGENPROBE:
    # Jede Zusage einmal brechen; der Pruefer MUSS rot werden. Arbeitet auf
    # Kopien im Speicher -- die echte Datei bleibt unberuehrt.
    faelle = []

    faelle.append(("doppelter Abschnitt",
                   gut + "\n### Hinzugefügt\n- nachgetragen\n"))
    faelle.append(("Bullet vor der ersten Ueberschrift",
                   gut.replace("### Hinzugefügt\n", "### Hinzugefügt\n", 1)
                   .replace("\n### ", "\n- verirrt\n\n### ", 1)))
    faelle.append(("Unreleased-Block",
                   gut.replace("## [0.1.0]", "## [Unreleased]\n\n## [0.1.0]", 1)))
    faelle.append(("unbekannter Abschnitt",
                   gut + "\n### Sonstiges\n- etwas\n"))
    faelle.append(("falsche Reihenfolge",
                   gut.replace("### Geändert", "### Veraltet", 1)
                   .replace("### Entfernt", "### Geändert", 1)
                   .replace("### Veraltet", "### Entfernt", 1)))
    faelle.append(("leerer Abschnitt",
                   gut.replace("### Sicherheit", "### Sicherheit", 1)
                   + "\n### Sicherheit\n"))

    for was, text in faelle:
        if text == gut:
            bad(f"Gegenprobe '{was}': Text unveraendert -- Fall greift nicht")
            continue
        if pruefe(text):
            ok(f"Gegenprobe '{was}': rot")
        else:
            bad(f"Gegenprobe '{was}': blieb gruen")

    # Roadmap-Waechter: ein zurueckgekehrter Haken MUSS auffallen.
    if not ROADMAP.is_file():
        bad("Gegenprobe 'Haken in der Roadmap': Roadmap fehlt")
    else:
        text = roadmap + "\n- [x] **alter Punkt**\n"
        if pruefe_roadmap(text):
            ok("Gegenprobe 'Haken in der Roadmap': rot")
        else:
            bad("Gegenprobe 'Haken in der Roadmap': blieb gruen")
        if pruefe_roadmap(roadmap.replace("\n## ", "\n#### ")):
            ok("Gegenprobe 'Roadmap ohne Abschnitte': rot")
        else:
            bad("Gegenprobe 'Roadmap ohne Abschnitte': blieb gruen")

print("\nErgebnis: %d ok, %d fehlgeschlagen" % (PASS, FAIL))
sys.exit(1 if FAIL else 0)
