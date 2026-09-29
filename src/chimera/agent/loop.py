"""Die Agent-Schleife: fragen, Werkzeuge benutzen, antworten.

Hier laufen die Teile zusammen. Der Ablauf je Umlauf:

    Kontext prüfen ── gegen das Modell, das WIRKLICH bedient
      ↓
    Modell fragen ── über die Aufgaben-Registry, mit Rückfall
      ↓
    Werkzeugaufruf? ── nein: fertig
      ↓
    reparieren + vorprüfen ── kaputtes JSON retten, Pflichtfelder
      ↓
    Schleife prüfen ── VOR der Ausführung
      ↓
    Sicherheitsschranke ── keine Shell, kein Ausbruch
      ↓
    ausführen, vermerken ── Ergebnis geht zurück ins Gespräch

Die Anbieterschicht liefert bisher nur Text, keine strukturierten
Werkzeugaufrufe. Deshalb werden sie **aus dem Text gelesen** — dasselbe
Verfahren, das openclawgotchi für seine Steuerbefehle benutzt. Das ist
nicht die elegante Lösung, aber es funktioniert mit jedem Anbieter, auch
mit kleinen lokalen Modellen, die keine Werkzeug-Schnittstelle haben.
Wenn die Anbieter später echte Werkzeugaufrufe liefern, kommt das
daneben, nicht anstelle.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field

from .context import Action, estimate_tokens, policy_for
from .loopguard import Config as GuardConfig
from .loopguard import Level, LoopGuard
from .preflight import PreflightError, preflight
from .tools import Toolbox

log = logging.getLogger(__name__)

#: So ruft das Modell ein Werkzeug auf. Bewusst schlicht, damit auch
#: kleine Modelle es treffen.
CALL_RE = re.compile(
    r"^\s*TOOL:\s*([a-z_]+)\s*(\{.*)$",
    re.MULTILINE | re.DOTALL,
)

SYSTEM_TEMPLATE = """Du bist Chimera, ein Gerät mit einem Gesicht auf einem kleinen Bildschirm.

Du kannst Werkzeuge benutzen. Dafür schreibst du eine Zeile in genau dieser Form:

TOOL: name {"feld": "wert"}

Danach hörst du auf zu schreiben und wartest auf das Ergebnis. Pro Antwort
höchstens ein Werkzeugaufruf. Wenn du kein Werkzeug brauchst, antworte
einfach normal.

Verfügbare Werkzeuge:
{tools}

Halte dich kurz. Du läufst auf einem kleinen Gerät, und deine Antworten
werden vorgelesen."""


@dataclass
class Step:
    """Was in einem Umlauf passiert ist — fürs Protokoll."""

    kind: str                  # "text", "tool", "blocked", "error"
    detail: str = ""
    tool: str | None = None


@dataclass
class Result:
    text: str
    steps: list[Step] = field(default_factory=list)
    provider: str = ""
    model: str = ""
    fell_back: bool = False
    tool_calls: int = 0


class Agent:
    """Ein Auftrag, ein Gespräch, ein Zustand."""

    def __init__(self, registry, toolbox: Toolbox, *, task: str = "gespraech",
                 max_turns: int = 8, guard: GuardConfig | None = None,
                 on_state=None, skills=None, memory=None):
        self.registry = registry
        self.tools = toolbox
        self.task = task
        self.max_turns = max_turns
        self.guard = LoopGuard(guard, known_tools=toolbox.names())
        self.history: list[dict] = []
        #: Rückruf für den Zustand — damit das Gesicht zeigt, was läuft.
        self.on_state = on_state
        self.skills = skills
        self.memory = memory

        # Skills als Werkzeug anmelden, wenn welche da sind. Ein Katalog
        # ohne Abrufmöglichkeit wäre ein offenes Ende (Regel 10h).
        if skills is not None:
            from .preflight import ToolSpec
            toolbox.add(ToolSpec(
                "read_skill",
                "Die Anleitung zu einem Skill lesen, bevor du ihn benutzt.",
                {"name": "Name des Skills"},
                ("name",),
            ), self._read_skill)
            self.guard = LoopGuard(guard, known_tools=toolbox.names())

    def _read_skill(self, name: str) -> str:
        sk = self.skills.get(name) if self.skills else None
        if sk is None:
            verf = ", ".join(s.name for s in self.skills.usable()) if self.skills else ""
            return f"Skill {name!r} gibt es nicht. Verfügbar: {verf}"
        if not sk.usable:
            return f"Skill {sk.name} ist hier nicht nutzbar: {sk.reason}"
        return sk.read()

    # --- Hilfen -----------------------------------------------------------

    def _system(self) -> str:
        lines = []
        for spec in (t.spec for t in self.tools._tools.values()):
            args = ", ".join(spec.params) or "keine"
            lines.append(f"- {spec.name}({args}): {spec.description}")
        text = SYSTEM_TEMPLATE.replace("{tools}", "\n".join(lines))

        if self.skills is not None:
            cat = self.skills.catalog()
            if cat:
                text += ("\n\nSkills (Anleitungen, mit read_skill abrufbar):\n"
                         + cat)

        if self.memory is not None:
            ctx = self.memory.context()
            if ctx:
                text += "\n\n" + ctx

        return text

    def _state(self, what: str) -> None:
        if self.on_state:
            try:
                self.on_state(what)
            except Exception as exc:       # das Gesicht darf nie stören
                log.debug("Zustandsmeldung fehlgeschlagen: %s", exc)

    def _check_context(self, conn) -> Action:
        pol = policy_for(conn)
        used = estimate_tokens(self.history)
        return pol.check(used)

    # --- der Lauf ---------------------------------------------------------

    def run(self, prompt: str) -> Result:
        self.guard.reset()
        steps: list[Step] = []
        system = self._system()
        self.history.append({"role": "user", "content": prompt})

        provider = model = ""
        fell_back = False
        text = ""

        for turn in range(self.max_turns):
            self._state("denkt")

            targets = self.registry.resolve(self.task)
            if targets:
                action = self._check_context(targets[0][0])
                if action is Action.COMPACT:
                    self._compact()
                    steps.append(Step("compact", "Verlauf verdichtet"))
                elif action is Action.EXHAUSTED:
                    steps.append(Step("error", "Kontext voll"))
                    return Result(
                        "Mein Gedächtnis für dieses Gespräch ist voll. "
                        "Fang bitte ein neues an.",
                        steps, provider, model, fell_back, self.guard.calls)

            reply = self.registry.call(self.task, "", self.history, system)
            provider, model = reply.provider, reply.model
            fell_back = fell_back or reply.fell_back
            text = reply.text

            call = CALL_RE.search(text)
            if not call:
                self.history.append({"role": "assistant", "content": text})
                steps.append(Step("text", text[:80]))
                self._state("spricht")
                return Result(text, steps, provider, model, fell_back,
                              self.guard.calls)

            name, raw_args = call.group(1), call.group(2)
            before = text[: call.start()].strip()
            self.history.append({"role": "assistant", "content": text})

            # 1. Reparieren und vorprüfen
            spec = self.tools.get(name)
            if spec is None:
                out = (f"Fehler: Werkzeug {name!r} gibt es nicht. "
                       f"Verfügbar: {', '.join(self.tools.names())}.")
                verdict = self.guard.check(name, raw_args)
                if verdict.blocked:
                    out = verdict.message or out
                    steps.append(Step("blocked", out, name))
                    self.guard.record(name, raw_args, out)
                    return Result(before or out, steps, provider, model,
                                  fell_back, self.guard.calls)
                self.guard.record(name, raw_args, out)
                steps.append(Step("error", out, name))
                self.history.append({"role": "user", "content": out})
                continue

            try:
                args = preflight(spec.spec, raw_args)
            except PreflightError as exc:
                out = str(exc)
                self.guard.record(name, raw_args, out)
                steps.append(Step("error", out, name))
                self.history.append({"role": "user", "content": out})
                continue

            # 2. Schleife prüfen -- vor der Ausführung
            verdict = self.guard.check(name, args)
            if verdict.level is Level.STOP:
                steps.append(Step("blocked", verdict.message or "", name))
                self._state("verwirrt")
                return Result(before or (verdict.message or ""), steps,
                              provider, model, fell_back, self.guard.calls)
            if verdict.level is Level.BLOCK:
                out = verdict.message or "Aufruf verhindert."
                self.guard.record(name, args, out)
                steps.append(Step("blocked", out, name))
                self._state("verwirrt")
                self.history.append({"role": "user", "content": out})
                continue
            if verdict.level is Level.WARN and verdict.message:
                self.history.append({"role": "user", "content": verdict.message})
                steps.append(Step("warn", verdict.message, name))

            # 3. Ausführen -- die Schranke sitzt in der Toolbox
            self._state("arbeitet")
            out = self.tools.call(name, args)
            self.guard.record(name, args, out)
            steps.append(Step("tool", out[:80], name))
            self.history.append({"role": "user",
                                 "content": f"Ergebnis von {name}:\n{out}"})

        # Umläufe aufgebraucht: das ist eine Auskunft, kein Absturz.
        steps.append(Step("error", f"{self.max_turns} Umläufe aufgebraucht"))
        return Result(
            text or "Ich komme hier nicht weiter.",
            steps, provider, model, fell_back, self.guard.calls)

    def _compact(self) -> None:
        """Den Verlauf verdichten.

        Die letzten Nachrichten bleiben wörtlich, der Rest wird von einem
        billigen Modell zusammengefasst. Scheitert das, wird gekürzt statt
        aufgegeben — ein verlorener Anfang ist besser als ein Abbruch.
        """
        if len(self.history) <= 6:
            return
        head, tail = self.history[:-4], self.history[-4:]
        text = "\n".join(f"{m['role']}: {m['content']}" for m in head)

        summary = None
        try:
            r = self.registry.call(
                "zusammenfassen",
                "Fasse diesen Gesprächsverlauf in höchstens fünf Sätzen "
                "zusammen. Nur die Fakten, keine Einleitung:\n\n" + text[:8000],
                [], None)
            summary = r.text.strip()
        except Exception as exc:
            log.info("Verdichten über das Modell ging nicht: %s", exc)

        if summary:
            self.history = [{"role": "user",
                             "content": f"[Bisheriges Gespräch]\n{summary}"}] + tail
        else:
            self.history = tail
