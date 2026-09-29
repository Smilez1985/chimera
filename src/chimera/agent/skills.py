"""Skills laden — mit Voraussetzungsprüfung.

Übernommen aus openclawgotchi (MIT). Sein Loader kann etwas, das
OpenMinis' SQLite-Variante nicht kann: **Gating**. Ein Skill sagt selbst,
was er braucht (Programme, Umgebungsvariablen, Betriebssystem), und wird
nur angeboten, wenn das vorhanden ist.

Das ist auf einem Gerät wichtiger als am Rechner: Ein Skill, der `curl`
braucht, hat auf einem schlanken DietPi ohne `curl` nichts verloren — und
das Modell soll gar nicht erst auf die Idee kommen, ihn zu benutzen.

Format ist das von Anthropic (`SKILL.md` mit Kopfteil), damit vorhandene
Skills unverändert laufen.
"""

from __future__ import annotations

import json
import logging
import os
import re
import shutil
import sys
from dataclasses import dataclass, field
from pathlib import Path

log = logging.getLogger(__name__)

FRONTMATTER = re.compile(r"^---\s*\n(.*?)\n---\s*\n?(.*)$", re.DOTALL)


@dataclass
class Requires:
    """Was ein Skill braucht, um angeboten zu werden."""

    bins: tuple[str, ...] = ()        # alle müssen da sein
    any_bins: tuple[str, ...] = ()    # mindestens eines
    env: tuple[str, ...] = ()         # gesetzt und nicht leer
    os_names: tuple[str, ...] = ()    # linux, darwin, win32
    always: bool = False              # nie prüfen

    def check(self) -> tuple[bool, str]:
        """(nutzbar, Begründung). Die Begründung ist für Menschen."""
        if self.always:
            return True, ""

        if self.os_names and sys.platform not in self.os_names:
            return False, f"läuft nur auf {', '.join(self.os_names)}"

        missing = [b for b in self.bins if not shutil.which(b)]
        if missing:
            return False, f"Programm fehlt: {', '.join(missing)}"

        if self.any_bins and not any(shutil.which(b) for b in self.any_bins):
            return False, f"keines davon da: {', '.join(self.any_bins)}"

        unset = [e for e in self.env if not os.environ.get(e)]
        if unset:
            return False, f"nicht gesetzt: {', '.join(unset)}"

        return True, ""


@dataclass
class Skill:
    name: str
    description: str
    path: Path
    body: str = ""
    emoji: str = ""
    requires: Requires = field(default_factory=Requires)
    usable: bool = True
    reason: str = ""

    def read(self) -> str:
        """Den vollen Text — erst wenn er gebraucht wird.

        Skills können lang sein. Sie alle in den Systemprompt zu legen
        würde das Fenster füllen, bevor das Gespräch beginnt.
        """
        return self.body


def _parse_requires(meta: dict) -> Requires:
    r = (meta or {}).get("requires") or {}
    return Requires(
        bins=tuple(r.get("bins") or ()),
        any_bins=tuple(r.get("any_bins") or ()),
        env=tuple(r.get("env") or ()),
        os_names=tuple(r.get("os") or ()),
        always=bool((meta or {}).get("always", False)),
    )


def parse_skill(path: Path) -> Skill | None:
    """Eine ``SKILL.md`` lesen. Unbrauchbare werden übersprungen."""
    try:
        text = path.read_text(encoding="utf-8")
    except Exception as exc:
        log.warning("Skill nicht lesbar: %s (%s)", path, exc)
        return None

    m = FRONTMATTER.match(text)
    if not m:
        log.warning("Skill ohne Kopfteil: %s", path)
        return None

    head, body = m.group(1), m.group(2)
    fields: dict[str, str] = {}
    meta: dict = {}

    # Absichtlich kein YAML-Leser: Der Kopfteil ist flach, und eine
    # Abhängigkeit für drei Zeilen wäre auf einem Pi Zero unangemessen.
    json_start = head.find("metadata:")
    if json_start >= 0:
        raw = head[json_start + len("metadata:"):].strip()
        try:
            meta = json.loads(raw)
        except json.JSONDecodeError:
            log.debug("metadata in %s nicht lesbar", path)
        head = head[:json_start]

    for line in head.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or ":" not in line:
            continue
        k, _, v = line.partition(":")
        fields[k.strip()] = v.strip().strip('"\'')

    name = fields.get("name") or path.parent.name
    inner = meta.get("openclaw") or meta.get("chimera") or meta
    req = _parse_requires(inner)
    usable, reason = req.check()

    return Skill(
        name=name,
        description=fields.get("description", ""),
        path=path,
        body=body.strip(),
        emoji=inner.get("emoji", "") if isinstance(inner, dict) else "",
        requires=req,
        usable=usable,
        reason=reason,
    )


class SkillStore:
    """Alle gefundenen Skills."""

    def __init__(self, *dirs: Path | str):
        self.dirs = [Path(d) for d in dirs]
        self._skills: dict[str, Skill] = {}
        self.reload()

    def reload(self) -> None:
        self._skills.clear()
        for d in self.dirs:
            if not d.is_dir():
                continue
            for md in sorted(d.glob("*/SKILL.md")):
                sk = parse_skill(md)
                if sk:
                    self._skills[sk.name.lower()] = sk

    def all(self) -> list[Skill]:
        return list(self._skills.values())

    def usable(self) -> list[Skill]:
        return [s for s in self._skills.values() if s.usable]

    def get(self, name: str) -> Skill | None:
        return self._skills.get(str(name).lower())

    def catalog(self) -> str:
        """Kurzliste für den Systemprompt.

        Nur Name und Beschreibung — der volle Text wird bei Bedarf
        nachgeladen. Nicht nutzbare Skills werden **mit Grund** genannt,
        statt sie zu verschweigen: Das Modell soll wissen, dass es sie
        gibt und warum sie gerade nicht gehen (Regel 10j).
        """
        lines = []
        for s in self._skills.values():
            if s.usable:
                lines.append(f"- {s.name}: {s.description}")
            else:
                lines.append(f"- {s.name} (nicht verfügbar: {s.reason})")
        return "\n".join(lines) or "(keine Skills gefunden)"
