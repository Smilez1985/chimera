"""Der Ton erinnert an offene Freigaben (DESIGN, Absatz "Kein Ablauf mehr —
der Ton erinnert").

Warum es das gibt (Entscheidung smilez, 13.11.2026): Freigaben laufen nicht
mehr ab. Der stille Ablauf machte mitten in der Arbeit zu, ohne dass man es
merkte -- aber ohne Ablauf bliebe eine vergessene Freigabe fuer immer offen.
Deshalb erinnert ein kurzer Ton alle ``erinnern_alle`` Sekunden, **wiederholt
bis der Nutzer die Freigabe schliesst** (auch wenn niemand da ist -- bewusste
Entscheidung).

Aufteilung: die Entscheidung *wann* ist rein (:class:`Erinnerung`, ohne Uhr
und ohne Ton, dadurch pruefbar). Nur die Ausgabe (:func:`abspielen`) fasst
ALSA an, und auch die nur ueber ``aplay`` mit fester ``argv``.

Warum kein ``numpy``: Ein Ton von 0,18 s ist eine Sinuswelle in ``array``;
numpy waere auf einem Pi mit 512 MB fuer ein Bierdeckel-Problem ein
Speicherposten (Regel 5g: keine Rechenbibliothek fuer Audio).
"""

from __future__ import annotations

import array
import logging
import math
import shutil
import subprocess
import tempfile
import wave
from pathlib import Path

log = logging.getLogger("chimera.freigabe")

#: Abstand, wenn der Eintrag keinen nennt.
ABSTAND_VORGABE = 300
#: Kuerzer ist kein Erinnern, sondern Dauerpiepen (dieselbe Grenze wie in Rust).
ABSTAND_MIN = 60
#: Laenge und Hoehe des Tons. Kurz und nicht schrill: er soll auffallen,
#: nicht erschrecken.
TON_DAUER_S = 0.18
TON_FREQ_HZ = 880
TON_RATE = 44100
TON_PEGEL = 0.35


class Erinnerung:
    """Entscheidet, wann es klingelt. Rein: ``jetzt`` kommt herein.

    ``tick`` wird beim ersten Sehen eines offenen Werkzeugs **nicht** sofort
    laut -- wer gerade freigegeben hat, soll nicht im selben Moment einen Ton
    bekommen. Erst nach dem Abstand.
    """

    def __init__(self, abstand_vorgabe: int = ABSTAND_VORGABE) -> None:
        self.abstand_vorgabe = int(abstand_vorgabe)
        self._faellig: dict[str, int] = {}

    def offene(self, freigaben: dict) -> dict[str, int]:
        """Werkzeug -> Abstand in Sekunden, nur was offen ist."""
        out: dict[str, int] = {}
        werkzeuge = freigaben.get("werkzeuge") if isinstance(freigaben, dict) else None
        if not isinstance(werkzeuge, dict):
            return out
        for name, e in werkzeuge.items():
            if not isinstance(e, dict) or e.get("modus") != "offen":
                continue
            roh = e.get("erinnern_alle")
            if isinstance(roh, bool) or not isinstance(roh, int):
                abstand = self.abstand_vorgabe
            else:
                abstand = max(ABSTAND_MIN, roh)
            out[str(name)] = int(abstand)
        return out

    def tick(self, freigaben: dict, jetzt: int) -> list[str]:
        """Welche Werkzeuge erinnern jetzt? Ein Ton je Aufruf, nicht je Werkzeug."""
        offen = self.offene(freigaben)
        # Geschlossenes wird vergessen -- eine spaetere neue Freigabe beginnt
        # wieder mit vollem Abstand (sonst klaenge sie sofort).
        for name in list(self._faellig):
            if name not in offen:
                del self._faellig[name]
        klingeln: list[str] = []
        for name, abstand in offen.items():
            faellig = self._faellig.get(name)
            if faellig is None:
                self._faellig[name] = jetzt + abstand
                continue
            if jetzt >= faellig:
                klingeln.append(name)
                # Ab jetzt rechnen, nicht nachholen: nach einer Stunde
                # Stillstand soll es einmal klingeln, nicht zwoelfmal.
                self._faellig[name] = jetzt + abstand
        return sorted(klingeln)


def ton_bauen(pfad: Path, *, dauer_s: float = TON_DAUER_S,
              freq: int = TON_FREQ_HZ, rate: int = TON_RATE,
              pegel: float = TON_PEGEL) -> Path:
    """Eine kurze Sinuswelle als 16-Bit-Mono-WAV schreiben."""
    anzahl = max(1, int(dauer_s * rate))
    rahmen = array.array("h")
    schritt = 2.0 * math.pi * freq / rate
    for i in range(anzahl):
        # Ein- und Ausblenden, damit es nicht knackt.
        rand = min(1.0, i / max(1, int(0.01 * rate)), (anzahl - 1 - i) / max(1, int(0.01 * rate)))
        rahmen.append(int(pegel * rand * 32767 * math.sin(schritt * i)))
    with wave.open(str(pfad), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(rahmen.tobytes())
    return pfad


def abspielen(pfad: Path, *, geraet: str = "default", timeout: float = 10.0,
              lauf=None) -> str:
    """Den Ton ueber ``aplay`` ausgeben. Leerer Text = gespielt.

    ``lauf`` ist zum Pruefen da (die ``argv`` wird gemessen, nicht behauptet).
    Ein Fehler wird zurueckgegeben statt geworfen: Eine Erinnerung, die den
    Dienst umbringt, waere schlimmer als eine, die schweigt.
    """
    if lauf is None:
        # Nur der echte Weg braucht das Programm; ein eingesetzter Lauf
        # (Pruefung) misst die argv, nicht das Vorhandensein von aplay.
        if not shutil.which("aplay"):
            return "aplay fehlt (Paket alsa-utils) -- es kann nicht erinnert werden"
        lauf = lambda befehl: subprocess.run(  # noqa: E731
            befehl, capture_output=True, text=True, timeout=timeout)
    try:
        r = lauf(["aplay", "-q", "-D", geraet, str(pfad)])
    except (OSError, subprocess.TimeoutExpired) as exc:
        return f"aplay nicht ausfuehrbar: {exc}"
    if getattr(r, "returncode", 0) != 0:
        return f"aplay rc {r.returncode}: {(getattr(r, 'stderr', '') or '').strip()[-200:]}"
    return ""


def klingeln(names: list[str], *, pfad: Path | None = None,
             geraet: str = "default", lauf=None) -> str:
    """Einen Ton fuer *alle* faelligen Werkzeuge -- nicht je Werkzeug einen.

    Die Namen stehen nur im Protokoll: Der Ton sagt "etwas ist offen", die
    Liste steht auf dem Panel und in Telegram.
    """
    if not names:
        return ""
    ziel = pfad
    if ziel is None:
        # Fester Ort statt eines neuen Ordners je Ton: auf einem Pi mit 512 MB
        # zaehlt /tmp (tmpfs) gegen den Arbeitsspeicher.
        ziel = Path(tempfile.gettempdir()) / "chimera-erinnerung.wav"
        if not ziel.is_file():
            ton_bauen(ziel)
    fehler = abspielen(ziel, geraet=geraet, lauf=lauf)
    if fehler:
        log.warning("Erinnerung nicht gespielt (%s): %s", ", ".join(names), fehler)
    else:
        log.info("Erinnerung: %s ist offen.", ", ".join(names))
    return fehler
