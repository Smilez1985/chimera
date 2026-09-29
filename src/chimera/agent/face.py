"""Die Brücke zwischen Agent und Gesicht.

Damit `set_face` nicht ins Leere greift und der Agentzustand sichtbar wird
(`docs/DESIGN.md` §7). Ohne diese Brücke wären Werkzeug und Renderer zwei
Bausteine ohne Verbindung — gebaut, aber nicht verdrahtet (Regel 10h).

Zwei Richtungen:

* **Der Agent setzt einen Ausdruck** — über einen Namen aus der
  Bibliothek oder eine Mischung (``CHILL+ROCK``).
* **Der Zustand setzt einen Ausdruck** — denkt, arbeitet, spricht,
  verwirrt. Das ist die ehrliche Anzeige: Ein Agent, der sich verrennt,
  sieht man das an.
"""

from __future__ import annotations

import logging

from ..mood import blend

log = logging.getLogger(__name__)

#: Welcher Ausdruck zu welchem Zustand passt. Die Namen sind Vorschläge —
#: fehlt einer in der Bibliothek, wird der Zustand einfach nicht angezeigt,
#: statt dass etwas abstürzt.
STATE_MOODS = {
    "wartet": ("IDLE", "LISTEN"),
    "hoert": ("LISTEN",),
    "denkt": ("CURIOUS", "LISTEN"),
    "arbeitet": ("FOCUS", "CURIOUS"),
    "spricht": ("TALK", "LISTEN"),
    "verwirrt": ("CHAOS", "SCARED"),
    "fehler": ("SAD", "SCARED"),
}

#: Zustände, die hart umschalten sollen — ein Schreck blendet nicht ein
#: (Regel 6b).
HARD_STATES = {"verwirrt", "fehler"}


class Face:
    """Setzt Ausdrücke auf dem Renderer-Zustand."""

    def __init__(self, registry, state):
        """``registry`` ist die Mood-Bibliothek, ``state`` der Renderer-Zustand."""
        self.moods = registry
        self.state = state
        self._last_state: str | None = None

    # --- vom Agenten ------------------------------------------------------

    def set_by_name(self, name: str, *, hard: bool = False) -> dict:
        """Einen Ausdruck setzen. ``A+B`` mischt, ``A+B:0.3`` gewichtet."""
        mood = self._resolve(name)
        self.state.set_mood(mood, hard=hard)
        return mood

    def _resolve(self, name: str) -> dict:
        text = str(name).strip()
        if not text:
            raise KeyError("leerer Name")

        if "+" in text:
            spec, _, weight = text.partition(":")
            a_name, _, b_name = spec.partition("+")
            try:
                t = float(weight) if weight.strip() else 0.5
            except ValueError:
                t = 0.5
            a = self._one(a_name)
            b = self._one(b_name)
            return blend.mix(a, b, t, name=text.upper())

        return self._one(text)

    def _one(self, name: str) -> dict:
        key = name.strip().upper()
        if not key:
            raise KeyError("leerer Name")
        found = self.moods.find(key)
        if found is None:
            raise KeyError(
                f"{key!r} — bekannt sind: {', '.join(sorted(self.moods.names())[:12])} …"
            )
        return self.moods.get(key)

    # --- vom Zustand ------------------------------------------------------

    def show_state(self, what: str) -> None:
        """Den Agentzustand anzeigen, wenn ein passender Ausdruck da ist.

        Kein Fehler, wenn nicht: Das Gesicht ist Beiwerk des Zustands,
        nicht umgekehrt.
        """
        if what == self._last_state:
            return
        self._last_state = what

        for candidate in STATE_MOODS.get(what, ()):
            mood = self.moods.find(candidate)
            if mood is not None:
                self.state.set_mood(self.moods.get(candidate),
                                    hard=(what in HARD_STATES))
                return
        log.debug("Kein Ausdruck für Zustand %r", what)
