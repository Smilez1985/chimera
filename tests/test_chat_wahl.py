"""Tests für die Chat-Wahl der Türen (``chimera.chat_wahl``) und der CLI.

Ein echter Unix-Socket-Server im Testprozess spielt das Gateway: das
Zeilenprotokoll (eine JSON-Zeile hin, eine zurück) und die Ablage
``wahl.json``. Geprüft wird der echte Connector (Regel 9), nicht ein Nachbau;
dass das ECHTE Gateway dieselben Ops kennt, zeigt der Rust-Test in
``rust/crates/tor/src/daten.rs`` (``wahl_lesen``/``wahl_feld_setzen``).

Der wichtigste Punkt: Die Regeln (gültige Kennung, bekannte Denkstufe,
leerer Wert löscht) stehen im Gateway. Hier wird geprüft, dass die Tür sie
**weiterreicht** und die Ablehnung nicht verschluckt.
"""
import json
import os
import socket
import sys
import tempfile
import threading
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from chimera import chat_wahl                      # noqa: E402
from chimera.provider.base import Unavailable      # noqa: E402

PASS = FAIL = 0
def ok(m):
    global PASS; PASS += 1; print(f"  ok    {m}")
def bad(m):
    global FAIL; FAIL += 1; print(f"  FAIL  {m}")
def check(m, got, want):
    ok(m) if got == want else bad(f"{m} — erwartet {want!r}, bekam {got!r}")

TMP = tempfile.mkdtemp(prefix="chimera-wahltest-")

DENKSTUFEN = ("aus", "niedrig", "mittel", "hoch", "max")


class Gateway:
    """Ein Gateway mit `wahl.json` im Speicher und den echten Ablehnungen."""

    def __init__(self, name, wahl=None):
        self.pfad = os.path.join(TMP, name + ".sock")
        self.wahl = dict(wahl or {})
        self.gesehen = []
        self.srv = socket.socket(socket.AF_UNIX)
        self.srv.bind(self.pfad)
        self.srv.listen(4)
        threading.Thread(target=self._lauf, daemon=True).start()

    def _lauf(self):
        while True:
            try:
                c, _ = self.srv.accept()
            except OSError:
                return
            try:
                buf = b""
                while not buf.endswith(b"\n"):
                    d = c.recv(65536)
                    if not d:
                        break
                    buf += d
                if not buf:
                    continue
                anfrage = json.loads(buf.decode("utf-8"))
                self.gesehen.append(anfrage)
                antwort = self._antwort(anfrage)
                c.sendall(json.dumps(antwort, ensure_ascii=False).encode() + b"\n")
            finally:
                c.close()

    def _antwort(self, a):
        op = a.get("op")
        if op == "wahl_lesen":
            return {"ok": True, "wahl": dict(self.wahl)}
        if op == "wahl_feld_setzen":
            feld, wert = a.get("feld"), a.get("wert")
            if feld not in ("anbieter", "modell", "denken"):
                return {"ok": False, "fehler": {"code": "feld_unbekannt",
                                                "text": f"Feld {feld!r} gibt es nicht."}}
            text = (wert or "").strip()
            if feld == "denken" and text and text.lower() not in DENKSTUFEN:
                return {"ok": False, "fehler": {
                    "code": "wert_ungueltig",
                    "text": f"Denkstufe {text!r} kenne ich nicht."}}
            if text:
                self.wahl[feld] = text.lower() if feld == "denken" else text
            else:
                self.wahl.pop(feld, None)
            return {"ok": True, "wert": text or None}
        return {"ok": False, "fehler": {"code": "op_unbekannt", "text": op or "?"}}


gw = Gateway("voll", {"anbieter": "deepseek", "modell": "deepseek-flash",
                      "denken": "hoch", "stream": True})

print("== lesen: nur die drei Felder, nur gesetzte ==")
w = chat_wahl.lesen(pfad=gw.pfad)
check("alle drei Felder", w, {"anbieter": "deepseek", "modell": "deepseek-flash",
                              "denken": "hoch"})
check("stream gehoert nicht zur Chat-Wahl", "stream" in w, False)
check("Anfrage war wahl_lesen", gw.gesehen[-1]["op"], "wahl_lesen")

leer = Gateway("leer")
check("leere Datei → leeres dict", chat_wahl.lesen(pfad=leer.pfad), {})

nur_eins = Gateway("nureins", {"modell": "m", "unbekannt": "x"})
check("nur gesetzte Felder, fremdes Feld weg",
      chat_wahl.lesen(pfad=nur_eins.pfad), {"modell": "m"})

zahlen = Gateway("zahlen", {"anbieter": 7, "modell": "m"})
check("falscher Typ wird nicht als Wahl ausgegeben",
      chat_wahl.lesen(pfad=zahlen.pfad), {"modell": "m"})

print("== setzen: Feld und Wert gehen so hinaus, wie sie sollen ==")
st = Gateway("setzen")
chat_wahl.setzen("denken", "Niedrig", pfad=st.pfad)
check("Denkstufe gesetzt", st.wahl.get("denken"), "niedrig")
check("Feld im Auftrag", st.gesehen[-1]["feld"], "denken")
check("Wert im Auftrag", st.gesehen[-1]["wert"], "Niedrig")

chat_wahl.setzen("modell", "m1", pfad=st.pfad)
check("Modell gesetzt", st.wahl.get("modell"), "m1")
chat_wahl.setzen("modell", "", pfad=st.pfad)
check("leerer Wert löscht", "modell" in st.wahl, False)

print("== Ablehnung des Gateways wird nicht verschluckt ==")
try:
    chat_wahl.setzen("denken", "sehr", pfad=st.pfad)
except chat_wahl.WahlFehler as exc:
    ok("WahlFehler bei unbekannter Stufe")
    check("Code kommt durch", exc.code, "wert_ungueltig")
    check("Grund kommt durch", "kenne ich nicht" in str(exc), True)
else:
    bad("unbekannte Denkstufe wurde angenommen")

try:
    chat_wahl.setzen("unfug", "x", pfad=st.pfad)
except ValueError:
    ok("unbekanntes Feld endet vor dem Socket")
else:
    bad("unbekanntes Feld ging durch")
check("und nichts wurde geschickt", st.gesehen[-1]["op"], "wahl_feld_setzen")

kaputt = Gateway("kaputt")
kaputt._antwort = lambda a: {"ok": False, "fehler": {"code": "wahl_kaputt",
                                                     "text": "wahl.json ist kein Objekt."}}
try:
    chat_wahl.lesen(pfad=kaputt.pfad)
except chat_wahl.WahlFehler as exc:
    check("kaputte Datei wird gemeldet", exc.code, "wahl_kaputt")
else:
    bad("kaputte Datei still als leer behandelt")

print("== auftrag: ohne Gateway leer, mit Gateway die Wahl ==")
check("auftrag liest die Wahl", chat_wahl.auftrag(pfad=gw.pfad),
      {"anbieter": "deepseek", "modell": "deepseek-flash", "denken": "hoch"})
weg = os.path.join(TMP, "gibtsnicht.sock")
check("kein Gateway → keine Wahl, kein Absturz", chat_wahl.auftrag(pfad=weg), {})

print("== CLI: --anbieter/--modell/--denken setzen und gehen mit ==")
# Der echte Weg von der Kommandozeile bis in die Sitzung, ohne Netz:
# `_lauf` mit einem App-Ersatz, der die Wahl der Frage mitschreibt.
from chimera import __main__ as cli                # noqa: E402

class FakeChi:
    def __init__(self):
        self.notes = []
        self.fragen = []
        self.registry = types.SimpleNamespace(available=lambda: True)
    def status(self):
        return "Fake"
    def start_display(self):
        return True
    def ask(self, prompt, channel, **wahl):
        self.fragen.append((prompt, wahl))
        return types.SimpleNamespace(text="ok", error=None)
    def stop_display(self):
        pass

cli_wahl = Gateway("cli")
os.environ["CHIMERA_TOR_SOCKET"] = cli_wahl.pfad
args = types.SimpleNamespace(frage="hallo", pruefen=False, dienst=False,
                             telegram=False, anbieter="deepseek", modell="deepseek-flash",
                             denken="hoch", ausfuehrlich=False, offline=True)

chi = FakeChi()
rc = cli._lauf(chi, args)
check("Rückgabewert 0", rc, 0)
check("anbieter in wahl.json", cli_wahl.wahl.get("anbieter"), "deepseek")
check("modell in wahl.json", cli_wahl.wahl.get("modell"), "deepseek-flash")
check("denken in wahl.json", cli_wahl.wahl.get("denken"), "hoch")
check("die Frage bekam die Wahl", chi.fragen[-1][1],
      {"anbieter": "deepseek", "modell": "deepseek-flash", "denken": "hoch"})

# Nicht angegeben heisst nicht löschen: `None` lässt das Feld stehen,
# `''` löscht es.
args2 = types.SimpleNamespace(frage="hallo", pruefen=False, dienst=False,
                              telegram=False, anbieter=None, modell="",
                              denken=None, ausfuehrlich=False, offline=True)
chi2 = FakeChi()
cli._lauf(chi2, args2)
check("None löscht nichts", cli_wahl.wahl.get("anbieter"), "deepseek")
check("'' löscht das Feld", "modell" in cli_wahl.wahl, False)
check("gelöschtes Feld geht nicht mehr mit", chi2.fragen[-1][1],
      {"anbieter": "deepseek", "denken": "hoch"})

print("== CLI: abgelehnte Wahl bricht ab (rc 2), statt still ohne sie zu laufen ==")
args3 = types.SimpleNamespace(frage="hallo", pruefen=False, dienst=False,
                              telegram=False, anbieter=None, modell=None,
                              denken="sehr", ausfuehrlich=False, offline=True)
chi3 = FakeChi()
check("rc 2 bei abgelehnter Wahl", cli._lauf(chi3, args3), 2)
check("und keine Frage gestellt", chi3.fragen, [])

print("== CLI: --pruefen setzt nichts ==")
vorher = dict(cli_wahl.wahl)
args4 = types.SimpleNamespace(frage=None, pruefen=True, dienst=False,
                              telegram=False, anbieter="ollama", modell=None,
                              denken=None, ausfuehrlich=False, offline=True)
cli._lauf(FakeChi(), args4)
check("--pruefen rührt die Wahl nicht an", cli_wahl.wahl, vorher)

print(f"\n{PASS} ok, {FAIL} FAIL")
sys.exit(1 if FAIL else 0)
