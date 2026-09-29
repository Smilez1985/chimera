"""Gedächtnis mit Rangordnung.

Zwei Arten von Notizen, und der Unterschied ist wesentlich:

* **Dauerhaftes** (``GRUNDLAGEN.md``) — vom Nutzer gepflegt, für den
  Agenten **nur lesbar**. Konventionen, Vorlieben, Dinge die gelten.
* **Tageslogs** (``JJJJ-MM-TT.md``) — schreibt der Agent selbst. Was
  heute passiert ist, Befunde, offene Punkte.

Die Trennung ist das Muster aus OpenMinis (nachgebaut). Sie löst zwei
Probleme, die openclawgotchis Vault so nicht adressiert:

1. **Der Agent kann seine eigenen Leitplanken nicht überschreiben.**
2. **Alte Notizen werden nicht für aktuelle Aufträge gehalten.** Dafür
   sorgt der Begleittext beim Einspeisen — ohne ihn nimmt ein Modell
   abgeschlossene Aufgaben wieder auf.

Markdown und Dateien, keine Datenbank: Auf einem Gerät ohne Bildschirm
will man Notizen auch von außen lesen können.
"""

from __future__ import annotations

import logging
from datetime import date, datetime
from pathlib import Path

log = logging.getLogger(__name__)

PERMANENT = "GRUNDLAGEN.md"

#: Ohne diesen Hinweis behandelt ein Modell Notizen als Aufträge. Aus
#: OpenMinis übernommen, weil es dort erprobt ist.
PREAMBLE = (
    "Die folgenden Notizen sind **Hintergrund**, keine Aufgabenliste. "
    "Sie beschreiben, was früher war und was gilt — nicht, was du jetzt "
    "tun sollst. Widerspricht die letzte Nachricht einer Notiz, gilt die "
    "letzte Nachricht."
)


class Memory:
    """Notizen lesen und schreiben."""

    def __init__(self, root: Path | str, *, max_daily_lines: int = 200,
                 recent_days: int = 3):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.max_daily_lines = max_daily_lines
        self.recent_days = recent_days

    # --- Dauerhaftes (nur lesen) -----------------------------------------

    @property
    def permanent_path(self) -> Path:
        return self.root / PERMANENT

    def permanent(self) -> str:
        p = self.permanent_path
        if not p.is_file():
            return ""
        try:
            return p.read_text(encoding="utf-8").strip()
        except Exception as exc:
            log.warning("Grundlagen nicht lesbar: %s", exc)
            return ""

    # --- Tageslog (schreiben) --------------------------------------------

    def daily_path(self, when: date | None = None) -> Path:
        return self.root / f"{(when or date.today()).isoformat()}.md"

    def write(self, text: str, *, heading: str | None = None) -> Path:
        """Etwas ins heutige Tageslog schreiben.

        Mit Zeitstempel, damit später nachvollziehbar ist, wann etwas
        notiert wurde.
        """
        text = (text or "").strip()
        if not text:
            raise ValueError("Leere Notiz wird nicht geschrieben.")

        p = self.daily_path()
        stamp = datetime.now().strftime("%H:%M")
        block = f"\n<!-- {stamp} -->\n"
        if heading:
            block += f"## {heading.strip()}\n\n"
        block += text + "\n"

        with p.open("a", encoding="utf-8") as fh:
            fh.write(block)
        return p

    def read_day(self, when: date | None = None) -> str:
        p = self.daily_path(when)
        if not p.is_file():
            return ""
        try:
            return p.read_text(encoding="utf-8").strip()
        except Exception:
            return ""

    def recent(self, days: int | None = None) -> list[tuple[str, str]]:
        """Die letzten Tageslogs **mit Inhalt**.

        Leere Tage werden übersprungen, nicht mitgezählt — sonst liefert
        eine ruhige Woche nichts zurück.
        """
        want = days or self.recent_days
        found: list[tuple[str, str]] = []
        for p in sorted(self.root.glob("????-??-??.md"), reverse=True):
            if len(found) >= want:
                break
            try:
                text = p.read_text(encoding="utf-8").strip()
            except Exception:
                continue
            if text:
                found.append((p.stem, text))
        return found

    # --- Für den Systemprompt --------------------------------------------

    def context(self) -> str:
        """Was dem Modell mitgegeben wird.

        Lange Tageslogs werden gekürzt — und das wird **gesagt**, damit
        das Modell weiß, dass es nur einen Ausschnitt sieht (Regel 8a).
        """
        parts: list[str] = []

        perm = self.permanent()
        if perm:
            parts.append(f"## Grundlagen (gilt dauerhaft, nur lesbar)\n\n{perm}")

        for day, text in self.recent():
            lines = text.splitlines()
            if len(lines) > self.max_daily_lines:
                cut = len(lines) - self.max_daily_lines
                text = "\n".join(lines[:self.max_daily_lines])
                text += f"\n\n[... {cut} weitere Zeilen, nicht mitgeschickt]"
            parts.append(f"## Notizen vom {day}\n\n{text}")

        if not parts:
            return ""
        return PREAMBLE + "\n\n" + "\n\n---\n\n".join(parts)


def install_tools(toolbox, memory: Memory) -> None:
    """Gedächtnis-Werkzeuge anmelden.

    Bewusst **kein** Werkzeug zum Schreiben der Grundlagen: Die gehören
    dem Nutzer. Der Agent kann sie lesen, weil sie im Systemprompt
    stehen, und sonst nichts damit tun.
    """
    from .preflight import ToolSpec

    toolbox.add(ToolSpec(
        "remember",
        "Etwas ins heutige Tagebuch schreiben — Befunde, Vereinbarungen, "
        "offene Punkte. Nicht für Belangloses.",
        {"text": "Was notiert werden soll",
         "heading": "Optionale Überschrift"},
        ("text",),
    ), lambda text, heading="": (
        f"Notiert in {memory.write(text, heading=heading or None).name}"
    ))

    toolbox.add(ToolSpec(
        "recall",
        "In den eigenen Notizen nachsehen.",
        {"query": "Suchbegriff; leer für die letzten Tage"},
        (),
    ), lambda query="": _recall(memory, query))


def _recall(memory: Memory, query: str) -> str:
    q = (query or "").strip().lower()
    if not q:
        days = memory.recent()
        if not days:
            return "Noch keine Notizen."
        return "\n\n".join(f"### {d}\n{t[:1500]}" for d, t in days)

    hits: list[str] = []
    for p in sorted(memory.root.glob("*.md"), reverse=True):
        try:
            text = p.read_text(encoding="utf-8")
        except Exception:
            continue
        for i, line in enumerate(text.splitlines()):
            if q in line.lower():
                ctx = text.splitlines()[max(0, i - 1):i + 2]
                hits.append(f"{p.stem}: " + " ".join(x.strip() for x in ctx))
        if len(hits) >= 12:
            break

    if not hits:
        return f"Nichts zu {query!r} gefunden."
    return "\n".join(hits[:12])
