"""Übergänge zwischen Moods.

Noisy blendet nur die Farben ineinander; alles andere springt. Das fällt
dort kaum auf, weil die Moods aus einer festen Tabelle kommen und einander
ähneln. In Chimera erfindet das Sprachmodell Ausdrücke — da können zwei
aufeinanderfolgende Moods weit auseinanderliegen, und ein Sprung sieht aus
wie ein Bildfehler.

Also über **alle** Felder blenden. Die Mechanik dafür steht schon in
:func:`chimera.mood.blend.mix`; hier kommt die Zeit dazu.

**Hart muss aber auch gehen.** Ein Reflex, der über eine halbe Sekunde
einblendet, ist kein Schreck, sondern eine Verzögerung (§3.4, Ebene 1).
Moods mit ``fast_track`` wechseln deshalb sofort — und wer es ausdrücklich
will, bekommt es auch ohne dieses Merkmal.

Die Dauer ist eine Angabe in Sekunden, keine Bildanzahl: Sinkt die Bildrate
beim Sprechen (§4.1), soll ein Übergang trotzdem gleich lang dauern.
"""

from __future__ import annotations

import time

from .blend import mix


def ease(t: float) -> float:
    """Weicher Verlauf statt gleichmäßiger.

    Ein linearer Übergang wirkt mechanisch: Er beginnt und endet abrupt,
    obwohl sich die Werte gleichmäßig ändern. Diese Kurve startet und
    stoppt sanft — dasselbe, was Noisys Glättung beim Audio tut.
    """
    t = max(0.0, min(1.0, t))
    return t * t * (3.0 - 2.0 * t)


class Transition:
    """Hält den laufenden Übergang und liefert den Mood für das Bild.

    Benutzung::

        tr = Transition(start_mood)
        tr.to(neuer_mood)             # weich, Standarddauer
        tr.to(schreck, hard=True)     # sofort
        mood = tr.current()           # in jedem Bild

    Der Fortschritt hängt an der Uhr, nicht an der Zahl der Aufrufe.
    Bleibt der Renderer einmal hängen, springt der Übergang weiter, statt
    stehenzubleiben.
    """

    #: Voreinstellung in Sekunden. Kurz genug, um nicht zäh zu wirken,
    #: lang genug, dass man den Wechsel sieht.
    DEFAULT_DURATION = 0.45

    def __init__(self, mood: dict, *, duration: float | None = None,
                 clock=time.monotonic) -> None:
        self._clock = clock
        self.duration = self.DEFAULT_DURATION if duration is None else duration
        self._from = mood
        self._to = mood
        self._start = self._clock()
        self._span = 0.0
        self._cached: dict | None = mood
        self._cached_t: float | None = None

    # --- Zustand ----------------------------------------------------------

    @property
    def target(self) -> dict:
        """Der Mood, auf den zugelaufen wird."""
        return self._to

    @property
    def active(self) -> bool:
        return self.progress < 1.0

    @property
    def progress(self) -> float:
        if self._span <= 0.0:
            return 1.0
        return min(1.0, (self._clock() - self._start) / self._span)

    # --- Steuern ----------------------------------------------------------

    def to(self, mood: dict, *, hard: bool = False,
           duration: float | None = None) -> None:
        """Auf einen neuen Mood wechseln.

        ``hard=True`` schaltet sofort um. Dasselbe geschieht automatisch bei
        Moods mit ``fast_track`` — ein Erschrecken darf nicht einblenden.
        """
        if mood is None:
            return

        # Derselbe Mood: nichts tun, sonst würde jeder Aufruf den Übergang
        # neu starten und das Gesicht bliebe in Bewegung.
        if mood is self._to or mood.get("name") == self._to.get("name"):
            self._to = mood
            return

        span = self.duration if duration is None else duration
        if hard or mood.get("fast_track") or span <= 0:
            self._from = self._to = mood
            self._span = 0.0
            self._cached, self._cached_t = mood, None
            return

        # Von dort aus weiter, wo der Übergang gerade steht -- nicht vom
        # alten Ausgangspunkt. Sonst ruckt es zurück, wenn zwei Wechsel
        # dicht aufeinanderfolgen.
        self._from = self.current()
        self._to = mood
        self._span = span
        self._start = self._clock()
        self._cached = self._cached_t = None

    def snap(self) -> None:
        """Laufenden Übergang sofort beenden."""
        self._from = self._to
        self._span = 0.0
        self._cached, self._cached_t = self._to, None

    # --- Abfragen ---------------------------------------------------------

    def current(self) -> dict:
        """Der Mood für das aktuelle Bild."""
        t = self.progress
        if t >= 1.0:
            self._from = self._to
            self._span = 0.0
            self._cached, self._cached_t = self._to, None
            return self._to

        # Mischen ist nicht umsonst -- bei gleichem Fortschritt das
        # Ergebnis wiederverwenden. Bei 15 Bildern je Sekunde spart das
        # nichts Dramatisches, aber es kostet auch nichts.
        if self._cached is not None and self._cached_t == t:
            return self._cached

        blended = mix(self._from, self._to, ease(t),
                      name=self._to.get("name", "?"))
        self._cached, self._cached_t = blended, t
        return blended
