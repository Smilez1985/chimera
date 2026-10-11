"""PiSugar Whisplay HAT: ST7789 240×280, RGB-LED, Backlight, eine Taste.

Nachgebaut aus ``runtime/whisplay.py`` (PiSugar, Apache-2.0, Commit
c73051e6) -- Einschaltwerte Stelle für Stelle übernommen, die Mechanik
(GPIO, SPI, PWM) aus dem eigenen Kern. Was der Hersteller nicht tut, tun
wir auch nicht: kein Daemon, kein exklusiver Zugriff (DESIGN Regel 7).
"""

from __future__ import annotations

import threading
import time
from pathlib import Path

from ..base import Panel, Profil, to_rgb565
from ..gpio import Leitungen
from ..softpwm import SoftPWM
from ..st7789 import DISPON, INVON, MADCTL, SLPOUT, St7789
from ..st7789 import Profil as St7789Profil

HIER = Path(__file__).resolve().parent

# Einschaltfolge PiSugar ``_init_display`` (Zeilen 544–594 der Vorlage).
INIT = (
    (SLPOUT, b""),
    (MADCTL, bytes([0xC0])),            # USE_HORIZONTAL = 1
    (0x3A, bytes([0x05])),
    (0xB2, bytes([0x0C, 0x0C, 0x00, 0x33, 0x33])),
    (0xB7, bytes([0x35])),
    (0xBB, bytes([0x32])),
    (0xC2, bytes([0x01])),
    (0xC3, bytes([0x15])),
    (0xC4, bytes([0x20])),
    (0xC6, bytes([0x0F])),
    (0xD0, bytes([0xA4, 0xA1])),
    (0xE0, bytes([0xD0, 0x08, 0x0E, 0x09, 0x09, 0x05, 0x31,
                  0x33, 0x48, 0x17, 0x14, 0x15, 0x31, 0x34])),
    (0xE1, bytes([0xD0, 0x08, 0x0E, 0x09, 0x09, 0x15, 0x31,
                  0x33, 0x48, 0x17, 0x14, 0x15, 0x31, 0x34])),
    (INVON, b""),
    (DISPON, b""),
)


def profil() -> Profil:
    return Profil.aus_datei(HIER / "display.json")


class WhisplayPanel(Panel):
    fps = 15

    def __init__(self, *, fps: int | None = None, taste_poll_s: float = 0.005,
                 backlight_pwm: bool | None = None) -> None:
        p = profil()
        self.profil = p
        self.width, self.height = p.breite, p.hoehe
        self.fps = int(fps) if fps is not None else int(p.bildrate)
        pins = p.pins
        self._st = St7789(St7789Profil(
            breite=p.breite, hoehe=p.hoehe, dc=pins["dc"], rst=pins["rst"],
            versatz_y=20, takt_hz=100_000_000, madctl=0xC0, init=INIT,
            gpiochip=pins["gpiochip"], spi_bus=pins["spi_bus"], spi_cs=pins["spi_cs"],
        ), verbraucher="chimera-whisplay")
        # Backlight und LED: LOW = an. Anfangswert 1 = aus, bis der PWM läuft.
        self._bl, self._r, self._g, self._b, self._taste = (
            pins["backlight"], pins["led_r"], pins["led_g"], pins["led_b"], pins["taste"])
        self._gpio = Leitungen(pins["gpiochip"], verbraucher="chimera-whisplay-led").request(
            ausgaenge={self._bl: 1, self._r: 1, self._g: 1, self._b: 1},
            eingaenge={self._taste: None})
        try:
            self._st.einschalten()
        except Exception:
            self._gpio.close()
            self._st.close()
            raise
        # Der Hersteller schaltet das Backlight beim Pi Zero (1) nur ein/aus,
        # sonst per PWM. Ein Pi Zero 2 W fällt dort unter PWM.
        if backlight_pwm is None:
            backlight_pwm = "Zero" not in _modell() or "2" in _modell()
        self._bl_pwm = (SoftPWM(lambda v: self._gpio.setze(self._bl, v), frequenz_hz=1000, aktiv_low=True)
                        if backlight_pwm else None)
        self._led = {
            k: SoftPWM(lambda v, k=k: self._gpio.setze(k, v), frequenz_hz=100, aktiv_low=True)
            for k in (self._r, self._g, self._b)}
        for pwm in self._led.values():
            pwm.start(0)
        self.backlight(100)
        self._taste_cb = None
        self._taste_laeuft = True
        self._taste_poll = taste_poll_s
        self._taste_faden = threading.Thread(target=self._taste_schleife, daemon=True,
                                             name="chimera-whisplay-taste")
        self._taste_faden.start()

    # --- Panel ---------------------------------------------------------------

    def show(self, image) -> None:
        self.pruefe_groesse(image)
        self._st.schreibe_bild(to_rgb565(image))

    def backlight(self, percent: int) -> None:
        p = max(0, min(100, int(percent)))
        if self._bl_pwm is not None:
            self._bl_pwm.start(p)
        else:
            self._gpio.setze(self._bl, 0 if p else 1)

    def led(self, r: int, g: int, b: int) -> None:
        for k, v in ((self._r, r), (self._g, g), (self._b, b)):
            self._led[k].setze_tastgrad(max(0, min(255, int(v))) / 255 * 100)

    def taste_gedrueckt(self) -> bool:
        return self._gpio.lies(self._taste) == 1

    def bei_taste(self, callback) -> None:
        """``callback(gedrueckt: bool)`` bei jedem Wechsel."""
        self._taste_cb = callback

    def _taste_schleife(self) -> None:
        letzter = self._gpio.lies(self._taste)
        while self._taste_laeuft:
            try:
                jetzt = self._gpio.lies(self._taste)
            except OSError:
                break
            if jetzt != letzter:
                letzter = jetzt
                cb = self._taste_cb
                if cb is not None:
                    cb(jetzt == 1)
            time.sleep(self._taste_poll)

    def close(self) -> None:
        self._taste_laeuft = False
        for pwm in self._led.values():
            pwm.stop(endpegel_an=False)
        if self._bl_pwm is not None:
            self._bl_pwm.stop(endpegel_an=False)
        else:
            try:
                self._gpio.setze(self._bl, 1)
            except OSError:
                pass
        self._gpio.close()
        self._st.close()


def _modell() -> str:
    try:
        return Path("/proc/device-tree/model").read_text(errors="ignore").strip("\0").strip()
    except OSError:
        return ""
