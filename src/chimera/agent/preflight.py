"""Werkzeugaufrufe prüfen und notfalls reparieren, bevor sie laufen.

Muster aus OpenMinis, **nachgebaut statt übernommen** (dort GPL-3, hier
MIT — `docs/HERKUNFT.md` §0).

Zwei Aufgaben, in dieser Reihenfolge:

1. **Reparieren.** Modelle brechen mitten im Strom ab und hinterlassen
   JSON, dem eine Klammer fehlt. Das wegzuwerfen kostet einen kompletten
   Umlauf — auf einem Gerät mit externem Modell sind das Sekunden und
   Tokens für nichts.
2. **Prüfen.** Pflichtfelder gegen **dieselbe** Beschreibung, die dem
   Modell geschickt wurde. Zwei getrennte Listen driften auseinander,
   sobald jemand ein Feld ergänzt — derselbe Gedanke wie bei der
   Mood-Tabelle (Regel 2).

Zeichenketten müssen außerdem nicht-leer sein: ``{"path": ""}`` besteht
eine reine Existenzprüfung und ist trotzdem kaputt.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field


@dataclass
class ToolSpec:
    """Beschreibung eines Werkzeugs — für das Modell **und** die Prüfung."""

    name: str
    description: str
    params: dict[str, str] = field(default_factory=dict)   # Name → Bedeutung
    required: tuple[str, ...] = ()

    def schema(self) -> dict:
        """Wie es dem Modell beschrieben wird."""
        return {
            "name": self.name,
            "description": self.description,
            "parameters": {
                "type": "object",
                "properties": {
                    k: {"type": "string", "description": v}
                    for k, v in self.params.items()
                },
                "required": list(self.required),
            },
        }


@dataclass
class Repair:
    args: dict
    steps: list[str] = field(default_factory=list)


def repair_json(raw: str | dict | None) -> Repair:
    """Aus einer möglicherweise kaputten Argumentangabe ein Dict machen.

    Drei Versuche, jeder nur wenn nötig:

    1. normal lesen
    2. fehlende Schlusszeichen anhängen (abgebrochener Strom)
    3. das erste vollständige Objekt herausschneiden (Nachgeplapper
       hinter dem JSON)
    """
    if raw is None:
        return Repair({}, [])
    if isinstance(raw, dict):
        return Repair(raw, [])

    text = str(raw).strip()
    if not text:
        return Repair({}, [])

    try:
        val = json.loads(text)
        return Repair(val if isinstance(val, dict) else {}, [])
    except json.JSONDecodeError:
        pass

    # Abgebrochen: Klammern und Anführungszeichen ergänzen. Die Reihenfolge
    # ist nicht beliebig -- erst den offenen String schließen, dann die
    # Strukturen von innen nach außen.
    for suffix in ('"}', '"]}',  '}', ']}', '"}]}',  '}}', ']}}'):
        try:
            val = json.loads(text + suffix)
            if isinstance(val, dict):
                return Repair(val, [f"Schlusszeichen {suffix!r} ergänzt"])
        except json.JSONDecodeError:
            continue

    # Nachgeplapper: bis zur passenden schließenden Klammer schneiden.
    if text.startswith("{"):
        depth = 0
        in_str = False
        esc = False
        for i, ch in enumerate(text):
            if esc:
                esc = False
                continue
            if ch == "\\":
                esc = True
                continue
            if ch == '"':
                in_str = not in_str
                continue
            if in_str:
                continue
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    try:
                        val = json.loads(text[: i + 1])
                        if isinstance(val, dict):
                            return Repair(val, ["Text hinter dem Objekt entfernt"])
                    except json.JSONDecodeError:
                        break
                    break

    return Repair({}, ["nicht lesbar"])


class PreflightError(Exception):
    """Der Aufruf ist nicht ausführbar. Der Text geht an das Modell."""


def preflight(spec: ToolSpec, raw_args) -> dict:
    """Argumente reparieren, prüfen und zurückgeben.

    Wirft ``PreflightError`` mit einer Begründung, die dem Modell hilft —
    „Feld fehlt" ist brauchbar, „ungültig" nicht.
    """
    rep = repair_json(raw_args)
    args = rep.args

    if not isinstance(args, dict):
        raise PreflightError(
            f"{spec.name}: Argumente müssen ein Objekt sein."
        )

    missing = [k for k in spec.required if k not in args]
    if missing:
        raise PreflightError(
            f"{spec.name}: Pflichtfeld fehlt: {', '.join(missing)}. "
            f"Erwartet: {', '.join(spec.required)}."
        )

    empty = [k for k in spec.required
             if isinstance(args.get(k), str) and not args[k].strip()]
    if empty:
        raise PreflightError(
            f"{spec.name}: Feld ist leer: {', '.join(empty)}."
        )

    unknown = [k for k in args if k not in spec.params]
    if unknown:
        # Kein Abbruch: ein überzähliges Feld ist meist ein Tippfehler,
        # kein Angriff. Es wird verworfen und gesagt.
        for k in unknown:
            args.pop(k, None)
        rep.steps.append(f"unbekannte Felder verworfen: {', '.join(unknown)}")

    return args
