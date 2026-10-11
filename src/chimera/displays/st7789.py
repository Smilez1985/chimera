"""ST7789-Kern: ein Panelbaustein, mehrere Platinen.

Whisplay (240×280, PiSugar) und GamePi13 (240×240, Waveshare) sitzen auf
demselben Baustein. Was sich unterscheidet, steht im ``Profil``: Pins,
Zeilenversatz im Panelspeicher, Ausrichtung, Takt und die Werte der
Einschaltfolge. Die Folge selbst -- Fenster setzen, Speicher schreiben --
ist für beide dieselbe.

Nachgebaut, nicht kopiert, aus zwei Vorlagen:
  * PiSugar ``runtime/whisplay.py`` (Apache-2.0), Stand c73051e6
  * Pimoroni ``st7789`` 1.0.1 (MIT, Kopf Adafruit 2014), wie auf dem
    GamePi13 von Noisy benutzt
Die Einschaltwerte je Platine sind die der Vorlage, Stelle für Stelle
(``profil.init``); eine Zeile ist nachgerechnet, nicht erfunden.

Lesen der Kennung (``0xDA``/``0xDB``/``0xDC``) geht nur im 3-Draht-Modus
über SDA; beide Platinen liefern ``81 81 B3`` (gemessen 11.10.2026).
Die Kennung sagt „ein ST7789 an spidev0.0", nicht welche Platine.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field

from .gpio import Leitungen
from .spi import Spi

SWRESET = 0x01
SLPOUT = 0x11
INVON = 0x21
DISPON = 0x29
CASET = 0x2A
RASET = 0x2B
RAMWR = 0x2C
MADCTL = 0x36
COLMOD = 0x3A

RDID1, RDID2, RDID3 = 0xDA, 0xDB, 0xDC
KENNUNG_BEKANNT = b"\x81\x81\xb3"


@dataclass
class Profil:
    """Was eine Platine vom ST7789-Kern unterscheidet."""

    breite: int
    hoehe: int
    dc: int                 # BCM-Nummer der DC-Leitung
    rst: int | None         # Reset-Leitung, None = nur Software-Reset
    versatz_x: int = 0
    versatz_y: int = 0
    takt_hz: int = 40_000_000
    madctl: int = 0x00
    invertiert: bool = True
    #: Einschaltfolge nach dem Reset: (Befehl, Datenbytes) in Reihenfolge.
    init: tuple[tuple[int, bytes], ...] = field(default_factory=tuple)
    #: Wartezeit nach SLPOUT, bevor der Baustein Daten annimmt.
    slpout_wartezeit: float = 0.12
    gpiochip: str = "/dev/gpiochip0"
    spi_bus: int = 0
    spi_cs: int = 0


class St7789:
    """Treiber für ein Profil. Öffnet SPI und Leitungen beim Anlegen."""

    def __init__(self, profil: Profil, *, verbraucher: str = "chimera-st7789"):
        self.p = profil
        ausgaenge = {profil.dc: 0}
        if profil.rst is not None:
            ausgaenge[profil.rst] = 1
        self._gpio = Leitungen(profil.gpiochip, verbraucher=verbraucher).request(ausgaenge=ausgaenge)
        try:
            self._spi = Spi(profil.spi_bus, profil.spi_cs, takt_hz=profil.takt_hz)
        except OSError:
            self._gpio.close()
            raise

    # --- Niedrig ------------------------------------------------------------

    def befehl(self, cmd: int, daten: bytes = b"") -> None:
        self._gpio.setze(self.p.dc, 0)
        self._spi.schreibe(bytes([cmd]))
        if daten:
            self._gpio.setze(self.p.dc, 1)
            self._spi.schreibe(daten)

    def daten(self, daten: bytes | bytearray | memoryview) -> None:
        self._gpio.setze(self.p.dc, 1)
        self._spi.schreibe(daten)

    def reset(self) -> None:
        if self.p.rst is not None:
            self._gpio.setze(self.p.rst, 1)
            time.sleep(0.1)
            self._gpio.setze(self.p.rst, 0)
            time.sleep(0.1)
            self._gpio.setze(self.p.rst, 1)
            time.sleep(0.12)
        else:
            self.befehl(SWRESET)
            time.sleep(0.15)

    # --- Einschalten --------------------------------------------------------

    def einschalten(self) -> None:
        self.reset()
        for cmd, daten in self.p.init:
            self.befehl(cmd, daten)
            if cmd == SLPOUT:
                time.sleep(self.p.slpout_wartezeit)
        time.sleep(0.1)

    def kennung(self) -> bytes:
        """Drei Kennungsbytes lesen. DC muss dafür unten sein."""
        self._gpio.setze(self.p.dc, 0)
        return b"".join(self._spi.lies_3draht(c, 1) for c in (RDID1, RDID2, RDID3))

    # --- Zeichnen -----------------------------------------------------------

    def fenster(self, x0: int, y0: int, x1: int, y1: int) -> None:
        x0 += self.p.versatz_x
        x1 += self.p.versatz_x
        y0 += self.p.versatz_y
        y1 += self.p.versatz_y
        self.befehl(CASET, bytes([x0 >> 8, x0 & 0xFF, x1 >> 8, x1 & 0xFF]))
        self.befehl(RASET, bytes([y0 >> 8, y0 & 0xFF, y1 >> 8, y1 & 0xFF]))
        self.befehl(RAMWR)

    def schreibe_bild(self, rgb565: bytes | bytearray | memoryview,
                      x: int = 0, y: int = 0, breite: int | None = None,
                      hoehe: int | None = None) -> None:
        breite = self.p.breite if breite is None else breite
        hoehe = self.p.hoehe if hoehe is None else hoehe
        erwartet = breite * hoehe * 2
        if len(rgb565) != erwartet:
            raise ValueError(f"RGB565: {len(rgb565)} Byte, erwartet {erwartet}")
        self.fenster(x, y, x + breite - 1, y + hoehe - 1)
        self.daten(rgb565)

    def close(self) -> None:
        self._spi.close()
        self._gpio.close()


# --- Erkennung ohne Treiber ------------------------------------------------

def kennung_lesen(dc: int, rst: int | None, *, gpiochip: str = "/dev/gpiochip0",
                  spi_bus: int = 0, spi_cs: int = 0) -> bytes:
    """Kennung lesen und alles wieder freigeben.

    Mit Reset-Leitung wird vorher hart zurückgesetzt, ohne per Software.
    Belegte Leitungen schlagen als ``LeitungBelegt`` durch -- das ist für
    die Erkennung ein eigener Befund („Dienst läuft"), kein „kein Panel".
    """
    ausgaenge = {dc: 0}
    if rst is not None:
        ausgaenge[rst] = 1
    with Leitungen(gpiochip, verbraucher="chimera-erkennung").request(ausgaenge=ausgaenge) as g:
        with Spi(spi_bus, spi_cs, takt_hz=500_000) as s:
            if rst is not None:
                g.setze(rst, 0)
                time.sleep(0.02)
                g.setze(rst, 1)
            else:
                s.schreibe(bytes([SWRESET]))
            time.sleep(0.15)
            g.setze(dc, 0)
            return b"".join(s.lies_3draht(c, 1) for c in (RDID1, RDID2, RDID3))
