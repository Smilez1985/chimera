"""Selbstauskunft: was Chimera ist, was schon gebaut ist und was offen ist.

**Der Befund (smilez, 16.11.2026).** Im Web-Chat gefragt, welche
Verbesserungen es vorschlagen würde, nannte das Modell sieben Punkte — vier
davon waren seit Tagen gebaut (Diagnose über ``status``, Dateizugriff,
43 Gesichtsausdrücke, Werkzeug-Protokoll). Es konnte das nicht wissen: der
Systemprompt sagt ihm ``Du bist Chimera, ein Gerät mit einem Gesicht``; mehr
über sich selbst steht dort nicht. Es sah die Werkzeugschnittstelle, aber
keine Inventur — keine Fassung, keinen Freigabemodus, keine Liste dessen,
was bereits läuft. Also riet es, und Raten klingt wie Vorschlag.

**Warum ein Werkzeug und kein Absatz im Prompt.** Der Prompt ist nach
5q der cache-empfindliche Teil: er wächst in *jeder* Anfrage mit. Eine
Inventur dort kostet Tokens pro Runde und veraltet im Betrieb, sobald
jemand etwas baut. Als Werkzeug geholt kostet sie nur, wenn danach gefragt
wird — und genau dann braucht das Modell sie. Im Prompt steht deshalb nur
der Satz, *dass* es sie gibt (``SELBST_TEMPLATE``).

**Warum aus dem laufenden System und nicht aus einer gepflegten Datei.**
Eine von Hand geschriebene ``system.md`` würde genau den Fehler wiederholen,
den diese Auskunft behebt: sie behauptet, was gebaut ist, und stimmt nach
dem nächsten Commit nicht mehr. Hier wird gelesen, was wirklich da ist
(Werkzeugliste, Ausdruckszahl, ``CHANGELOG.md``, ``docs/ROADMAP.md``).
Was nicht lesbar ist, wird **benannt** und nicht erfunden (Regel 8a).
"""

from __future__ import annotations

import logging
import os
import re
import socket
from pathlib import Path

log = logging.getLogger(__name__)

#: Wo die Dokumente liegen. Vorgabe: vom Modul aus den Baum hinauf
#: (``…/code/src/chimera/agent/selbstbild.py`` → ``…/code``). Im Betrieb
#: setzt der Installer den Wert; die Umgebungsvariable sticht die Vorgabe.
DOKUMENTE_ENV = "CHIMERA_DOKUMENTE"

#: Wie viel Auszug. Die Auskunft ist ein Überblick, kein Ersatz für die
#: Datei: „mehr steht in CHANGELOG.md" ist ehrlicher als alles abzuschneiden.
GEBAUT_JE_ABSCHNITT = 4
OFFEN_MAX = 20

#: Reihenfolge, in der die Abschnitte des CHANGELOG gelesen werden. Das
#: Neueste steht jeweils oben (angehängt wird vorn).
ABSCHNITTE = ("Hinzugefügt", "Behoben")


def wurzel(explicit: Path | str | None = None) -> Path | None:
    """Der Baum, in dem die Dokumente liegen — oder ``None``."""
    if explicit:
        p = Path(explicit)
    elif os.environ.get(DOKUMENTE_ENV):
        p = Path(os.environ[DOKUMENTE_ENV])
    else:
        p = Path(__file__).resolve().parents[3]
    return p if (p / "CHANGELOG.md").is_file() or (p / "docs").is_dir() else None


def _ohne_markup(text: str) -> str:
    """Sternchen und Rückschrägstriche weg — die Auskunft wird gesprochen."""
    text = text.replace("**", "").replace("`", "")
    return re.sub(r"\s+", " ", text).strip()


def _erste_zeile(text: str) -> str:
    return _ohne_markup(text.splitlines()[0] if text else "")


def _titel(text: str, grenze: int = 120) -> str:
    """Der **Titel** eines Eintrags, nicht sein erster Satz.

    Ein CHANGELOG-Eintrag beginnt mit seinem Titel in Sternchen
    (``- **Selbstauskunft als Werkzeug** (Befund …): …``). Die erste Zeile
    abzuschneiden ergab in der Auskunft Halbsätze wie ``… (Befund smilez
    16.11.: *„die`` — am Gerät gesehen, 16.11.2026. Gibt es keinen
    Fettdruck, wird die erste Zeile genommen und ein Schnitt als solcher
    gekennzeichnet.
    """
    zeile = (text.splitlines()[0] if text else "").strip()
    m = re.match(r"\*\*(.+?)\*\*", zeile)
    if m:
        return _ohne_markup(m.group(1))[:grenze]
    klar = _ohne_markup(zeile)
    return klar if len(klar) <= grenze else klar[:grenze].rstrip() + "…"


def gebaut(root: Path, abschnitte: tuple[str, ...] = ABSCHNITTE,
           je: int = GEBAUT_JE_ABSCHNITT) -> list[tuple[str, list[str]]]:
    """Die neuesten Einträge je Abschnitt: ``[(Abschnitt, [Titel, ...]), ...]``.

    Gelesen wird *nicht* nach Datum, sondern nach Position: was oben steht,
    ist zuletzt dazugekommen (so wird dieses CHANGELOG geführt). Ein
    fehlender Abschnitt ist kein Fehler — er fehlt dann einfach.
    """
    p = root / "CHANGELOG.md"
    try:
        zeilen = p.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        log.debug("CHANGELOG nicht lesbar: %s", exc)
        return []

    ergebnis: list[tuple[str, list[str]]] = []
    such = list(abschnitte)
    aktuell: str | None = None
    gesammelt: list[str] = []

    def _abschluss():
        if aktuell is not None:
            ergebnis.append((aktuell, list(gesammelt)))

    for z in zeilen:
        if z.startswith("### "):
            name = z[4:].strip()
            _abschluss()
            # Nur gewünschte Abschnitte werden gesammelt; jeder Abschnitt
            # endet mit dem nächsten `###`. **Kein `break` hier**: der
            # `break` stand in der ersten Fassung direkt nach dem Kopf des
            # letzten gesuchten Abschnitts — seine Einträge wurden nie
            # gelesen (16.11.2026, der Test hat es gefunden).
            if name in such:
                such.remove(name)
                aktuell, gesammelt = name, []
            else:
                aktuell, gesammelt = None, []
            continue
        if aktuell is not None and z.startswith("- ") and len(gesammelt) < je:
            gesammelt.append(_titel(z[2:]))
    _abschluss()

    # Reihenfolge wie angefragt, nicht wie gefunden.
    nach = dict(ergebnis)
    return [(a, nach[a]) for a in abschnitte if a in nach]


def offen(root: Path, max_titel: int = OFFEN_MAX) -> tuple[list[str], int]:
    """Offene Roadmap-Punkte: ``(Titel[:max], Gesamtzahl)``.

    Ein Punkt ohne Titel (Fliesstext) wird mit seinem Anfang genannt —
    lieber ungenau als unsichtbar.
    """
    p = root / "docs" / "ROADMAP.md"
    try:
        zeilen = p.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        log.debug("ROADMAP nicht lesbar: %s", exc)
        return [], 0

    titel: list[str] = []
    for z in zeilen:
        s = z.strip()
        if not s.startswith("- [ ]"):
            continue
        rest = s[len("- [ ]"):].strip()
        m = re.match(r"\*\*(.+?)\*\*", rest)
        text = m.group(1) if m else rest
        titel.append(_ohne_markup(text)[:120])
    return titel[:max_titel], len(titel)


def _gedaechtnis(pfad: Path | str | None) -> str:
    if not pfad:
        return "kein Gedächtnis eingerichtet"
    d = Path(pfad)
    grund = d / "GRUNDLAGEN.md"
    tage = sorted(d.glob("????-??-??.md"))
    teile = []
    if grund.is_file():
        try:
            n = len(grund.read_text(encoding="utf-8").splitlines())
            teile.append(f"GRUNDLAGEN.md ({n} Zeilen)")
        except OSError:
            teile.append("GRUNDLAGEN.md (nicht lesbar)")
    else:
        teile.append("keine GRUNDLAGEN.md")
    teile.append(f"{len(tage)} Tagesnotiz(en)")
    return ", ".join(teile)


def text(*, version: str = "", werkzeuge: list[str] | None = None,
         ausdruecke: int | None = None, freigabe: str = "",
         tueren: list[str] | None = None, skills: int | None = None,
         gedaechtnis: Path | str | None = None,
         root: Path | str | None = None) -> str:
    """Die ganze Auskunft als ein Textblock.

    Jeder Eingang ist optional: was nicht übergeben wurde, wird als
    *nicht messbar* benannt und nicht geraten.
    """
    w = wurzel(root)
    zeilen: list[str] = []
    if not version and w is not None:
        try:
            version = (w / "VERSION").read_text(encoding="utf-8").strip()
        except OSError:
            version = ""
    kopf = f"Selbstauskunft Chimera {version or '(Fassung nicht messbar)'}"
    try:
        kopf += f" auf {socket.gethostname()}"
    except OSError:
        pass
    zeilen.append(kopf)

    if werkzeuge is not None:
        zeilen.append("Werkzeuge (%d): %s" % (len(werkzeuge), ", ".join(werkzeuge)))
    if ausdruecke is not None:
        zeilen.append(f"Gesichtsausdrücke: {ausdruecke} (Liste über das Werkzeug 'moods')")
    if freigabe:
        zeilen.append(f"Freigabe: {freigabe}")
    if tueren:
        zeilen.append("Offene Türen: " + ", ".join(tueren))
    if skills is not None:
        zeilen.append(f"Skills: {skills}")
    zeilen.append("Gedächtnis: " + _gedaechtnis(gedaechtnis))

    if w is None:
        zeilen.append("")
        zeilen.append("Dokumente: nicht gefunden — was gebaut und was offen ist, "
                      "kann ich nicht sagen (nicht raten).")
        return "\n".join(zeilen)

    zeilen.append(f"Dokumente: {w} (docs/DESIGN.md, docs/ROADMAP.md, CHANGELOG.md)")

    gebaute = gebaut(w)
    if gebaute:
        zeilen.append("")
        zeilen.append("Schon gebaut (neueste Einträge aus CHANGELOG.md):")
        for abschnitt, titel in gebaute:
            for t in titel:
                zeilen.append(f"- [{abschnitt}] {t}")
        zeilen.append("Das ist gebaut. Schlage es nicht als Verbesserung vor — "
                      "die vollständige Liste steht in CHANGELOG.md.")
    else:
        zeilen.append("")
        zeilen.append("CHANGELOG.md: nicht lesbar — was gebaut ist, kann ich "
                      "nicht sagen (nicht raten).")

    offene, gesamt = offen(w)
    zeilen.append("")
    if offene:
        zeilen.append(f"Offen laut docs/ROADMAP.md ({gesamt} Punkte, "
                      f"hier die ersten {len(offene)}):")
        for t in offene:
            zeilen.append(f"- {t}")
    else:
        zeilen.append("docs/ROADMAP.md: keine offenen Punkte lesbar "
                      "(Datei fehlt oder alle erledigt).")
    return "\n".join(zeilen)
