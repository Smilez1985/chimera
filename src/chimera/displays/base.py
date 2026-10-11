"""Gemeinsame Schnittstelle aller Anzeigen (DISPLAYS.md §1, Regel 6c).

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

try:
    import numpy as _np
except ImportError:  # pragma: no cover - auf dem Zielgerät vorhanden
    _np = None


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
            quelle=dict(d.get("quelle", {})), ton=dict(d.get("ton", {})), roh=d,
        )


def to_rgb565(image) -> bytes:
    """Pillow-Bild → Panelspeicher. Big-Endian, 5/6/5 Bit.

    Mit numpy 25-mal schneller als bildpunktweise (gemessen, siehe
    ROADMAP Phase 3). Der Rückfall bleibt, damit es ohne numpy läuft --
    und meldet sich, statt stillschweigend langsam zu sein.
    """
    rgb = image.convert("RGB")
    if _np is not None:
        a = _np.asarray(rgb, dtype=_np.uint16)
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


class Panel:
    """Gemeinsame Oberfläche für die Bildausgabe."""

    width: int = 240
    height: int = 280
    #: Wie oft dieses Panel gezeichnet werden will (Regel 7a). ``0`` heißt
    #: „nur auf Anstoß" — dann zeichnet der Renderer nicht von selbst.
    fps: int = 15
    profil: Profil | None = None

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
