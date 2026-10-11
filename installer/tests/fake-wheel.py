#!/usr/bin/env python3
"""Baut ein winziges, reines Python-Wheel ohne Netz -- fuer Tests.

Aufruf: fake-wheel.py <zielverzeichnis> <name> <version>

Das Wheel enthaelt nur ein leeres Modul <name>.py. Damit laesst sich der
echte `pip install`-Weg eines Installerschritts fahren (pip findet das
Paket ueber PIP_FIND_LINKS), ohne dass ein Quellbau (spidev braucht
Python-Header und gcc) oder PyPI im Spiel ist.
"""
import base64
import hashlib
import sys
import zipfile
from pathlib import Path

ziel, name, version = Path(sys.argv[1]), sys.argv[2], sys.argv[3]
ziel.mkdir(parents=True, exist_ok=True)
info = f"{name}-{version}.dist-info"
dateien = {
    f"{name}.py": f"# Attrappe {name} {version} (Test)\n__version__ = {version!r}\n",
    f"{info}/METADATA": f"Metadata-Version: 2.1\nName: {name}\nVersion: {version}\n",
    f"{info}/WHEEL": "Wheel-Version: 1.0\nGenerator: chimera-test\n"
                     "Root-Is-Purelib: true\nTag: py3-none-any\n",
}


def zeile(pfad, inhalt):
    roh = inhalt.encode()
    sha = base64.urlsafe_b64encode(hashlib.sha256(roh).digest()).rstrip(b"=").decode()
    return f"{pfad},sha256={sha},{len(roh)}"


record = "\n".join(zeile(p, i) for p, i in dateien.items()) + f"\n{info}/RECORD,,\n"
whl = ziel / f"{name}-{version}-py3-none-any.whl"
with zipfile.ZipFile(whl, "w") as z:
    for p, i in dateien.items():
        z.writestr(p, i)
    z.writestr(f"{info}/RECORD", record)
print(whl)
