"""Software-PWM für eine GPIO-Leitung (Backlight, LED).

Nachgebaut nach PiSugar ``runtime/whisplay.py`` (``SoftPWM``, Apache-2.0).
Ein Faden je Leitung, der die Leitung im Takt schaltet. Das ist auf einem
Pi Zero 2 W für Backlight (1 kHz) und drei LED-Kanäle (100 Hz) ausreichend
und braucht keinen Hardware-PWM-Pin -- die Whisplay hat keinen am
Backlight.

``LOW=an``-Leitungen (Whisplay: Backlight und LED) werden über
``aktiv_low=True`` behandelt: 100 % Helligkeit heißt dann Leitung unten.

**Fester Pegel kostet nichts (11.10.2026).** Die Vorlage schläft auch bei
0 % und 100 % je Periode und setzt die Leitung neu -- bei 1 kHz sind das
tausend Wecker je Sekunde für einen Pegel, der sich nicht ändert. Gemessen
am chimera-pi: Backlight 100 % = 4,8 % eines Kerns, LED aus je 0,4 %.
Hier wird ein fester Pegel EINMAL gesetzt, und der Faden wartet, bis sich
der Tastgrad ändert. Nur echte Zwischenwerte takten.
"""

from __future__ import annotations

import threading
import time


class SoftPWM:
    def __init__(self, setze, *, frequenz_hz: float = 100.0, aktiv_low: bool = False):
        self._setze = setze
        self.periode = 1.0 / float(frequenz_hz)
        self.aktiv_low = aktiv_low
        self.tastgrad = 0.0
        self._laeuft = False
        self._faden: threading.Thread | None = None
        self._geaendert = threading.Event()

    def _pegel(self, an: bool) -> int:
        return (0 if an else 1) if self.aktiv_low else (1 if an else 0)

    def start(self, tastgrad: float = 0.0) -> None:
        self.setze_tastgrad(tastgrad)
        if self._laeuft:
            return
        self._laeuft = True
        self._faden = threading.Thread(target=self._schleife, daemon=True,
                                       name="chimera-softpwm")
        self._faden.start()

    def setze_tastgrad(self, tastgrad: float) -> None:
        neu = max(0.0, min(100.0, float(tastgrad)))
        if neu != self.tastgrad:
            self.tastgrad = neu
            self._geaendert.set()

    def stop(self, *, endpegel_an: bool = False) -> None:
        self._laeuft = False
        self._geaendert.set()          # aus dem Warten holen
        if self._faden is not None:
            self._faden.join(timeout=1.0)
            self._faden = None
        try:
            self._setze(self._pegel(endpegel_an))
        except Exception:  # pragma: no cover - Leitung schon freigegeben
            pass

    def _schleife(self) -> None:
        while self._laeuft:
            tg = self.tastgrad
            if tg <= 0 or tg >= 100:
                # Fester Pegel: setzen, dann schlafen, bis jemand den
                # Tastgrad aendert (oder stop ruft). Kein Takt.
                self._geaendert.clear()
                self._setze(self._pegel(tg >= 100))
                if self.tastgrad == tg and self._laeuft:
                    self._geaendert.wait()
                continue
            an = self.periode * tg / 100.0
            self._setze(self._pegel(True))
            time.sleep(an)
            self._setze(self._pegel(False))
            time.sleep(self.periode - an)
