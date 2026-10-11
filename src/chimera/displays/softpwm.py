"""Software-PWM für eine GPIO-Leitung (Backlight, LED).

Nachgebaut nach PiSugar ``runtime/whisplay.py`` (``SoftPWM``, Apache-2.0).
Ein Faden je Leitung, der die Leitung im Takt schaltet. Das ist auf einem
Pi Zero 2 W für Backlight (1 kHz) und drei LED-Kanäle (100 Hz) ausreichend
und braucht keinen Hardware-PWM-Pin -- die Whisplay hat keinen am
Backlight.

``LOW=an``-Leitungen (Whisplay: Backlight und LED) werden über
``aktiv_low=True`` behandelt: 100 % Helligkeit heißt dann Leitung unten.
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
        self.tastgrad = max(0.0, min(100.0, float(tastgrad)))

    def stop(self, *, endpegel_an: bool = False) -> None:
        self._laeuft = False
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
            if tg <= 0:
                self._setze(self._pegel(False))
                time.sleep(self.periode)
            elif tg >= 100:
                self._setze(self._pegel(True))
                time.sleep(self.periode)
            else:
                an = self.periode * tg / 100.0
                self._setze(self._pegel(True))
                time.sleep(an)
                self._setze(self._pegel(False))
                time.sleep(self.periode - an)
