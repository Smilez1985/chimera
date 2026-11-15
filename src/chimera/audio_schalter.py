"""Mikrofon und Lautsprecher **hart** abschalten, wenn sie nicht gebraucht werden.

Auftrag smilez (15.11.2026): *„wir schalten einfach hart per Software Mic und
audio ab wenn unbenutzt und an wenn benutzt, das Icon kann sich daran
ausrichten"*.

Das ist kein Symbolwunsch, sondern eine Entscheidung: Ein Gerät, das im
Wohnzimmer steht und dauerhaft zuhört, soll das **nicht** tun, solange es
nichts damit anfängt. Und ein Lautsprecher, der stumm geschaltet ist, während
niemand etwas abspielt, ist die ehrlichere Grundstellung als einer, der
„bereit" ist.

**Wie hart ist hart — zwei Wege, einer davon ist besser.** Gibt es einen
echten **Mute-Schalter** (`pswitch`/`cswitch` an der Kontrolle), wird der
benutzt: Er ist der schnellere Weg *und* er lässt die Lautstärke stehen —
beim Einschalten kommt also genau die eingestellte Lautstärke zurück, nicht
„zu laut" oder „zu leise" (smilez, 15.11.2026). Gibt es keinen Schalter (am
Whisplay-HAT: `amixer -c whisplaysound scontrols` kennt nur `mic` und
`speaker`, beide **nur** `volume volume-joined`), fällt der Schalter auf
**Lautstärke 0 %** zurück und merkt sich den vorherigen Wert (am Pi 80 %).
Die Fähigkeit wird **einmal** gemessen und gemerkt, nicht bei jedem Schalten.

**Der Zustand ist die Wahrheit, nicht die Absicht.** Nach jedem Schaltversuch
wird der gemerkte Zustand gesetzt — auch wenn das Kommando scheitert, wird
das **gesagt** (`letzter_fehler`), nicht verschluckt. Ohne Karte (Sandkasten,
fremdes Gerät) bleibt der Zustand trotzdem richtig: Es gibt dann nichts
abzuschalten, und das Symbol lügt nicht.

**Lautsprecher und die Erinnerung.** Der Freigabeton läuft über `aplay`. Ist
die Wiedergabe aus, wäre er stumm — deshalb gibt es
:meth:`AudioSchalter.mit_lautsprecher`: schaltet für die Dauer eines Tons an
und danach wieder aus. Wer den Ton spielt, benutzt sie; wer sie vergisst,
hört nichts (das ist der Preis dafür, dass der Lautsprecher nicht dauerhaft
offen steht).
"""

from __future__ import annotations

import logging
import subprocess
from contextlib import contextmanager

log = logging.getLogger(__name__)

#: Die ALSA-Karte des Whisplay-HAT, am Pi gemessen (`aplay -l`: „Karte 0:
#: whisplaysound"). Auf einem anderen Gerät wird sie über ``karte=`` gesetzt;
#: fehlt sie, schlägt ``amixer`` fehl und das wird gemeldet.
KARTE = "whisplaysound"

#: Reglernamen auf dem HAT (gemessen, `scontrols`). Beides Lautstärken:
#: es gibt keinen Schalter zum Stummschalten.
REGLER = {"mikrofon": "mic", "lautsprecher": "speaker"}

#: Vorgabe-Lautstärke, wenn vorher keine bekannt ist (am Pi 80 %).
STANDARD_LAUTSTAERKE = "80%"

#: **Aufnahme läuft über das Gerät `chimera_mikro`, nicht über harte Kanäle.**
#: Das linke Mikrofon dieses Boards klirrt (smilez, 15.11.2026: *„unser linkes
#: mic muss aber immer aus bleiben, das ist defekt und rauscht"*). Das ist
#: aber schon gemessen und eingerichtet: `chimera.displays.mikro` spielt
#: Stufentöne und entscheidet je Gerät zwischen ``beide``/``links``/
#: ``rechts``/``keins``; der Installer (Modul 46) schreibt daraus
#: ``/etc/alsa/conf.d/50-chimera-mikro.conf``. Am chimera-pi steht dort seit
#: 11.10.2026 „rechts" — `ttable.0.1 1` führt genau den guten Kanal als Mono.
#: **Deshalb gibt es hier keine Kanalwahl in Software**: Wer aufnimmt, öffnet
#: ``chimera_mikro``; eine zweite Auswahl im Code wäre eine zweite Wahrheit
#: und würde bei einem anderen Gerät falsch liegen.
AUFNAHME_GERAET = "chimera_mikro"


class AudioSchalter:
    """Schaltet Mikrofon und Wiedergabe hart an und aus.

    ``ausfuehren`` ist für Tests einsetzbar: eine Funktion, die eine
    Argumentliste bekommt und ``(rc, meldung)`` zurückgibt. Ohne sie läuft
    ``amixer`` als Kindprozess mit fester Argumentliste (keine Shell).
    """

    def __init__(self, *, karte: str = KARTE, ausfuehren=None):
        self.karte = karte
        self._ausfuehren = ausfuehren or _amixer
        self._mikrofon_an = False
        self._lautsprecher_an = False
        #: Zuletzt gesehene Lautstärke je Regler (für das Zurückschalten).
        self._lautstaerke: dict[str, str] = {}
        #: Kann diese Kontrolle muten? Ergebnis der einmaligen Messung.
        self._schalter: dict[str, bool] = {}
        #: Letzter Grund, aus dem ein Schalten nicht ging (für das Journal).
        self.letzter_fehler = ""

    # --- Auskunft ---------------------------------------------------------

    def zustand(self) -> dict:
        """Was gerade gilt — die Quelle für die Symbole in der Anzeige."""
        return {"mikrofon_an": self._mikrofon_an,
                "lautsprecher_an": self._lautsprecher_an}

    # --- Schalten ---------------------------------------------------------

    def mikrofon(self, an: bool) -> bool:
        """Aufnahme an oder aus. Rückgabe: was danach gilt."""
        self._mikrofon_an = self._schalte("mikrofon", an)
        return self._mikrofon_an

    def lautsprecher(self, an: bool) -> bool:
        """Wiedergabe an oder aus. Rückgabe: was danach gilt."""
        self._lautsprecher_an = self._schalte("lautsprecher", an)
        return self._lautsprecher_an

    def alles_aus(self) -> None:
        """Grundstellung: beide aus. Beim Dienststart der erste Griff."""
        self.mikrofon(False)
        self.lautsprecher(False)

    @contextmanager
    def mit_lautsprecher(self):
        """Wiedergabe für die Dauer des Blocks an, danach wieder aus.

        Gedacht für den Erinnerungston (`aplay`): Er soll hörbar sein, ohne
        dass der Lautsprecher dauerhaft offen steht.
        """
        vorher = self._lautsprecher_an
        self.lautsprecher(True)
        try:
            yield
        finally:
            if not vorher:
                self.lautsprecher(False)

    # --- innen ------------------------------------------------------------

    def _schalte(self, was: str, an: bool) -> bool:
        """Muten, wenn es einen Schalter gibt — sonst Lautstärke 0 %."""
        regler = REGLER[was]
        if self._hat_schalter(regler):
            rc, meldung = self._ausfuehren(
                ["amixer", "-q", "-c", self.karte, "sset", regler,
                 "unmute" if an else "mute"])
            if rc == 0:
                self.letzter_fehler = ""
                log.info("Audio: %s %s (Schalter)", regler,
                         "an" if an else "aus")
                return an
            # Ein vorhandener Schalter, der nicht will: benennen und den
            # Lautstärke-Weg trotzdem versuchen, statt stumm zu bleiben.
            log.warning("Audio: Schalter %s ging nicht (%s) — Lautstärke-Weg",
                        regler, meldung or rc)
        return self._ueber_lautstaerke(was, an)

    def _hat_schalter(self, regler: str) -> bool:
        """Hat diese Kontrolle einen Mute-Schalter? Einmal messen, dann merken."""
        if regler in self._schalter:
            return self._schalter[regler]
        rc, text = self._ausfuehren(
            ["amixer", "-q", "-c", self.karte, "sget", regler], lesen=True)
        faehig = rc == 0 and ("pswitch" in (text or "") or "cswitch" in (text or ""))
        self._schalter[regler] = faehig
        return faehig

    def _ueber_lautstaerke(self, was: str, an: bool) -> bool:
        """Lautstärke auf 0 (aus) oder auf den gemerkten Wert (an)."""
        regler = REGLER[was]
        if an:
            wert = self._lautstaerke.get(was) or STANDARD_LAUTSTAERKE
        else:
            # Den aktuellen Wert merken, damit „an" nicht auf gut Glück auf
            # 80 % springt, sondern auf das, was der Nutzer eingestellt hat.
            rc, jetzt = self._ausfuehren(
                ["amixer", "-q", "-c", self.karte, "sget", regler], lesen=True)
            if rc == 0:
                gemessen = _prozent(jetzt)
                if gemessen:
                    self._lautstaerke[was] = gemessen
            wert = "0%"
        rc, meldung = self._ausfuehren(
            ["amixer", "-q", "-c", self.karte, "sset", regler, wert])
        if rc == 0:
            self.letzter_fehler = ""
            log.info("Audio: %s %s (%s)", was, "an" if an else "aus", wert)
            return an
        # Kein stilles Scheitern: der Zustand bleibt, wie er war, und der
        # Grund steht im Journal und in `letzter_fehler`.
        self.letzter_fehler = meldung or f"rc={rc}"
        log.warning("Audio: %s %s ging nicht: %s", was,
                    "an" if an else "aus", self.letzter_fehler)
        return self._mikrofon_an if was == "mikrofon" else self._lautsprecher_an


def _prozent(text: str) -> str:
    """``"80%"`` aus der ``amixer``-Ausgabe (``Mono: 80 [80%]``)."""
    import re

    treffer = re.findall(r"\[(\d+)%\]", text or "")
    return f"{treffer[-1]}%" if treffer else ""


def _amixer(argv: list[str], *, lesen: bool = False) -> tuple[int, str]:
    """``amixer`` als Kindprozess — feste Argumentliste, harte Frist."""
    try:
        p = subprocess.run(argv, capture_output=True, text=True, timeout=5)
    except (OSError, subprocess.SubprocessError) as exc:
        return 127, f"{type(exc).__name__}: {exc}"
    if p.returncode != 0:
        return p.returncode, (p.stderr or p.stdout or "").strip()[:200]
    return 0, ""
