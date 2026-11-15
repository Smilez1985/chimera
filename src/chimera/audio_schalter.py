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

**Einmal einstellen, dann nur noch schalten** (smilez, 15.11.2026:
*„Set and forget"*). Die Lautstärke ist eine Einstellung, kein Zustand: Sie
wird **einmal** gewählt und in ``config/audio.json`` abgelegt; geschaltet wird
danach nur noch an/aus. Ohne Ablage (oder bei Neustart mitten im Aus) würde
sonst nach einem Neustart auf einen Vorgabewert gesprungen — genau das „zu
laut oder zu leise", das niemand eingestellt hat.

**Lautsprecher und die Erinnerung.** Der Freigabeton läuft über `aplay`. Ist
die Wiedergabe aus, wäre er stumm — deshalb gibt es
:meth:`AudioSchalter.mit_lautsprecher`: schaltet für die Dauer eines Tons an
und danach wieder aus. Wer den Ton spielt, benutzt sie; wer sie vergisst,
hört nichts (das ist der Preis dafür, dass der Lautsprecher nicht dauerhaft
offen steht).
"""

from __future__ import annotations

import logging
from pathlib import Path
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

    def __init__(self, *, karte: str = KARTE, ausfuehren=None, ablage=None):
        self.karte = karte
        #: Wo die eingestellten Lautstärken liegen (``config/audio.json``).
        #: Ohne Ablage bleibt es beim Merken im Prozess (Tests, Sandkasten).
        self.ablage = ablage
        self._ausfuehren = ausfuehren or _amixer
        self._mikrofon_an = False
        self._lautsprecher_an = False
        #: Zuletzt gesehene Lautstärke je Regler (für das Zurückschalten).
        self._lautstaerke: dict[str, str] = {}
        #: Kann diese Kontrolle muten? Ergebnis der einmaligen Messung.
        self._schalter: dict[str, bool] = {}
        self._laden()
        #: Letzter Grund, aus dem ein Schalten nicht ging (für das Journal).
        self.letzter_fehler = ""

    # --- Auskunft ---------------------------------------------------------

    # --- Ablage -----------------------------------------------------------

    def _laden(self) -> None:
        """Gespeicherte Lautstärken holen (``config/audio.json``)."""
        if not self.ablage:
            return
        try:
            import json
            daten = json.loads(Path(self.ablage).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return
        for was, wert in (daten or {}).items():
            if was in REGLER and isinstance(wert, str) and wert.endswith("%"):
                self._lautstaerke[was] = wert

    def _sichern(self) -> None:
        """Lautstärken ablegen — atomar, damit ein Absturz keine halbe Datei lässt."""
        if not self.ablage:
            return
        try:
            import json
            ziel = Path(self.ablage)
            ziel.parent.mkdir(parents=True, exist_ok=True)
            tmp = ziel.with_suffix(".neu")
            tmp.write_text(json.dumps(self._lautstaerke, indent=2) + "\n",
                           encoding="utf-8")
            tmp.replace(ziel)
        except OSError as exc:
            log.warning("Audio-Lautstärke nicht ablegbar: %s", exc)

    def zustand(self) -> dict:
        """Was gerade gilt — die Quelle für die Symbole in der Anzeige."""
        return {"mikrofon_an": self._mikrofon_an,
                "lautsprecher_an": self._lautsprecher_an}

    def lautstaerke(self, was: str) -> int | None:
        """Eingestellte Lautstärke in Prozent (``None`` = nicht messbar).

        **Ist der Kanal aus, gilt der gemerkte Wert.** „Aus" heißt hier
        Lautstärke 0 %; wer die 0 als Einstellung anzeigt, behauptet, der
        Nutzer hätte den Regler zugezogen. Gemessen wird deshalb nur, solange
        der Kanal an ist — dann zählt, was wirklich am Regler steht (auch
        wenn jemand mit ``alsamixer`` gedreht hat). Ist das Kommando nicht da
        (Sandkasten, fremdes Gerät), gilt der gemerkte Wert, und wenn auch
        der fehlt: ``None`` statt einer erfundenen Zahl.
        """
        if was not in REGLER:
            return None
        an = self._mikrofon_an if was == "mikrofon" else self._lautsprecher_an
        gespeichert = self._lautstaerke.get(was) or ""
        gemerkt = int(gespeichert.rstrip("%")) if gespeichert.endswith("%") else None
        if not an:
            return gemerkt
        rc, text = self._ausfuehren(
            ["amixer", "-q", "-c", self.karte, "sget", REGLER[was]], lesen=True)
        if rc == 0:
            gemessen = _prozent(text)
            if gemessen:
                self._lautstaerke[was] = gemessen
                return int(gemessen.rstrip("%"))
        return gemerkt

    def lautstaerke_setzen(self, was: str, prozent) -> tuple[bool, str]:
        """Eine Lautstärke **einstellen** (0..100), nicht schalten.

        Ist der Kanal aus, bleibt er aus: Der Wert wird gemerkt und beim
        nächsten Einschalten angewendet. Ein Einstellen, das den stummen
        Lautsprecher hörbar macht, wäre ein Nebeneffekt, den niemand bestellt
        hat (smilez: „Set and forget" — die Lautstärke ist eine Einstellung,
        der Zustand ein anderer).
        """
        if was not in REGLER:
            return (False, f"unbekannter Regler {was!r} — erlaubt: "
                           + ", ".join(REGLER))
        if isinstance(prozent, bool):
            return (False, f"{was}: {prozent!r} ist keine Zahl")
        try:
            zahl = int(str(prozent).strip())
        except (TypeError, ValueError):
            return (False, f"{was}: {prozent!r} ist keine Zahl 0..100")
        if zahl < 0 or zahl > 100:
            return (False, f"{was}: {zahl} liegt außerhalb 0..100 — nichts geändert")
        wert = f"{zahl}%"
        an = self._mikrofon_an if was == "mikrofon" else self._lautsprecher_an
        self._lautstaerke[was] = wert
        self._sichern()
        if not an:
            return (True, f"{was}: {zahl}% gemerkt (aus — gilt beim Einschalten)")
        rc, meldung = self._ausfuehren(
            ["amixer", "-q", "-c", self.karte, "sset", REGLER[was], wert])
        if rc != 0:
            self.letzter_fehler = meldung or f"rc={rc}"
            log.warning("Audio: %s auf %s ging nicht: %s", was, wert,
                        self.letzter_fehler)
            return (False, f"{was}: {zahl}% nicht gesetzt ({self.letzter_fehler})")
        self.letzter_fehler = ""
        log.info("Audio: %s auf %s", was, wert)
        return (True, f"{was}: {zahl}%")

    def als_json(self) -> dict:
        """Was die Einstellungsseite braucht — Zustand **und** Lautstärken.

        ``lautstaerke_*`` ist ``None``, wenn sie nicht messbar ist; die Seite
        zeigt dann „nicht messbar" statt einer erfundenen 80.
        """
        return {"mikrofon_an": self._mikrofon_an,
                "lautsprecher_an": self._lautsprecher_an,
                "lautstaerke_mikrofon": self.lautstaerke("mikrofon"),
                "lautstaerke_lautsprecher": self.lautstaerke("lautsprecher"),
                "karte": self.karte,
                "letzter_fehler": self.letzter_fehler}

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
                if gemessen and self._lautstaerke.get(was) != gemessen:
                    self._lautstaerke[was] = gemessen
                    self._sichern()
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
