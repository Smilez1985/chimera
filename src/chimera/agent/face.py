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

#: Ausdrücke, die eine **Tätigkeit behaupten**. Sie gehören einem Zustand,
#: nicht dem Agenten: „WORK" heißt „ich arbeite gerade". Steht der Agent
#: still, darf das Gesicht das nicht weiter sagen (smilez, 15.11.2026:
#: *„aktuell zeigt er Work … aber da das llm momentan nicht arbeitet ist der
#: Zustand gelogen"*). Deshalb nimmt die Ruhe diese Ausdrücke zurück, auch
#: wenn der Agent sie selbst gesetzt hat — ein ``set_face WORK`` von Hand ist
#: kein Dauerzustand, sondern eine Aussage über einen Moment.
#:
#: Ausdrücke, die **keine** Tätigkeit behaupten (BONG, ROCK, COFFEE, eigene
#: Moods), bleiben davon unberührt: sie sind Stimmung, nicht Arbeitsbericht.
STATE_ANSPRUCH = frozenset(
    name for zustand, namen in STATE_MOODS.items() if zustand != "wartet"
    for name in namen
)

#: Zustände, die hart umschalten sollen — ein Schreck blendet nicht ein
#: (Regel 6b).
HARD_STATES = {"verwirrt", "fehler"}

#: Veraltet: Die Standzeit kommt aus dem Aufruf oder aus dem Ausdruck.
#: Ohne beides gilt ein Ausdruck **bis zur Ablösung** (smilez, 15.11.2026:
#: „muss das mood … oder das llm entscheiden — bis Ablösung oder x
#: Sekunden"). Die Zahl bleibt als benannter Wert stehen, damit niemand
#: eine alte 5 aus dem Code fischen muss.
#:
#: Fund am Gerät (15.11.2026, smilez): *„wird das so schnell abgespielt … das
#: es kaum zu sehen und sofort vorbei ist"*. Nachgemessen: Die Bewegung eines
#: Moods ist in Ordnung (eingebaute Ausdrücke schwingen zwischen 0,5 s und
#: 21 s je Periode), aber der Ausdruck war nur **0,45 s** zu sehen — die
#: Übergangsdauer. Danach meldete die Schleife ``arbeitet`` und blendete ihn
#: weg. Ein Befehl, dessen Ergebnis man nicht sieht, ist kein Befehl.
#:
#: Seit derselben Nacht entscheidet die Dauer der Aufruf selbst (smilez:
#: „muss das mood … oder das llm entscheiden — bis Ablösung oder x
#: Sekunden"): ``dauer`` am Werkzeug, sonst ``dauer_s`` des Ausdrucks,
#: sonst diese Zahl.
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
        #: Bis wann der Agentenausdruck steht: ``None`` = bis zur Ablösung
        #: (niemand übernimmt ihn), eine Zahl = Zeitpunkt auf der Uhr.
        self._haelt_bis: float | None = None
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

    def set_by_name(self, name: str, *, hard: bool = False,
                    dauer: float | None = None) -> dict:
        """Einen Ausdruck setzen. ``A+B`` mischt, ``A+B:0.3`` gewichtet.

        ``dauer`` (Sekunden) entscheidet, wie lange er steht — smilez,
        15.11.2026: *„muss das mood (bei Animationen mit festem Ablauf) oder
        das llm entscheiden (bis Ablösung, oder x Sekunden/Minuten)"*. Die
        Reihenfolge ist: was das Modell sagt → was der Ausdruck selbst
        mitbringt (``dauer_s``) → ``HALT_S`` als Untergrenze. ``0`` heißt
        **bis zur Ablösung**: der Ausdruck bleibt, bis jemand anders ihn
        ersetzt.
        """
        mood = self._resolve(name)
        vorher = self.state.mood
        self.state.set_mood(mood, hard=hard)
        # Der Agent hat hier bewusst gewählt — das ist der Ausdruck, zu dem
        # `wartet` zurückkehrt (Regel „Sprechgesicht" 6).
        self._agent_mood = str(mood.get("name") or "")
        self._last_state = ""
        # … und er bleibt stehen, sonst sieht niemand das Ergebnis des
        # Werkzeugaufrufs.
        sekunden = self._dauer_von(mood, dauer)
        if sekunden <= 0:
            self._haelt_bis = None                 # bis zur Ablösung
            self.state.mood_bis = None
            self.state.mood_zurueck = None
            self.state.mood_ablauf = None
            return mood
        self._haelt_bis = self._uhr() + sekunden
        self.state.mood_bis = self._uhr() + sekunden
        self.state.mood_zurueck = vorher
        # Der Renderer ruft das nach Ablauf auf — er läuft ohnehin im Takt,
        # ein zweiter Faden wäre teurer als der Nutzen.
        self.state.mood_ablauf = self._ablauf
        return mood

    def _dauer_von(self, mood: dict, dauer: float | None) -> float:
        """Die Standzeit in Sekunden: Modell → Ausdruck → Untergrenze.

        **Ein Ausdruck mit eigener Länge läuft ganz** (smilez, 15.11.2026:
        *„bong friert mitten in der mood Animation ein, das muss ganz laufen,
        von Anfang bis Ende"*). Am Pi gesehen: das Modell rief
        ``set_face BONG dauer=4``, die Zug-Animation dauert aber
        ``TOKE_PERIOD`` = 13 s — nach 4 s wurde mitten im Zug zurückgenommen.
        Deshalb gilt für einen Ausdruck mit ``dauer_s``:

        - ``dauer`` **verlängert** (größerer Wert), kürzt aber nie.
        - ``dauer`` 0/leer heißt bei einem endlichen Ausdruck **einmal ganz**,
          nicht „endlos": ein Zug ist eine Handlung mit Anfang und Ende, kein
          Dauerzustand. Endlose Ausdrücke (etwa ``ROCK``) haben keine
          ``dauer_s`` und bleiben bis zur Ablösung.
        """
        eigene = 0.0
        try:
            eigene = max(0.0, float(mood.get("dauer_s") or 0))
        except (TypeError, ValueError):
            eigene = 0.0
        if dauer is None:
            return eigene
        try:
            wert = max(0.0, float(dauer))
        except (TypeError, ValueError):
            wert = 0.0
        if eigene > 0:
            return max(wert, eigene)
        return wert

    def _ablauf(self, zurueck: dict | None = None) -> None:
        """Ein Ausdruck mit fester Dauer ist vorbei (gerufen vom Renderer).

        ``zurueck`` ist der Ausdruck, der vor dem gesetzten galt — der
        Renderer übergibt ihn, damit das Zurücknehmen nicht davon abhängt,
        in welcher Reihenfolge die Felder geräumt werden.

        Seit 15.11.2026 ist der Ablauf **kein Löschen der Wahl** (smilez, am
        Pi gesehen: das Modell sagte „das Gesicht bleibt WORK", auf dem
        Display stand `IDLE`). Vorher setzte diese Stelle `_agent_mood = ""`;
        damit fand `wartet` kein Agentengesicht mehr und fiel auf `IDLE`
        zurück, obwohl der vorherige Ausdruck weiter in der Bibliothek stand.
        Jetzt wird der vorherige zum Agentengesicht: `IDLE` bleibt genau der
        Fall „der Agent hat noch nichts gewählt".
        """
        if zurueck is None:
            zurueck = self.state.mood_zurueck
        name = str((zurueck or {}).get("name") or "").strip()
        # Kein Tätigkeitsausdruck als stehendes Gesicht (15.11.2026, zweiter
        # Fund am Pi): set_face WORK -> set_face BONG 13 s -> nach dem Zug
        # stand wieder WORK, und niemand meldete je wieder ``wartet``. Das
        # Display behauptete stundenlang Arbeit, die nicht lief. Der
        # vorherige Ausdruck darf zurückkommen, wenn er eine Stimmung ist;
        # behauptet er eine Tätigkeit, gehört das Gesicht dem Ruhezustand.
        if name and self.moods.find(name) and name not in STATE_ANSPRUCH:
            self._agent_mood = name
            zurueck_mood = zurueck
        else:
            self._agent_mood = ""
            zurueck_mood = self._ruhemood()
        self._haelt_bis = 0.0
        self._last_state = ""
        self.state.mood_bis = None
        self.state.mood_ablauf = None
        self.state.mood_zurueck = None
        if zurueck_mood is not None:
            self.state.set_mood(zurueck_mood)

    def _ruhemood(self) -> dict | None:
        """Der Ausdruck des Ruhezustands (``IDLE``), oder ``None``."""
        for candidate in STATE_MOODS.get("wartet", ()):
            mood = self.moods.find(candidate)
            if mood is not None:
                return self.moods.get(candidate)
        return None

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
        elif what != "wartet" and self._haelt():
            # Der Agent hat gerade ein Gesicht gesetzt: Es bleibt stehen,
            # statt im nächsten Zustand zu verschwinden. ``_last_state``
            # wird absichtlich NICHT gesetzt — derselbe Zustand darf es
            # nach Ablauf der Frist erneut versuchen. ``wartet`` ist
            # ausgenommen: Es zeigt ohnehin den Agentenausdruck, und ein
            # inzwischen gelöschter muss auf IDLE zurückfallen können.
            rest = ("bis zur Ablösung" if self._haelt_bis is None
                    else f"{self._haelt_bis - self._uhr():.1f} s")
            log.debug("Zustand %r wartet: Ausdruck %r hält noch (%s)",
                      what, self._agent_mood, rest)
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

    @property
    def laeuft(self) -> bool:
        """Laeuft gerade ein endlicher Ausdruck, der Zustände sperrt?

        Fuer aussen (Dienst, Ambiente): Wer etwas zeigen will, muss wissen,
        ob es gerade blockiert (DESIGN, Regel „Sprechgesicht" Punkt 9).
        """
        return self._haelt()

    def _haelt(self) -> bool:
        """Steht ein gesetzter Ausdruck und **blockiert** er andere Zustände?

        Seit 15.11.2026 (smilez) gilt die Trennung nach Länge:

        - **Endlicher Ausdruck** (``dauer`` am Aufruf oder ``dauer_s`` am
          Ausdruck): Er läuft ganz und blockiert jeden Zustandswechsel bis zu
          seinem Ende. Nur ein Reflex (``verwirrt``, ``fehler``) bricht ihn.
          Grund: *„bong friert mitten in der mood Animation ein, das muss
          ganz laufen, von Anfang bis Ende"*.
        - **Endloser Ausdruck** (keine Dauer, etwa ``ROCK``): *„moods wie
          Rock ohne feste länge weil endlos Loop brauchen keine harte
          Laufzeit"* — er ist das **stehende Gesicht** und wird von
          Zuständen ohne Sperre abgelöst; nach dem Zustand kommt er zurück.

        ``_haelt_bis is None`` heißt also nicht mehr „für immer sperren",
        sondern „kein Lauf, keine Sperre".
        """
        if not self._agent_mood:
            return False
        if self._haelt_bis is None:
            return False
        return self._uhr() < self._haelt_bis

    def _ruhegesicht(self) -> bool:
        """Das vom Agenten gewählte Gesicht zeigen, wenn es noch existiert.

        **Kein Tätigkeitsausdruck** (siehe ``STATE_ANSPRUCH``): „WORK" in der
        Ruhe wäre eine Lüge über den Zustand. Der Merker wird dabei geräumt,
        damit die Ruhe nicht bei jedem Aufruf neu prüft.

        Rückgabe False, wenn es keines gibt — dann zeigt der Zustand wie
        bisher `IDLE`.
        """
        name = self._agent_mood.strip().upper()
        if not name or self.moods.find(name) is None:
            return False
        if name in STATE_ANSPRUCH:
            # Der Ausdruck behauptet Arbeit, Zuhören, Denken oder Sprechen.
            # Steht der Agent still, gehört das Gesicht dem Zustand.
            log.debug("Ruhe: Ausdruck %r behauptet einen Zustand — "
                      "zurück auf das Ruhegesicht", name)
            self._agent_mood = ""
            return False
        self.state.set_mood(self.moods.get(name), hard=False)
        return True
