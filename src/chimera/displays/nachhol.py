"""Anzeige, die beim Start belegt war — wird nachgeholt, statt blind zu bleiben.

Fund am Pi (15.11.2026, 02:45): Beim Installerlauf startet Schritt
``98-service`` den Agenten, **während** der Fortschrittsbalken des Installers
(``installer/lib/py/fortschritt.py``) das Panel noch hält. Der Dienst bekam

    [Errno 16] Leitung belegt auf /dev/gpiochip0: [27, 4]

und fiel auf ``NullPanel`` — das Gesicht lief blind, das Panel blieb
**dauerhaft dunkel**, obwohl der Zeichner zwei Sekunden später von selbst
endete. Die Leitung war also nur vorübergehend belegt; niemand hat es erneut
versucht.

Deshalb dieser Baustein: Ein belegtes Panel ist kein Defekt, sondern eine
Warteschlange. ``NachholPanel`` kennt Maße und Bildrate aus dem ``Profil``
(nicht aus einer geöffneten Leitung), nimmt Bilder an, verwirft sie, solange
niemand da ist, und versucht es nach einem Plan erneut. Sobald die Leitung
frei ist, wird das echte Panel geöffnet und alles Weitere geht daran.

Der Plan ist endlich (``VERSUCH_ABSTAENDE``, rund fünf Minuten): Ist die
Leitung wirklich einem anderen Besitzer, bleibt es beim Blindlauf — aber mit
einer ablesbaren Zeile („nach N Versuchen aufgegeben"), nicht still.

Regeln: 8a (der Unterschied zwischen „läuft blind" und „ist kaputt" ist
ablesbar), 6e (der Dienst *erkennt* nicht neu — er wartet auf die Leitung,
die ihm genannt wurde; der Typ kommt weiter aus ``CHIMERA_ANZEIGE``).
"""

from __future__ import annotations

import logging
import time

from . import registry
from .base import Panel, Profil

log = logging.getLogger(__name__)

#: Abstand bis zum nächsten Versuch, in Sekunden. Dicht am Anfang (der
#: Installer-Zeichner endet Sekunden nach dem Dienststart), dann weiter —
#: wer wirklich fremd hält, kostet so nur noch ein Öffnen je Minute.
VERSUCH_ABSTAENDE: tuple[float, ...] = (
    (2.0,) * 15 + (10.0,) * 6 + (30.0,) * 8
)


class NachholPanel(Panel):
    """Panel-Hülle, die ein belegtes Panel nachholt.

    ``typ`` ist der eingestellte Anzeigetyp (z. B. ``whisplay``), ``profil``
    sein ``Profil`` — daraus stammen Maße und Bildrate, damit der Renderer
    nicht mit einer falschen Größe rechnet. ``grund`` ist der Fehler des
    ersten Versuchs; er steht in ``hinweis``, bis es geklappt hat.
    """

    def __init__(self, typ: str, quelle: str, grund: object, *,
                 profil: Profil | None = None,
                 abstaende: tuple[float, ...] = VERSUCH_ABSTAENDE,
                 uhr=time.monotonic,
                 oeffnen=None) -> None:
        self.typ = typ
        self.quelle = quelle
        self.grund = grund
        self.profil = profil
        if profil is not None:
            self.width = profil.breite
            self.height = profil.hoehe
            self.fps = int(profil.bildrate) if profil.bildrate else 0
            self.ruhe_fps = min(self.fps, 2)
        self._abstaende = tuple(abstaende) or (0.0,)
        self._uhr = uhr
        self._oeffnen = oeffnen or (lambda name: registry.oeffne(name))
        self._echt: Panel | None = None
        self._versuche = 0
        self._aufgegeben = False
        self._naechster = uhr()          # erster Versuch sofort
        self._licht: int | None = None
        self._farbe: tuple[int, int, int] | None = None
        self._letztes = None
        self.verworfen = 0
        self.hinweis = (f"Anzeige {typ} ({quelle}) war beim Start belegt: "
                        f"{grund} — wird nachgeholt")

    # --- Zustand ---------------------------------------------------------

    @property
    def bereit(self) -> bool:
        """Zeichnet dieses Panel wirklich? (NullPanel und Vor-Holung: nein.)"""
        return self._echt is not None

    @property
    def versuche(self) -> int:
        return self._versuche

    # --- Holen -----------------------------------------------------------

    def _versuche_jetzt(self) -> Panel | None:
        """Einmal versuchen, wenn der Plan es zulässt. Gibt das echte Panel."""
        if self._echt is not None:
            return self._echt
        jetzt = self._uhr()
        if jetzt < self._naechster:
            return None
        try:
            echt = self._oeffnen(self.typ)
        except Exception as exc:                       # noqa: BLE001
            self._versuche += 1
            # Abstand aus dem Plan; ist er erschöpft, gilt der letzte weiter
            # (60 s) — die Leitung kann jederzeit frei werden, und ein
            # Öffnen je Minute kostet nichts. Aufgegeben wird nur das
            # *dichte* Probieren, und das steht als Warnung im Protokoll.
            i = min(self._versuche, len(self._abstaende)) - 1
            self._naechster = jetzt + self._abstaende[i]
            if self._versuche == 1 or self._versuche % 5 == 0:
                if self._versuche <= len(self._abstaende):
                    log.info("Anzeige %s noch belegt (%s) — Versuch %d, "
                             "nächster in %.0f s.", self.typ, exc,
                             self._versuche, self._abstaende[i])
                else:
                    log.info("Anzeige %s noch belegt (%s) — Versuch %d.",
                             self.typ, exc, self._versuche)
            if self._versuche == len(self._abstaende) + 1 and not self._aufgegeben:
                self._aufgegeben = True
                self.hinweis = (f"Anzeige {self.typ} ({self.quelle}) nach "
                                f"{self._versuche} Versuchen nicht zu "
                                f"bekommen: {exc} — Gesicht bleibt blind")
                log.warning("Anzeige %s nach %d Versuchen nicht zu bekommen "
                            "(%s) — Gesicht bleibt blind, nächster Versuch "
                            "alle %.0f s.", self.typ, self._versuche, exc,
                            self._abstaende[-1])
            return None

        self._echt = echt
        self.hinweis = ""
        # Was der Renderer in der Zwischenzeit wollte, geht jetzt nach:
        # sonst bliebe das Panel dunkel bzw. die LED aus, obwohl das Gesicht
        # längst zeichnet.
        try:
            if self._licht is not None:
                echt.backlight(self._licht)
            if self._farbe is not None:
                echt.led(*self._farbe)
        except Exception as exc:                       # noqa: BLE001
            log.warning("Anzeige %s: Nachziehen von Licht/LED scheiterte (%s).",
                        self.typ, exc)
        if self._letztes is not None:
            try:
                echt.show(self._letztes)
            except Exception as exc:                   # noqa: BLE001
                log.warning("Anzeige %s: erstes Bild scheiterte (%s).",
                            self.typ, exc)
        log.info("Anzeige %s doch noch bekommen (Versuch %d) — Gesicht "
                 "zeichnet.", self.typ, self._versuche)
        return echt

    # --- Panel-Schnittstelle --------------------------------------------

    def show(self, image) -> None:
        echt = self._versuche_jetzt()
        if echt is None:
            # Das letzte Bild aufheben: Wer nachholt, zeigt sofort etwas,
            # statt auf die nächste Änderung des Gesichts zu warten (in Ruhe
            # wird selten gezeichnet — sonst bliebe das Glas erst einmal
            # dunkel, obwohl die Leitung frei ist).
            self._letztes = image
            self.verworfen += 1
            return
        echt.show(image)

    @property
    def bild_bytes(self) -> bytes | None:
        """Nur da, wenn das echte Panel offen ist — sonst gibt es kein Bild."""
        return getattr(self._echt, "bild_bytes", None)

    def backlight(self, percent: int) -> None:
        self._licht = percent
        echt = self._versuche_jetzt()
        if echt is not None:
            echt.backlight(percent)

    def led(self, r: int, g: int, b: int) -> None:
        self._farbe = (r, g, b)
        echt = self._versuche_jetzt()
        if echt is not None:
            echt.led(r, g, b)

    def close(self) -> None:
        if self._echt is not None:
            self._echt.close()
