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


GELB = (255, 180, 0)
GRUEN = (0, 210, 70)
ROT = (230, 30, 30)
AUS = (0, 0, 0)


def _led(panel, farbe) -> None:
    """LED setzen, ohne dass ein Panel ohne LED den Lauf stoert."""
    try:
        panel.led(*farbe)
    except Exception:                              # noqa: BLE001
        pass


def led_abschluss(panel, ergebnis: str, spur=None) -> None:
    """Abschlusszeichen: gruen aufleuchten, bei Fehler rot SOS.

    Vorgabe smilez (2.11.): waehrend des Updates gelb blinken, bei Abschluss
    gruen aufleuchten, bei Fehler rot SOS blinken.
    """
    # Drei Ausgaenge, nicht zwei: Ein Befund (rc 1) ist kein Fehler -- sonst
    # leuchtet die LED nach jedem Lauf rot, in dem nur etwas fehlt (etwa das
    # Gateway-Binary ohne Commit). Gelb ruhig heisst "geschafft, mit Hinweis".
    if ergebnis in ("ok", "", "0"):
        _spur(spur, "LED: gruen (Abschluss)")
        _led(panel, GRUEN)
        time.sleep(3.0)
        return
    if ergebnis in ("befund", "hinweis"):
        _spur(spur, "LED: gelb ruhig (Abschluss mit Befund)")
        _led(panel, GELB)
        time.sleep(3.0)
        return
    # SOS: kurz-kurz-kurz, lang-lang-lang, kurz-kurz-kurz -- ein Durchgang.
    _spur(spur, "LED: rot SOS (Fehler)")
    punkte = [(0.2, 0.2)] * 3 + [(0.6, 0.2)] * 3 + [(0.2, 0.2)] * 3
    for an, pause in punkte:
        _led(panel, ROT)
        time.sleep(an)
        _led(panel, AUS)
        time.sleep(pause)
    time.sleep(0.8)


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


def lies_ergebnis(pfad: str) -> str:
    """Abschluss aus der Ergebnisdatei: ``ok`` oder alles andere = Fehler."""
    if not pfad:
        return "ok"
    try:
        return Path(pfad).read_text(encoding="utf-8").strip() or "ok"
    except OSError:
        return "ok"


def _spur(pfad: str, text: str) -> None:
    """Eine Zeile mit Zeitstempel in die Zeichnerspur schreiben."""
    if not pfad:
        return
    try:
        with open(pfad, "a", encoding="utf-8") as f:
            f.write(f"{time.strftime('%H:%M:%S')} {text}\n")
    except OSError:
        pass


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(prog="fortschritt")
    ap.add_argument("--datei", required=True)
    ap.add_argument("--marke", default="",
                    help="Marke: fertig -- zeichnet 100 %% und endet")
    ap.add_argument("--pause", default="",
                    help="Marke: nur beenden (Panel wird anderswo gebraucht)")
    ap.add_argument("--spur", default="", help="Zeichenspur (Werte) ablegen")
    ap.add_argument("--ergebnis", default="",
                    help="Datei mit ok|fehler fuer das Abschlusszeichen der LED")
    ap.add_argument("--log", default="",
                    help="Zeichnerspur (Zeitstempel, Grund) ablegen")
    ap.add_argument("--wieder", default="",
                    help="Wiedereinstiegspunkt: die Pause schreibt hierher, "
                         "wie weit sie gekommen ist")
    ap.add_argument("--moods", default="")
    ap.add_argument("--sekunden", type=float, default=600.0)
    ap.add_argument("--still", action="store_true", help="kein Panel, nur rechnen")
    ap.add_argument("--bild", default="", help="letztes Bild als PNG ablegen")
    ap.add_argument("--text", default="Updating...",
                    help="Beschriftung ueber dem Balken")
    args = ap.parse_args(argv)

    from chimera.display.panel import open_panel

    _spur(args.log, f"Start (PID {os.getpid()}), Stand aus {args.datei}")
    datei = Path(args.datei)
    marke = Path(args.marke) if args.marke else None
    pause = Path(args.pause) if args.pause else None
    if args.still:
        # Ohne Panel (Tests, Prüfung der Rechnung): dasselbe Bild, nur nicht
        # auf die Leitung -- kein stilles Ueberspringen, der Aufrufer weiss es.
        from chimera.displays import NullPanel

        panel = NullPanel(width=240, height=280)
    else:
        panel = open_panel("auto")
    ren = baue(getattr(panel, "width", 240), getattr(panel, "height", 280),
               Path(args.moods) if args.moods else Path("data/moods-builtin.json"))

    blinken = True
    blink_an = True
    pausiert = False
    letzter = -1.0
    letzter_stand: tuple[int, int] | None = None
    letzte_aenderung = time.time()
    fertig_gezeichnet = False

    while True:
        if blinken:
            _led(panel, GELB if blink_an else AUS)
            blink_an = not blink_an

        stand = lies(datei)
        if stand:
            letzter_stand = stand
        wert = anteil(*stand) if stand else 0.0
        if abs(wert - letzter) > 1e-9:
            img = ren.render()
            if img is not None:
                zeichne_text(img, args.text)
                zeichne_balken(img, wert)
                panel.show(img)
                _spur(args.log, f"gezeichnet {wert:.4f} ({stand[0]}/{stand[1]})")
                if args.bild:
                    img.save(args.bild)
            if args.spur:
                try:
                    with open(args.spur, "a", encoding="utf-8") as f:
                        f.write(f"{wert:.4f}\n")
                except OSError:
                    pass
            letzter = wert
            letzte_aenderung = time.time()
        # Pause: Das Panel wird von einem Schritt gebraucht (Anzeige-Erkennung).
        # Beenden, ohne 100 % zu zeichnen -- sonst springt der Balken auf voll
        # und gleich wieder zurueck (am Geraet gesehen, 2.11.).
        if pause is not None and pause.exists():
            # Der Zeichner setzt den Wiedereinstiegspunkt selbst -- an der
            # Stelle, an der er die Pause ansetzt. So beginnt der naechste
            # Zeichner genau dort, wo dieser aufgehoert hat.
            if args.wieder and letzter_stand:
                try:
                    Path(args.wieder).write_text(
                        f"{letzter_stand[0]} {letzter_stand[1]}\n",
                        encoding="utf-8")
                except OSError as exc:
                    print(f"Wiedereinstiegspunkt nicht schreibbar: {exc}",
                          file=sys.stderr)
            pausiert = True
            _spur(args.log, "Pause: Panel wird freigegeben, Stand gesetzt")
            break
        if marke is not None and marke.exists() and not fertig_gezeichnet:
            _spur(args.log, "Ende: fertig")
            img = ren.render()
            if img is not None:
                zeichne_text(img, args.text)
                zeichne_balken(img, 1.0)
                panel.show(img)
                if args.spur:
                    try:
                        with open(args.spur, "a", encoding="utf-8") as f:
                            f.write("1.0000\n")
                    except OSError:
                        pass
            fertig_gezeichnet = True
            blinken = False
            led_abschluss(panel, lies_ergebnis(args.ergebnis), args.log)
            break
        if time.time() - letzte_aenderung > args.sekunden:
            print("kein Fortschritt mehr — Anzeige beendet", file=sys.stderr)
            break
        time.sleep(0.5)
    if not pausiert:
        _spur(args.log, "Ende: Panel wird geschlossen (Hintergrundlicht aus)")
        try:
            panel.close()
        except Exception:                          # noqa: BLE001
            pass
    else:
        _spur(args.log, "Pause: kein close() -- Hintergrundlicht bleibt an")
    # Beim Pausieren wird bewusst NICHT geschlossen: close() setzt die
    # Hintergrundbeleuchtung aus, und das Display bliebe waehrend des Schritts
    # dunkel (am Geraet gesehen: 6 bis 24 s schwarz). Die Leitungen gibt der
    # Prozess beim Ende ohnehin frei.
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
