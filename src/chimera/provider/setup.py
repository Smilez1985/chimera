"""Ersteinrichtung: suchen, vorschlagen, nicht entscheiden.

Beim ersten Lauf soll Chimera benutzbar sein, ohne dass jemand eine
Konfigurationsdatei schreibt. Also wird gesucht, was erreichbar ist, und
daraus ein **Vorschlag** gebaut.

Ein Vorschlag, kein Zwang (Regel 10g): Was gefunden wurde, wird benannt.
Was vermutet wird, wird als Vermutung benannt. Der Nutzer sieht die
Zuordnung und ändert jede Zeile, die ihm nicht passt.

Die Zuordnung folgt den Kosten: Was nichts kostet, bekommt die häufigen
Aufgaben; das Gespräch bekommt das beste verfügbare Modell.
"""

from __future__ import annotations

import logging

from .anthropic import ClaudeApiConnector, ClaudeSubscriptionConnector
from .base import CostClass
from .ollama import OllamaConnector, discover
from .registry import Registry, Strategy, Target

log = logging.getLogger(__name__)

#: Die Aufgaben, für die Chimera Modelle braucht. Reihenfolge nach
#: Anspruch -- oben das teuerste.
TASKS = {
    "gespraech": "Unterhaltung, Werkzeuge, Kontext — braucht das beste Modell",
    "mood_erfindung": "neue Ausdrücke erfinden — Struktur zählt, nicht Weltwissen",
    "umgebung": "Geräuschlage deuten — knapp und häufig",
    "zusammenfassen": "Verlauf verdichten — läuft im Hintergrund",
    "titel": "Benennen, Aufräumen — trivial",
}

#: Welche Aufgaben mit einem kleinen, billigen Modell auskommen.
CHEAP_TASKS = ("mood_erfindung", "umgebung", "zusammenfassen", "titel")


def build_registry(*, probe_network: bool = True) -> tuple[Registry, list[str]]:
    """Anbieter aufnehmen, die eingerichtet oder erreichbar sind.

    Liefert die Registry und die Zeilen für das Protokoll. Aufgenommen
    wird auch, was gerade nicht antwortet — nur so kann der Nutzer sehen,
    *dass* es eingetragen ist (und warum es nicht geht).
    """
    reg = Registry()
    notes: list[str] = []

    # --- Ollama -----------------------------------------------------------
    ollama = OllamaConnector()
    if not ollama.configured and probe_network:
        found = discover()
        if found:
            ollama = OllamaConnector(base_url=found[0])
            notes.append(f"Ollama gefunden: {found[0]}")
            if len(found) > 1:
                notes.append(f"  weitere: {', '.join(found[1:])}")
        else:
            notes.append("Ollama: nicht gefunden (kein Server im Netz erreichbar)")
    elif ollama.configured:
        grund = ollama.why_unavailable()
        notes.append(f"Ollama: {ollama.base_url}" + (f" — {grund}" if grund else " ✓"))
    else:
        notes.append("Ollama: nicht eingerichtet")

    if ollama.configured:
        reg.register(ollama)
        if ollama.is_available():
            models = ollama.models()
            if models:
                notes.append(f"  Modelle: {', '.join(models[:6])}"
                             + (" …" if len(models) > 6 else ""))

    # --- Claude, getrennt nach Zugang -------------------------------------
    abo = ClaudeSubscriptionConnector()
    if abo.is_available():
        reg.register(abo)
        notes.append("Claude (Abo): eingerichtet ✓")
    else:
        notes.append(f"Claude (Abo): {abo.why_unavailable()}")

    api = ClaudeApiConnector()
    if api.is_available():
        reg.register(api)
        notes.append("Claude (API): eingerichtet ✓")
    else:
        notes.append(f"Claude (API): {api.why_unavailable()}")

    return reg, notes


def suggest(reg: Registry) -> dict[str, list[str]]:
    """Eine Zuordnung vorschlagen.

    Grundsatz: Für jede Aufgabe eine **Kette über Anbietergrenzen**. Ist
    Ollama weg, hilft ein zweites Ollama-Modell nicht — es muss auf einen
    anderen Anbieter ausgewichen werden können.
    """
    conns = reg.connectors()
    if not conns:
        return {}

    # Nach Kosten sortieren: kostenlos zuerst, abgerechnet zuletzt.
    by_cost = sorted(conns, key=lambda c: c.cost.rank)
    cheap = [c for c in by_cost if c.cost is not CostClass.METERED] or by_cost
    best = [c for c in conns if c.cost is not CostClass.FREE] or conns

    def chain(primary, rest, prefer) -> list[str]:
        """Kette aus Zielen bauen, ohne Doppelungen."""
        out, seen = [], set()
        for c in list(primary) + list(rest):
            if c.name in seen:
                continue
            seen.add(c.name)
            out.append(_target_for(c, prefer=prefer))
        return out

    plan: dict[str, list[str]] = {}

    # Gespräch: das größte verfügbare Modell, alles andere als Rückfall.
    plan["gespraech"] = chain(best, by_cost, "big")

    # Der Rest kommt mit einem kleinen Modell aus -- schneller und
    # billiger, und für Struktur einhalten reicht es (docs/PROVIDER.md).
    for task in CHEAP_TASKS:
        plan[task] = chain(cheap, by_cost, "small")

    return plan


#: Modelle, die für Chimera nicht in Frage kommen -- sie können kein
#: Gespräch führen, tauchen aber in Ollamas Liste auf.
_SKIP = ("embed", "ocr", "rerank", "-vision", "coder")


def _size_of(name: str) -> float:
    """Parameterzahl aus dem Namen schätzen, z. B. ``qwen3.8:27b`` → 27.

    Grob, aber es genügt: Wir wollen nur groß von klein unterscheiden.
    Unbekannt gilt als mittelgroß, damit nichts fälschlich ganz vorn oder
    ganz hinten landet.
    """
    import re
    m = re.search(r"[:\-](\d+(?:\.\d+)?)\s*b\b", name.lower())
    return float(m.group(1)) if m else 8.0


def _usable_models(conn) -> list[str]:
    return [m for m in conn.models()
            if not any(s in m.lower() for s in _SKIP)]


def _target_for(conn, *, prefer: str = "any") -> str:
    """Anbieter plus ein passendes Modell.

    ``prefer="big"`` für das Gespräch, ``"small"`` für Hintergrundarbeit.
    Ohne Modellliste bleibt es bei der Voreinstellung des Anbieters --
    dann entscheidet der Anbieter selbst.
    """
    found = _usable_models(conn)
    if found and prefer != "any":
        found.sort(key=_size_of, reverse=(prefer == "big"))
        return f"{conn.name}/{found[0]}"

    model = getattr(conn, "default_model", None) or (found[0] if found else None)
    return f"{conn.name}/{model}" if model else conn.name


def apply(reg: Registry, plan: dict[str, list[str]]) -> Registry:
    """Eine Zuordnung übernehmen."""
    for task, targets in plan.items():
        reg.assign(task, targets, strategy=Strategy.FALLBACK)
    return reg


def autoconfigure(*, probe_network: bool = True) -> tuple[Registry, list[str]]:
    """Alles zusammen: suchen, vorschlagen, übernehmen.

    Liefert die fertige Registry und das Protokoll. Ohne einen einzigen
    erreichbaren Anbieter bleibt die Registry leer — das ist kein Absturz,
    sondern eine Auskunft (Regel 5h: Chimera bleibt benutzbar).
    """
    reg, notes = build_registry(probe_network=probe_network)
    plan = suggest(reg)
    if plan:
        apply(reg, plan)
        notes.append("")
        notes.append("Vorschlag übernommen — jede Zeile ist änderbar:")
        for task, targets in plan.items():
            notes.append(f"  {task:<16} {' → '.join(targets)}")
    else:
        notes.append("")
        notes.append("Kein Sprachmodell erreichbar. Chimera läuft trotzdem:")
        notes.append("  Gesicht, Mischen und Variieren brauchen keines.")
        notes.append("  Zum Einrichten: OLLAMA_API_BASE, ANTHROPIC_API_KEY")
        notes.append("  oder Abo-Anmeldung über die Claude-CLI.")
    return reg, notes
