"""Gemeinsame Schnittstelle aller Anzeigen (DISPLAYS.md `docs/DISPLAYS.md`, Abschnitt „Grundsatz", Regel 6c).

Oberhalb dieser Schicht weiß niemand, welches Panel steckt. Ein Panel
beschreibt sich über sein ``Profil`` (Maße, Farben, Bildrate) und kann
``show``, ``backlight``, ``led``, ``close``. Was es nicht kann, tut nichts
-- ein E-Paper hat kein Backlight, ein nacktes Panel keine LED.

Das ``Profil`` kommt aus ``display.json`` des Moduls. Dieselbe Datei liest
der Installer; es gibt sie einmal.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path

log = logging.getLogger(__name__)

# numpy wird beim ERSTEN BILD geladen, nicht beim Import. Jeder
# Installer-Aufruf von ``python3 -m chimera.displays`` (Profil lesen,
# Erkennung, Ton, Mikro) importiert dieses Modul, wandelt aber kein Bild --
# und zahlte ``import numpy`` trotzdem jedes Mal (gemessen 11.10.2026 am
# chimera-pi: Profil lesen 1,0 s mit, 0,46 s ohne). Der Dienst zahlt es
# weiter genau einmal, beim ersten Bild.
_np = None
_np_versucht = False

def _numpy():
    """numpy beim ersten Gebrauch laden; ``None``, wenn es fehlt."""
    global _np, _np_versucht
    if not _np_versucht:
        _np_versucht = True
        try:
            import numpy as geladen
        except ImportError:  # pragma: no cover - auf dem Zielgerät vorhanden
            geladen = None
        _np = geladen
    return _np


@dataclass(frozen=True)
class Profil:
    """Was ein Modul über seine Anzeige sagt (``display.json``)."""

    typ: str
    name: str
    breite: int
    hoehe: int
    farben: str                 # rgb565 | mono | mono+rot
    bildrate: float             # Bilder je Sekunde, 0 = nur auf Anstoß
    darstellung: str            # animiert | standbild | reduziert | reduziert+akzent
    mindestabstand_s: float = 0.0   # E-Paper: Abstand zwischen Auffrischungen
    pins: dict = field(default_factory=dict)
    deps: dict = field(default_factory=dict)       # {"pip": [...], "apt": [...]}
    erkennung: list = field(default_factory=list)  # Prüfliste, siehe erkennen.py
    hinweis: str = ""
    quelle: dict = field(default_factory=dict)     # Herkunft des Treibers (Doku)
    ton: dict = field(default_factory=dict)        # Laufzeit-Overlays für Ton
    #: Taktfrequenz der Software-PWM für die RGB-LED (Hz). Sie ist eine
    #: Eigenschaft des Moduls: Bei 100 Hz kosteten drei Kanäle zusammen
    #: ~3,9 % eines Kerns im Leerlauf, bei 60 Hz ~3,0 % (am Pi gemessen,
    #: 3.11.2026). 60 Hz trägt weiterhin, ist aber billiger.
    led_frequenz_hz: float = 100.0
    roh: dict = field(default_factory=dict)

    @classmethod
    def aus_datei(cls, pfad: Path) -> "Profil":
        d = json.loads(Path(pfad).read_text(encoding="utf-8"))
        pflicht = ("typ", "name", "breite", "hoehe", "farben", "bildrate", "darstellung")
        fehlt = [k for k in pflicht if k not in d]
        if fehlt:
            raise ValueError(f"{pfad}: Felder fehlen: {', '.join(fehlt)}")
        return cls(
            typ=str(d["typ"]), name=str(d["name"]),
            breite=int(d["breite"]), hoehe=int(d["hoehe"]),
            farben=str(d["farben"]), bildrate=float(d["bildrate"]),
            darstellung=str(d["darstellung"]),
            mindestabstand_s=float(d.get("mindestabstand_s", 0)),
            pins=dict(d.get("pins", {})), deps=dict(d.get("deps", {})),
            erkennung=list(d.get("erkennung", [])), hinweis=str(d.get("hinweis", "")),
            quelle=dict(d.get("quelle", {})), ton=dict(d.get("ton", {})),
            led_frequenz_hz=float(d.get("led_frequenz_hz", 100)), roh=d,
        )


def to_rgb565(image) -> bytes:
    """Pillow-Bild → Panelspeicher. Big-Endian, 5/6/5 Bit.

    Mit numpy 25-mal schneller als bildpunktweise (gemessen, siehe
    ROADMAP Phase 3). Der Rückfall bleibt, damit es ohne numpy läuft --
    und meldet sich, statt stillschweigend langsam zu sein.
    """
    rgb = image.convert("RGB")
    np = _numpy()
    if np is not None:
        a = np.asarray(rgb, dtype=np.uint16)
        v = (((a[:, :, 0] & 0xF8) << 8) | ((a[:, :, 1] & 0xFC) << 3) | (a[:, :, 2] >> 3))
        return v.astype(">u2").tobytes()
    log.warning("numpy fehlt — RGB565 wird bildpunktweise gerechnet, das ist rund "
                "25-mal langsamer und hält keine 15 Bilder je Sekunde.")
    out = bytearray()
    for r, g, b in rgb.getdata():
        value = ((r & 0xF8) << 8) | ((g & 0xFC) << 3) | (b >> 3)
        out.append((value >> 8) & 0xFF)
        out.append(value & 0xFF)
    return bytes(out)


def aenderungsrechtecke(alt, neu, breite: int, hoehe: int) -> list[tuple[int, int, int, int]]:
    """Wo unterscheiden sich zwei RGB565-Bilder? → ``[(x, y, w, h), …]``.

    Der Panelspeicher eines ST7789 behält seinen Inhalt, solange niemand ihn
    überschreibt (DESIGN Regel 7). Also muss nur das übertragen werden, was
    sich geändert hat — ein stehendes Gesicht kostet dann **nichts**. Am Pi
    gemessen (3.11.): 572 `write()` je Sekunde auf `/dev/spidev0.0`, rund 17
    volle Bilder/s ohne Änderung, 28 % eines Kerns im Leerlauf.

    Geschnitten wird in **Streifen zusammenhängender Zeilen**; je Streifen ist
    das Rechteck die Spanne der geänderten Spalten. Das ist der Kompromiss
    zwischen „ein Rechteck für alles" (überträgt viel Unverändertes) und
    „ein Rechteck je Bildpunkt" (kostet je Fenster vier Befehle).
    """
    if len(alt) != breite * hoehe * 2 or len(neu) != breite * hoehe * 2:
        raise ValueError(f"RGB565: {len(alt)} / {len(neu)} Byte, "
                         f"erwartet {breite * hoehe * 2}")
    if alt == neu:
        return []

    np = _numpy()
    if np is not None:
        a = np.frombuffer(alt, dtype=np.uint8).reshape(hoehe, breite, 2)
        b = np.frombuffer(neu, dtype=np.uint8).reshape(hoehe, breite, 2)
        anders = a != b
        zeilen = np.flatnonzero(anders.any(axis=(1, 2)))
        rechtecke: list[tuple[int, int, int, int]] = []
        for streifen in _streifen(zeilen.tolist()):
            oben, unten = streifen[0], streifen[-1]
            # Spalten: über Zeilen UND die zwei Bytes je Bildpunkt reduzieren,
            # sonst wäre das Ergebnis ein Byte-Offset statt einer Spalte.
            spalten = np.flatnonzero(anders[oben:unten + 1].any(axis=(0, 2)))
            links, rechts = int(spalten[0]), int(spalten[-1])
            rechtecke.append((links, oben, rechts - links + 1, unten - oben + 1))
        return rechtecke

    # Ohne numpy: zeilenweise vergleichen, je Streifen die ganze Breite.
    # Langsamer, aber dasselbe Ergebnis in der Fläche -- und der Rückfall
    # meldet sich nicht als „schnell".
    mv_alt, mv_neu = memoryview(alt), memoryview(neu)
    zeile = breite * 2
    anders = [y for y in range(hoehe)
              if mv_alt[y * zeile:(y + 1) * zeile] != mv_neu[y * zeile:(y + 1) * zeile]]
    return [(0, s[0], breite, s[-1] - s[0] + 1) for s in _streifen(anders)]


def _streifen(zeilen: list[int]) -> list[list[int]]:
    """Zusammenhängende Zeilennummern zu Streifen bündeln."""
    if not zeilen:
        return []
    streifen = [[zeilen[0]]]
    for y in zeilen[1:]:
        if y == streifen[-1][-1] + 1:
            streifen[-1].append(y)
        else:
            streifen.append([y])
    return streifen


def ausschnitt(rgb, breite: int, x: int, y: int, w: int, h: int) -> bytes:
    """Ein Rechteck aus einem RGB565-Puffer schneiden (zeilenweise kopiert)."""
    zeile = breite * 2
    if x == 0 and w == breite:
        return bytes(rgb[y * zeile:(y + h) * zeile])
    np = _numpy()
    if np is not None:
        a = np.frombuffer(rgb, dtype=np.uint8).reshape(-1, zeile)
        return a[y:y + h, x * 2:(x + w) * 2].tobytes()
    mv = memoryview(rgb)
    aus = bytearray()
    for yy in range(y, y + h):
        aus += mv[yy * zeile + x * 2: yy * zeile + (x + w) * 2]
    return bytes(aus)


class Panel:
    """Gemeinsame Oberfläche für die Bildausgabe."""
    width: int = 240
    height: int = 280
    #: Wie oft dieses Panel gezeichnet werden will (Regel 7a). ``0`` heißt
    #: „nur auf Anstoß" — dann zeichnet der Renderer nicht von selbst.
    fps: int = 15
    #: Wie oft in der Ruhe gezeichnet wird (Regel 7a, Ergänzung 3.11.2026):
    #: ``fps`` gilt, wenn etwas passiert (Blinzeln, Sprechen); für ein
    #: schwingendes Gesicht genügen wenige Bilder. ``0`` heißt „in Ruhe
    #: nicht zeichnen". Ein E-Ink-Panel erbt ``fps = 0`` und damit auch hier 0.
    ruhe_fps: int = 2
    profil: Profil | None = None
    #: Warum dieses Panel so ist, wie es ist — gefüllt, wenn etwas nicht
    #: ging (Regel 8a: „läuft blind" und „ist kaputt" muss ablesbar sein).
    hinweis: str = ""

    def pruefe_groesse(self, image) -> None:
        if image.size != (self.width, self.height):
            # Bewusst kein stilles Skalieren: Eine falsche Bildgröße ist ein
            # Fehler im Renderer (Regel 8a).
            raise ValueError(f"Bild ist {image.size}, Panel erwartet "
                             f"({self.width}, {self.height})")

    def show(self, image) -> None:
        raise NotImplementedError

    def backlight(self, percent: int) -> None:
        pass

    def led(self, r: int, g: int, b: int) -> None:
        pass

    def close(self) -> None:
        pass


class NullPanel(Panel):
    """Panel ohne Panel — zählt nur, was ankäme (Entwicklung, Messung)."""

    def __init__(self, width: int = 240, height: int = 280,
                 *, convert: bool = True, fps: int = 15) -> None:
        self.width, self.height = width, height
        self.convert = convert
        self.fps = fps
        self.frames = 0
        self.last: bytes | None = None

    def show(self, image) -> None:
        self.pruefe_groesse(image)
        if self.convert:
            self.last = to_rgb565(image)
        self.frames += 1
