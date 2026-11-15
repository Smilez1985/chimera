"""Die Brücke zwischen Agent und Gesicht.

Damit `set_face` nicht ins Leere greift und der Agentzustand sichtbar wird
(`docs/DESIGN.md`, Abschnitt „Zustand sichtbar machen"). Ohne diese Brücke wären Werkzeug und Renderer zwei
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
import time

from ..mood import ablage as moodablage
from ..mood import blend
from ..mood.ablage import AblageFehler

log = logging.getLogger(__name__)

#: Welcher Ausdruck zu welchem Zustand passt. Die Namen sind Vorschläge —
#: fehlt einer in der Bibliothek, wird der Zustand einfach nicht angezeigt,
#: statt dass etwas abstürzt.
STATE_MOODS = {
    "wartet": ("IDLE",),
    "hoert": ("LISTEN",),
    "denkt": ("CURIOUS", "IDLE"),
    "arbeitet": ("WORK", "CURIOUS"),
    "spricht": ("SPEAK",),
    "verwirrt": ("CHAOS", "SCARED"),
    "fehler": ("SAD", "SCARED"),
}

#: Zustände, die hart umschalten sollen — ein Schreck blendet nicht ein
#: (Regel 6b).
HARD_STATES = {"verwirrt", "fehler"}

#: Wie lange ein vom **Agenten** gesetztes Gesicht stehen bleibt, bevor ein
#: Zustand (``arbeitet``, ``spricht``) es übernehmen darf — in Sekunden.
#:
#: Fund am Gerät (15.11.2026, smilez): *„wird das so schnell abgespielt … das
#: es kaum zu sehen und sofort vorbei ist"*. Nachgemessen: Die Bewegung eines
#: Moods ist in Ordnung (eingebaute Ausdrücke schwingen zwischen 0,5 s und
#: 21 s je Periode), aber der Ausdruck war nur **0,45 s** zu sehen — die
#: Übergangsdauer. Danach meldete die Schleife ``arbeitet`` und blendete ihn
#: weg. Ein Befehl, dessen Ergebnis man nicht sieht, ist kein Befehl.
HALT_S = 5.0


class Face:
    """Setzt Ausdrücke auf dem Renderer-Zustand."""

    def __init__(self, registry, state, *, ablage=None, clock=time.monotonic):
        """``registry`` ist die Mood-Bibliothek, ``state`` der Renderer-Zustand.

        ``ablage`` ist die Datei der eigenen Ausdrücke (DESIGN 3.3b). Fehlt
        sie, kann der Agent nichts ablegen — er sagt das dann, statt still
        zu verlieren, was er gerade erfunden hat.
        """
        self.moods = registry
        self.state = state
        self.ablage = ablage
        self._last_state: str | None = None
        #: Der Ausdruck, den der **Agent** zuletzt bewusst gesetzt hat
        #: (DESIGN, Regel „Sprechgesicht" 6). `wartet` kehrt dorthin zurück,
        #: statt auf IDLE — sonst radiert jeder Turn das Gesicht aus.
        self._agent_mood: str = ""
        #: Bis wann der Agentenausdruck stehen bleibt (``HALT_S``).
        self._haelt_bis: float = 0.0
        #: Einsetzbare Uhr — die Haltezeit wird ohne Warten geprüft.
        self._uhr = clock

    # --- eigene Ausdrücke -----------------------------------------------

    def anlegen(self, name: str, *, von: str = "", felder: dict | None = None):
        """Einen Ausdruck erfinden und behalten (DESIGN 3.3b)."""
        if self.ablage is None:
            raise AblageFehler("Keine Ablage für eigene Ausdrücke gesetzt — "
                              "es wird nichts gespeichert.")
        return moodablage.anlegen(self.moods, self.ablage, name,
                                  von=von, felder=felder)

    def entfernen(self, name: str) -> str:
        """Einen selbst angelegten Ausdruck löschen. Eingebaute nie."""
        if self.ablage is None:
            raise AblageFehler("Keine Ablage für eigene Ausdrücke gesetzt.")
        return moodablage.entfernen(self.moods, self.ablage, name)

    # --- vom Agenten ------------------------------------------------------

    def set_by_name(self, name: str, *, hard: bool = False) -> dict:
        """Einen Ausdruck setzen. ``A+B`` mischt, ``A+B:0.3`` gewichtet."""
        mood = self._resolve(name)
        self.state.set_mood(mood, hard=hard)
        # Der Agent hat hier bewusst gewählt — das ist der Ausdruck, zu dem
        # `wartet` zurückkehrt (Regel „Sprechgesicht" 6).
        self._agent_mood = str(mood.get("name") or "")
        # … und er bleibt erst einmal stehen (HALT_S), sonst sieht niemand
        # das Ergebnis des Werkzeugaufrufs.
        self._haelt_bis = self._uhr() + HALT_S
        self._last_state = ""
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
                f"{key!r} — die ganze Liste gibt das Werkzeug 'moods' "
                f"({len(self.moods)} Ausdrücke, z. B. "
                f"{', '.join(sorted(self.moods.names())[:6])} …)"
            )
        return self.moods.get(key)

    # --- vom Zustand ------------------------------------------------------

    def show_state(self, what: str) -> None:
        """Den Agentzustand anzeigen, wenn ein passender Ausdruck da ist.

        Kein Fehler, wenn nicht: Das Gesicht ist Beiwerk des Zustands,
        nicht umgekehrt.

        ``wartet`` ist die Ausnahme (Regel „Sprechgesicht" 6): Der Ruhezustand
        ist das **Agentengesicht**, nicht IDLE. Sonst wäre jedes `set_face`
        am Turn-Ende vergessen — genau das war am Display zu sehen.
        """
        if what == self._last_state:
            return
        if what in HARD_STATES:
            # Ein Schreck ist ein Reflex und bricht die Haltezeit.
            self._haelt_bis = 0.0
        elif what != "wartet" and self._uhr() < self._haelt_bis:
            # Der Agent hat gerade ein Gesicht gesetzt: Es bleibt stehen,
            # statt im nächsten Zustand zu verschwinden. ``_last_state``
            # wird absichtlich NICHT gesetzt — derselbe Zustand darf es
            # nach Ablauf der Frist erneut versuchen. ``wartet`` ist
            # ausgenommen: Es zeigt ohnehin den Agentenausdruck, und ein
            # inzwischen gelöschter muss auf IDLE zurückfallen können.
            log.debug("Zustand %r wartet: Ausdruck %r hält noch %.1f s",
                      what, self._agent_mood, self._haelt_bis - self._uhr())
            return
        self._last_state = what

        if what == "wartet" and self._ruhegesicht():
            return

        for candidate in STATE_MOODS.get(what, ()):
            mood = self.moods.find(candidate)
            if mood is not None:
                self.state.set_mood(self.moods.get(candidate),
                                    hard=(what in HARD_STATES))
                return
        log.debug("Kein Ausdruck für Zustand %r", what)

    def _ruhegesicht(self) -> bool:
        """Das vom Agenten gewählte Gesicht zeigen, wenn es noch existiert.

        Rückgabe False, wenn es keines gibt — dann zeigt der Zustand wie
        bisher `IDLE`.
        """
        name = self._agent_mood.strip().upper()
        if not name or self.moods.find(name) is None:
            return False
        self.state.set_mood(self.moods.get(name), hard=False)
        return True
