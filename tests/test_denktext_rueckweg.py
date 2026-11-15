"""Denktext geht zurück — DeepSeek-Denkmodus mit Werkzeugen (15.11.2026).

Fund am Pi: `gespraech über DeepSeek fehlgeschlagen: 400 "The
`reasoning_content` in the thinking mode must be passed back to the API"` —
jede Runde mit Werkzeugaufruf brach ab, der Agent fiel still auf qwen zurück.

Geprüft wird die **Kette** an den echten Stellen, nicht ein Nachbau:
1. `GatewayAnbieter` liest `gedacht` aus der Gateway-Antwort.
2. `Registry` reicht es in die `Reply`.
3. Der Agent hängt es an die Assistenznachricht im Verlauf.
4. Das Gateway übersetzt es (Rust, eigener Test) und Ollama sieht es nicht.

Aufruf: python3 tests/test_denktext_rueckweg.py
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(os.environ.get("CHIMERA_SRC") or ROOT / "src")))

from chimera.provider.base import Access, CostClass, Reply  # noqa: E402
from chimera.provider.registry import Registry  # noqa: E402

PASS = FAIL = 0


def ok(m):
    global PASS
    PASS += 1
    print(f"  ok    {m}")


def bad(m):
    global FAIL
    FAIL += 1
    print(f"  FAIL  {m}")


def pruefe(ist, soll, was):
    if ist == soll:
        ok(f"{was}: {ist!r}")
    else:
        bad(f"{was}: {ist!r} (erwartet {soll!r})")


print("== 1. Die Reply trägt den Denktext")

pruefe(Reply("x", "p", "m", Access.LOCAL, CostClass.FREE).gedacht, "",
       "ohne Denktext leer (nichts zurückzugeben)")

print("== 2. Die Registry reicht ihn durch")
class Conn:
    name = "stub"
    label = "Attrappe"
    access = Access.LOCAL
    cost = CostClass.FREE
    context_window = 1000
    supports_tools = True
    supports_streaming = False
    letzte_gedacht = "ich denke nach"
    letzte_verbrauch = {}

    def call(self, prompt, history, system=None, **kw):
        self.letzte_werkzeuge = []
        return "text"

    def verfuegbar(self):
        return True


class Reg(Registry):
    def __init__(self, conn):
        self._conn = conn
        self._tasks = {}
        self._ziele = {}

    def resolve(self, task, bevorzugt=None):
        return [(self._conn, "m")]

    def _first_target(self, task):
        return None


r = Reg(Conn())
antwort = r.call("gespraech", "hi")
pruefe(antwort.gedacht, "ich denke nach", "Denktext steht in der Reply")

print("== 3. Der Agent hängt ihn an die Assistenznachricht")
import tempfile  # noqa: E402

from chimera.agent.loop import Agent  # noqa: E402
from chimera.agent.sohelper import Ausfuehrer  # noqa: E402
from chimera.agent.tools import Toolbox  # noqa: E402


class StubRegistry:
    """Erste Antwort: ein Aufruf mit Denktext, dann die Antwort."""

    def __init__(self):
        self.antworten = [
            Reply("", "stub", "m", Access.LOCAL, CostClass.FREE,
                  werkzeuge=[{"name": "list_dir", "argumente": {"path": "a"}}],
                  gedacht="erst schauen, dann reden"),
            Reply("Fertig.", "stub", "m", Access.LOCAL, CostClass.FREE,
                  gedacht="kein Aufruf mehr"),
        ]
        self.gesehen = []

    def resolve(self, task):
        return [(Conn(), "m")]

    def call(self, task, prompt, history=None, system=None, **kw):
        self.gesehen.append({"verlauf": [dict(m) for m in (history or [])], **kw})
        return self.antworten.pop(0)


with tempfile.TemporaryDirectory() as td:
    tb = Toolbox(td, ausfuehrer=Ausfuehrer(Path(td) / "kein.sock"))
    reg = StubRegistry()
    Agent(reg, tb).run("was liegt da?")
    zweiter = reg.gesehen[1]["verlauf"]
    assistant = [m for m in zweiter if m.get("role") == "assistant"
                 and m.get("tool_calls")]
    pruefe(bool(assistant), True, "Assistenznachricht mit Aufruf im Verlauf")
    pruefe(assistant[0].get("gedacht"), "erst schauen, dann reden",
           "Denktext steht an der Assistenznachricht")
    # Eine Antwort **ohne** Aufruf braucht ihn nicht — sie wird nicht
    # wiederholt, und der Verlauf soll nicht wachsen.
    pruefe(all("gedacht" not in m or m.get("role") == "assistant"
               for m in zweiter), True, "kein Denktext an fremden Rollen")

print("== 4. Der Gateway-Anbieter liest `gedacht` aus der Antwort")
# Ohne diesen Punkt waere die Kette an der ersten Stelle gerissen: das
# Gateway schickt den Denktext, Python wirft ihn weg.
from chimera.provider import gateway as gwmod  # noqa: E402

echt = gwmod.anfragen
try:
    gwmod.anfragen = lambda anfrage, **kw: {
        "ok": True, "text": "moin", "werkzeuge": [],
        "verbrauch": {}, "gedacht": "hmm, kurz nachdenken"}
    anbieter = gwmod.GatewayAnbieter("deepseek")
    text = anbieter.call("hi", [], "sys")
    pruefe(text, "moin", "Antwort kommt an")
    pruefe(getattr(anbieter, "letzte_gedacht", ""), "hmm, kurz nachdenken",
           "Denktext gemerkt")
    gwmod.anfragen = lambda anfrage, **kw: {"ok": True, "text": "moin"}
    anbieter2 = gwmod.GatewayAnbieter("deepseek")
    anbieter2.call("hi", [], "sys")
    pruefe(getattr(anbieter2, "letzte_gedacht", "fehlt"), "",
           "ohne Denktext bleibt es leer")
finally:
    gwmod.anfragen = echt

print()
print(f"Ergebnis: {PASS} ok, {FAIL} fehlgeschlagen")
sys.exit(0 if FAIL == 0 else 1)
