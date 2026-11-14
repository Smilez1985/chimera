"""Die Felder des Statusbereichs — ein Modul je Feld.

Die Liste wird **aus diesem Verzeichnis gelesen** (Regel „Anzeigefelder"):
Jedes Modul ohne führenden Unterstrich, das ein ``FELD`` anbietet, ist ein
Feld. Ein neues Feld ist damit eine neue Datei — kein Katalog, den jemand
nachpflegen muss, keine Änderung an ``statusline.py``.

Dasselbe Auffindemuster wie :mod:`chimera.agent.skills`: Verzeichnis
durchsuchen, Kopfteil lesen, Unbrauchbares **überspringen und benennen**
statt abstürzen. Ein kaputtes Feld darf das Gesicht nicht anhalten.
"""

from __future__ import annotations

import importlib
import logging
import pkgutil

from ..feld import Feld

__all__ = ["alle", "ladeprobleme"]

log = logging.getLogger("chimera.display.felder")

#: Was beim Laden schiefging — von ``statusline`` abgeholt und gemeldet,
#: statt still zu verschwinden (Regel 8a).
ladeprobleme: list[str] = []


def alle() -> list[Feld]:
    """Alle Felder dieses Verzeichnisses, sortiert nach Priorität."""
    felder: list[Feld] = []
    gesehen: list[str] = []
    for eintrag in sorted(pkgutil.iter_modules(__path__), key=lambda m: m.name):
        if eintrag.name.startswith("_"):
            continue
        try:
            modul = importlib.import_module(f"{__name__}.{eintrag.name}")
        except Exception as exc:               # noqa: BLE001
            grund = f"{eintrag.name}: nicht ladbar ({type(exc).__name__}: {exc})"
            log.warning("Feld %s", grund)
            ladeprobleme.append(grund)
            continue
        feld = getattr(modul, "FELD", None)
        if not isinstance(feld, Feld):
            grund = f"{eintrag.name}: kein FELD (Feld-Objekt) im Modul"
            log.warning("Feld %s", grund)
            ladeprobleme.append(grund)
            continue
        if feld.name in gesehen:
            grund = f"{eintrag.name}: Name {feld.name!r} doppelt"
            log.warning("Feld %s", grund)
            ladeprobleme.append(grund)
            continue
        gesehen.append(feld.name)
        felder.append(feld)
    return sorted(felder, key=lambda f: (f.prioritaet, f.name))
