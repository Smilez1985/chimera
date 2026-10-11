"""SPI über ``/dev/spidevB.C`` -- ohne das Paket ``spidev``.

``spidev`` aus pip baut auf dem Pi aus Quelltext und braucht dafür die
Python-Header (gemessen am chimera-pi, 11.10.2026: ``python3-dev`` nötig).
Was das Paket tut, sind drei ``ioctl``-Aufrufe und ein ``write``; die stehen
hier, nach ``include/uapi/linux/spi/spidev.h``.

Schreiben geht über ``os.write`` (schnellster Weg, ein Systemaufruf je
Block). Lesen braucht den 3-Draht-Modus und eine zusammenhängende
Nachricht aus Befehl und Antwort, damit CS zwischen beiden unten bleibt --
die ST7789-Panels am Whisplay und am GamePi13 haben keine MISO-Leitung,
sie antworten auf SDA (Schaltplan PiSugar, gemessen 11.10.2026).
"""

from __future__ import annotations

import ctypes
import fcntl
import os

# Die Kernel-Schreibgrenze für eine SPI-Übertragung ist bufsiz des
# spidev-Moduls (Vorgabe 4096). Größere Blöcke lehnt write() ab.
BLOCK = 4096

SPI_MODE_0 = 0
SPI_3WIRE = 0x10

_IOC_WRITE = 1
_IOC_READ = 2


def _ioc(richtung: int, nr: int, groesse: int) -> int:
    return (richtung << 30) | (groesse << 16) | (ord("k") << 8) | nr


WR_MODE = _ioc(_IOC_WRITE, 1, 1)
WR_BITS = _ioc(_IOC_WRITE, 3, 1)
WR_SPEED = _ioc(_IOC_WRITE, 4, 4)


class _Transfer(ctypes.Structure):
    _fields_ = [("tx_buf", ctypes.c_uint64), ("rx_buf", ctypes.c_uint64),
                ("len", ctypes.c_uint32), ("speed_hz", ctypes.c_uint32),
                ("delay_usecs", ctypes.c_uint16), ("bits_per_word", ctypes.c_uint8),
                ("cs_change", ctypes.c_uint8), ("tx_nbits", ctypes.c_uint8),
                ("rx_nbits", ctypes.c_uint8), ("word_delay_usecs", ctypes.c_uint8),
                ("pad", ctypes.c_uint8)]


assert ctypes.sizeof(_Transfer) == 32, ctypes.sizeof(_Transfer)


def _message(n: int) -> int:
    return _ioc(_IOC_WRITE, 0, n * ctypes.sizeof(_Transfer))


class Spi:
    """Ein geöffnetes ``spidev``-Gerät."""

    def __init__(self, bus: int = 0, cs: int = 0, *, takt_hz: int = 1_000_000):
        self.pfad = f"/dev/spidev{bus}.{cs}"
        self.takt_hz = int(takt_hz)
        self._fd = os.open(self.pfad, os.O_RDWR | os.O_CLOEXEC)
        try:
            fcntl.ioctl(self._fd, WR_MODE, bytes([SPI_MODE_0]))
            fcntl.ioctl(self._fd, WR_BITS, bytes([8]))
            fcntl.ioctl(self._fd, WR_SPEED, ctypes.c_uint32(self.takt_hz))
        except OSError:
            os.close(self._fd)
            raise

    def close(self) -> None:
        if self._fd >= 0:
            os.close(self._fd)
            self._fd = -1

    def __enter__(self) -> "Spi":
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    def schreibe(self, daten: bytes | bytearray | memoryview) -> None:
        """Daten in Blöcken schreiben, jeder Block vollständig."""
        sicht = memoryview(daten)
        for start in range(0, len(sicht), BLOCK):
            block = sicht[start:start + BLOCK]
            geschrieben = os.write(self._fd, block)
            if geschrieben != len(block):
                raise OSError(f"SPI: {geschrieben} von {len(block)} Byte geschrieben")

    def lies_3draht(self, befehl: int, anzahl: int, *, takt_hz: int = 500_000) -> bytes:
        """Befehl senden und Antwort auf derselben Datenleitung lesen.

        Beides in EINER Nachricht, sonst hebt der Treiber CS zwischen
        Befehl und Antwort an und das Panel vergisst den Befehl.
        Danach steht der Modus wieder auf 4-Draht.
        """
        tx = (ctypes.c_uint8 * 1)(befehl)
        rx = (ctypes.c_uint8 * anzahl)()
        t = (_Transfer * 2)()
        t[0].tx_buf = ctypes.addressof(tx)
        t[0].len = 1
        t[0].speed_hz = takt_hz
        t[0].bits_per_word = 8
        t[1].rx_buf = ctypes.addressof(rx)
        t[1].len = anzahl
        t[1].speed_hz = takt_hz
        t[1].bits_per_word = 8
        fcntl.ioctl(self._fd, WR_MODE, bytes([SPI_MODE_0 | SPI_3WIRE]))
        try:
            fcntl.ioctl(self._fd, _message(2), t)
        finally:
            fcntl.ioctl(self._fd, WR_MODE, bytes([SPI_MODE_0]))
        return bytes(rx)
