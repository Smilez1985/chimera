"""Wann ein Verlauf verdichtet werden muss.

Muster aus OpenMinis, nachgebaut. openclawgotchi macht das mit einer
festen Zahl (die letzten fünf Nachrichten wörtlich) — das ist bei einem
kleinen Fenster zu großzügig und bei einem großen Verschwendung.

Der eigentliche Lerneffekt steckt aber woanders: **Die Kapazität muss
gegen das Modell geprüft werden, das die Anfrage tatsächlich bedient.**
Bei OpenMinis lief das auseinander, wenn eine Gruppe auf ein anderes
Mitglied umgeroutet hatte — geprüft wurde gegen das falsche Fenster.

Chimera hat mit der Anbieter-Registry samt Rückfall (Regel 5a) exakt
dieselbe Konstellation: Fällt Ollama mit 32 K aus und das Abo mit 200 K
übernimmt, gelten andere Grenzen. Deshalb nimmt :func:`policy_for` den
Connector, nicht eine Zahl aus der Konfiguration.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class Action(str, Enum):
    OK = "ok"
    OFFLOAD = "offload"      # Anhänge und lange Ergebnisse auslagern
    COMPACT = "compact"      # Verlauf zusammenfassen
    EXHAUSTED = "exhausted"  # nichts mehr zu holen — neu anfangen


@dataclass(frozen=True)
class Policy:
    """Schwellen für ein bestimmtes Kontextfenster."""

    window: int
    offload_at: int          # 0 = kein Auslagern
    compact_at: int          # 0 = kein Verdichten
    manual_compact: bool

    @classmethod
    def for_window(cls, window: int) -> "Policy":
        """Schwellen staffeln, statt eine feste Zahl zu nehmen.

        Die Reserve wächst mit dem Fenster: Bei 200 K ist eine einzelne
        Antwort samt Werkzeugergebnissen schnell 20 K groß, bei 8 K wäre
        dieselbe Reserve das halbe Fenster.
        """
        if window <= 0:
            return cls(0, 0, 0, False)
        if window < 32_000:
            # Zu klein zum Verdichten -- die Zusammenfassung selbst würde
            # einen nennenswerten Teil des Fensters belegen.
            return cls(window, 0, 0, False)
        if window < 64_000:
            return cls(window, window - 10_000, 0, True)
        if window < 128_000:
            return cls(window, window - 20_000, window - 10_000, True)
        return cls(window, window - 40_000, window - 20_000, True)

    def check(self, used: int) -> Action:
        if self.window <= 0:
            return Action.OK
        if self.compact_at and used >= self.compact_at:
            return Action.COMPACT
        if self.offload_at and used >= self.offload_at:
            return Action.OFFLOAD
        if used >= self.window * 0.95:
            # Kein Verdichten möglich und trotzdem voll: das muss gesagt
            # werden, statt die Anfrage scheitern zu lassen.
            return Action.EXHAUSTED
        return Action.OK


def policy_for(connector) -> Policy:
    """Die Schwellen des Anbieters, der gerade bedient.

    Nicht die aus der Konfiguration — sonst prüft man beim Rückfall gegen
    das falsche Fenster.
    """
    return Policy.for_window(getattr(connector, "context_window", 0) or 0)


def estimate_tokens(messages: list[dict]) -> int:
    """Grobe Schätzung der belegten Token.

    Absichtlich einfach: Ein echter Zähler bräuchte je Anbieter ein
    eigenes Verfahren, und für eine Schwelle genügt die Größenordnung.
    Vier Zeichen je Token ist für deutsche und englische Texte brauchbar;
    dazu ein Zuschlag je Nachricht für den Rollenkopf.
    """
    total = 0
    for m in messages:
        content = m.get("content") or ""
        if isinstance(content, list):      # Werkzeugergebnisse u. Ä.
            content = " ".join(str(c) for c in content)
        total += len(str(content)) // 4 + 4
    return total
