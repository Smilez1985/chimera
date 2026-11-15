"""Mikrofon und Lautsprecher **hart** abschalten, wenn sie nicht gebraucht werden.

Auftrag smilez (15.11.2026): *„wir schalten einfach hart per Software Mic und
audio ab wenn unbenutzt und an wenn benutzt, das Icon kann sich daran
ausrichten"*.

Das ist kein Symbolwunsch, sondern eine Entscheidung: Ein Gerät, das im
Wohnzimmer steht und dauerhaft zuhört, soll das **nicht** tun, solange es
nichts damit anfängt. Und ein Lautsprecher, der stumm geschaltet ist, während
niemand etwas abspielt, ist die ehrlichere Grundstellung als einer, der
„bereit" ist.

**Wie hart ist hart? Am Whisplay-HAT gibt es keinen Schalter.** Am Pi
gemessen (`amixer -c whisplaysound scontrols`): nur zwei Regler, `mic` und
`speaker`, beide **nur Lautstärke** („Capabilities: volume volume-joined") —
kein `pswitch`, kein `cswitch`. Es gibt also nichts zu „muten"; der einzige
harte Weg ist **Lautstärke auf 0** (Aufnahmeverstärkung bzw. Ausgang), und
beim Einschalten den vorher gemerkten Wert zurück (am Pi 80 %).

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

#: **Das linke Mikrofon ist defekt und rauscht** (smilez, 15.11.2026). Der
#: Codec liefert Stereo, der einfache Mixer hat aber nur **einen** Regler
#: („mic", values=1, am Pi gemessen) — links lässt sich also nicht per
#: `amixer` abschalten. Deshalb wird bei der Aufnahme **nur der rechte
#: Kanal** genommen: `nur_rechter_kanal()` macht aus dem Stereo-Puffer die
#: rechte Spur. Wer die Aufnahme baut (Phase 5), benutzt sie — sonst hört
#: Chimera dauerhaft Rauschen auf einem Ohr.
MIKRO_KANAL = "rechts"


def nur_rechter_kanal(pcm: bytes) -> bytes:
    """Aus interleaved Stereo (S16_LE) die **rechte** Spur allein.

    ``pcm`` sind 2 Byte je Wert, abwechselnd links/rechts. Zurück kommen
    die rechten Werte ohne Zwischenschritt über numpy: Auf dem Zero 2 W
    zählt jedes Byte, und die Aufgabe ist ein Slicing.
    """
    if len(pcm) < 4:
        return b""
    return b"".join(pcm[i:i + 2] for i in range(2, len(pcm) - 1, 4))


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
