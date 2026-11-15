"""Von selbst etwas tun: Tageszeit, Abstand, Ruhe.

**Vorbild und Abgrenzung.** Noisy wuerfelt alle 30--300 s einen Ausdruck aus
einem tageszeitlich gefilterten Pool (``noisy_orchestrator.py:712-772``,
``get_time_biased_idle_pool``). Der Gedanke ist richtig: Ein Geraet, das nur
auf Eingaben reagiert, wirkt tot. Die Mechanik ist fuer Chimera nicht
brauchbar:

- **Keine Abklingzeit.** In Noisy ist jeder Wurf gleich wahrscheinlich, auch
  fuenfmal dieselbe Handlung hintereinander.
- **Keine Ruecksicht auf einen laufenden Ausdruck.** Der naechste Wurf
  ersetzt den vorigen jederzeit -- dort faellt das nicht auf, weil Noisy
  keine Sperre kennt; hier wuerde es die Regel brechen, dass ein endlicher
  Ausdruck ganz laeuft (DESIGN, Regel „Sprechgesicht" Punkt 9).
- **Zufall statt Lage.** Noisy kennt keinen Zustand; Chimera schon. Was
  zufaellig aussieht, muss nicht zufaellig sein.

Deshalb hier: **Fenster** nach Tageszeit, **Mindestabstand** zwischen zwei
Aktionen, **Sperre je Ausdruck**, und nur wenn wirklich nichts laeuft. Die
Entscheidung ist eine **reine Funktion** -- kein Faden, kein Timer: Der
Dienst ruft sie in seinem 30-s-Takt, neben ``melden`` und ``erinnern``
(``__main__.dienst``). Damit gibt es weiterhin genau eine Schleife.

Der Zufall bleibt, aber gedeckelt: hoechstens eine Aktion je Fenster-Takt
und nur mit einer festen Wahrscheinlichkeit. So wirkt es lebendig, ohne dass
der Dienst im Minutentakt die Stimmung wechselt.
"""

from __future__ import annotations

import logging
import random
import time

log = logging.getLogger(__name__)

#: Welche Ausdruecke zu welcher Tageszeit passen. Die Stunde ist die lokale
#: Stunde (0-23); das Fenster gilt ``von <= h < bis``. Was hier steht und in
#: der Bibliothek fehlt, wird beim Waehlen uebergangen -- kein Fehler, denn
#: eigene Bibliotheken duerfen kleiner sein (smilez, 15.11.2026: „Mehr
#: Fenster").
FENSTER = (
    # frueh: aufwachen. Kaffee ist die Handlung, Gaehnen und Strecken passen
    # dazu; Wetter und Natur gehoeren zum Morgen.
    (6, 10, ("COFFEE", "YAWN", "STRETCH", "NATURE", "WEATHER", "EXERCISE")),
    # tagsueber: Grundstimmung. Alles hier ist endlos (keine dauer_s), es
    # bleibt also stehen, bis ein Zustand es abloest.
    (10, 18, ("ROCK", "MUSIC", "HIPHOP", "JAZZ", "CLASSIC", "REGGAE",
              "HOUSE", "TV", "POPCORN", "DANCE")),
    # abends: die Handlungen mit Ablauf (dauer_s = ein Zug) und CHILL.
    (18, 23, ("BONG", "JOINT", "CHILL", "MEDITATE", "TV", "POPCORN")),
    # nachts: Ruhe. Kein Fenster -- der Agent soll nicht rauchen, waehrend
    # niemand hinsieht.
)

#: Mindestabstand zwischen zwei Aktionen, in Sekunden. Ohne diese Sperre
#: wuerde der Dienst bei jedem Takt (30 s) erneut wuerfeln duerfen.
#:
#: **Von 20 auf 10 Minuten (15.11.2026, am Pi gesehen).** Mit 20 min Abstand
#: und 90 min Sperre stand ein Ausdruck eine halbe Stunde und der naechste
#: war trotzdem erzwungen; smilez: *„jetzt steht da seit Stunden das face
#: chill"*.
MIN_ABSTAND_S = 10 * 60

#: Sperre je Ausdruck: derselbe Ausdruck kommt fruehestens nach 35 Minuten
#: wieder. Sonst raucht das Geraet den ganzen Abend.
#:
#: **Von 90 auf 35 Minuten (15.11.2026).** Die alte Frist war laenger als der
#: Umlauf durch das Fenster: bei drei Ausdruecken und 20 min Abstand blieb je
#: Takt genau **ein** Kandidat uebrig, und aus dem Wurf wurde eine feste
#: Reihenfolge (ROCK -> CHILL -> MUSIC -> ROCK …). Am Pi stand in jeder
#: Zeile „1 moeglich". Jetzt ist die Sperre kuerzer als der Umlauf, damit
#: wieder mehr als einer zur Wahl steht.
SPERRE_JE_AUSDRUCK_S = 35 * 60

#: Wahrscheinlichkeit, dass ein faelliger Takt wirklich etwas ausloest.
#: 0.35 heisst: im Schnitt drei Takte (90 s) nach Ablauf des Abstands.
CHANCE = 0.35


#: Ausdruecke, die in einem Fenster nur **zu Gast** sind (15.11.2026, smilez:
#: *„warum hast du die idle Animationen wie Joint, bong und Kaffee ignoriert?"*).
#: Sie standen zwar im Fenster, aber mit zehn Musiknamen im Tag fenster kam
#: keiner mehr dran. Ein Gast hat ein **kleines Gewicht**: er kommt vor, aber
#: er verdraengt die Grundstimmung nicht.
GAST = {
    (6, 10): {"CHILL": 0.4},
    (10, 18): {"BONG": 0.25, "JOINT": 0.25, "COFFEE": 0.2},
    (18, 23): {"COFFEE": 0.2},
}

#: Gewicht eines Ausdrucks im Fenster. 1.0 = normal, kleiner = seltener.
STANDARD_GEWICHT = 1.0


def _fenster(stunde: int):
    h = int(stunde) % 24
    for von, bis, namen in FENSTER:
        if von <= h < bis:
            return von, bis, namen
    return None


def kandidaten(stunde: int) -> tuple[str, ...]:
    """Die Ausdruecke, die zu dieser Stunde passen (leer = Ruhe).

    Gäste (``GAST``) stehen dahinter; ihr Gewicht sagt ``gewicht``.
    """
    f = _fenster(stunde)
    if f is None:
        return ()
    von, bis, namen = f
    gaeste = tuple(n for n in GAST.get((von, bis), {}) if n not in namen)
    return tuple(namen) + gaeste


def gewicht(name: str, stunde: int) -> float:
    """Wie gern dieser Ausdruck zu dieser Stunde kommt (0 < g <= 1)."""
    f = _fenster(stunde)
    if f is None:
        return 0.0
    von, bis, _ = f
    return GAST.get((von, bis), {}).get(name, STANDARD_GEWICHT)


class Ambiente:
    """Waehlt gelegentlich eine passende Handlung -- und merkt sich, wann.

    ``uhr`` ist die monotone Uhr (fuer Tests einsetzbar), ``zufall`` liefert
    Werte in ``[0, 1)``. Beides ist austauschbar, damit die Entscheidung ohne
    Warten und ohne Wuerfelglueck pruefbar bleibt.
    """

    def __init__(self, *, uhr=time.monotonic, zufall=random.random):
        self._uhr = uhr
        self._zufall = zufall
        self._letzter: float | None = None
        self._letzter_name: str | None = None
        self._je: dict[str, float] = {}

    # --- Entscheidung -----------------------------------------------------

    def tick(self, *, stunde: int, frei: bool, haelt: bool,
             vorhanden) -> str | None:
        """Ein Takt. Rueckgabe: der Ausdruck, der jetzt gezeigt werden soll.

        ``frei``    -- der Agent tut gerade nichts (kein laufender Auftrag).
        ``haelt``   -- ein endlicher Ausdruck laeuft und sperrt.
        ``vorhanden`` -- die Namen der Bibliothek (was es wirklich gibt).
        """
        if not frei or haelt:
            return None
        jetzt = self._uhr()
        if (self._letzter is not None
                and jetzt - self._letzter < MIN_ABSTAND_S):
            return None
        namen = [n for n in kandidaten(stunde) if n in vorhanden]
        if not namen:
            return None
        # Nie zweimal dasselbe hintereinander (15.11.2026): sonst wirkt der
        # Wurf wie ein haengendes Gesicht. Nur wenn es nichts anderes gibt,
        # bleibt der letzte Ausdruck im Rennen.
        if len(namen) > 1 and self._letzter_name in namen:
            namen = [n for n in namen if n != self._letzter_name]
        alter = {n: jetzt - self._je.get(n, float("-inf")) for n in namen}
        erlaubt = [n for n in namen if alter[n] >= SPERRE_JE_AUSDRUCK_S]
        if not erlaubt:
            return None
        # Die Sperre ist eine Vorliebe, keine Mauer. Bliebe nur ein Kandidat
        # uebrig, waere der "Wurf" eine feste Reihenfolge -- am Pi stand in
        # jeder Zeile "1 moeglich" und das Gesicht wirkte eingefroren. Sind
        # mindestens zwei Namen im Fenster, stehen deshalb immer die beiden
        # am laengsten nicht gezeigten zur Wahl.
        if len(erlaubt) < 2 and len(namen) > 1:
            erlaubt = sorted(namen, key=lambda n: alter[n], reverse=True)[:2]
        if self._zufall() > CHANCE:
            return None
        # Gewichtet wuerfeln: Gaeste kommen seltener (siehe GAST).
        gewichte = [gewicht(n, stunde) for n in erlaubt]
        rest = self._zufall() * sum(gewichte)
        wahl = erlaubt[-1]
        for name, g in zip(erlaubt, gewichte):
            rest -= g
            if rest <= 0:
                wahl = name
                break
        self._letzter = jetzt
        self._letzter_name = wahl
        self._je[wahl] = jetzt
        log.info("Ambiente: %s gewaehlt (Stunde %d, %d von %d moeglich)",
                 wahl, stunde, len(erlaubt), len(namen))
        return wahl

    def vergessen(self) -> None:
        """Alles zuruecksetzen (Neustart, Test)."""
        self._letzter = None
        self._letzter_name = None
        self._je.clear()
