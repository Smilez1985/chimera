"""Die gemeinsame Schnittstelle aller Sprachmodell-Anbieter.

Grundlage ist openclawgotchis ``LLMConnector`` (MIT) — sie hat bereits die
richtige Form: eine Aufrufmethode, eine Verfügbarkeitsprüfung, getrennte
Fehlerarten. Ergänzt wurde, was Chimeras Aufgabenzuordnung braucht
(``docs/PROVIDER.md``).

Wichtig ist die Unterscheidung von **Anbieter** und **Zugangsart**:
Claude über ein Abo und Claude über einen API-Schlüssel sind derselbe
Anbieter, aber zwei Einträge — mit eigener Abrechnung, eigenen Grenzen und
eigener Verfügbarkeit. Wer beides eingerichtet hat, soll beides benutzen
und **sehen können, was gerade zieht** (Regel 5h).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum


class CostClass(str, Enum):
    """Was ein Aufruf kostet — steuert die automatische Zuordnung."""

    FREE = "free"                  # eigener Rechner, eigenes Netz
    SUBSCRIPTION = "subscription"  # Abo, Kontingent statt Einzelabrechnung
    METERED = "metered"            # pro Token

    @property
    def rank(self) -> int:
        """Je kleiner, desto lieber für häufige Aufgaben."""
        return {"free": 0, "subscription": 1, "metered": 2}[self.value]


class Access(str, Enum):
    """Wie der Zugang zustande kommt. Für die Anzeige, nicht nur intern.

    Der Nutzer soll in der Übersicht erkennen, ob eine Antwort über sein
    Abo läuft oder abgerechnet wird — das ist ein Unterschied, den man
    nicht raten sollte.
    """

    LOCAL = "local"                # nichts verlässt das Netz
    SUBSCRIPTION = "subscription"  # Anmeldung, Abo
    API_KEY = "api_key"            # Schlüssel

    @property
    def label(self) -> str:
        return {"local": "lokal", "subscription": "Abo", "api_key": "API"}[self.value]


class LLMError(Exception):
    """Allgemeiner Fehler eines Anbieters."""


class RateLimitError(LLMError):
    """Grenze erreicht — ein anderer Anbieter kann es sofort versuchen."""


class Unavailable(LLMError):
    """Nicht erreichbar oder nicht eingerichtet.

    Getrennt von ``LLMError``, weil die Registry damit anders umgeht:
    Ein nicht eingerichteter Anbieter wird stillschweigend übersprungen,
    ein fehlgeschlagener wird protokolliert.
    """


@dataclass
class Reply:
    """Die Antwort samt Herkunft.

    Die Herkunft mitzuliefern ist kein Beiwerk: Ohne sie weiß niemand, ob
    gerade das Abo oder der bezahlte Schlüssel gezogen hat, und Ausfälle
    bleiben unsichtbar.
    """

    text: str
    provider: str
    model: str
    access: Access
    cost: CostClass
    fell_back: bool = False   # ein vorheriger Anbieter hat nicht geliefert

    def __str__(self) -> str:
        return self.text


class Connector(ABC):
    """Ein Anbieter mit einem bestimmten Zugang.

    Eine Unterklasse beschreibt nicht „Anthropic", sondern „Anthropic über
    das Abo" oder „Anthropic über einen Schlüssel" — der Unterschied ist
    für Verfügbarkeit, Kosten und Grenzen wesentlich.
    """

    name: str = "base"
    access: Access = Access.API_KEY
    cost: CostClass = CostClass.METERED
    supports_tools: bool = False
    supports_streaming: bool = False
    context_window: int = 0

    #: Wie es dem Nutzer angezeigt wird: "Claude (Abo)" statt "anthropic_oauth"
    @property
    def label(self) -> str:
        return f"{self.name} ({self.access.label})"

    @abstractmethod
    def is_available(self) -> bool:
        """Ist dieser Anbieter jetzt benutzbar?

        Soll **nicht** teuer sein — die Registry ruft das bei jedem
        Rückfall auf. Netzabfragen gehören zwischengespeichert.
        """

    @abstractmethod
    def call(self, prompt: str, history: list[dict],
             system: str | None = None, *, model: str | None = None,
             **kw) -> str:
        """Das Modell aufrufen. Wirft ``LLMError`` bei Fehlschlag."""

    def models(self) -> list[str]:
        """Verfügbare Modelle, soweit abfragbar. Leer heißt: unbekannt."""
        return []

    def __repr__(self) -> str:
        return f"<{type(self).__name__} {self.label}>"
