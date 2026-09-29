"""Tests für die Anbieterschicht. Ohne Netz, ohne Schlüssel."""
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from chimera.provider.base import (  # noqa: E402
    Access, Connector, CostClass, LLMError, RateLimitError, Unavailable)
from chimera.provider.registry import (  # noqa: E402
    NoProvider, Registry, Strategy, Target)
from chimera.provider import setup  # noqa: E402

PASS = FAIL = 0
def ok(m):
    global PASS; PASS += 1; print(f"  ok    {m}")
def bad(m):
    global FAIL; FAIL += 1; print(f"  FAIL  {m}")
def check(m, got, want):
    ok(m) if got == want else bad(f"{m} — erwartet {want!r}, bekam {got!r}")


class Fake(Connector):
    """Anbieter zum Prüfen — antwortet oder fällt aus, wie bestellt."""
    def __init__(self, name, *, up=True, fails=False, access=Access.API_KEY,
                 cost=CostClass.METERED, model="m1"):
        self.name = name; self.up = up; self.fails = fails
        self.access = access; self.cost = cost
        self.default_model = model; self.calls = 0
    def is_available(self): return self.up
    def models(self): return [self.default_model]
    def call(self, prompt, history, system=None, *, model=None, **kw):
        self.calls += 1
        if self.fails:
            raise LLMError("kaputt")
        return f"{self.name}:{model or self.default_model}"


print("== Ziele ==")
check("Anbieter/Modell", str(Target.parse("ollama/qwen-3.8:27B")), "ollama/qwen-3.8:27B")
t = Target.parse("ollama/ollama_chat/qwen")
check("Schrägstrich im Modellnamen", (t.provider, t.model), ("ollama", "ollama_chat/qwen"))
check("nur Anbieter", Target.parse("claude-abo").model, None)

print("== Rückfall über Anbietergrenzen ==")
reg = Registry()
reg.register(Fake("ollama", up=False, cost=CostClass.FREE, access=Access.LOCAL))
reg.register(Fake("claude-abo", cost=CostClass.SUBSCRIPTION, access=Access.SUBSCRIPTION))
reg.assign("mood", ["ollama/qwen-a", "ollama/qwen-b", "claude-abo/haiku"])

r = reg.call("mood", "hallo")
# Das ist der Kern: Ollama ist weg, also nützen BEIDE Ollama-Modelle
# nichts — es muss der Anbieter gewechselt werden.
check("weicht auf anderen Anbieter aus", r.provider, "claude-abo")
check("Modell mitgenommen", r.model, "haiku")
ok("Rückfall wird gemeldet") if r.fell_back else bad("fell_back nicht gesetzt")

# Gegenprobe: fell_back darf sich nicht an der Position in der gefilterten
# Liste bemessen -- Claude stand dort an Stelle 0, obwohl zwei Ziele
# übersprungen wurden. Es zählt das eingetragene erste Ziel.
reg1b = Registry()
reg1b.register(Fake("ollama", up=True, cost=CostClass.FREE))
reg1b.register(Fake("claude-abo", cost=CostClass.SUBSCRIPTION))
reg1b.assign("mood", ["ollama/qwen-a", "claude-abo/haiku"])
ok("Gegenprobe: erstes Ziel meldet keinen Rückfall") \
    if not reg1b.call("mood", "x").fell_back else bad("fälschlich Rückfall")

# Auch ein anderes Modell beim selben Anbieter ist ein Rückfall.
reg1c = Registry()
reg1c.register(Fake("ollama", up=True, cost=CostClass.FREE))
reg1c.assign("mood", ["ollama/qwen-a", "ollama/qwen-b"])
r1c = reg1c.call("mood", "x")
check("gleiches Ziel, kein Rückfall", r1c.fell_back, False)

# Gegenprobe: ist Ollama da, wird es genommen und nichts fällt zurück.
reg2 = Registry()
reg2.register(Fake("ollama", up=True, cost=CostClass.FREE))
reg2.register(Fake("claude-abo", cost=CostClass.SUBSCRIPTION))
reg2.assign("mood", ["ollama/qwen-a", "claude-abo/haiku"])
r2 = reg2.call("mood", "hallo")
check("Gegenprobe: erstes Ziel zieht", r2.provider, "ollama")
ok("Gegenprobe: kein Rückfall") if not r2.fell_back else bad("fälschlich Rückfall")

print("== Fehlerarten ==")
reg3 = Registry()
reg3.register(Fake("a", fails=True))
reg3.register(Fake("b"))
reg3.assign("t", ["a/m", "b/m"])
check("Fehler führt zum nächsten Ziel", reg3.call("t", "x").provider, "b")

reg4 = Registry()
reg4.register(Fake("a", up=False))
reg4.assign("t", ["a/m"])
try:
    reg4.call("t", "x"); bad("hätte scheitern müssen")
except NoProvider as e:
    ok("kein Ziel erreichbar wird gemeldet")
    ok("Meldung nennt die Einträge") if "a/m" in str(e) else bad("Einträge fehlen")

try:
    Registry().call("unbekannt", "x"); bad("hätte scheitern müssen")
except NoProvider as e:
    ok("unbekannte Aufgabe wird gemeldet") if "nicht zugeordnet" in str(e) \
        else bad(f"unklare Meldung: {e}")

print("== Abo und Schlüssel getrennt ==")
abo = Fake("claude-abo", access=Access.SUBSCRIPTION, cost=CostClass.SUBSCRIPTION)
api = Fake("claude-api", access=Access.API_KEY, cost=CostClass.METERED)
check("Abo beschriftet", abo.label, "claude-abo (Abo)")
check("API beschriftet", api.label, "claude-api (API)")
reg5 = Registry(); reg5.register(abo); reg5.register(api)
reg5.assign("g", ["claude-abo/sonnet", "claude-api/sonnet"])
r5 = reg5.call("g", "x")
check("Abo zuerst", r5.access, Access.SUBSCRIPTION)
check("Herkunft in der Antwort", r5.cost, CostClass.SUBSCRIPTION)
ok("Übersicht zeigt beide") if "Abo" in reg5.overview() and "API" in reg5.overview() \
    else bad("Übersicht unterscheidet nicht")

print("== Verteilen ==")
a, b = Fake("a"), Fake("b")
reg6 = Registry(); reg6.register(a); reg6.register(b)
reg6.assign("t", ["a/m", "b/m"], strategy=Strategy.SPREAD)
for _ in range(4):
    reg6.call("t", "x")
ok(f"beide benutzt (a={a.calls}, b={b.calls})") if a.calls and b.calls \
    else bad(f"ungleich verteilt: a={a.calls}, b={b.calls}")

# Auch beim Verteilen muss ein Ausfall aufgefangen werden.
c, d = Fake("c", up=False), Fake("d")
reg7 = Registry(); reg7.register(c); reg7.register(d)
reg7.assign("t", ["c/m", "d/m"], strategy=Strategy.SPREAD)
check("Verteilen fängt Ausfall auf", reg7.call("t", "x").provider, "d")

print("== Ollama-Platzhalter ==")
from chimera.provider.ollama import OllamaConnector  # noqa: E402
o = OllamaConnector(base_url="http://ollama-server:11434")
ok("Platzhalter gilt als nicht eingerichtet") if not o.configured \
    else bad("Platzhalter durchgelassen")
ok("Grund im Klartext") if "Platzhalter" in (o.why_unavailable() or "") \
    else bad(f"unklar: {o.why_unavailable()}")
check("leer ist nicht eingerichtet", OllamaConnector(base_url="").configured, False)
ok("echte Adresse gilt") if OllamaConnector(base_url="http://10.0.0.5:11434").configured \
    else bad("echte Adresse abgelehnt")

print("== Claude-Kennung (PR #407) ==")
from chimera.provider import anthropic as ant  # noqa: E402
v = ant.claude_cli_version()
ok(f"Kennung ermittelt: {v}") if v and v.count(".") == 2 else bad(f"unbrauchbar: {v}")
ok("nicht einkompiliert") if "claude-cli/" in ant.user_agent() else bad("falsches Format")
# Gegenprobe: ohne CLI greift der Rückfallwert, statt zu scheitern.
ant._cached_version = None
import shutil as _sh
_orig = _sh.which
_sh.which = lambda x: None
try:
    check("ohne CLI greift der Rückfall", ant.claude_cli_version(refresh=True),
          ant.FALLBACK_CLI_VERSION)
finally:
    _sh.which = _orig
    ant._cached_version = None

print("== Ersteinrichtung ==")
reg8, notes = setup.autoconfigure(probe_network=False)
ok("läuft ohne Anbieter durch") if isinstance(notes, list) and notes else bad("keine Notizen")
ok("sagt, was fehlt") if any("nicht" in n.lower() for n in notes) else bad("keine Auskunft")
if not reg8.connectors():
    ok("ohne Anbieter keine Zuordnung") if not reg8.tasks() else bad("Zuordnung ohne Anbieter")

r9 = Registry()
r9.register(Fake("ollama", cost=CostClass.FREE, access=Access.LOCAL, model="qwen"))
r9.register(Fake("claude-abo", cost=CostClass.SUBSCRIPTION, access=Access.SUBSCRIPTION, model="sonnet"))
plan = setup.suggest(r9)
check("alle Aufgaben bedacht", set(plan), set(setup.TASKS))
ok("Gespräch nimmt das bessere Modell") if plan["gespraech"][0].startswith("claude-abo") \
    else bad(f"Gespräch: {plan['gespraech']}")
ok("Mood-Erfindung bleibt billig") if plan["mood_erfindung"][0].startswith("ollama") \
    else bad(f"Mood: {plan['mood_erfindung']}")
ok("jede Aufgabe hat Rückfall") if all(len(v) > 1 for v in plan.values()) \
    else bad("Aufgabe ohne Rückfall")
# Der Rückfall muss einen ANDEREN Anbieter nennen, sonst nützt er nichts.
firsts = {t: v[0].split("/")[0] for t, v in plan.items()}
ok("Rückfall wechselt den Anbieter") if all(
    any(x.split("/")[0] != firsts[t] for x in v[1:]) for t, v in plan.items()) \
    else bad("Rückfall bleibt beim selben Anbieter")

print("== Modellwahl ==")
class Many(Fake):
    def models(self):
        return ["nomic-embed-text:latest", "qwen2.5:14b",
                "gemma4:31b", "qwen3-coder:30b", "deepseek-ocr:latest"]

r10 = Registry()
r10.register(Many("ollama", cost=CostClass.FREE, access=Access.LOCAL, model=None))
plan2 = setup.suggest(r10)
ok(f"Gespräch nimmt das größte ({plan2['gespraech'][0]})") \
    if "31b" in plan2["gespraech"][0] else bad(plan2["gespraech"][0])
ok(f"Hintergrund nimmt ein kleines ({plan2['titel'][0]})") \
    if "14b" in plan2["titel"][0] else bad(plan2["titel"][0])
# Einbettungs- und OCR-Modelle können kein Gespräch führen.
alle = " ".join(x for v in plan2.values() for x in v)
ok("Embed/OCR ausgeschlossen") if "embed" not in alle and "ocr" not in alle \
    else bad(f"untaugliches Modell vorgeschlagen: {alle}")

check("Größe aus dem Namen", setup._size_of("qwen3.8:27b-q4_K_M"), 27.0)
check("Größe ohne Angabe", setup._size_of("irgendwas:latest"), 8.0)

print()
print(f"Ergebnis: {PASS} ok, {FAIL} fehlgeschlagen")
sys.exit(1 if FAIL else 0)
