#!/usr/bin/env python3
"""Fortschrittsanzeige während eines Installer-Laufs.

Warum ein eigener Prozess: Der Installer hält den Dienst an, bevor er Dateien
tauscht. Der Dienst kann die Anzeige also nicht bedienen — genau in der Zeit,
in der man den Fortschritt sehen will.

Aufruf:  fortschritt.py --datei DATEI [--marke DATEI] [--moods PFAD]
                        [--sekunden N] [--still]

Die Fortschrittsdatei enthält eine Zeile: ``<fertig> <gesamt>``.
Die Marke stoppt den Zeichner; er zeichnet dann 100 % und endet.
Ohne Fortschritt für ``--sekunden`` (Vorgabe 600) endet er von selbst — ein
abgestürzter Installer darf das Panel nicht belegen.

Gezeichnet wird nur bei Änderung: Auf einem Pi Zero kostet jedes Bild Zeit,
und ein Balken, der sich im Kreis neu zeichnet, ist keine Anzeige.
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path


def anteil(fertig: int, gesamt: int) -> float:
    """Anteil 0.0 bis 1.0 — jede Stufe zählt gleich viel.

    ``gesamt`` 0 heißt: nichts zu tun, also fertig. Kein Teilen durch Null,
    und keine 100 %, die aus einer Division durch etwas Unbekanntes stammen.
    """
    if gesamt <= 0:
        return 1.0
    if fertig <= 0:
        return 0.0
    if fertig >= gesamt:
        return 1.0
    return fertig / gesamt


def lies(datei: Path) -> tuple[int, int] | None:
    try:
        text = datei.read_text(encoding="utf-8").strip()
    except OSError:
        return None
    teile = text.split()
    if len(teile) != 2:
        return None
    try:
        return int(teile[0]), int(teile[1])
    except ValueError:
        return None


def _schrift(groesse: int):
    """Eine lesbare Schrift; ohne TrueType bleibt die eingebaute."""
    from PIL import ImageFont

    for name in ("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
                 "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"):
        try:
            return ImageFont.truetype(name, groesse)
        except OSError:
            continue
    try:
        return ImageFont.load_default(size=groesse)
    except TypeError:                      # aeltere Pillow-Fassung
        return ImageFont.load_default()


def zeichne_text(img, text: str = "Updating...") -> None:
    """Die Beschriftung ueber dem Balken, mittig und gut lesbar.

    Ohne Beschriftung sagt ein Balken nicht, was laeuft -- er koennte genauso
    ein Ladebalken des Dienstes sein.
    """
    from PIL import ImageDraw

    w, h = img.size
    rand = max(8, w // 20)
    hoehe = max(8, h // 24)
    oben = h - hoehe - rand
    d = ImageDraw.Draw(img)
    schrift = _schrift(max(10, w // 13))
    # Schatten, damit die Schrift auch auf hellem Grund steht.
    try:
        links, top, rechts, unten = d.textbbox((0, 0), text, font=schrift)
        breite, thoehe = rechts - links, unten - top
    except AttributeError:                 # sehr alte Pillow-Fassung
        breite, thoehe = d.textlength(text, font=schrift), schrift.size
    x = (w - breite) // 2
    y = oben - thoehe - max(4, hoehe // 2)
    d.text((x + 1, y + 1), text, font=schrift, fill=(0, 0, 0))
    d.text((x, y), text, font=schrift, fill=(245, 236, 210))


def zeichne_balken(img, wert: float) -> None:
    """Den Balken unten ins Bild malen: Spur dunkel, Füllung bernstein."""
    from PIL import ImageDraw

    w, h = img.size
    rand = max(8, w // 20)
    hoehe = max(8, h // 24)
    oben = h - hoehe - rand
    d = ImageDraw.Draw(img)
    d.rectangle([rand, oben, w - rand - 1, oben + hoehe - 1], fill=(40, 32, 20))
    breite = int((w - 2 * rand) * max(0.0, min(1.0, wert)))
    if breite > 0:
        d.rectangle([rand, oben, rand + breite - 1, oben + hoehe - 1],
                    fill=(235, 170, 60))


def baue(breite: int, hoehe: int, moods: Path):
    """Renderer mit dem Gesicht UPDATE aufbauen."""
    from chimera.mood.registry import Registry
    from chimera.render.avatar import NoisyRenderer, State

    reg = Registry.load(moods)
    st = State()
    st.set_mood(reg.get("UPDATE"), hard=True)
    return NoisyRenderer(state=st, width=breite, height=hoehe)


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(prog="fortschritt")
    ap.add_argument("--datei", required=True)
    ap.add_argument("--marke", default="")
    ap.add_argument("--moods", default="")
    ap.add_argument("--sekunden", type=float, default=600.0)
    ap.add_argument("--still", action="store_true", help="kein Panel, nur rechnen")
    ap.add_argument("--bild", default="", help="letztes Bild als PNG ablegen")
    ap.add_argument("--text", default="Updating...",
                    help="Beschriftung ueber dem Balken")
    args = ap.parse_args(argv)

    from chimera.display.panel import open_panel

    datei = Path(args.datei)
    marke = Path(args.marke) if args.marke else None
    panel = open_panel("auto")
    ren = baue(getattr(panel, "width", 240), getattr(panel, "height", 280),
               Path(args.moods) if args.moods else Path("data/moods-builtin.json"))

    letzter = -1.0
    letzte_aenderung = time.time()
    fertig_gezeichnet = False

    while True:
        stand = lies(datei)
        wert = anteil(*stand) if stand else 0.0
        if abs(wert - letzter) > 1e-9:
            img = ren.render()
            if img is not None:
                zeichne_text(img, args.text)
                zeichne_balken(img, wert)
                panel.show(img)
                if args.bild:
                    img.save(args.bild)
            letzter = wert
            letzte_aenderung = time.time()
        if marke is not None and marke.exists() and not fertig_gezeichnet:
            img = ren.render()
            if img is not None:
                zeichne_text(img, args.text)
                zeichne_balken(img, 1.0)
                panel.show(img)
            fertig_gezeichnet = True
            break
        if time.time() - letzte_aenderung > args.sekunden:
            print("kein Fortschritt mehr — Anzeige beendet", file=sys.stderr)
            break
        time.sleep(0.5)
    try:
        panel.close()
    except Exception:                              # noqa: BLE001
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
