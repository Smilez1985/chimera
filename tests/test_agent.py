"""Tests für Sicherheit, Vorprüfung, Schleifenerkennung, Kontext und Lauf."""
import json, sys, tempfile
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from chimera.agent.context import Action, Policy, estimate_tokens, policy_for  # noqa: E402
from chimera.agent.loop import Agent  # noqa: E402
from chimera.agent.loopguard import Config, Level, LoopGuard  # noqa: E402
from chimera.agent.preflight import PreflightError, ToolSpec, preflight, repair_json  # noqa: E402
from chimera.agent.safety import Limits, Rejected, check_command, clip, safe_path  # noqa: E402
from chimera.agent.tools import Toolbox  # noqa: E402

PASS = FAIL = 0
def ok(m):
    global PASS; PASS += 1; print(f"  ok    {m}")
def bad(m):
    global FAIL; FAIL += 1; print(f"  FAIL  {m}")
def check(m, got, want):
    ok(m) if got == want else bad(f"{m} — erwartet {want!r}, bekam {got!r}")
def rejects(m, cmd, limits=None):
    try:
        check_command(cmd, limits); bad(f"{m} — durchgelassen: {cmd!r}")
    except Rejected: ok(m)

print("== Sicherheitsschranke ==")
check("normaler Befehl", check_command("ls -la logs").argv, ["ls", "-la", "logs"])
rejects("Pipe", "cat /etc/passwd | mail")
rejects("Umlenkung", "echo x > /etc/hosts")
rejects("Verkettung", "ls; rm -rf /")
rejects("Ersetzung", "echo $(whoami)")
rejects("Backtick", "echo `id`")
rejects("sudo", "sudo reboot")
rejects("Interpreter", "bash -c 'rm -rf /'")
rejects("Fork-Bombe", ":(){ :|:& };:")
rejects("rm -rf /", "rm -rf /")
rejects("mehrzeilig", "ls\nrm -rf /")
rejects("leer", "   ")

# Netz ist zu, außer es wird erlaubt.
rejects("Netz gesperrt", "curl http://x")
ok("Netz erlaubt wenn gewollt") if check_command(
    "curl http://x", Limits(allow_network=True)).uses_network else bad("Netz-Flag falsch")

print("== Pfadschutz ==")
with tempfile.TemporaryDirectory() as td:
    root = Path(td); (root / "a").mkdir()
    (root / "a" / "f.txt").write_text("x")
    check("innen ist erlaubt", safe_path("a/f.txt", root).name, "f.txt")
    for p in ("../etc/passwd", "/etc/passwd", "a/../../x"):
        try:
            safe_path(p, root); bad(f"Ausbruch durchgelassen: {p}")
        except Rejected: ok(f"Ausbruch verhindert: {p}")
    try:
        safe_path(".env", root, for_write=True); bad(".env beschreibbar")
    except Rejected: ok(".env ist schreibgeschützt")
    ok(".env ist lesbar") if safe_path(".env", root) else bad("nicht lesbar")

check("Kürzen meldet sich", "gekürzt" in clip("x" * 5000, Limits(max_output=100)), True)
check("kurz bleibt kurz", clip("hallo"), "hallo")

print("== JSON-Reparatur ==")
check("heiles JSON", repair_json('{"a": 1}').args, {"a": 1})
r = repair_json('{"path": "x.txt"')
check("fehlende Klammer", r.args, {"path": "x.txt"})
ok("Reparatur vermerkt") if r.steps else bad("stillschweigend repariert")
check("abgebrochener String", repair_json('{"path": "x.txt').args, {"path": "x.txt"})
check("Nachgeplapper", repair_json('{"a": 1} und dann noch was').args, {"a": 1})
check("unrettbar", repair_json("völlig kaputt").args, {})
check("schon ein Dict", repair_json({"a": 1}).args, {"a": 1})
check("leer", repair_json("").args, {})

print("== Vorprüfung ==")
spec = ToolSpec("t", "Test", {"path": "Pfad", "mode": "Modus"}, ("path",))
check("gültig", preflight(spec, '{"path": "a.txt"}'), {"path": "a.txt"})
for label, args in (("Pflichtfeld fehlt", '{"mode": "r"}'),
                    ("leeres Pflichtfeld", '{"path": "   "}'),
                    ("kein Objekt", '"nur text"')):
    try:
        preflight(spec, args); bad(f"{label} durchgelassen")
    except PreflightError as e:
        ok(f"{label} abgelehnt") if "t:" in str(e) else bad(f"unklar: {e}")
check("unbekanntes Feld verworfen",
      preflight(spec, '{"path": "a", "quatsch": 1}'), {"path": "a"})
# Schema und Prüfung aus EINER Quelle.
check("Schema kennt dieselben Pflichtfelder",
      tuple(spec.schema()["parameters"]["required"]), spec.required)

print("== Schleifenerkennung ==")
g = LoopGuard(Config(warn_at=3, block_at=5, stop_at=8), known_tools={"t"})
levels = []
for i in range(6):
    v = g.check("t", {"x": 1}); levels.append(v.level)
    if not v.blocked: g.record("t", {"x": 1}, "immer dasselbe")
ok("warnt vor dem Blocken") if Level.WARN in levels else bad(f"keine Warnung: {levels}")
ok("blockt schließlich") if Level.BLOCK in levels else bad(f"kein Block: {levels}")

# Gegenprobe: wechselnde Ergebnisse sind kein Kreis.
g2 = LoopGuard(Config(warn_at=3, block_at=5, stop_at=99), known_tools={"t"})
for i in range(8):
    v = g2.check("t", {"x": 1})
    if not v.blocked: g2.record("t", {"x": 1}, f"neu-{i}")
check("Gegenprobe: wechselnde Ergebnisse gehen durch", v.level, Level.OK)

# Unterschiedliche Argumente sind auch keine Schleife.
g3 = LoopGuard(Config(warn_at=3, block_at=5, stop_at=99), known_tools={"t"})
for i in range(8):
    g3.record("t", {"x": i}, "gleich")
check("verschiedene Argumente", g3.check("t", {"x": 99}).level, Level.OK)

g4 = LoopGuard(Config(unknown_at=3), known_tools={"echt"})
for i in range(2): g4.record("erfunden", {}, "gibts nicht")
v4 = g4.check("erfunden", {})
ok("erfundenes Werkzeug wird gestoppt") if v4.blocked else bad("durchgelassen")
ok("Meldung nennt die echten") if "echt" in (v4.message or "") else bad("keine Hilfe")

# stop_at zaehlt ALLE Aufrufe, block_at nur die gleichen -- die beiden
# duerfen sich nicht gegenseitig hochsetzen.
g5 = LoopGuard(Config(stop_at=5), known_tools={"t"})
for i in range(5): g5.record("t", {"x": i}, f"r{i}")
check("Notbremse greift", g5.check("t", {"x": 99}).level, Level.STOP)
check("stop_at bleibt wie gesetzt", Config(stop_at=5).stop_at, 5)
# Gegenprobe: warn/block zaehlen dasselbe und werden sehr wohl geordnet.
check("block wird ueber warn gehoben", Config(warn_at=10, block_at=3).block_at, 11)

print("== Kontextschwellen ==")
check("winziges Fenster: kein Verdichten", Policy.for_window(8000).compact_at, 0)
check("mittleres: nur Auslagern", Policy.for_window(40_000).compact_at, 0)
ok("mittleres lagert aus") if Policy.for_window(40_000).offload_at == 30_000 else bad("falsch")
p200 = Policy.for_window(200_000)
check("großes Fenster verdichtet", p200.compact_at, 180_000)
check("unter der Schwelle", p200.check(100_000), Action.OK)
check("über der Auslagerschwelle", p200.check(165_000), Action.OFFLOAD)
check("über der Verdichtungsschwelle", p200.check(185_000), Action.COMPACT)
check("kleines Fenster läuft voll", Policy.for_window(8000).check(7900), Action.EXHAUSTED)

class C:  # Connector-Ersatz
    def __init__(self, w): self.context_window = w
check("Schwellen kommen vom Connector", policy_for(C(200_000)).window, 200_000)
# Das ist der Kern: nach einem Rückfall gilt das Fenster des ANDEREN.
ok("Rückfall ändert die Schwellen") \
    if policy_for(C(32_000)).compact_at != policy_for(C(200_000)).compact_at \
    else bad("Schwellen identisch")
ok("Schätzung plausibel") if 20 < estimate_tokens(
    [{"role": "user", "content": "x" * 400}]) < 200 else bad("Schätzung daneben")

print("== Werkzeuge ==")
# Seit 11.11.2026 führt der Dienst nichts mehr selbst aus: Prüfung und
# Ausführung liegen beim Ausführer (DESIGN, Regel „Wer prüft, führt aus").
# Hier bleibt, was ohne ihn prüfbar ist -- die Werkzeuge sind da, und ohne
# Ausführer wird **nichts** getan, sondern der Grund genannt.
# Was er wirklich tut, prüft tests/test_tools_socket.py.
with tempfile.TemporaryDirectory() as td:
    from chimera.agent.sohelper import Ausfuehrer
    tb = Toolbox(td, ausfuehrer=Ausfuehrer(Path(td) / "gibt-es-nicht.sock"))
    check("Werkzeuge da", "run_command" in tb.names(), True)
    check("Schemas vollständig", len(tb.schemas()), len(tb.names()))
    for werkzeug, args in (
        ("run_command", {"command": "ls"}),
        ("read_file", {"path": "a.txt"}),
        ("write_file", {"path": "a.txt", "content": "x"}),
        ("list_dir", {}),
    ):
        aus = tb.call(werkzeug, args)
        ok(f"{werkzeug}: ohne Ausführer nichts getan") \
            if "nicht erreichbar" in aus and "nichts ausgeführt" in aus \
            else bad(f"{werkzeug}: {aus[:80]}")
    check("ohne Ausführer keine Datei geschrieben",
          any(Path(td).iterdir()), False)
    ok("unbekanntes Werkzeug gemeldet") if "gibt es nicht" in tb.call("quatsch", {}) \
        else bad("stillschweigend")

print("== Websuche (DESIGN Regel 5r) ==")
# Der Dienst hat kein Netz: die Suche geht ueber das Gateway. Geprueft wird
# hier, dass er wirklich fragt, und was er aus den Antworten macht.
from chimera.provider import gateway as _gw  # noqa: E402

_echt = _gw.anfragen
try:
    gesehen = []

    def _fake(anfrage, **kw):
        gesehen.append(dict(anfrage))
        return {"ok": True, "quelle": "searxng", "treffer": [
            {"titel": "Ollama", "url": "https://ollama.com", "auszug": "lokal"},
            {"titel": "Zwei", "url": "https://z", "auszug": "x"},
        ]}

    _gw.anfragen = _fake
    with tempfile.TemporaryDirectory() as td:
        tb2 = Toolbox(td)
        text = tb2.call("web_suche", {"frage": "was ist ollama", "anzahl": 2})
        check("Suche geht ueber das Gateway", gesehen[0]["op"], "web_suche")
        check("Frage wird mitgeschickt", gesehen[0]["frage"], "was ist ollama")
        check("Anzahl wird mitgeschickt", gesehen[0]["anzahl"], 2)
        check("Treffer mit URL in der Antwort", "https://ollama.com" in text, True)
        check("Quelle wird genannt", "searxng" in text, True)

    def _leer(anfrage, **kw):
        return {"ok": False, "fehler": {"code": "keine_quelle",
                                        "text": "Es ist keine Suchquelle eingetragen."}}

    _gw.anfragen = _leer
    with tempfile.TemporaryDirectory() as td:
        text = Toolbox(td).call("web_suche", {"frage": "x"})
        check("ohne Quelle wird der Grund genannt", "keine Suchquelle" in text, True)

    def _keine(anfrage, **kw):
        return {"ok": True, "quelle": "searxng", "treffer": []}

    _gw.anfragen = _keine
    with tempfile.TemporaryDirectory() as td:
        check("keine Treffer ist eine Auskunft",
              "Keine Treffer" in Toolbox(td).call("web_suche", {"frage": "x"}), True)
finally:
    _gw.anfragen = _echt

print("== Webabruf: die Entscheidung faellt im Gateway, nicht hier ==")
_echt = _gw.anfragen
try:
    gesehen = []

    def _fake_abruf(anfrage, **kw):
        gesehen.append(dict(anfrage))
        return {"ok": True, "url": "https://beispiel.example/a",
                "endgueltige_url": "https://beispiel.example/b", "typ": "text/html",
                "status": 200, "umleitungen": 1, "gekuerzt": True,
                "text": "Inhalt der Seite"}

    _gw.anfragen = _fake_abruf
    with tempfile.TemporaryDirectory() as td:
        text = Toolbox(td).call("web_abruf", {"url": "https://beispiel.example/a"})
        check("Abruf geht ueber das Gateway", gesehen[0]["op"], "web_abruf")
        check("Adresse wird mitgeschickt", gesehen[0]["url"], "https://beispiel.example/a")
        check("Endadresse und Typ stehen in der Antwort",
              "beispiel.example/b" in text and "text/html" in text, True)
        check("Umleitung und Kuerzung werden benannt",
              "Umleitung" in text and "gekuerzt" in text, True)
        check("fremder Inhalt wird als solcher benannt",
              "Fremder Inhalt" in text and "Inhalt der Seite" in text, True)

    def _gesperrt(anfrage, **kw):
        return {"ok": False, "fehler": {"code": "abruf_gesperrt", "werkzeug": "web_abruf",
                                        "ziel": "intern.example",
                                        "text": "Der Abruf von intern.example ist nicht "
                                                "freigegeben: keine Freigabe eingetragen"}}

    _gw.anfragen = _gesperrt
    with tempfile.TemporaryDirectory() as td:
        text = Toolbox(td).call("web_abruf", {"url": "https://intern.example/x"})
        check("Ablehnung nennt Ziel und Grund",
              "intern.example" in text and "keine Freigabe" in text, True)
        check("Ablehnung wird nicht als Fehler des Programms ausgegeben",
              "Fehler in 'web_abruf'" not in text, True)
finally:
    _gw.anfragen = _echt

print("== ssh: nur Host und Befehl, die Entscheidung faellt im Gateway ==")
_echt = _gw.anfragen
try:
    gesehen = []

    def _fake_ssh(anfrage, **kw):
        gesehen.append(dict(anfrage))
        return {"ok": True, "text": " 21:04:11 up 3 days", "exitcode": 0, "dauer_s": 1,
                "host": anfrage["host"], "ziel": "dietpi@radxa"}

    _gw.anfragen = _fake_ssh
    with tempfile.TemporaryDirectory() as td:
        text = Toolbox(td).call("ssh", {"host": "radxa", "befehl": "uptime"})
        check("geht als eigene Operation zum Gateway", gesehen[0]["op"], "ssh")
        check("nur Host und Befehl gehen mit",
              sorted(gesehen[0]), ["befehl", "host", "op"])
        check("Ziel und Ausgabe stehen in der Antwort",
              "dietpi@radxa" in text and "up 3 days" in text, True)

    def _gesperrt_ssh(anfrage, **kw):
        return {"ok": False, "fehler": {"code": "ssh_gesperrt",
                "text": "Die Fernausfuehrung nach dietpi@radxa ist nicht freigegeben: "
                        "keine Freigabe eingetragen"}}

    _gw.anfragen = _gesperrt_ssh
    with tempfile.TemporaryDirectory() as td:
        text = Toolbox(td).call("ssh", {"host": "radxa", "befehl": "uptime"})
        check("Ablehnung nennt Ziel und Grund",
              "dietpi@radxa" in text and "keine Freigabe" in text, True)
        check("kein Programmfehler, sondern eine Auskunft",
              "Fehler in 'ssh'" not in text, True)
finally:
    _gw.anfragen = _echt

print("== ssh_vorschlag: der Agent schlaegt nur vor, er oeffnet nichts ==")
_echt = _gw.anfragen
try:
    gesehen = []

    def _fake_vorschlag(anfrage, **kw):
        gesehen.append(dict(anfrage))
        return {"ok": True, "host": anfrage["host"], "brauchbar": False}

    _gw.anfragen = _fake_vorschlag
    with tempfile.TemporaryDirectory() as td:
        text = Toolbox(td).call("ssh_vorschlag",
                                {"host": "radxa", "adresse": "box.example", "nutzer": "dietpi"})
        check("Vorschlag geht als eigene Operation zum Gateway", gesehen[0]["op"], "ssh_vorschlag")
        check("Adresse und Nutzer gehen mit",
              (gesehen[0]["adresse"], gesehen[0]["nutzer"]), ("box.example", "dietpi"))
        check("ohne Port wird keiner erfunden", "port" in gesehen[0], False)
        check("der Agent sagt, dass der Vorschlag nicht wirkt",
              "wirkt noch" in text and "Fernzugriff" in text, True)

        text = Toolbox(td).call("ssh_vorschlag",
                                {"host": "radxa", "adresse": "box.example", "nutzer": "dietpi",
                                 "port": "2222"})
        check("ein genannter Port geht als Zahl mit", gesehen[1]["port"], 2222)
        text = Toolbox(td).call("ssh_vorschlag",
                                {"host": "radxa", "adresse": "box.example", "nutzer": "dietpi",
                                 "port": "zweiundzwanzig"})
        check("kein Port ist ein klarer Satz, kein Aufruf", "keine Zahl" in text, True)
        check("und es wurde nichts geschickt", len(gesehen), 2)

    def _abgelehnt(anfrage, **kw):
        return {"ok": False, "fehler": {"code": "host_bekannt",
                "text": "\"radxa\" steht schon in der Tabelle -- ein Vorschlag aendert nichts."}}

    _gw.anfragen = _abgelehnt
    with tempfile.TemporaryDirectory() as td:
        text = Toolbox(td).call("ssh_vorschlag",
                                {"host": "radxa", "adresse": "box.example", "nutzer": "dietpi"})
        check("Ablehnung kommt mit Grund, nicht als Fehler des Programms",
              "steht schon in der Tabelle" in text and "Fehler in 'ssh_vorschlag'" not in text, True)
finally:
    _gw.anfragen = _echt

print("== Guthaben: ein natives Werkzeug, kein Text-Trick ==")
from chimera.agent.tools import guthaben_als_text  # noqa: E402

with tempfile.TemporaryDirectory() as td:
    tb = Toolbox(td)
    namen = tb.names()
    check("guthaben ist ein Werkzeug des Agenten", "guthaben" in namen, True)
    schema = [s for s in tb.schemas() if s["name"] == "guthaben"]
    check("und geht als Schema an das Modell", len(schema), 1)
    check("keine Pflichtfelder — die Frage allein genuegt",
          schema[0]["parameters"]["required"], [])
    check("der Anbieter ist optional",
          "anbieter" in schema[0]["parameters"]["properties"], True)

# Text ohne Netz: je Waehrung ein Betrag, Komma statt Punkt, Grund statt 0.
check("Betrag wird gesprochen geschrieben", "12,34 CNY" in guthaben_als_text({"anbieter": [
    {"bezeichnung": "DeepSeek", "zustand": "gut",
     "pools": [{"waehrung": "CNY", "gesamt": "12.34"}],
     "herkunft": {"quelle": "offizielle API"}}]}), True)
text = guthaben_als_text({"anbieter": [
    {"bezeichnung": "D", "zustand": "gut", "pools": [
        {"waehrung": "CNY", "gesamt": "1.00"}, {"waehrung": "USD", "gesamt": "2.00"}]}]})
check("zwei Waehrungen bleiben zwei Betraege", ("1,00 CNY" in text and "2,00 USD" in text), True)
check("nichts wird summiert", "3,00" in text, False)
check("veraltet wird gesagt, nicht verschwiegen",
      "veraltet, Stand vor 2 Stunden" in guthaben_als_text({"anbieter": [
          {"bezeichnung": "D", "zustand": "gut", "pools": [{"waehrung": "CNY", "gesamt": "1"}],
           "veraltet": True, "alter_s": 7200}]}), True)
check("lokal braucht kein Guthaben",
      "kein Guthaben noetig" in guthaben_als_text({"anbieter": [
          {"bezeichnung": "Ollama", "zustand": "kein_guthaben_noetig"}]}), True)
check("nicht abrufbar nennt den Grund",
      "Admin-Schluessel" in guthaben_als_text({"anbieter": [
          {"bezeichnung": "Anthropic", "zustand": "nicht_abrufbar",
           "hinweis": "Admin-Schluessel noetig"}]}), True)
check("ohne Anbieter kommt ein Satz, keine leere Antwort",
      guthaben_als_text({"ok": True, "anbieter": []}),
      "Es ist kein Anbieter eingetragen -- es gibt kein Guthaben abzufragen.")
check("ohne Zahl steht der Fehler, keine 0",
      "keine Zahl -- 500 kaputt" in guthaben_als_text({"anbieter": [
          {"bezeichnung": "X", "zustand": "abruf_gescheitert", "fehler": {"text": "500 kaputt"}}]}), True)

# Der Weg zum Gateway: eine Operation, nichts nachgebaut.
_gw = __import__("chimera.provider.gateway", fromlist=["anfragen"])
_echt_gw = _gw.anfragen
try:
    gesehen = []

    def _fake_quota(anfrage, **kw):
        gesehen.append(dict(anfrage))
        return {"ok": True, "anbieter": [{"bezeichnung": "DeepSeek", "zustand": "gut",
                "pools": [{"waehrung": "CNY", "gesamt": "5.00"}]}]}

    _gw.anfragen = _fake_quota
    with tempfile.TemporaryDirectory() as td:
        tb = Toolbox(td)
        text = tb.call("guthaben", {})
        check("geht als eigene Operation zum Gateway", gesehen[0]["op"], "quota_lesen")
        check("ohne Anbieter wird keiner geschickt", "id" in gesehen[0], False)
        check("kein Neuladen ohne Auftrag", "neu" in gesehen[0], False)
        check("die Zahl steht in der Antwort", "5,00 CNY" in text, True)
        tb.call("guthaben", {"anbieter": "deepseek", "neu": "ja"})
        check("ein genannter Anbieter geht mit", gesehen[1]["id"], "deepseek")
        check("'neu: ja' erzwingt den Abruf", gesehen[1].get("neu"), True)

    def _kaputt(anfrage, **kw):
        return {"ok": False, "fehler": {"code": "schluessel_falsch",
                "text": "api.deepseek.com nimmt den Schluessel nicht an (401)"}}

    _gw.anfragen = _kaputt
    with tempfile.TemporaryDirectory() as td:
        text = Toolbox(td).call("guthaben", {})
        check("Ablehnung kommt als Satz, nicht als Programmfehler",
              "401" in text and "Fehler in" not in text, True)
finally:
    _gw.anfragen = _echt_gw

print("== Native Werkzeugaufrufe (DESIGN, Regel „Aufrufe, nicht Text“) ==")
# Der Anbieter liefert strukturierte Aufrufe -- kein Text-Protokoll.
from chimera.provider.base import Access, CostClass, Reply  # noqa: E402


class StubConn:
    name = "stub"
    context_window = 200_000
    access = Access.LOCAL
    cost = CostClass.FREE


class StubRegistry:
    """Erste Antwort: zwei Aufrufe, dann eine Antwort ohne Aufrufe."""

    def __init__(self):
        self.antworten = [
            Reply("", "stub", "m", Access.LOCAL, CostClass.FREE,
                  werkzeuge=[{"name": "list_dir", "argumente": {"path": "a"}},
                             {"name": "quatsch", "argumente": {}}]),
            Reply("Fertig.", "stub", "m", Access.LOCAL, CostClass.FREE),
        ]
        self.gesehen = []

    def resolve(self, task):
        return [(StubConn(), "m")]

    def call(self, task, prompt, history=None, system=None, **kw):
        self.gesehen.append({"verlauf": [dict(m) for m in (history or [])], **kw})
        return self.antworten.pop(0)


with tempfile.TemporaryDirectory() as td:
    from chimera.agent.sohelper import Ausfuehrer
    tb = Toolbox(td, ausfuehrer=Ausfuehrer(Path(td) / "kein.sock"))
    reg = StubRegistry()
    res = Agent(reg, tb).run("was liegt da?")
    check("Antwort ohne Aufrufe beendet den Lauf", res.text, "Fertig.")
    check("Schemas gingen mit", "werkzeuge" in reg.gesehen[0], True)
    check("Schema ist neutral (name/description/parameters)",
          sorted(reg.gesehen[0]["werkzeuge"][0]), ["description", "name", "parameters"])
    # Der zweite Aufruf sieht den Verlauf: assistant mit tool_calls, dann
    # role:"tool" mit dem Namen -- so korreliert Ollama den Aufruf.
    verlauf = reg.gesehen[1]["verlauf"]
    arten = [m["role"] for m in verlauf]
    check("Verlauf endet mit dem Werkzeugergebnis", arten[-1], "tool")
    mit_aufrufen = [m for m in verlauf if m.get("tool_calls")]
    check("die Aufrufe stehen in der Assistenten-Nachricht", len(mit_aufrufen), 1)
    check("beide Aufrufe sind dort verzeichnet",
          len(mit_aufrufen[0]["tool_calls"]), 2)
    check("Argumente gehen als Objekt in den Verlauf",
          isinstance(mit_aufrufen[0]["tool_calls"][0]["function"]["arguments"], dict), True)
    werkzeuge = [m for m in verlauf if m["role"] == "tool"]
    check("zwei Aufrufe protokolliert", len(werkzeuge), 2)
    check("Ergebnis nennt das Werkzeug", werkzeuge[0]["tool_name"], "list_dir")
    check("ohne Ausfuehrer wird nichts getan, aber gesagt",
          "nicht erreichbar" in werkzeuge[0]["content"], True)
    check("unbekanntes Werkzeug als Fehlertext",
          "gibt es nicht" in werkzeuge[1]["content"], True)
    check("Werkzeugaufrufe mitgezaehlt", res.tool_calls, 2)

print()
print(f"Ergebnis: {PASS} ok, {FAIL} fehlgeschlagen")
sys.exit(1 if FAIL else 0)
