"""Vorschau: einen Ausdruck ohne Gerät als Bild zeichnen.

Warum das ein Werkzeug im Baum ist und kein Einzeiler: Eigene Ausdrücke (die
der Agent selbst anlegt, DESIGN 3.3b, und die freien Formen aus
`mood/draw.py`) lassen sich sonst nur auf dem Pi beurteilen — dort, wo die
Leitung exklusiv ist und das Gesicht live läuft. Wer einen Ausdruck baut,
will ihn **vorher** sehen: als Datei, in Größe des Panels, ohne Hardware.

Das Bild kommt aus demselben `NoisyRenderer`, der auch auf dem Gerät zeichnet
(`NullPanel` statt Whisplay) — kein zweiter Zeichenweg, der auseinanderlaufen
könnte. Ein Streifen (`--bilder N`) zeigt die Bewegung, `--seed` macht ihn
wiederholbar.

Aufruf:
    python3 tools/vorschau.py --mood ROCK
    python3 tools/vorschau.py --datei eigener-ausdruck.json --bilder 6
    python3 tools/vorschau.py --liste
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from PIL import Image  # noqa: E402

from chimera.display.panel import NullPanel  # noqa: E402
from chimera.mood import ablage  # noqa: E402
from chimera.mood.validate import validate  # noqa: E402
from chimera.render.avatar import NoisyRenderer, State  # noqa: E402

BUILTIN = ROOT / "data" / "moods-builtin.json"


class VorschauFehler(Exception):
    """Ein Grund, der dem Aufrufer gesagt wird — kein stiller Abbruch."""


def eigene_datei(pfad: Path | None = None) -> Path:
    """Wo die eigenen Ausdrücke lägen (wie im Dienst: `<root>/moods.json`)."""
    if pfad is not None:
        return Path(pfad)
    import os
    home = Path(os.environ.get("CHIMERA_HOME") or Path.home() / ".chimera")
    return home / "moods.json"


def bibliothek(eigene: Path | None = None) -> tuple[object, list[str]]:
    """Mitgelieferte und eigene Ausdrücke laden. Meldet, was auffiel."""
    reg, hinweise = ablage.lade(BUILTIN, eigene_datei(eigene))
    return reg, hinweise


def namen(reg) -> list[str]:
    return sorted(e.name for e in reg.entries())


def mood_holen(reg, name: str) -> dict:
    """Einen Mood per Namen holen — der Name darf klein geschrieben sein."""
    e = reg.find(name)
    if e is None:
        bekannt = namen(reg)
        # Nicht raten, sondern den nächsten Namen nennen (Regel 8a).
        nah = [n for n in bekannt if n.lower().startswith(name.lower()[:2])][:6]
        raise VorschauFehler(
            f"Ausdruck {name!r} unbekannt ({len(bekannt)} bekannt"
            + (f"; ähnlich: {', '.join(nah)}" if nah else "") + ")")
    return e.mood


def mood_aus_datei(pfad: Path, name: str | None = None) -> tuple[dict, str]:
    """Eine Mood-Datei prüfen und übernehmen. Gibt (Mood, Bericht) zurück."""
    p = Path(pfad)
    if not p.is_file():
        raise VorschauFehler(f"Datei fehlt: {p}")
    try:
        roh = json.loads(p.read_text(encoding="utf-8"))
    except ValueError as exc:
        raise VorschauFehler(f"{p} ist kein JSON: {exc}") from exc
    # Eine Datei darf den Mood direkt enthalten oder unter {"moods": [...]}.
    if isinstance(roh, dict) and "moods" in roh:
        eintraege = roh["moods"]
        if not eintraege:
            raise VorschauFehler(f"{p} enthält keine Ausdrücke")
        roh = eintraege[0] if name is None else next(
            (m for m in eintraege if str(m.get("name", "")).upper() == name.upper()),
            eintraege[0])
    if not isinstance(roh, dict):
        raise VorschauFehler(f"{p}: ein Ausdruck muss ein Objekt sein, "
                             f"ist {type(roh).__name__}")
    try:
        mood, bericht = validate(roh)
    except Exception as exc:                          # noqa: BLE001 — Befund
        raise VorschauFehler(f"{p} ist kein gültiger Ausdruck: {exc}") from exc
    return mood, str(bericht)


def vorschau(mood: dict, *, breite: int = 240, hoehe: int = 280,
             bilder: int = 1, abstand: float = 0.2, sekunde: float = 0.0,
             seed: int | None = None, intensitaet: float = 90.0,
             beat: float = 40.0) -> tuple[Image.Image, dict]:
    """Den Ausdruck zeichnen. Gibt (Bild, Kennwerte) zurück.

    ``bilder > 1`` ergibt einen waagerechten Streifen: dasselbe Bild
    ``abstand`` Sekunden später, damit man die Bewegung sieht. Bei ``1`` ist
    das Ergebnis genau ein Panelbild.
    """
    if breite < 8 or hoehe < 8:
        raise VorschauFehler(f"Größe unbrauchbar: {breite}x{hoehe}")
    if bilder < 1:
        raise VorschauFehler("--bilder muss mindestens 1 sein")

    state = State()
    state.mood = mood
    state.mood_name = str(mood.get("name") or "VORSCHAU")
    state.intensity = float(intensitaet)
    state.beat = float(beat)
    panel = NullPanel(width=breite, height=hoehe)
    r = NoisyRenderer(state, panel, target_fps=0)

    if seed is not None:
        random.seed(seed)
    r.frame = sekunde * r.TARGET_FPS if r.TARGET_FPS else sekunde

    einzeln = []
    for i in range(bilder):
        # Zeit vorstellen, statt zu warten: dieselbe Bildfolge, in
        # Millisekunden statt in Sekunden.
        r.frame = (sekunde + i * abstand) * (r.TARGET_FPS or 1)
        einzeln.append(r.render())

    if bilder == 1:
        bild, lage = einzeln[0], (0, 0)
    else:
        bild = Image.new("RGB", (breite * bilder, hoehe), (10, 10, 14))
        for i, e in enumerate(einzeln):
            bild.paste(e, (i * breite, 0))
        lage = (0, 0)
    del lage
    return bild, {"breite": breite, "hoehe": hoehe, "bilder": bilder,
                  "frame": r.frame, "name": state.mood_name}


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        description="Einen Ausdruck ohne Gerät als PNG zeichnen.")
    p.add_argument("--mood", help="Name des Ausdrucks (Groß/klein egal)")
    p.add_argument("--datei", help="Mood-JSON prüfen und zeichnen")
    p.add_argument("--eigene", help="Datei der eigenen Ausdrücke "
                                    "(Vorgabe: $CHIMERA_HOME/moods.json)")
    p.add_argument("--liste", action="store_true", help="bekannte Ausdrücke zeigen")
    p.add_argument("--out", default="vorschau.png")
    p.add_argument("--breite", type=int, default=240)
    p.add_argument("--hoehe", type=int, default=280)
    p.add_argument("--bilder", type=int, default=1,
                   help="Anzahl Bilder im Streifen (Bewegung)")
    p.add_argument("--abstand", type=float, default=0.2,
                   help="Sekunden zwischen zwei Bildern")
    p.add_argument("--sekunde", type=float, default=0.0,
                   help="Startzeit im Ablauf")
    p.add_argument("--seed", type=int, help="Zufall festlegen (wiederholbar)")
    p.add_argument("--intensitaet", type=float, default=90.0)
    p.add_argument("--beat", type=float, default=40.0)
    a = p.parse_args(argv)

    try:
        reg, hinweise = bibliothek(Path(a.eigene) if a.eigene else None)
        for h in hinweise:
            print(f"  Hinweis: {h}")

        if a.liste:
            alle = namen(reg)
            print(f"{len(alle)} Ausdrücke:")
            for n in alle:
                print(f"  {n}")
            return 0

        if not a.mood and not a.datei:
            p.error("--mood oder --datei oder --liste")

        if a.datei:
            mood, bericht = mood_aus_datei(Path(a.datei), a.mood)
            print(f"  Datei: {a.datei} — {bericht}")
        else:
            mood = mood_holen(reg, a.mood)

        bild, kenn = vorschau(
            mood, breite=a.breite, hoehe=a.hoehe, bilder=a.bilder,
            abstand=a.abstand, sekunde=a.sekunde, seed=a.seed,
            intensitaet=a.intensitaet, beat=a.beat)
        ziel = Path(a.out)
        if ziel.parent and not ziel.parent.exists():
            ziel.parent.mkdir(parents=True, exist_ok=True)
        bild.save(ziel)
    except VorschauFehler as exc:
        print(f"FEHLER: {exc}", file=sys.stderr)
        return 1

    print(f"  {kenn['name']}: {kenn['breite']}x{kenn['hoehe']}, "
          f"{kenn['bilder']} Bild(er), Seed {a.seed} -> {ziel}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
