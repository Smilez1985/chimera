"""GPIO über das Zeichengerät des Kernels (``/dev/gpiochipN``, ABI v2).

Ohne Fremdpaket. Die Python-Bindung ``gpiod`` gibt es in zwei unverträglichen
Fassungen (v1 auf Debian 12, v2 ab Debian 13 und per pip); der
Herstellertreiber der Whisplay trägt deshalb eine eigene Anpassschicht. Der
Kernel-ABI darunter ist seit Linux 5.10 fest. Ihn direkt zu benutzen kostet
vier Strukturen und spart die Abhängigkeit samt Versionsfrage.

Strukturen nach ``include/uapi/linux/gpio.h``. Die Größen sind kein
Rechenergebnis, sondern am Gerät gegen die Kernelkonstanten geprüft
(Pi Zero 2 W, Kernel 6.18, aarch64): Anfrage 592, Konfiguration 272,
Werte 16 Byte. Ein ``ioctl`` mit falscher Größe wird vom Kernel mit
``ENOTTY`` abgewiesen -- ein falsches Layout fällt also auf, es rät nicht.
"""

from __future__ import annotations

import ctypes
import errno
import fcntl
import os
import select

LINES_MAX = 64
NUM_ATTRS_MAX = 10
NAME_SIZE = 32

FLAG_ACTIVE_LOW = 1 << 1
FLAG_INPUT = 1 << 2
FLAG_OUTPUT = 1 << 3
FLAG_EDGE_RISING = 1 << 4
FLAG_EDGE_FALLING = 1 << 5
FLAG_BIAS_PULL_UP = 1 << 8
FLAG_BIAS_PULL_DOWN = 1 << 9
FLAG_BIAS_DISABLED = 1 << 10

#: Was ein Ereignis ist: 1 = steigende Flanke, 2 = fallende
#: (``enum gpio_v2_line_event_id`` in ``include/uapi/linux/gpio.h``).
EREIGNIS_STEIGEND = 1
EREIGNIS_FALLEND = 2


ATTR_FLAGS = 1
ATTR_OUTPUT_VALUES = 2


class _LineAttribute(ctypes.Structure):
    _fields_ = [("id", ctypes.c_uint32), ("padding", ctypes.c_uint32),
                ("value", ctypes.c_uint64)]


class _LineConfigAttribute(ctypes.Structure):
    _fields_ = [("attr", _LineAttribute), ("mask", ctypes.c_uint64)]


class _LineConfig(ctypes.Structure):
    _fields_ = [("flags", ctypes.c_uint64), ("num_attrs", ctypes.c_uint32),
                ("padding", ctypes.c_uint32 * 5),
                ("attrs", _LineConfigAttribute * NUM_ATTRS_MAX)]


class _LineRequest(ctypes.Structure):
    _fields_ = [("offsets", ctypes.c_uint32 * LINES_MAX),
                ("consumer", ctypes.c_char * NAME_SIZE),
                ("config", _LineConfig),
                ("num_lines", ctypes.c_uint32),
                ("event_buffer_size", ctypes.c_uint32),
                ("padding", ctypes.c_uint32 * 5),
                ("fd", ctypes.c_int32)]


class _LineValues(ctypes.Structure):
    _fields_ = [("bits", ctypes.c_uint64), ("mask", ctypes.c_uint64)]


class _LineEvent(ctypes.Structure):
    """Ein Kantenereignis, wie der Kernel es auf den Zeilen-FD schreibt.

    ``id`` sagt, welche Flanke (1 steigend, 2 fallend), ``offset`` welche
    Leitung. Die Groesse ist kein Rechenergebnis: Der Kernel liefert bei
    ``read()`` genau diesen Satz, geprueft gegen ``struct gpio_v2_line_event``
    (8 + 4*4 + 6*4 = 48 Byte).
    """
    _fields_ = [("timestamp_ns", ctypes.c_uint64),
                ("id", ctypes.c_uint32),
                ("offset", ctypes.c_uint32),
                ("seqno", ctypes.c_uint32),
                ("line_seqno", ctypes.c_uint32),
                ("padding", ctypes.c_uint32 * 6)]


assert ctypes.sizeof(_LineRequest) == 592, ctypes.sizeof(_LineRequest)
assert ctypes.sizeof(_LineConfig) == 272, ctypes.sizeof(_LineConfig)
assert ctypes.sizeof(_LineValues) == 16, ctypes.sizeof(_LineValues)
assert ctypes.sizeof(_LineEvent) == 48, ctypes.sizeof(_LineEvent)


def _iowr(nr: int, size: int) -> int:
    return (3 << 30) | (size << 16) | (0xB4 << 8) | nr


GET_LINE = _iowr(0x07, ctypes.sizeof(_LineRequest))
GET_VALUES = _iowr(0x0E, ctypes.sizeof(_LineValues))
SET_VALUES = _iowr(0x0F, ctypes.sizeof(_LineValues))


class LeitungBelegt(OSError):
    """Eine Leitung gehört schon einem anderen Prozess.

    Das ist der Fall „laufender Dienst hält die Pins" -- für die Erkennung
    ein eigener Befund, kein allgemeiner Fehler.
    """


class Leitungen:
    """Ein Satz Leitungen eines Chips, in einer Anfrage belegt.

    ``ausgaenge``: ``{offset: anfangswert}``; ``eingaenge``: ``{offset: bias}``
    mit bias ``"hoch"``, ``"runter"`` oder ``None``. Belegt wird mit
    ``request``, freigegeben mit ``close`` (auch als Kontextmanager).
    """

    def __init__(self, chip: str = "/dev/gpiochip0", *, verbraucher: str = "chimera"):
        self.chip = chip
        self.verbraucher = verbraucher
        self._fd = -1
        self._index: dict[int, int] = {}
        self._kanten = False
        # Ereignisse fremder Leitungen werden nicht verworfen, sondern
        # aufgehoben: Wer nach Leitung filtert, soll die anderen nicht
        # verschlucken (ein verlorenes Tastenereignis faellt niemandem auf).
        self._puffer: list[tuple[int, str]] = []

    # --- Belegen / Freigeben ------------------------------------------------

    def request(self, ausgaenge: dict[int, int] | None = None,
                eingaenge: dict[int, str | None] | None = None,
                kanten: dict[int, str] | None = None) -> "Leitungen":
        """Leitungen belegen.

        ``kanten`` fordert fuer Eingaenge **Kantenereignisse** an
        (``"steigend"``, ``"fallend"``, ``"beide"``). Dann schreibt der
        Kernel bei jeder Flanke einen Satz auf den Zeilen-FD, und
        :meth:`ereignisse` wartet darauf — statt die Leitung im Takt
        abzufragen (am Pi gemessen: 200 ioctls je Sekunde fuer einen Taster,
        1,3 % eines Kerns im Leerlauf).
        """
        ausgaenge = dict(ausgaenge or {})
        eingaenge = dict(eingaenge or {})
        offsets = list(ausgaenge) + list(eingaenge)
        if not offsets:
            raise ValueError("keine Leitung angegeben")
        if len(offsets) > LINES_MAX:
            raise ValueError(f"mehr als {LINES_MAX} Leitungen")
        if len(set(offsets)) != len(offsets):
            raise ValueError("eine Leitung ist doppelt angegeben")

        anfrage = _LineRequest()
        for i, off in enumerate(offsets):
            anfrage.offsets[i] = off
        anfrage.num_lines = len(offsets)
        anfrage.consumer = self.verbraucher.encode()[:NAME_SIZE - 1]
        kanten = dict(kanten or {})
        ohne_eingang = [o for o in kanten if o not in eingaenge]
        if ohne_eingang:
            raise ValueError(f"Kanten nur fuer Eingaenge: {ohne_eingang}")
        if kanten:
            # Platz fuer mehrere Ereignisse im Kernel-Puffer, damit beim
            # Abholen nichts verlorengeht, wenn zwei Flanken kurz folgen.
            anfrage.event_buffer_size = 16

        # Grundflag: Ausgang, wenn es Ausgänge gibt, sonst Eingang. Die
        # abweichende Gruppe bekommt ihr Flag über ein Attribut mit Maske.
        attrs = []
        if ausgaenge:
            anfrage.config.flags = FLAG_OUTPUT
            werte = 0
            maske = 0
            for i, off in enumerate(offsets):
                if off in ausgaenge:
                    maske |= 1 << i
                    if ausgaenge[off]:
                        werte |= 1 << i
            attrs.append((ATTR_OUTPUT_VALUES, werte, maske))
        else:
            anfrage.config.flags = FLAG_INPUT
        # Eingaenge: Leitungen mit gleichem Flagsatz teilen sich eine Maske.
        # Bias und Kanten sind je Leitung verschieden, deshalb wird gruppiert
        # statt je Leitung ein Attribut zu setzen (davon gibt es nur zehn).
        gruppen: dict[int, int] = {}
        for i, off in enumerate(offsets):
            if off not in eingaenge:
                continue
            flags = (FLAG_INPUT | _bias_flag(eingaenge[off])
                     | _kanten_flag(kanten.get(off)))
            gruppen[flags] = gruppen.get(flags, 0) | (1 << i)
        for flags, maske in gruppen.items():
            attrs.append((ATTR_FLAGS, flags, maske))
        if len(attrs) > NUM_ATTRS_MAX:
            raise ValueError("zu viele verschiedene Leitungsarten")
        anfrage.config.num_attrs = len(attrs)
        for i, (art, wert, maske) in enumerate(attrs):
            anfrage.config.attrs[i].attr.id = art
            anfrage.config.attrs[i].attr.value = wert
            anfrage.config.attrs[i].mask = maske

        chip_fd = os.open(self.chip, os.O_RDWR | os.O_CLOEXEC)
        try:
            try:
                fcntl.ioctl(chip_fd, GET_LINE, anfrage)
            except OSError as exc:
                if exc.errno == errno.EBUSY:
                    raise LeitungBelegt(
                        errno.EBUSY, f"Leitung belegt auf {self.chip}: {offsets}") from exc
                raise
        finally:
            os.close(chip_fd)
        self._fd = anfrage.fd
        self._index = {off: i for i, off in enumerate(offsets)}
        self._kanten = bool(kanten)
        return self

    def close(self) -> None:
        if self._fd >= 0:
            os.close(self._fd)
            self._fd = -1
            self._index = {}
            self._kanten = False
            self._puffer = []

    def __enter__(self) -> "Leitungen":
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    @property
    def offen(self) -> bool:
        return self._fd >= 0

    # --- Werte ------------------------------------------------------------

    def setze(self, offset: int, wert: int) -> None:
        i = self._index[offset]
        v = _LineValues(bits=(1 << i) if wert else 0, mask=1 << i)
        fcntl.ioctl(self._fd, SET_VALUES, v)

    def setze_mehrere(self, werte: dict[int, int]) -> None:
        bits = 0
        maske = 0
        for off, w in werte.items():
            i = self._index[off]
            maske |= 1 << i
            if w:
                bits |= 1 << i
        v = _LineValues(bits=bits, mask=maske)
        fcntl.ioctl(self._fd, SET_VALUES, v)

    def lies(self, offset: int) -> int:
        i = self._index[offset]
        v = _LineValues(bits=0, mask=1 << i)
        fcntl.ioctl(self._fd, GET_VALUES, v)
        return 1 if v.bits & (1 << i) else 0

    # --- Kanten -----------------------------------------------------------

    def ereignisse(self, offset: int | None = None,
                   timeout: float | None = 1.0) -> list[tuple[int, str]]:
        """Auf Kantenereignisse warten — ohne Abfragen im Takt.

        ``timeout=None`` wartet ohne Grenze, sonst bis zu so vielen
        Sekunden. Rueckgabe: ``[(offset, "steigend"|"fallend")]``, bei
        Zeitablauf eine leere Liste. Nur Leitungen aus ``request(kanten=…)``
        melden etwas; wer ohne Kanten belegt hat, bekommt einen Fehler statt
        einer stillen Leere.
        """
        if self._fd < 0:
            raise OSError(errno.EBADF, "Leitung nicht belegt")
        if not self._kanten:
            raise RuntimeError("keine Kanten angefordert "
                               "(request(..., kanten={offset: art}))")
        # Zuerst, was beim letzten Mal fuer andere Leitungen kam: Ein
        # gefilterter Aufruf darf fremde Ereignisse nicht verschlucken.
        ergebnis: list[tuple[int, str]] = []
        uebrig: list[tuple[int, str]] = []
        for eintrag in self._puffer:
            if offset is None or eintrag[0] == offset:
                ergebnis.append(eintrag)
            else:
                uebrig.append(eintrag)
        self._puffer = uebrig
        if ergebnis:
            return ergebnis

        bereit, _, _ = select.select([self._fd], [], [], timeout)
        if not bereit:
            return []
        gross = ctypes.sizeof(_LineEvent)
        roh = os.read(self._fd, gross * 8)
        for i in range(0, len(roh) - gross + 1, gross):
            ereignis = _LineEvent.from_buffer_copy(roh[i:i + gross])
            if ereignis.id == EREIGNIS_STEIGEND:
                art = "steigend"
            elif ereignis.id == EREIGNIS_FALLEND:
                art = "fallend"
            else:
                continue
            if offset is not None and ereignis.offset != offset:
                self._puffer.append((ereignis.offset, art))
                continue
            ergebnis.append((ereignis.offset, art))
        return ergebnis


def _kanten_flag(art: str | None) -> int:
    if art is None:
        return 0
    if art == "steigend":
        return FLAG_EDGE_RISING
    if art == "fallend":
        return FLAG_EDGE_FALLING
    if art == "beide":
        return FLAG_EDGE_RISING | FLAG_EDGE_FALLING
    raise ValueError(f"unbekannte Kante: {art!r}")


def _bias_flag(bias: str | None) -> int:
    if bias == "hoch":
        return FLAG_BIAS_PULL_UP
    if bias == "runter":
        return FLAG_BIAS_PULL_DOWN
    if bias is None:
        return 0
    raise ValueError(f"unbekannter Bias: {bias!r}")
