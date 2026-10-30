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
    if a["op"] == "modelle":
        return {"ok": True, "host": "ollama.example:11434", "modelle": ["qwen3:27b", "gemma:7b"]}
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
check("Registry nimmt ollama ueber das Gateway auf", [x.name for x in reg.connectors()][:1], ["ollama"])
check("es ist der Gateway-Connector", type(reg.connector("ollama")).__name__, "GatewayOllama")
check("Protokoll nennt das Gateway", any("Gateway: erreichbar" in n for n in notes), True)
check("Protokoll nennt keine Adresse, nur den Host", any("ollama.example:11434" in n for n in notes), True)

os.environ["CHIMERA_TOR_SOCKET"] = os.path.join(TMP, "weg.sock")
reg2, _ = setup.build_registry(probe_network=False)
check("ohne Gateway bleibt der direkte Weg", type(reg2.connector("ollama")).__name__ if reg2.connector("ollama") else None, None)

print()
print(f"Ergebnis: {PASS} ok, {FAIL} fehlgeschlagen")
sys.exit(1 if FAIL else 0)
