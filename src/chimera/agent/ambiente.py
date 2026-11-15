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
    # dazu; CHILL fuer Tage, an denen nichts ansteht.
    (6, 10, ("COFFEE", "YAWN", "STRETCH", "CHILL")),
    # tagsueber: Grundstimmung. ROCK und MUSIC sind endlos (keine dauer_s),
    # sie bleiben also stehen, bis ein Zustand sie abloest.
    (10, 18, ("ROCK", "MUSIC", "CHILL")),
    # abends: die Handlungen mit Ablauf (dauer_s = ein Zug).
    (18, 23, ("BONG", "JOINT", "CHILL")),
    # nachts: Ruhe. Kein Fenster -- der Agent soll nicht rauchen, waehrend
    # niemand hinsieht.
)

#: Mindestabstand zwischen zwei Aktionen, in Sekunden. Ohne diese Sperre
#: wuerde der Dienst bei jedem Takt (30 s) erneut wuerfeln duerfen.
MIN_ABSTAND_S = 20 * 60

#: Sperre je Ausdruck: derselbe Ausdruck kommt fruehestens nach 90 Minuten
#: wieder. Sonst raucht das Geraet den ganzen Abend.
SPERRE_JE_AUSDRUCK_S = 90 * 60

#: Wahrscheinlichkeit, dass ein faelliger Takt wirklich etwas ausloest.
#: 0.35 heisst: im Schnitt drei Takte (90 s) nach Ablauf des Abstands.
CHANCE = 0.35


def kandidaten(stunde: int) -> tuple[str, ...]:
    """Die Ausdruecke, die zu dieser Stunde passen (leer = Ruhe)."""
    h = int(stunde) % 24
    for von, bis, namen in FENSTER:
        if von <= h < bis:
            return namen
    return ()


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
        namen = [n for n in namen
                 if jetzt - self._je.get(n, float("-inf")) >= SPERRE_JE_AUSDRUCK_S]
        if not namen:
            return None
        if self._zufall() > CHANCE:
            return None
        wahl = namen[min(len(namen) - 1, int(self._zufall() * len(namen)))]
        self._letzter = jetzt
        self._je[wahl] = jetzt
        log.info("Ambiente: %s gewaehlt (Stunde %d, %d moeglich)",
                 wahl, stunde, len(namen))
        return wahl

    def vergessen(self) -> None:
        """Alles zuruecksetzen (Neustart, Test)."""
        self._letzter = None
        self._je.clear()
