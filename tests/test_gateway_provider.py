"""Tests für den Anbieter hinter dem Gateway (provider/gateway.py).

Ein echter Unix-Socket-Server im Testprozess spricht das Zeilenprotokoll
des Gateways (eine JSON-Zeile hin, eine zurück). Geprüft wird der echte
Connector (Regel 9), nicht ein Nachbau. Ob das ECHTE Gateway antwortet,
zeigt der Test am Gerät und der Rust-Test in rust/crates/tor.
"""
import json
import os
import socket
import sys
import tempfile
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from chimera.provider import gateway, setup  # noqa: E402
from chimera.provider.base import LLMError, Unavailable  # noqa: E402

PASS = FAIL = 0
def ok(m):
    global PASS; PASS += 1; print(f"  ok    {m}")
def bad(m):
    global FAIL; FAIL += 1; print(f"  FAIL  {m}")
def check(m, got, want):
    ok(m) if got == want else bad(f"{m} — erwartet {want!r}, bekam {got!r}")

TMP = tempfile.mkdtemp(prefix="chimera-gwtest-")


class Attrappe:
    """Ein Gateway, das nach Vorgabe antwortet und die Anfragen merkt."""

    def __init__(self, name, antwort):
        self.pfad = os.path.join(TMP, name + ".sock")
        self.antwort = antwort            # dict oder Funktion(anfrage) -> dict
        self.gesehen = []
        self.srv = socket.socket(socket.AF_UNIX)
        self.srv.bind(self.pfad)
        self.srv.listen(4)
        self.t = threading.Thread(target=self._lauf, daemon=True)
        self.t.start()

    def _lauf(self):
        while True:
            try:
                c, _ = self.srv.accept()
            except OSError:
                return
            buf = b""
            while not buf.endswith(b"\n"):
                d = c.recv(65536)
                if not d:
                    break
                buf += d
            if not buf:
                c.close()
                continue
            req = json.loads(buf)
            self.gesehen.append(req)
            a = self.antwort(req) if callable(self.antwort) else self.antwort
            c.sendall(json.dumps(a).encode() + b"\n")
            c.close()

    def ende(self):
        self.srv.close()


print("== Erreichbarkeit ==")
check("kein Socket -> nicht erreichbar", gateway.erreichbar(os.path.join(TMP, "gibt-es-nicht.sock")), False)

# Eine Socket-Datei ohne Lauscher darf nicht als „erreichbar“ gelten.
tot = os.path.join(TMP, "tot.sock")
s = socket.socket(socket.AF_UNIX); s.bind(tot); s.close()
check("tote Socket-Datei -> nicht erreichbar", gateway.erreichbar(tot), False)

g = Attrappe("ping", {"ok": True, "programm": "chimera-tor"})
check("antwortender Socket -> erreichbar", gateway.erreichbar(g.pfad), True)
g2 = Attrappe("ping2", {"ok": False})
check("Antwort ohne ok -> nicht erreichbar", gateway.erreichbar(g2.pfad), False)

print("== Anfragen ==")
try:
    gateway.anfragen({"op": "ping"}, pfad=os.path.join(TMP, "nix.sock"))
    bad("fehlender Socket wirft nichts")
except Unavailable:
    ok("fehlender Socket -> Unavailable (Registry faellt zurueck)")

g3 = Attrappe("muell", None)
g3.antwort = lambda a: "kein objekt"
try:
    gateway.anfragen({"op": "ping"}, pfad=g3.pfad)
    bad("Nicht-Objekt wird angenommen")
except LLMError:
    ok("Antwort ohne Objekt -> LLMError")

print("== Connector ==")
def chat(a):
    if a["op"] == "ping":
        return {"ok": True, "programm": "chimera-tor"}
    if a["op"] == "anbieter_liste":
        # Seit 14.11. fragt der Dienst zuerst, WELCHE Anbieter es gibt --
        # vorher war "ollama" fest eingebaut.
        return {"ok": True, "anbieter": [
            {"id": "ollama", "typ": "ollama", "bezeichnung": "Ollama im LAN", "an": True},
            {"id": "deepseek", "typ": "deepseek", "bezeichnung": "DeepSeek", "an": True},
            {"id": "skurril", "typ": "anthropic", "bezeichnung": "ohne Modul", "an": True},
            {"id": "aus", "typ": "ollama", "bezeichnung": "ausgeschaltet", "an": False},
        ], "meldungen": []}
    if a["op"] == "modelle":
        return {"ok": True, "host": "ollama.example:11434", "modelle": ["qwen3:27b", "gemma:7b"],
                "wahl": "qwen3:27b"}
    if a["op"] == "chat":
        return {"ok": True, "text": f"antwort auf {a['prompt']}", "host": "ollama.example:11434",
                "modell": a["modell"], "anbieter": "ollama"}
    return {"ok": False, "fehler": {"code": "op_unbekannt", "text": "?"}}

g4 = Attrappe("chat", chat)
c = gateway.GatewayOllama(default_model="qwen3:27b", pfad=g4.pfad)
check("verfuegbar", c.is_available(), True)
check("Modelle vom Gateway", c.models(), ["qwen3:27b", "gemma:7b"])
check("Name bleibt ollama (Ketten unveraendert)", c.name, "ollama")
check("Anzeige nennt den Host", c.label, "ollama @ ollama.example:11434")
check("Dienst kennt keine Adresse", c.base_url, "")
text = c.call("Hi", [{"role": "user", "content": "frueher"}], "Sys", model="gemma:7b")
check("Text kommt zurueck", text, "antwort auf Hi")
chatanfrage = [a for a in g4.gesehen if a["op"] == "chat"][0]
check("Modell der Kette wird durchgereicht", chatanfrage["modell"], "gemma:7b")
check("System wird durchgereicht", chatanfrage["system"], "Sys")
check("Verlauf wird durchgereicht", chatanfrage["verlauf"], [{"role": "user", "content": "frueher"}])
check("Anbieter ist ollama", chatanfrage["anbieter"], "ollama")

print("== Fehlerarten ==")
def fehler(code):
    return lambda a: {"ok": False, "fehler": {"code": code, "text": f"text-{code}"}}

for code, erwartet in (("nicht_eingerichtet", Unavailable), ("nicht_erreichbar", Unavailable),
                       ("ausgelastet", Unavailable), ("anbieter_fehler", LLMError),
                       ("leer", LLMError)):
    gx = Attrappe("f-" + code, fehler(code))
    cx = gateway.GatewayOllama(pfad=gx.pfad)
    try:
        cx.call("x", [])
        bad(f"{code}: kein Fehler")
    except Unavailable:
        ok(f"{code} -> Unavailable") if erwartet is Unavailable else bad(f"{code}: Unavailable statt LLMError")
    except LLMError:
        ok(f"{code} -> LLMError") if erwartet is LLMError else bad(f"{code}: LLMError statt Unavailable")

# Ein nicht eingerichteter Anbieter darf nicht als verfuegbar gelten.
gn = Attrappe("nein", fehler("nicht_eingerichtet"))
cn = gateway.GatewayOllama(pfad=gn.pfad)
check("Gateway ohne Ollama-Adresse -> nicht verfuegbar", cn.is_available(), False)
check("Grund wird genannt", cn.why_unavailable(), "text-nicht_eingerichtet")

print("== Einbindung in die Registry ==")
os.environ["CHIMERA_TOR_SOCKET"] = g4.pfad
reg, notes = setup.build_registry(probe_network=False)
check("Registry nimmt die Chat-Anbieter auf", [x.name for x in reg.connectors()][:2], ["ollama", "deepseek"])
check("Typ ohne Chat-Modul wird nicht aufgenommen",
      [x.name for x in reg.connectors() if x.name == "skurril"], [])
check("ausgeschalteter Anbieter wird nicht aufgenommen",
      [x.name for x in reg.connectors() if x.name == "aus"], [])
check("es ist der Gateway-Connector", type(reg.connector("ollama")).__name__, "GatewayAnbieter")
check("Protokoll nennt das Gateway", any("Gateway: erreichbar" in n for n in notes), True)
check("Protokoll nennt keine Adresse, nur den Host", any("ollama.example:11434" in n for n in notes), True)

# Ohne Gateway gibt es keinen Ollama-Anbieter mehr, der arbeitet (Regel 5n):
# Der Dienst hat kein Netz, ein direkter Weg waere unmoeglich. Der Anbieter
# ist eingetragen, aber nicht verfuegbar -- die Kette faellt auf den naechsten
# zurueck, und das Protokoll sagt warum.
os.environ["CHIMERA_TOR_SOCKET"] = os.path.join(TMP, "weg.sock")
reg2, notes2 = setup.build_registry(probe_network=False)
_o2 = reg2.connector("ollama")
check("ohne Gateway: Anbieter eingetragen, aber nicht verfuegbar",
      bool(_o2) and not _o2.is_available(), True)
check("ohne Gateway: es wird nichts direkt geholt", type(_o2).__name__, "GatewayAnbieter")
check("ohne Gateway: das Protokoll sagt es",
      any("nicht erreichbar" in n for n in notes2), True)

print("== Ausdrueckliche Wahl: kein Rueckfall (DESIGN, Modellwahl 14.11.) ==")
# Die Registry traegt ollama und deepseek. Wer deepseek waehlt, bekommt
# deepseek -- und wenn der nicht kann, einen Fehler, nicht stillschweigend
# ollama.
os.environ["CHIMERA_TOR_SOCKET"] = g4.pfad     # der Block davor zeigt auf "weg"
_reg, _ = setup.build_registry(probe_network=False)
# Die Kette setzt sonst `autoconfigure`; hier wird sie von Hand gesetzt, damit
# die Zusage ohne Netz gemessen wird.
_reg.assign("chat", ["ollama/qwen3:27b", "deepseek/deepseek-flash"])
check("ohne Wahl gilt die Reihenfolge des Anbieters",
      [c.name for c, _m in _reg.resolve("chat")], ["ollama", "deepseek"])
check("mit Wahl nur das gewaehlte Ziel",
      [(c.name, m) for c, m in _reg.resolve("chat", "deepseek/deepseek-flash")],
      [("deepseek", "deepseek-flash")])
check("unbekannter Anbieter ergibt nichts, statt zu raten",
      _reg.resolve("chat", "gibtsnicht/x"), [])
# Der Aufruf landet wirklich beim gewaehlten Anbieter: die Attrappe sieht,
# welche Anbieter-Kennung im Auftrag steht.
_ci3 = gateway.GatewayOllama(anbieter="deepseek", pfad=g4.pfad)
_reg.register(_ci3)
_ci3.call("Hi", [], model="deepseek-flash")
check("gewaehlte Kennung geht als anbieter ins Gateway",
      [a for a in g4.gesehen if a["op"] == "chat"][-1]["anbieter"], "deepseek")

print("== Kontextfenster ==")
# DESIGN 5a: Das Fenster kommt aus der Abfrage, nicht aus einer Konstante.
# Der Katalog des Gateways traegt, was /api/show gemeldet hat.
# Die Form des Katalogs ist die des Gateways (daten::katalog_lesen):
# {"stand": <sekunden>, "modelle": {<name>: {...}}}. Frueher stand hier eine
# flache Form -- damit war der Test gruen und der Code las trotzdem nichts.
_kat = Attrappe("kat", lambda a: {
    "ok": True, "modelle": ["klein:3b", "gross:27b"], "host": "ollama.example:11434",
    "wahl": "gross:27b",
} if a["op"] == "modelle" else {
    "ok": True, "id": "ollama",
    "katalog": {"stand": 1, "modelle": {
        "gross:27b": {"kontext": 262144, "tools": True},
        "klein:3b": {"kontext": 8192, "tools": True}}},
})
_c = gateway.GatewayOllama(pfad=_kat.pfad)
check("Katalog wird befragt", _c.is_available(), True)
check("Fenster gemessen, nicht geraten", _c.context_window, 262144)
check("Fenster gilt als gemessen", _c.fenster_angenommen, False)

# Ohne Katalogeintrag bleibt der Vorgabewert -- aber er sagt, dass er einer ist.
_leer = Attrappe("leer", lambda a: {"ok": True, "modelle": ["x"], "host": "h", "katalog": {}}
                 if a["op"] == "modelle" else {"ok": True, "id": "ollama", "katalog": {}})
_c2 = gateway.GatewayOllama(default_model="x", pfad=_leer.pfad)
_c2.is_available()
check("ohne Katalog bleibt der Vorgabewert", _c2.context_window, 32_000)
check("und gilt als angenommen", _c2.fenster_angenommen, True)

print("== Das Modell kommt vom Server (DESIGN 5n, smilez 11.11.) ==")
# 1. Keine Einstellung als Quelle: OLLAMA_MODEL wird nicht mehr gelesen.
os.environ["OLLAMA_MODEL"] = "alt:1b"
_gi = Attrappe("ignoriert", chat)
_ci = gateway.GatewayOllama(pfad=_gi.pfad)
check("OLLAMA_MODEL ist keine Quelle mehr", _ci.default_model, None)
_ci.is_available()
_ci.call("Hi", [])
check("ohne eigene Wahl wird kein Name geschickt",
      [a for a in _gi.gesehen if a["op"] == "chat"][0]["modell"], "")

# 2. Gewaehlt wird im Gateway; der Dienst uebernimmt nur das Ergebnis.
_ci2 = gateway.GatewayOllama(pfad=_gi.pfad)
_ci2.is_available()
check("Wahl des Gateways wird uebernommen", _ci2.gewaehlt, "qwen3:27b")
check("Vorschlag nimmt die Wahl, nicht den groessten Namen",
      setup._target_for(_ci2, prefer="big"), "ollama/qwen3:27b")

# Gegenprobe: Ohne Wahl entscheidet weiter der Name (Verhalten fuer Anbieter,
# die keine Wahl melden). Sonst wuerde der Test oben auch mit kaputtem
# `_target_for` gruen.
class OhneWahl:
    name = "ollama"
    default_model = None
    gewaehlt = None
    def models(self):
        return ["klein:70b", "gross:3b"]
check("ohne Wahl gilt weiter der Name", setup._target_for(OhneWahl(), prefer="big"), "ollama/klein:70b")
del os.environ["OLLAMA_MODEL"]

print()
print(f"Ergebnis: {PASS} ok, {FAIL} fehlgeschlagen")
sys.exit(1 if FAIL else 0)
