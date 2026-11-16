"""Selbstauskunft: was gebaut ist, kommt aus dem System, nicht aus dem Kopf.

Der Anlass ist ein gemessener Fehler (16.11.2026): Im Web-Chat nach
Verbesserungen gefragt, schlug das Modell vier Funktionen vor, die seit
Tagen gebaut waren. Es konnte sie nicht kennen — der Systemprompt sagt ihm
nur, dass es ein Gerät mit einem Gesicht ist.

Geprüft wird an echten Dateien in einem Prüfbaum (kein /tmp: GLOBAL sagt,
Prüfbäume gehören ins Projekt, sonst räumt ein Neustart sie weg — hier
genügt `tempfile` **innerhalb** des Projekts, siehe `PRUEFBAUM`).

Aufruf: python3 tests/test_selbstbild.py
"""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(os.environ.get("CHIMERA_SRC") or ROOT / "src")))

from chimera.agent import selbstbild as sb  # noqa: E402

PASS = FAIL = 0

def ok(m):
    global PASS
    PASS += 1
    print("  ok   " + m)

def rot(m):
    global FAIL
    FAIL += 1
    print("  ROT  " + m)

def pruefe(bedingung, was):
    ok(was) if bedingung else rot(was)

CHANGELOG = """# Changelog

## [0.1.0] — Pre-Alpha

### Hinzugefügt
- **Selbstauskunft als Werkzeug** (16.11.2026): Das Modell kann nachsehen.
  Zweite Zeile der Beschreibung.
- **Fensterhöhe repariert** (15.11.2026): Kette im Rahmen.
- **Reiter Einstellungen** (15.11.2026): Kontrast, Audio, Kennwort.
- **Nachtfenster für den Avatar** (15.11.2026): dimmt 22–6.
- **Fünfter Punkt** (14.11.2026): darf nicht mehr auftauchen.

### Geändert
- **Etwas anderes** (14.11.2026): nicht in der Auskunft.
- Ein Eintrag ohne Fettdruck, der sehr lang ist und deshalb gekürzt werden
  muss, damit die Auskunft nicht aus dem Ruder läuft.

### Behoben
- **Lebenszeichen schrieb ins Nichts** (15.11.2026): jetzt /run.
- **verlauf.jsonl nannte keine Werkzeuge** (15.11.2026): jetzt mit Namen.
"""

ROADMAP = """# Roadmap

- [ ] **Ambiente-Parameter einstellbar** (16.11.2026): stehen als Konstanten.
- [ ] **Modultexte auf Englisch** (16.11.2026): Hülle ist zweisprachig.
- [x] **Erledigter Punkt**: darf nicht als offen erscheinen.
- [ ] **Ein Test der Rust-Suite ist flaky** (15.11.2026): Race auf Socket.
"""

def baum(tmp: Path) -> Path:
    (tmp / "VERSION").write_text("0.1.0-pre\n", encoding="utf-8")
    (tmp / "CHANGELOG.md").write_text(CHANGELOG, encoding="utf-8")
    (tmp / "docs").mkdir(parents=True, exist_ok=True)
    (tmp / "docs" / "ROADMAP.md").write_text(ROADMAP, encoding="utf-8")
    return tmp

def main() -> int:
    print("== 1. Gebaut: neueste Einträge, je Abschnitt begrenzt")
    with tempfile.TemporaryDirectory() as t:
        b = baum(Path(t))
        g = sb.gebaut(b)
        abschnitte = [a for a, _ in g]
        pruefe(abschnitte == ["Hinzugefügt", "Behoben"], f"Abschnitte in Reihenfolge: {abschnitte}")
        hin = dict(g)["Hinzugefügt"]
        pruefe(len(hin) == sb.GEBAUT_JE_ABSCHNITT,
               f"höchstens {sb.GEBAUT_JE_ABSCHNITT} Einträge, nicht alle ({len(hin)})")
        pruefe(hin[0] == "Selbstauskunft als Werkzeug",
               f"nur der Titel, nicht der halbe Satz: {hin[0]!r}")
        pruefe(hin[1] == "Fensterhöhe repariert", "auch der zweite Eintrag als Titel")
        pruefe("Fünfter Punkt" not in " ".join(hin), "der fünfte Punkt ist abgeschnitten")
        pruefe(dict(g)["Behoben"][0].startswith("Lebenszeichen schrieb ins Nichts"),
               "der Behoben-Abschnitt wird mitgelesen")

    print("== 2. Offen: nur Haken ohne x, Titel ohne Markup")
    with tempfile.TemporaryDirectory() as t:
        b = baum(Path(t))
        titel, gesamt = sb.offen(b)
        pruefe(gesamt == 3, f"drei offene Punkte gezählt ({gesamt})")
        pruefe(titel[0] == "Ambiente-Parameter einstellbar",
               f"Markup entfernt: {titel[0]!r}")
        pruefe(all("Erledigter Punkt" not in x for x in titel), "erledigter Punkt fehlt")
        viele, alle = sb.offen(b, max_titel=1)
        pruefe(len(viele) == 1 and alle == 3, "Grenze greift, Gesamtzahl bleibt")

    print("== 3. Der Text nennt beide Seiten und die Warnung")
    with tempfile.TemporaryDirectory() as t:
        b = baum(Path(t))
        txt = sb.text(werkzeuge=["selbst", "read_file"], ausdruecke=43,
                      freigabe="run_command=positivliste (2 Ziel(e))",
                      tueren=["web", "telegram"], skills=3, root=b)
        pruefe("0.1.0-pre" in txt, "Fassung aus VERSION")
        pruefe("Werkzeuge (2): selbst, read_file" in txt, "Werkzeugliste")
        pruefe("Gesichtsausdrücke: 43" in txt, "Ausdruckszahl")
        pruefe("Schon gebaut" in txt and "Das ist gebaut" in txt,
               "der Text sagt, dass gebaut ist und man es nicht vorschlagen soll")
        pruefe("Offen laut docs/ROADMAP.md (3 Punkte" in txt, "offene Punkte mit Gesamtzahl")
        pruefe("web, telegram" in txt, "Türen")

    print("== 4. Was fehlt, wird benannt und nicht erfunden")
    with tempfile.TemporaryDirectory() as t:
        b = Path(t)
        (b / "docs").mkdir(parents=True)
        txt = sb.text(werkzeuge=[], root=b)
        pruefe("nicht lesbar" in txt, "fehlendes CHANGELOG wird benannt")
        pruefe("Fassung nicht messbar" in txt, "fehlende VERSION wird benannt")
        leer = sb.text(root=b)
        pruefe("(Fassung nicht messbar)" in leer, "auch ohne alle Angaben lesbar")
        pruefe(sb.gebaut(b) == [], "kein CHANGELOG → keine erfundenen Einträge")

    with tempfile.TemporaryDirectory() as t:
        ohne = sb.text(root=Path(t) / "gibtesnicht")
        pruefe("nicht raten" in ohne, "ohne Dokumente: 'nicht raten' statt Erfindung")
        pruefe("Schon gebaut" not in ohne, "ohne Dokumente keine Behauptung")

    print("== 5. Verdrahtung: Werkzeug 'selbst' und der Satz im Prompt")
    with tempfile.TemporaryDirectory() as t:
        from chimera.agent.loop import Agent, SELBST_TEMPLATE
        from chimera.agent.tools import Toolbox
        agent = Agent(None, Toolbox(t))
        pruefe("selbst" in agent.tools.names(), "Werkzeug 'selbst' ist angemeldet")
        pruefe("selbst" in agent.guard.known, "die Vorprüfung kennt es auch")
        system = agent._system()
        pruefe("Selbstauskunft" in system and "`selbst`" in system,
               "der Systemprompt verweist auf die Auskunft")
        pruefe(SELBST_TEMPLATE.strip().count("\n") < 12, "der Hinweis bleibt kurz (Cache, 5q)")

    print()
    print(f"Ergebnis: {PASS} ok, {FAIL} fehlgeschlagen")
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
