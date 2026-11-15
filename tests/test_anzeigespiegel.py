"""Anzeigespiegel: veröffentlichen, ohne je ein halbes Bild zu zeigen.

DESIGN, Regel „Anzeigespiegel". Geprüft wird die **echte** Schreibseite
(`src/chimera/display/spiegel.py`) und ihre Verdrahtung im Renderer — nicht
eine nachgebaute Formel. Die Gegenseite (Rust) hat ihre eigenen Tests in
`rust/crates/tor/src/anzeige.rs`, die Browser-Rechnung in
`tests/js/anzeige_bild.mjs`.

Der Baum kommt aus `CHIMERA_SRC`, damit die Gegenprobe eine verfälschte Kopie
prüfen kann, ohne die echte Datei anzufassen.

Aufruf: python3 tests/test_anzeigespiegel.py
"""

from __future__ import annotations

import os
import struct
import sys
import tempfile
import threading
import time
from pathlib import Path

HIER = Path(__file__).resolve().parent
ROOT = HIER.parent
SRC = Path(os.environ.get("CHIMERA_SRC") or ROOT / "src")
sys.path.insert(0, str(SRC))

from chimera.display.spiegel import (  # noqa: E402
    FORMAT_RGB565_BE,
    KOPF_LAENGE,
    MAGIC,
    Spiegel,
    kopf_bauen,
    kopf_lesen,
)

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


def bild(breite=4, hoehe=3, farbe=0xAB) -> bytes:
    return bytes([farbe]) * (breite * hoehe * 2)


def neuer_spiegel(name: str) -> tuple[Spiegel, Path]:
    d = Path(tempfile.mkdtemp(prefix=f"spiegel-{name}-"))
    p = d / "anzeige" / "bild"
    os.environ.pop("CHIMERA_SPIEGEL", None)
    s = Spiegel(pfad=p)
    return s, p


def main() -> int:
    print("=== Anzeigespiegel ===")

    # --- Kopf ---
    k = kopf_bauen(240, 280, 7)
    check("Kopf ist 32 Byte", len(k), KOPF_LAENGE)
    check("Kennung steht vorn", k[:4], MAGIC)
    gelesen = kopf_lesen(k)
    check("Kopf wird gedeutet", gelesen,
          {"format": FORMAT_RGB565_BE, "breite": 240, "hoehe": 280, "zaehler": 7})
    # Zähler steht als 64-Bit big-endian an Offset 12 — so liest ihn auch Rust.
    check("Zaehler big-endian an Offset 12",
          struct.unpack(">Q", k[12:20])[0], 7)
    kaputt = bytearray(k)
    kaputt[0] = ord("X")
    check("fremde Kennung ist kein Bild", kopf_lesen(bytes(kaputt)), None)
    kaputt = bytearray(k)
    kaputt[4] = 2
    check("fremde Fassung ist kein Bild", kopf_lesen(bytes(kaputt)), None)
    check("zu kurzer Kopf ist kein Bild", kopf_lesen(k[:18]), None)

    # --- Schreiben ---
    s, pfad = neuer_spiegel("schreiben")
    b1 = bild()
    check("erste Veroeffentlichung meldet Erfolg", s.zeige(b1, 4, 3), True)
    check("Datei existiert", pfad.is_file(), True)
    inhalt = pfad.read_bytes()
    check("Laenge = Kopf + Pixel", len(inhalt), KOPF_LAENGE + len(b1))
    check("Pixel stehen unveraendert in der Datei", inhalt[KOPF_LAENGE:], b1)
    check("Kopf der Datei passt", kopf_lesen(inhalt),
          {"format": FORMAT_RGB565_BE, "breite": 4, "hoehe": 3, "zaehler": 1})
    check("Datei ist fuer andere lesbar (0644)",
          oct(pfad.stat().st_mode & 0o777), "0o644")
    check("keine Zwischendatei liegen geblieben",
          sorted(x.name for x in pfad.parent.iterdir()), ["bild"])

    # --- Nichts doppelt veröffentlichen ---
    check("gleiches Bild wird nicht veroeffentlicht", s.zeige(b1, 4, 3), False)
    check("Zaehler bleibt stehen", s.zaehler, 1)
    # Auch ein neues Objekt mit gleichem Inhalt zaehlt nicht als Aenderung.
    check("gleicher Inhalt, neues Objekt: keine Veroeffentlichung",
          s.zeige(bild(), 4, 3), False)
    check("neues Bild wird veroeffentlicht", s.zeige(bild(farbe=0x11), 4, 3), True)
    check("Zaehler steigt", s.zaehler, 2)
    check("Zaehler in der Datei", kopf_lesen(pfad.read_bytes())["zaehler"], 2)

    # --- Falsche Länge: nicht raten, nichts schreiben ---
    vorher = pfad.read_bytes()
    check("falsche Laenge wird abgelehnt", s.zeige(b"x" * 10, 4, 3), False)
    check("Zaehler bleibt bei Ablehnung", s.zaehler, 2)
    check("Datei bleibt unveraendert", pfad.read_bytes(), vorher)

    # --- Kein Verzeichnis: einmal sagen, nicht im Bildtakt ---
    # Ein Testlauf ist root -- chmod haelt root nicht auf. Ein Pfad, dessen
    # ElternTEIL eine Datei ist, scheitert dagegen immer (ENOTDIR).
    d = Path(tempfile.mkdtemp(prefix="spiegel-gesperrt-"))
    sperre = d / "keine-ordner"
    sperre.write_text("x")
    s2 = Spiegel(pfad=sperre / "bild")
    check("nicht schreibbar: kein Erfolg", s2.zeige(b1, 4, 3), False)
    check("Grund wird gemerkt", bool(s2._fehler), True)
    erster = s2._fehler
    s2.zeige(bild(farbe=0x22), 4, 3)
    check("Grund wird nicht neu gesetzt (gleiche Meldung)", s2._fehler, erster)
    # Nach dem Erlauben geht es weiter, und der Fehler gilt als erledigt.
    s2.pfad = d / "jetzt" / "bild"
    s2._verzeichnis_ok = False
    check("nach dem Erlauben wieder Erfolg", s2.zeige(bild(farbe=0x33), 4, 3), True)
    check("Fehler ist geräumt", s2._fehler, None)

    # --- Abschalter ---
    d3 = Path(tempfile.mkdtemp(prefix="spiegel-aus-"))
    os.environ["CHIMERA_SPIEGEL"] = "0"
    try:
        s3 = Spiegel(pfad=d3 / "bild")
        check("CHIMERA_SPIEGEL=0 schaltet ab", s3.zeige(b1, 4, 3), False)
        check("und schreibt nichts", (d3 / "bild").exists(), False)
    finally:
        os.environ.pop("CHIMERA_SPIEGEL", None)

    # --- Atomar: ein Leser sieht nie ein halbes Bild ---
    s4, pfad4 = neuer_spiegel("atomar")
    soll = KOPF_LAENGE + 240 * 280 * 2
    s4.zeige(bytes(soll - KOPF_LAENGE), 240, 280)
    kaputt_gelesen = []
    fertig = threading.Event()

    def lesen():
        while not fertig.is_set():
            try:
                daten = pfad4.read_bytes()
            except OSError:
                kaputt_gelesen.append("fehlt")
                continue
            if len(daten) != soll:
                kaputt_gelesen.append(len(daten))
            time.sleep(0.001)

    t = threading.Thread(target=lesen, daemon=True)
    t.start()
    for i in range(60):
        s4.zeige(bytes([i & 0xFF]) * (240 * 280 * 2), 240, 280)
    fertig.set()
    t.join(timeout=5)
    check("Leser sieht nie ein halbes Bild", kaputt_gelesen, [])
    # Bild 0 ist dasselbe wie das erste (alles 0) -- es wird nicht neu
    # veröffentlicht. 1 + 60 verschiedene Inhalte, davon einer doppelt.
    check("Zaehler nach 60 Bildern", s4.zaehler, 60)

    # --- Verdrahtung im Renderer ---
    from PIL import Image
    from chimera.displays.base import NullPanel
    from chimera.render.avatar import NoisyRenderer

    s5, pfad5 = neuer_spiegel("renderer")
    panel = NullPanel(width=8, height=8)
    r = NoisyRenderer(panel=panel, target_fps=0, spiegel=s5)
    r.show(Image.new("RGB", (8, 8), (10, 20, 30)))
    check("Renderer veroeffentlicht ein Bild", s5.zaehler, 1)
    check("Datei passt zum Panel", len(pfad5.read_bytes()), KOPF_LAENGE + 8 * 8 * 2)
    check("Masse im Kopf kommen vom Panel", kopf_lesen(pfad5.read_bytes()),
          {"format": FORMAT_RGB565_BE, "breite": 8, "hoehe": 8, "zaehler": 1})
    # Ohne Spiegel darf show() nichts schreiben und nichts tun.
    r2 = NoisyRenderer(panel=NullPanel(width=8, height=8), target_fps=0)
    check("ohne Spiegel ist der Renderer still", r2.spiegel, None)
    r2.show(Image.new("RGB", (8, 8), (1, 2, 3)))

    print(f"\nErgebnis: {PASS} ok, {FAIL} fehlgeschlagen")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
