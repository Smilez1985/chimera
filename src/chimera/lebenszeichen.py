"""Lebenszeichen an systemd (DESIGN, Regel „Lebenszeichen", 14.11.2026).

**Warum es das gibt.** Mojo prüft stündlich und bei `OnFailure`. Ein Dienst,
der läuft, aber **hängt** (kein Absturz), fällt damit bis zu einer Stunde
nicht auf — auf einem Gerät, das unbeaufsichtigt im Wohnzimmer steht, ist eine
Stunde Stille von gewolltem Nichtstun nicht zu unterscheiden.

**Die Bauform (Entscheidung smilez: hybrid).**

* Das Lebenszeichen kommt aus einem **eigenen Faden**. Käme es aus dem
  Hauptfaden, wäre es genau dann still, wenn ein Aufruf hängt — und würde im
  schlimmsten Fall einen hängenden Aufruf als gesund melden.
* Der Hauptfaden (bzw. der Faden, der einen Turn rechnet) darf **`busy`** mit
  einer Frist setzen: Solange sie läuft, gilt ein Ausbleiben von Fortschritt
  als erwartet. `busy` verlängert die Geduld, es ersetzt sie nicht — die
  Obergrenze steht in der Frist selbst.
* Bleibt der Fortschritt über die erlaubte Stille hinaus aus, wird **kein**
  `WATCHDOG=1` mehr geschickt; systemd startet nach `WatchdogSec` neu. Der
  Watchdog sagt „läuft nicht mehr", Mojo sagt danach **warum**.

**Zwei Uhren, mit Absicht.** Entschieden wird auf `time.monotonic()`: eine
springende Systemzeit (NTP auf einem Gerät ohne RTC) darf keinen Neustart
auslösen und keine Frist verlängern. In der Zustandsdatei steht die Frist
zusätzlich als Unix-Zeit — für Menschen und für Mojo, nicht für die
Entscheidung.

Fehlt `$NOTIFY_SOCKET` (Start von Hand, Test), läuft der Dienst weiter und
**sagt es**: stiller Erfolg wäre hier, dass niemand merkt, dass niemand
aufpasst.
"""

from __future__ import annotations

import json
import logging
import os
import socket
import threading
import time
from pathlib import Path

log = logging.getLogger(__name__)

__all__ = [
    "Melder", "erlaubte_stille", "beat_erlaubt",
    "setze_melder", "melder", "fortschritt", "busy",
    "WATCHDOG_S", "TAKT_S", "GRUND_S", "NACHLASS_S",
]

#: Was in der Unit als `WatchdogSec=` steht. Der Wert hier ist nur die
#: Vorgabe für den eigenen Takt; die Wahrheit ist die Unit.
WATCHDOG_S = 30.0
#: So oft wird geschlagen (ein Drittel der Frist: zwei verpasste Schläge
#: sind noch kein Ausfall).
TAKT_S = 10.0
#: Wie lange Fortschrittsstille **ohne** `busy` hingenommen wird. Größer als
#: der Diensttakt (30 s), sonst startet jeder Takt mit Jitter neu.
GRUND_S = 90.0
#: Zuschlag auf eine `busy`-Frist: die Frist ist die erwartete Dauer, der
#: Zuschlag deckt Aufräumen danach.
NACHLASS_S = 30.0


def erlaubte_stille(grund: float = GRUND_S, busy_rest: float = 0.0,
                    nachlass: float = NACHLASS_S) -> float:
    """Wie lange darf der Fortschritt ausbleiben, ohne dass es ein Hänger ist?

    Reine Rechnung, damit sie ohne Faden und ohne systemd prüfbar ist.
    `busy_rest` ist die **verbleibende** Zeit einer laufenden Frist; eine
    abgelaufene Frist zählt als 0 und schaltet damit nur die Grundgeduld frei.
    """
    return max(float(grund), max(0.0, float(busy_rest)) + float(nachlass))


def beat_erlaubt(seit_fortschritt: float, grund: float = GRUND_S,
                 busy_rest: float = 0.0, nachlass: float = NACHLASS_S) -> bool:
    """Darf jetzt geschlagen werden? Nein heißt: der Dienst hängt."""
    return float(seit_fortschritt) <= erlaubte_stille(grund, busy_rest, nachlass)


class Melder:
    """Schickt `READY=1` und `WATCHDOG=1` an `$NOTIFY_SOCKET`.

    `jetzt` und `adresse` sind einsetzbar, damit der Test ohne systemd und
    ohne echte Zeit auskommt (Muster: `freigabe_erinnerung`).
    """

    def __init__(self, adresse: str | None = None, *, watchdog_s: float = WATCHDOG_S,
                 takt_s: float = TAKT_S, grund: float = GRUND_S,
                 nachlass: float = NACHLASS_S, jetzt=None,
                 zustandsdatei: str | Path | None = None) -> None:
        self.adresse = adresse if adresse is not None else os.environ.get("NOTIFY_SOCKET", "")
        self.watchdog_s = float(watchdog_s)
        self.takt = max(0.5, float(takt_s))
        self.grund = float(grund)
        self.nachlass = float(nachlass)
        self._jetzt = jetzt or time.monotonic
        self.zustandsdatei = Path(zustandsdatei) if zustandsdatei else None
        self._fortschritt = self._jetzt()
        self._busy_bis = 0.0
        self._busy_zweck = ""
        self._stop = threading.Event()
        self._faden: threading.Thread | None = None
        self._gesendet = 0
        self._verweigert = 0

    # --- Zustand ----------------------------------------------------------

    def fortschritt(self) -> None:
        """Der Dienst lebt: der Hauptfaden ist einmal herumgekommen."""
        self._fortschritt = self._jetzt()

    def busy(self, zweck: str, sekunden: float) -> None:
        """Eine erwartet lange Stelle anmelden (Modellaufruf, Werkzeug)."""
        if sekunden <= 0:
            return
        jetzt = self._jetzt()
        bis = jetzt + float(sekunden)
        # Eine kürzere Frist verlängert nichts: der längste erwartete Aufruf
        # bestimmt die Geduld.
        if bis > self._busy_bis:
            self._busy_bis = bis
            self._busy_zweck = str(zweck or "")
            self._zustand_schreiben(sekunden)

    def busy_rest(self) -> float:
        return max(0.0, self._busy_bis - self._jetzt())

    def erlaubt(self) -> bool:
        return beat_erlaubt(self._jetzt() - self._fortschritt, self.grund,
                            self.busy_rest(), self.nachlass)

    # --- Senden -----------------------------------------------------------

    def _ziel(self) -> bytes:
        a = self.adresse
        # "@name" ist der abstrakte Namensraum von Linux: das erste Byte ist
        # die Null.
        return (b"\0" + a[1:].encode()) if a.startswith("@") else a.encode()

    def schlagen(self, text: str) -> bool:
        """Eine Zeile an systemd. True heißt: abgeschickt."""
        if not self.adresse:
            return False
        try:
            with socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM) as s:
                s.settimeout(2)
                s.connect(self._ziel())
                s.sendall(text.encode())
            self._gesendet += 1
            return True
        except OSError as exc:
            # Ein nicht erreichbarer Socket ist ein Befund, kein Grund zu
            # sterben: der Dienst soll weiterarbeiten (Regel 10e).
            log.warning("Lebenszeichen nicht zustellbar (%s): %s", text, exc)
            return False

    # --- Faden ------------------------------------------------------------

    def start(self) -> bool:
        """Faden starten. False heißt: es gibt keinen Notify-Socket."""
        if not self.adresse:
            log.warning("Kein NOTIFY_SOCKET — der Watchdog greift nicht. "
                        "Der Dienst läuft weiter, aber niemand merkt einen Hänger.")
            return False
        if self._faden is not None:
            return True
        self._fortschritt = self._jetzt()
        self.schlagen("READY=1")
        self._faden = threading.Thread(target=self._lauf, name="lebenszeichen", daemon=True)
        self._faden.start()
        log.info("Lebenszeichen aktiv (Watchdog %.0f s, Takt %.0f s).", self.watchdog_s, self.takt)
        return True

    def _lauf(self) -> None:
        while not self._stop.wait(self.takt):
            if self.erlaubt():
                self.schlagen("WATCHDOG=1")
            else:
                self._verweigert += 1
                # Nicht jede Sekunde dieselbe Zeile: das Protokoll soll den
                # Anfang eines Hängers zeigen, nicht 300 gleiche Zeilen.
                if self._verweigert == 1 or self._verweigert % 30 == 0:
                    log.error("Kein Lebenszeichen: seit %.0f s kein Fortschritt%s — "
                              "systemd startet nach der Watchdog-Frist neu.",
                              self._jetzt() - self._fortschritt,
                              f" (erwartet: {self._busy_zweck})" if self._busy_zweck else "")

    def stop(self, *_: object) -> None:
        self._stop.set()
        if self._faden is not None:
            self._faden.join(timeout=2)
            self._faden = None

    # --- Zustandsdatei (nur zur Ansicht, nie zur Entscheidung) ------------

    def _zustand_schreiben(self, sekunden: float) -> None:
        if self.zustandsdatei is None:
            return
        try:
            self.zustandsdatei.parent.mkdir(parents=True, exist_ok=True)
            daten = {
                "zweck": self._busy_zweck,
                "sekunden": round(float(sekunden), 1),
                # Unix-Zeit für Menschen und Mojo; die Entscheidung fällt auf
                # der monotonen Uhr.
                "busy_bis": round(time.time() + float(sekunden), 3),
            }
            tmp = self.zustandsdatei.with_name(self.zustandsdatei.name + ".neu")
            tmp.write_text(json.dumps(daten, ensure_ascii=False) + "\n", encoding="utf-8")
            os.replace(tmp, self.zustandsdatei)
        except OSError as exc:
            log.warning("Lebenszeichen-Zustand nicht schreibbar: %s", exc)


# --- Der eine Melder des Prozesses ----------------------------------------
#
# Die Agentenschleife und die Dienstschleife rufen `busy`/`fortschritt` an
# Stellen, die nichts von systemd wissen sollen. Ohne Melder (Test, Terminal)
# sind beide Aufrufe stille No-Ops.
_melder: Melder | None = None


def setze_melder(m: Melder | None) -> None:
    global _melder
    _melder = m


def melder() -> Melder | None:
    return _melder


def fortschritt() -> None:
    if _melder is not None:
        _melder.fortschritt()


def busy(zweck: str, sekunden: float) -> None:
    if _melder is not None:
        _melder.busy(zweck, sekunden)
