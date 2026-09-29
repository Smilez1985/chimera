"""Eine Sitzung, mehrere Türen.

Der Agent hält seinen Verlauf in ``self.history`` — pro Instanz. Solange
es nur eine Bedienschnittstelle gibt, fällt das nicht auf. Sobald eine
zweite dazukommt (Telegram neben der Sprache), entscheidet sich hier, ob
das Gerät **ein** Gegenüber ist oder zwei.

`docs/DESIGN.md` Regel 5d verlangt das Erste: Wer morgens per Telegram
etwas bespricht und abends davorsteht und nachfragt, redet mit demselben
Gegenüber. Diese Datei setzt das um, statt es zu hoffen.

Der Aufbau:

* **Kanal** — beschreibt eine Tür: wie lang darf die Antwort sein, wird
  sie gelesen oder gehört. Kein eigener Zustand, nur Eigenschaften.
* **Sitzung** — besitzt **einen** Agenten und serialisiert den Zugriff.
  Jede Tür ruft dieselbe ``ask()``, der Verlauf ist gemeinsam.

Warum die Sperre: Der Agent ist nicht wiedereintrittsfähig. Zwei
gleichzeitige Läufe würden sich in ``history`` und im Schleifenwächter
gegenseitig überschreiben — ein Fehler, der sich erst unter Last zeigt
und dann nicht reproduzierbar ist. Deshalb wird nicht parallel gedacht,
sondern angestellt.
"""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass, field, replace
from typing import Callable

log = logging.getLogger(__name__)

#: Ein Hinweis an das Modell, wie die Antwort ankommt. Kein Befehl an die
#: Technik — das Kürzen erledigt der Kanal selbst (siehe ``Channel.trim``),
#: weil ein Modell sich an Längenvorgaben nur ungefähr hält.
_STYLE = {
    "text": "Du antwortest im Chat. Absätze sind erlaubt, bleib trotzdem knapp.",
    "voice": ("Deine Antwort wird vorgelesen. Zwei bis drei Sätze, keine "
              "Aufzählungen, keine Sonderzeichen, keine Formatierung."),
}

@dataclass(frozen=True)
class Channel:
    """Eine Tür in die Sitzung.

    ``name``    — wie der Kanal im Protokoll und gegenüber dem Modell heißt.
    ``mode``    — ``"text"`` oder ``"voice"``; bestimmt den Stilhinweis.
    ``limit``   — harte Obergrenze in Zeichen, 0 heißt unbegrenzt.
    """

    name: str
    mode: str = "text"
    limit: int = 0

    def __post_init__(self) -> None:
        if not str(self.name).strip():
            raise ValueError("Ein Kanal braucht einen Namen")
        if self.mode not in _STYLE:
            raise ValueError(
                f"Unbekannte Betriebsart {self.mode!r} — bekannt: "
                + ", ".join(sorted(_STYLE))
            )
        if self.limit < 0:
            raise ValueError("Die Obergrenze kann nicht negativ sein")

    # --- was der Agent erfährt -------------------------------------------

    def hint(self) -> str:
        """Der Satz, der dem Modell den Kanal mitteilt."""
        return f"[Kanal: {self.name}] {_STYLE[self.mode]}"

    # --- was beim Nutzer ankommt -----------------------------------------

    def trim(self, text: str) -> str:
        """Auf die Obergrenze kürzen — an einer Satzgrenze, wenn möglich.

        Ein Modell hält sich an „zwei Sätze" nur ungefähr. Wer sich darauf
        verlässt, bekommt irgendwann eine vorgelesene Bildschirmseite.
        Deshalb wird hier gemessen, nicht gebeten.
        """
        text = (text or "").strip()
        if not self.limit or len(text) <= self.limit:
            return text

        cut = text[: self.limit]
        # Rückwärts bis zum letzten Satzende suchen, aber nur im hinteren
        # Drittel — sonst bleibt von einer langen Antwort ein Wortfetzen.
        floor = int(self.limit * 0.6)
        best = max(cut.rfind(z) for z in (". ", "! ", "? ", ".\n", "\n"))
        if best >= floor:
            return cut[: best + 1].strip()
        if cut.endswith((".", "!", "?")):
            return cut.strip()

        # Abbruchzeichen anhängen, ohne die Grenze zu reißen: Es muss in
        # die Grenze hineinpassen, nicht obendrauf. Wer eine Obergrenze
        # zusagt und sie beim Kürzen überschreitet, hat sie nicht.
        mark = " …"
        return cut[: max(self.limit - len(mark), 0)].rstrip() + mark

#: Die Tür, die immer existiert: der Standardweg ohne Besonderheiten.
DIRECT = Channel("direkt", mode="text")

@dataclass
class Turn:
    """Was ein Umlauf gekostet und gebracht hat — fürs Protokoll."""

    channel: str
    prompt: str
    text: str
    provider: str = ""
    model: str = ""
    tool_calls: int = 0
    fell_back: bool = False
    error: str = ""

@dataclass
class Session:
    """Ein Agent, ein Verlauf, beliebig viele Türen.

    Die Sitzung besitzt den Agenten. Wer sie benutzt, ruft ``ask()`` mit
    einem Kanal — der Verlauf ist für alle derselbe.
    """

    agent: object
    log_size: int = 50
    _lock: threading.RLock = field(default_factory=threading.RLock, repr=False)
    _turns: list[Turn] = field(default_factory=list, repr=False)
    _busy_channel: str | None = field(default=None, repr=False)

    # --- Zustand ----------------------------------------------------------

    @property
    def busy(self) -> bool:
        """Läuft gerade ein Umlauf?"""
        return self._busy_channel is not None

    @property
    def busy_channel(self) -> str | None:
        """Welcher Kanal beschäftigt den Agenten gerade."""
        return self._busy_channel

    def turns(self, limit: int = 0) -> list[Turn]:
        """Die letzten Umläufe, jüngster zuletzt."""
        with self._lock:
            return list(self._turns[-limit:] if limit else self._turns)

    # --- der Weg hinein ---------------------------------------------------

    def ask(self, prompt: str, channel: Channel = DIRECT) -> Turn:
        """Eine Frage stellen — egal durch welche Tür.

        Der Kanalhinweis wird dem Auftrag vorangestellt, nicht in den
        Systemtext geschrieben: Der Systemtext gilt für die ganze Sitzung,
        der Kanal wechselt von Umlauf zu Umlauf.

        Fehler des Agenten werden hier abgefangen und als Text beantwortet.
        Ein Bot, der bei einem Modellfehler stirbt, ist schlechter als
        einer, der sagt, dass etwas nicht ging.
        """
        text = (prompt or "").strip()
        if not text:
            raise ValueError("Leerer Auftrag")

        with self._lock:
            self._busy_channel = channel.name
            try:
                result = self.agent.run(f"{channel.hint()}\n\n{text}")
                turn = Turn(
                    channel=channel.name,
                    prompt=text,
                    text=channel.trim(result.text),
                    provider=getattr(result, "provider", ""),
                    model=getattr(result, "model", ""),
                    tool_calls=getattr(result, "tool_calls", 0),
                    fell_back=getattr(result, "fell_back", False),
                )
            except Exception as exc:                  # noqa: BLE001
                log.exception("Umlauf auf Kanal %s gescheitert", channel.name)
                turn = Turn(
                    channel=channel.name,
                    prompt=text,
                    text="Da ging gerade etwas schief. Versuch es nochmal.",
                    error=f"{type(exc).__name__}: {exc}",
                )
            finally:
                self._busy_channel = None

            self._turns.append(turn)
            if len(self._turns) > self.log_size:
                del self._turns[: len(self._turns) - self.log_size]
            return turn

    # --- Bequemlichkeit ---------------------------------------------------

    def door(self, channel: Channel) -> Callable[[str], Turn]:
        """Eine an einen Kanal gebundene ``ask``-Funktion.

        Damit eine Bedienschnittstelle nur eine Funktion kennen muss und
        nicht die ganze Sitzung — und den Kanal nicht vergessen kann.
        """
        return lambda prompt: self.ask(prompt, channel)

    def with_limit(self, channel: Channel, limit: int) -> Channel:
        """Denselben Kanal mit anderer Obergrenze (etwa je Endgerät)."""
        return replace(channel, limit=limit)
