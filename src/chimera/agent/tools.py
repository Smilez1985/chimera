"""Die Werkzeuge, die der Agent benutzen darf.

Bewusst wenige. Jedes Werkzeug ist eine Tür nach draußen, und die Auswahl
aus openclawgotchi (rund zwanzig) enthält vieles, was Chimera nicht
braucht — Artikel veröffentlichen, Dienste verwalten, sich selbst neu
starten.

Was hier fehlt und später dazukommt, steht in der Roadmap, nicht als
halbfertige Funktion im Code (Regel 10h).

Jedes Werkzeug bringt seine Beschreibung selbst mit (:class:`ToolSpec`).
Aus derselben Beschreibung entsteht das Schema für das Modell **und** die
Vorprüfung — zwei Listen würden auseinanderdriften.
"""

from __future__ import annotations

import logging
import subprocess
from dataclasses import dataclass
from pathlib import Path

from .preflight import ToolSpec
from .safety import Limits, Rejected, check_command, clip, safe_path

log = logging.getLogger(__name__)


@dataclass
class Tool:
    spec: ToolSpec
    run: callable

    @property
    def name(self) -> str:
        return self.spec.name


class Toolbox:
    """Die Werkzeuge eines Agenten, gebunden an ein Arbeitsverzeichnis."""

    def __init__(self, root: Path | str, limits: Limits | None = None,
                 *, face=None):
        self.root = Path(root).resolve()
        self.limits = limits or Limits()
        self.face = face          # optional: Zustand fürs Gesicht
        self._tools: dict[str, Tool] = {}
        self._register_default()

    # --- Verwaltung -------------------------------------------------------

    def add(self, spec: ToolSpec, fn) -> None:
        self._tools[spec.name] = Tool(spec, fn)

    def get(self, name: str) -> Tool | None:
        return self._tools.get(name)

    def names(self) -> list[str]:
        return sorted(self._tools)

    def schemas(self) -> list[dict]:
        """Was dem Modell geschickt wird."""
        return [t.spec.schema() for t in self._tools.values()]

    def call(self, name: str, args: dict) -> str:
        tool = self._tools.get(name)
        if tool is None:
            return (f"Fehler: Werkzeug {name!r} gibt es nicht. "
                    f"Verfügbar: {', '.join(self.names())}.")
        try:
            return clip(str(tool.run(**args)), self.limits)
        except Rejected as exc:
            return f"Abgelehnt: {exc}"
        except TypeError as exc:
            return f"Fehler: falsche Argumente für {name!r} ({exc})."
        except Exception as exc:
            log.warning("Werkzeug %s scheiterte: %s", name, exc)
            return f"Fehler in {name!r}: {type(exc).__name__}: {exc}"

    # --- Die Werkzeuge ----------------------------------------------------

    def _register_default(self) -> None:
        self.add(ToolSpec(
            "run_command",
            "Ein einzelnes Programm ausführen. Keine Pipes, keine "
            "Umlenkung, keine Shell-Ersetzung.",
            {"command": "Der Befehl, z. B. 'ls -la logs'"},
            ("command",),
        ), self._run_command)

        self.add(ToolSpec(
            "read_file",
            "Eine Datei im Arbeitsverzeichnis lesen.",
            {"path": "Pfad, relativ zum Arbeitsverzeichnis"},
            ("path",),
        ), self._read_file)

        self.add(ToolSpec(
            "write_file",
            "Eine Datei im Arbeitsverzeichnis schreiben oder anlegen.",
            {"path": "Pfad, relativ zum Arbeitsverzeichnis",
             "content": "Der vollständige neue Inhalt"},
            ("path", "content"),
        ), self._write_file)

        self.add(ToolSpec(
            "list_dir",
            "Den Inhalt eines Verzeichnisses auflisten.",
            {"path": "Pfad, leer für das Arbeitsverzeichnis"},
            (),
        ), self._list_dir)

        self.add(ToolSpec(
            "set_face",
            "Den Gesichtsausdruck setzen. Entweder ein bekannter "
            "Mood-Name oder eine Mischung wie 'CHILL+ROCK'.",
            {"mood": "Name des Ausdrucks",
             "hard": "'ja' für sofortigen Wechsel (Schreck), sonst weich"},
            ("mood",),
        ), self._set_face)

    def _run_command(self, command: str) -> str:
        cmd = check_command(command, self.limits)
        try:
            res = subprocess.run(
                cmd.argv, shell=False, capture_output=True, text=True,
                timeout=self.limits.timeout, cwd=str(self.root),
            )
        except subprocess.TimeoutExpired:
            return f"Abgebrochen nach {self.limits.timeout}s."
        except FileNotFoundError:
            return f"Programm nicht gefunden: {cmd.argv[0]!r}"

        out = ""
        if res.stdout.strip():
            out += res.stdout.strip() + "\n"
        if res.stderr.strip():
            out += f"[Fehlerausgabe] {res.stderr.strip()}\n"
        if res.returncode != 0:
            out += f"[Exitcode {res.returncode}]\n"
        return out or "(keine Ausgabe)"

    def _read_file(self, path: str) -> str:
        p = safe_path(path, self.root, self.limits)
        if not p.is_file():
            return f"Keine Datei: {path}"
        try:
            return p.read_text(encoding="utf-8", errors="replace")
        except Exception as exc:
            return f"Nicht lesbar: {exc}"

    def _write_file(self, path: str, content: str) -> str:
        p = safe_path(path, self.root, self.limits, for_write=True)
        data = content.encode("utf-8")
        if len(data) > self.limits.max_write_bytes:
            return (f"Zu groß: {len(data)} Bytes, erlaubt sind "
                    f"{self.limits.max_write_bytes}.")
        p.parent.mkdir(parents=True, exist_ok=True)
        # Über eine Nachbardatei und Umbenennen -- ein abgebrochener
        # Schreibvorgang darf keine halbe Datei hinterlassen (Regel 8a).
        tmp = p.with_suffix(p.suffix + ".tmp")
        tmp.write_bytes(data)
        tmp.replace(p)
        return f"Geschrieben: {path} ({len(data)} Bytes)"

    def _list_dir(self, path: str = "") -> str:
        p = safe_path(path or ".", self.root, self.limits)
        if not p.is_dir():
            return f"Kein Verzeichnis: {path or '.'}"
        # Format bewusst eindeutig: Das Modell liest das als Text, und
        # "logbuch.txt  12" wurde bereits als zwei Einträge missverstanden
        # -- eine Datei und eine mysteriöse Zahl. Beim echten Lauf
        # aufgefallen.
        rows = []
        for item in sorted(p.iterdir()):
            if item.is_dir():
                rows.append(f"{item.name}/ (Verzeichnis)")
            else:
                rows.append(f"{item.name} ({item.stat().st_size} Bytes)")
        return "\n".join(rows) or "(leer)"

    def _set_face(self, mood: str, hard: str = "") -> str:
        """Den Ausdruck setzen — das ist `FACE:` aus openclawgotchi.

        Die Steuerbefehle bleiben erhalten, nur das Ziel wechselt
        (`docs/HYBRID-PLAN.md` §3).
        """
        if self.face is None:
            return "Keine Anzeige angeschlossen."
        want_hard = str(hard).strip().lower() in ("ja", "yes", "true", "1", "hart")
        try:
            self.face.set_by_name(mood, hard=want_hard)
        except KeyError as exc:
            return f"Unbekannter Ausdruck: {exc}"
        return f"Ausdruck gesetzt: {mood}" + (" (sofort)" if want_hard else "")
