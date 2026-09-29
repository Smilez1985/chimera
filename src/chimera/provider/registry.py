"""Aufgaben, Gruppen und die Auswahl des Anbieters.

openclawgotchis Router kennt zwei Anbieter als feste Attribute und
schaltet mit einem Bool zwischen ihnen um. Ein dritter passt da nicht
hinein — deshalb hier eine Registry (Regel 5a).

Der Aufbau hat drei Ebenen:

    Aufgabe          "mood_erfindung"
      └─ Gruppe      [ ollama/qwen, claude-abo/haiku, claude-api/haiku ]
           └─ Ziel   Anbieter + Modellname

**Der Rückfall läuft über Gruppengrenzen hinweg.** Ist Ollama nicht
erreichbar, nützt ein anderes Ollama-Modell nichts — es muss auf einen
*anderen Anbieter* ausgewichen werden können. Deshalb ist ein Gruppen-
Eintrag immer ein Paar aus Anbieter und Modell, nie nur ein Modellname.

Und deshalb prüft die Auswahl **je Eintrag** die Verfügbarkeit, statt
einmal je Gruppe: Sonst würde ein toter Anbieter die ganze Gruppe
blockieren, obwohl dahinter ein lebender steht.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum

from .base import Access, Connector, CostClass, LLMError, Reply, Unavailable

log = logging.getLogger(__name__)


class Strategy(str, Enum):
    FALLBACK = "fallback"   # der Reihe nach, bis einer antwortet
    SPREAD = "spread"       # abwechselnd, wenn mehrere gleichwertig sind


@dataclass(frozen=True)
class Target:
    """Ein Ziel: dieser Anbieter mit diesem Modell."""

    provider: str
    model: str | None = None

    def __str__(self) -> str:
        return f"{self.provider}/{self.model}" if self.model else self.provider

    @classmethod
    def parse(cls, text: str) -> "Target":
        """``"ollama/qwen-3.8:27B"`` → Ziel.

        Der Modellname darf Schrägstriche enthalten (``ollama_chat/qwen``),
        deshalb wird nur am ersten getrennt.
        """
        s = str(text).strip()
        if "/" not in s:
            return cls(s, None)
        prov, model = s.split("/", 1)
        return cls(prov.strip(), model.strip() or None)


@dataclass
class Group:
    """Geordnete Ziele für eine Aufgabe."""

    name: str
    targets: list[Target] = field(default_factory=list)
    strategy: Strategy = Strategy.FALLBACK
    _turn: int = 0

    def order(self) -> list[Target]:
        """Die Ziele in der Reihenfolge, in der sie versucht werden."""
        if self.strategy is Strategy.SPREAD and self.targets:
            # Reihum beginnen, aber alle behalten -- Verteilen heißt nicht,
            # dass ein Ausfall nicht aufgefangen wird.
            i = self._turn % len(self.targets)
            self._turn += 1
            return self.targets[i:] + self.targets[:i]
        return list(self.targets)


class NoProvider(LLMError):
    """Kein Ziel dieser Aufgabe war benutzbar."""


class Registry:
    """Hält Anbieter und Aufgabenzuordnung."""

    def __init__(self) -> None:
        self._conns: dict[str, Connector] = {}
        self._tasks: dict[str, Group] = {}

    # --- Anbieter ---------------------------------------------------------

    def register(self, conn: Connector) -> Connector:
        """Einen Anbieter aufnehmen. Der Name ist der Schlüssel."""
        if conn.name in self._conns:
            log.warning("Anbieter %r wird ersetzt", conn.name)
        self._conns[conn.name] = conn
        return conn

    def connector(self, name: str) -> Connector | None:
        return self._conns.get(name)

    def connectors(self) -> list[Connector]:
        return list(self._conns.values())

    def available(self) -> list[Connector]:
        out = []
        for c in self._conns.values():
            try:
                if c.is_available():
                    out.append(c)
            except Exception as exc:          # ein kaputter Anbieter darf
                log.warning("%s: Prüfung fehlgeschlagen: %s", c.name, exc)
        return out

    # --- Aufgaben ---------------------------------------------------------

    def assign(self, task: str, targets, *,
               strategy: Strategy = Strategy.FALLBACK) -> Group:
        """Einer Aufgabe Ziele zuordnen.

        ``targets`` nimmt Zeichenketten (``"ollama/qwen"``) oder ``Target``.
        """
        parsed = [t if isinstance(t, Target) else Target.parse(t)
                  for t in targets]
        grp = Group(task, parsed, strategy)
        self._tasks[task] = grp
        return grp

    def group(self, task: str) -> Group | None:
        return self._tasks.get(task)

    def tasks(self) -> dict[str, Group]:
        return dict(self._tasks)

    # --- Auswahl ----------------------------------------------------------

    def _first_target(self, task: str) -> Target | None:
        grp = self._tasks.get(task)
        return grp.targets[0] if grp and grp.targets else None

    def resolve(self, task: str) -> list[tuple[Connector, str | None]]:
        """Die benutzbaren Ziele einer Aufgabe, in Reihenfolge.

        Unbekannte oder nicht verfügbare Ziele fallen heraus. Die Liste
        kann leer sein — das ist keine Ausnahme, sondern eine Auskunft.
        """
        grp = self._tasks.get(task)
        if grp is None:
            return []

        out: list[tuple[Connector, str | None]] = []
        for tgt in grp.order():
            conn = self._conns.get(tgt.provider)
            if conn is None:
                log.debug("%s: Anbieter %r unbekannt", task, tgt.provider)
                continue
            try:
                if not conn.is_available():
                    continue
            except Exception as exc:
                log.warning("%s: %s nicht prüfbar: %s", task, conn.name, exc)
                continue
            out.append((conn, tgt.model))
        return out

    def call(self, task: str, prompt: str, history: list[dict] | None = None,
             system: str | None = None, **kw) -> Reply:
        """Eine Aufgabe ausführen, mit Rückfall über Anbietergrenzen.

        Scheitert ein Ziel, wird das nächste versucht — auch wenn es zu
        einem anderen Anbieter gehört. Genau darum geht es: Ist Ollama
        weg, hilft ein zweites Ollama-Modell nicht.
        """
        history = history or []
        candidates = self.resolve(task)

        if not candidates:
            grp = self._tasks.get(task)
            if grp is None:
                raise NoProvider(f"Aufgabe {task!r} ist nicht zugeordnet.")
            ziele = ", ".join(str(t) for t in grp.targets) or "(keine)"
            raise NoProvider(
                f"Für {task!r} ist gerade nichts erreichbar. "
                f"Eingetragen: {ziele}."
            )

        # Ob zurückgefallen wurde, misst sich am EINGETRAGENEN ersten Ziel --
        # nicht an der Position in der gefilterten Liste. Sonst gilt ein
        # Anbieter als erste Wahl, nur weil die eigentlich erste Wahl schon
        # bei der Verfügbarkeitsprüfung herausgefallen ist. Genau das ist
        # der häufigste Fall: Ollama ist aus, also zieht das Abo.
        wanted = self._first_target(task)

        errors: list[str] = []
        for conn, model in candidates:
            try:
                text = conn.call(prompt, history, system, model=model, **kw)
                fell_back = wanted is not None and (
                    conn.name != wanted.provider
                    or (wanted.model is not None and model != wanted.model)
                )
                return Reply(
                    text=text,
                    provider=conn.name,
                    model=model or "(Voreinstellung)",
                    access=conn.access,
                    cost=conn.cost,
                    fell_back=fell_back,
                )
            except Unavailable as exc:
                errors.append(f"{conn.label}: nicht verfügbar ({exc})")
            except LLMError as exc:
                errors.append(f"{conn.label}: {exc}")
                log.warning("%s über %s fehlgeschlagen: %s", task, conn.label, exc)
            except Exception as exc:      # fremder Code, unbekannte Fehler
                errors.append(f"{conn.label}: {type(exc).__name__}: {exc}")
                log.warning("%s über %s: unerwartet: %s", task, conn.label, exc)

        raise NoProvider(
            f"Alle Ziele für {task!r} sind gescheitert:\n  "
            + "\n  ".join(errors)
        )

    # --- Übersicht --------------------------------------------------------

    def overview(self) -> str:
        """Was ist eingerichtet, was zieht gerade — zum Anzeigen.

        Abo und Schlüssel werden **getrennt ausgewiesen**: Es ist ein
        Unterschied, ob eine Antwort das Kontingent belastet oder
        abgerechnet wird, und das soll man sehen, nicht raten.
        """
        lines = ["Anbieter:"]
        if not self._conns:
            lines.append("  (keine eingerichtet)")
        for c in self._conns.values():
            try:
                ok = c.is_available()
            except Exception:
                ok = False
            mark = "  " if ok else "✗ "
            lines.append(f"  {mark}{c.label:<28} {c.cost.value}")

        lines.append("")
        lines.append("Aufgaben:")
        if not self._tasks:
            lines.append("  (keine zugeordnet)")
        for name, grp in self._tasks.items():
            usable = {id(c) for c, _ in self.resolve(name)}
            parts = []
            for tgt in grp.targets:
                conn = self._conns.get(tgt.provider)
                live = conn is not None and id(conn) in usable
                parts.append(f"{tgt}{'' if live else ' (aus)'}")
            hint = "" if grp.strategy is Strategy.FALLBACK else f" [{grp.strategy.value}]"
            lines.append(f"  {name:<18} {' → '.join(parts)}{hint}")
        return "\n".join(lines)
