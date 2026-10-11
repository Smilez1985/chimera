"""I2C-Anwesenheitsprüfung über ``/dev/i2c-N`` -- ohne ``i2c-tools``.

Macht, was ``i2cdetect -y N`` für Adressen außerhalb 0x30–0x37 und
0x50–0x5F tut: eine SMBus-„Quick"-Schreibanfrage. Antwortet der Chip mit
ACK, ist er da. Ein Register lesen können wir nicht voraussetzen -- der
WM8960 der Whisplay ist ein reiner Schreibchip (gemessen 11.10.2026:
``i2cget`` scheitert, Quick-Write trifft).

Zwei Quellen, in dieser Reihenfolge:
  1. Sysfs ``/sys/bus/i2c/devices/N-00aa``: ein Treiber hält den Chip --
     dann ist er sicher da (``i2cdetect`` zeigt dort ``UU``).
  2. Quick-Write über ``/dev/i2c-N`` (braucht das Modul ``i2c-dev``).
Fehlt beides, ist das Ergebnis „nicht prüfbar", nicht „nicht da".
"""

from __future__ import annotations

import ctypes
import errno
import fcntl
import os
from pathlib import Path

I2C_SLAVE_FORCE = 0x0706
I2C_SMBUS = 0x0720
I2C_SMBUS_WRITE = 0
I2C_SMBUS_QUICK = 0


class _SmbusIoctl(ctypes.Structure):
    _fields_ = [("read_write", ctypes.c_uint8), ("command", ctypes.c_uint8),
                ("size", ctypes.c_uint32), ("data", ctypes.c_void_p)]


def chip_da(bus: int, adresse: int, *, root: str = "") -> bool | None:
    """True = antwortet, False = antwortet nicht, None = nicht prüfbar."""
    sysfs = Path(f"{root}/sys/bus/i2c/devices/{bus}-{adresse:04x}")
    if sysfs.is_dir():
        return True
    dev = f"{root}/dev/i2c-{bus}"
    if not os.path.exists(dev):
        return None
    try:
        fd = os.open(dev, os.O_RDWR | os.O_CLOEXEC)
    except OSError:
        return None
    try:
        fcntl.ioctl(fd, I2C_SLAVE_FORCE, adresse)
        anfrage = _SmbusIoctl(read_write=I2C_SMBUS_WRITE, command=0,
                              size=I2C_SMBUS_QUICK, data=None)
        try:
            fcntl.ioctl(fd, I2C_SMBUS, anfrage)
            return True
        except OSError as exc:
            if exc.errno in (errno.EREMOTEIO, errno.ENXIO, errno.EIO, errno.ETIMEDOUT):
                return False
            return None
    finally:
        os.close(fd)


def bus_da(bus: int, *, root: str = "") -> bool:
    """Ist der Bus beim Kernel registriert (unabhängig von ``i2c-dev``)?"""
    return Path(f"{root}/sys/bus/i2c/devices/i2c-{bus}").exists()

def dev_bereitstellen(bus: int, *, root: str = "") -> bool:
    """``/dev/i2c-N`` herstellen, wenn es fehlt und wir dürfen.

    Vor dem Dienst (Boot-Abgleich als root) ist kein Codec-Treiber gebunden
    -- der Sysfs-Weg schweigt dann, und ohne ``i2c-dev`` fehlt auch das
    Gerät. Gemessen chimera-pi 11.10.2026: ohne Overlay weder ``1-001a``
    noch ``/dev/i2c-1``. Als root wird das Modul geladen; sonst bleibt es
    beim Befund „nicht prüfbar". Rückgabe: Gerät vorhanden.
    """
    dev = f"{root}/dev/i2c-{bus}"
    if os.path.exists(dev):
        return True
    if root or os.geteuid() != 0:
        return False
    import subprocess
    try:
        subprocess.run(["modprobe", "i2c-dev"], check=False, timeout=10,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except (OSError, subprocess.TimeoutExpired):
        return False
    return os.path.exists(dev)
