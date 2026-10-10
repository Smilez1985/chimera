"""Dienstprotokoll als Datei im Arbeitsspeicher (DESIGN Regel 10r).

Unter systemd geht die Ausgabe ins Journal. Das reicht nicht: DietPi hält
``/var/log`` im RAM und leert es stündlich, und das Journal ist nach einem
Neustart je nach Einstellung weg. Deshalb schreibt der Dienst zusätzlich
eine Datei nach ``$CHIMERA_LOG_RAM`` (tmpfs, ``RuntimeDirectory=`` der
Unit). Auf die Karte bringt sie ``installer/bin/log-abgleich.sh`` —
beim Stoppen und in Ruhezeiten. Python gleicht selbst nichts ab: Ein
zweiter Abgleichsweg wäre eine Doppelimplementierung.

* **Eine Datei je Start** (``dienst-<zeit>.log``). Mit einem festen Namen
  überschriebe der nächste Start beim Abgleich das Protokoll des vorigen —
  ausgerechnet das, das man nach einem Absturz lesen will.
* **Größendeckel hier**, weil ``/run`` klein ist (auf dem Pi Zero 2 W rund
  90 MiB, geteilt mit dem ganzen System): ab ``GROESSE`` Byte wird in
  Stücke ``dienst-<zeit>.1.log`` … geteilt, höchstens ``STUECKE``. Wie
  viele Dateien auf der Karte bleiben, regelt ``log_rotate`` in
  ``common.sh``.
"""
from __future__ import annotations

import logging
import logging.handlers
import os
import time
from pathlib import Path

GROESSE = 1 << 20   # 1 MiB je Datei
STUECKE = 3         # ältere Stücke neben der laufenden Datei
FORMAT = "%(asctime)s %(levelname)-7s %(name)s: %(message)s"

log = logging.getLogger(__name__)


def _namer(name: str) -> str:
    """``dienst-X.log.1`` → ``dienst-X.1.log``.

    Die Endung ``.log`` muss hinten bleiben: ``log_sync`` und
    ``log_rotate`` sehen nur ``*.log``. Ein Stück mit ``.log.1`` fiele beim
    Abgleich stumm heraus.
    """
    kopf, punkt, nummer = name.rpartition(".")
    if punkt and nummer.isdigit() and kopf.endswith(".log"):
        return f"{kopf[:-4]}.{nummer}.log"
    return name


def datei_einrichten(env=None, jetzt: float | None = None,
                     logger: logging.Logger | None = None) -> Path | None:
    """Datei-Handler an ``logger`` (Vorgabe: Wurzel) hängen.

    Rückgabe der Pfad der Datei, oder ``None``, wenn keiner eingerichtet
    wurde. Scheitert das Einrichten, läuft der Dienst weiter — mit einer
    Warnung im Journal. Protokollieren ist Nebensache; es darf den Dienst
    nicht beenden.
    """
    env = os.environ if env is None else env
    ziel = (env.get("CHIMERA_LOG_RAM") or "").strip()
    if not ziel:
        log.info("CHIMERA_LOG_RAM nicht gesetzt — Protokoll nur im Journal.")
        return None
    stempel = time.strftime("%Y%m%d-%H%M%S",
                            time.localtime(time.time() if jetzt is None else jetzt))
    pfad = Path(ziel) / f"dienst-{stempel}.log"
    try:
        pfad.parent.mkdir(parents=True, exist_ok=True)
        h = logging.handlers.RotatingFileHandler(
            pfad, maxBytes=GROESSE, backupCount=STUECKE, encoding="utf-8")
    except OSError as exc:
        log.warning("Protokolldatei nicht anlegbar (%s): %s — nur Journal.",
                    pfad, exc)
        return None
    h.namer = _namer
    h.setFormatter(logging.Formatter(FORMAT))
    (logger or logging.getLogger()).addHandler(h)
    log.info("Protokoll: %s", pfad)
    return pfad
