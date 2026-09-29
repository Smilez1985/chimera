"""Erkennen, wenn sich ein Modell im Kreis dreht.

Muster aus OpenMinis, nachgebaut. Für Chimera ist das kein Komfort: Das
Gerät arbeitet autonom (Zeitsteuerung, Umgebungshören) und hängt an einem
externen Modell. Eine Schleife um drei Uhr nachts ist dort keine
Unannehmlichkeit, sondern eine Rechnung — und bei einem Abo ein
verbrauchtes Kontingent.

Drei Feinheiten, die den Unterschied zu einem simplen Zähler machen:

* **Geprüft wird vor der Ausführung.** Bei ``BLOCK`` wird der Aufruf
  verhindert und die Meldung als *Werkzeugergebnis* eingespeist — das
  Modell erfährt damit, dass es feststeckt, statt stumm ins Leere zu
  laufen.
* **Auch das Ergebnis zählt.** Gleiche Frage mit gleicher Antwort ist eine
  Schleife. Gleiche Frage mit wechselnder Antwort ist legitimes Nachsehen
  (Datei beobachten, auf einen Dienst warten) und darf nicht abgewürgt
  werden.
* **Warnungen sind gedrosselt**, sonst wird die Warnung selbst zur
  Schleife.
"""

from __future__ import annotations

import hashlib
import json
import time
from collections import deque
from dataclasses import dataclass
from enum import Enum


class Level(str, Enum):
    OK = "ok"
    WARN = "warn"       # Hinweis einspeisen, Ausführung läuft weiter
    BLOCK = "block"     # diesen Aufruf verhindern
    STOP = "stop"       # Notbremse, Schleife ganz beenden


@dataclass
class Verdict:
    level: Level
    message: str | None = None

    @property
    def blocked(self) -> bool:
        return self.level in (Level.BLOCK, Level.STOP)


@dataclass
class Config:
    history: int = 30
    warn_at: int = 10          # gleiche Aufrufe → Hinweis
    block_at: int = 20         # gleiche Aufrufe → verhindern
    stop_at: int = 30          # Aufrufe gesamt ohne Fortschritt → Schluss
    unknown_at: int = 10       # Aufrufe eines Werkzeugs, das es nicht gibt
    warn_every: int = 5        # so oft wird eine Warnung wiederholt

    def __post_init__(self):
        # warn_at und block_at zaehlen dasselbe (gleiche Aufrufe), also
        # muss ihre Reihenfolge stimmen -- sonst blockt es, bevor gewarnt
        # wurde.
        self.warn_at = max(1, self.warn_at)
        self.block_at = max(self.warn_at + 1, self.block_at)

        # stop_at zaehlt etwas ANDERES: alle Aufrufe zusammen, nicht die
        # gleichen. Die beiden gegeneinander abzugleichen waere ein
        # Denkfehler -- "nach 5 Aufrufen Schluss" ist eine sinnvolle
        # Einstellung, auch wenn erst ab 20 gleichen geblockt wird.
        # (Gefunden durch den eigenen Test.)
        self.stop_at = max(1, self.stop_at)
        self.history = max(self.history, self.block_at, self.stop_at)


def _hash(value) -> str:
    try:
        text = json.dumps(value, sort_keys=True, default=str)
    except Exception:
        text = repr(value)
    return hashlib.sha1(text.encode("utf-8")).hexdigest()[:16]


@dataclass
class Record:
    tool: str
    args: str
    result: str | None = None
    at: float = 0.0


class LoopGuard:
    """Beobachtet die Werkzeugaufrufe eines Auftrags."""

    def __init__(self, config: Config | None = None, known_tools=None):
        self.cfg = config or Config()
        self.known = set(known_tools or ())
        self._hist: deque[Record] = deque(maxlen=self.cfg.history)
        self._warned: dict[str, int] = {}
        self._total = 0

    def reset(self) -> None:
        """Vor einem neuen Auftrag. Schleifen sind auftragsbezogen."""
        self._hist.clear()
        self._warned.clear()
        self._total = 0

    # --- vor der Ausführung ----------------------------------------------

    def check(self, tool: str, args) -> Verdict:
        ah = _hash(args)

        if self.known and tool not in self.known:
            n = sum(1 for r in self._hist if r.tool == tool)
            if n + 1 >= self.cfg.unknown_at:
                return Verdict(
                    Level.BLOCK,
                    f"Das Werkzeug {tool!r} gibt es nicht, und du hast es "
                    f"{n + 1}-mal versucht. Verfügbar: "
                    f"{', '.join(sorted(self.known))}."
                )

        same = [r for r in self._hist if r.tool == tool and r.args == ah]
        n = len(same)

        # Wechselnde Ergebnisse sind kein Kreis, sondern Beobachtung.
        if n >= self.cfg.warn_at:
            results = {r.result for r in same if r.result is not None}
            if len(results) > 1:
                n = 0

        if self._total >= self.cfg.stop_at:
            return Verdict(
                Level.STOP,
                f"Notbremse: {self._total} Werkzeugaufrufe ohne erkennbaren "
                f"Fortschritt. Bitte antworte mit dem, was du bisher hast."
            )

        if n >= self.cfg.block_at:
            return Verdict(
                Level.BLOCK,
                f"Du rufst {tool!r} zum {n + 1}. Mal mit denselben "
                f"Argumenten auf und bekommst dasselbe Ergebnis. Der Aufruf "
                f"wurde verhindert — versuche einen anderen Weg oder "
                f"antworte mit dem, was du hast."
            )

        if n >= self.cfg.warn_at:
            key = f"{tool}:{ah}"
            bucket = n // self.cfg.warn_every
            if self._warned.get(key) != bucket:
                self._warned[key] = bucket
                return Verdict(
                    Level.WARN,
                    f"Hinweis: {tool!r} wurde bereits {n}-mal mit denselben "
                    f"Argumenten aufgerufen. Das Ergebnis wird sich nicht "
                    f"ändern."
                )

        return Verdict(Level.OK)

    # --- nach der Ausführung ---------------------------------------------

    def record(self, tool: str, args, result=None) -> None:
        self._hist.append(Record(tool, _hash(args), _hash(result) if result is not None else None,
                                 time.monotonic()))
        self._total += 1

    @property
    def calls(self) -> int:
        return self._total
