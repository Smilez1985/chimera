"""Bildausgabe auf das Whisplay-Panel.

Das Verfahren ist dasselbe wie bei Noisy auf dem GamePi13: Ein Bild wird
mit Pillow im Arbeitsspeicher gezeichnet und **als Ganzes** über SPI in den
Panelspeicher geschoben. Kein Zwischenspeichern auf dem Datenträger, keine
Bilddateien.

Unterschiede zwischen den beiden Anschlüssen, die hier gekapselt werden:

* Noisy benutzt die Bibliothek ``st7789``, die das Bild selbst entgegennimmt
  (``display(image)``). Die Whisplay bringt eine eigene Klasse mit, die
  **fertige Bytes** erwartet (``draw_image(x, y, w, h, daten)``). Der
  Panel-Befehlssatz darunter ist derselbe — Fensterbereich setzen (0x2A/0x2B),
  Schreiben beginnen (0x2C), Daten schieben.
* Das Panel ist 240×280 und sitzt mit einem Versatz von 20 Zeilen im
  Speicher des Bausteins. Das erledigt die Whisplay-Klasse selbst.

**Das eigentliche Problem liegt woanders**: in der Umrechnung nach RGB565.
Das Beispiel des Herstellers geht Bildpunkt für Bildpunkt durch zwei
Python-Schleifen — 67 200 Durchläufe je Bild. Gemessen in der
Entwicklungsumgebung (aarch64, deutlich schneller als ein Pi Zero 2 W):

    Bildpunktweise:  62,9 ms je Bild
    Mit numpy:        2,5 ms je Bild   (25-mal schneller, gleiches Ergebnis)

Bei 15 Bildern je Sekunde stehen 66,7 ms zur Verfügung — für *alles*,
Zeichnen eingeschlossen. Die bildpunktweise Fassung verbraucht dieses
Budget allein schon auf schnellerer Hardware. Sie ist hier deshalb nur der
Rückfall, wenn numpy fehlt, und meldet das auch.
"""

from __future__ import annotations

import logging

log = logging.getLogger(__name__)

try:
    import numpy as _np
except ImportError:  # pragma: no cover - auf dem Zielgerät vorhanden
    _np = None


def to_rgb565(image) -> bytes:
    """Ein Pillow-Bild in den Speicherinhalt des Panels umrechnen.

    Big-Endian, zwei Byte je Bildpunkt: 5 Bit Rot, 6 Bit Grün, 5 Bit Blau.
    """
    rgb = image.convert("RGB")

    if _np is not None:
        a = _np.asarray(rgb, dtype=_np.uint16)
        v = (
            ((a[:, :, 0] & 0xF8) << 8)
            | ((a[:, :, 1] & 0xFC) << 3)
            | (a[:, :, 2] >> 3)
        )
        return v.astype(">u2").tobytes()

    # Rückfall. Auf einem Pi Zero 2 W reicht das nicht für flüssige
    # Darstellung -- deshalb die Warnung, statt es stillschweigend
    # langsam zu machen.
    log.warning(
        "numpy fehlt — RGB565 wird bildpunktweise gerechnet, das ist rund "
        "25-mal langsamer und hält keine 15 Bilder je Sekunde."
    )
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

    #: Wie oft dieses Panel gezeichnet werden will (Regel 7a). Die Bildrate
    #: ist eine Eigenschaft der Anzeige, nicht des Renderers: Ein LCD will
    #: 15 Bilder je Sekunde, E-Ink eines alle paar Sekunden. ``0`` heißt
    #: „nur auf Anstoß" — dann zeichnet der Renderer nicht von selbst.
    #: Damit bleibt der Renderer für beide Fälle derselbe Code.
    fps: int = 15

    def show(self, image) -> None:
        raise NotImplementedError

    def backlight(self, percent: int) -> None:
        pass

    def led(self, r: int, g: int, b: int) -> None:
        pass

    def close(self) -> None:
        pass


class WhisplayPanel(Panel):
    """Das echte Panel über die Whisplay-Bibliothek.

    Erwartet ``whisplay`` aus PiSugars Treiberpaket. Die Klasse dort kümmert
    sich um SPI, Fensterbereich und den Zeilenversatz; hier bleibt nur die
    Umrechnung und die Prüfung der Bildgröße.
    """

    #: Ein LCD hat kein Ghosting und keine Wartezeit zwischen Bildern —
    #: hier ist Animation der Normalfall (Regel 7a). 15 ist Noisys
    #: erprobter Wert auf einem Zero 2 W.
    fps = 15

    def __init__(self, board=None, *, fps: int | None = None) -> None:
        if board is None:
            from whisplay import WhisplayBoard  # type: ignore

            board = WhisplayBoard()
        self._board = board
        self.width = getattr(board, "LCD_WIDTH", 240)
        self.height = getattr(board, "LCD_HEIGHT", 280)
        if fps is not None:
            self.fps = int(fps)

    def show(self, image) -> None:
        if image.size != (self.width, self.height):
            # Bewusst kein stilles Skalieren: Eine falsche Bildgröße ist ein
            # Fehler im Renderer, und stillschweigend zurechtgezogene Bilder
            # verstecken ihn (Regel 8a).
            raise ValueError(
                f"Bild ist {image.size}, Panel erwartet "
                f"({self.width}, {self.height})"
            )
        self._board.draw_image(0, 0, self.width, self.height, to_rgb565(image))

    def backlight(self, percent: int) -> None:
        self._board.set_backlight(max(0, min(100, int(percent))))

    def led(self, r: int, g: int, b: int) -> None:
        self._board.set_rgb(int(r), int(g), int(b))

    def close(self) -> None:
        try:
            self._board.cleanup()
        except Exception:  # pragma: no cover
            pass


class NullPanel(Panel):
    """Panel ohne Panel — zählt nur, was ankäme.

    Für Entwicklung ohne Gerät und für Messungen: Wie lange braucht das
    Zeichnen, wie lange die Umrechnung, ohne dass SPI dazwischenfunkt.
    """

    def __init__(self, width: int = 240, height: int = 280,
                 *, convert: bool = True, fps: int = 15) -> None:
        self.width, self.height = width, height
        self.convert = convert
        self.fps = fps
        self.frames = 0
        self.last: bytes | None = None

    def show(self, image) -> None:
        if image.size != (self.width, self.height):
            raise ValueError(
                f"Bild ist {image.size}, Panel erwartet "
                f"({self.width}, {self.height})"
            )
        if self.convert:
            self.last = to_rgb565(image)
        self.frames += 1


def open_panel(kind: str = "auto", **kw) -> Panel:
    """Panel öffnen. ``auto`` nimmt das echte, wenn es erreichbar ist."""
    if kind in ("auto", "whisplay"):
        try:
            return WhisplayPanel(**kw)
        except Exception as exc:
            if kind == "whisplay":
                raise
            log.info("Kein Whisplay-Panel (%s) — ohne Anzeige weiter.", exc)
    return NullPanel(**{k: v for k, v in kw.items() if k in ("width", "height", "convert")})
