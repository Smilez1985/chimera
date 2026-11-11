"""Der Weg der Werkzeuge über den Socket (DESIGN, Regel „Wer prüft, führt aus").

Drei Dinge werden geprüft:

1. **Der Dienst startet nichts mehr selbst.** `agent/tools.py` darf für
   `run_command`, `read_file`, `write_file`, `list_dir` kein Programm
   starten und kein `subprocess` kennen — sonst gäbe es einen zweiten Weg
   neben dem Ausführer, und die Trennung wäre nur eine Behauptung.
2. **Was gefragt wird, kommt an.** Ein erfundener Socket schreibt die
   Anfrage mit und antwortet; geprüft werden `op`, die Felder und die
   Umformung der Antwort in den Text, den das Modell sieht.
3. **Mit dem echten Binary** (wenn es hier läuft): die vier Werkzeuge über
   `Toolbox`, wie der Dienst sie benutzt.
"""
from __future__ import annotations

import ast
import json
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from chimera.agent.sohelper import Ausfuehrer, AusfuehrerFehler  # noqa: E402
from chimera.agent.tools import Toolbox  # noqa: E402

PASS = FAIL = 0


def ok(m):
    global PASS
    PASS += 1
    print(f"  ok    {m}")


def bad(m):
    global FAIL
    FAIL += 1
    print(f"  FAIL  {m}")


def check(m, got, want):
    ok(m) if got == want else bad(f"{m} — erwartet {want!r}, bekam {got!r}")


# --- 1. Kein zweiter Weg im Dienst ---------------------------------------
def struktur():
    print("== tools.py startet nichts selbst ==")
    quelle = (ROOT / "src" / "chimera" / "agent" / "tools.py").read_text(encoding="utf-8")
    baum = ast.parse(quelle)

    verboten = []
    fuer = {"run_command", "read_file", "write_file", "list_dir"}
    for knoten in ast.walk(baum):
        # Ein Programmstart wäre: subprocess.*, os.system/popen/spawn*.
        if isinstance(knoten, ast.Import):
            for a in knoten.names:
                if a.name.split(".")[0] in ("subprocess",):
                    verboten.append(f"import {a.name}")
        elif isinstance(knoten, ast.ImportFrom):
            if (knoten.module or "").split(".")[0] == "subprocess":
                verboten.append(f"from {knoten.module} import …")
        elif isinstance(knoten, ast.Call):
            f = knoten.func
            if isinstance(f, ast.Attribute) and f.attr in {"system", "popen", "spawn", "spawnl", "execv"}:
                verboten.append(f"…{f.attr}(…)")
    check("kein Programmstart in tools.py", verboten, [])

    # Die vier Werkzeuge müssen über den Ausführer gehen.
    rufe = set()
    for knoten in ast.walk(baum):
        if isinstance(knoten, ast.FunctionDef) and knoten.name in {"_" + w for w in fuer}:
            for kind in ast.walk(knoten):
                if isinstance(kind, ast.Call) and isinstance(kind.func, ast.Attribute):
                    rufe.add((knoten.name, kind.func.attr))
    for w in sorted(fuer):
        ok(f"_{w} fragt den Ausführer") if (f"_{w}", "_frage") in rufe \
            else bad(f"_{w} geht NICHT über den Ausführer")


# --- 1b. Derselbe Socket wie im Installer ---------------------------------
def socket_pfad_passt():
    """Der Vorgabepfad im Code und der im Installer dürfen nicht driften.

    Zwei Stellen, ein Pfad: Wenn der Installer den Socket woanders anlegt,
    findet der Dienst ihn nie — und es fällt erst auf dem Gerät auf.
    """
    print("== Socket-Pfad wie im Installer ==")
    from chimera.agent.sohelper import STANDARD_SOCKET
    lib = (ROOT / "installer" / "lib" / "sohelper.sh").read_text(encoding="utf-8")
    treffer = [z for z in lib.splitlines()
               if z.startswith(": \"${CHIMERA_SOHELPER_SOCKET:=")]
    if not treffer:
        bad("installer/lib/sohelper.sh nennt keinen Socket-Vorgabewert")
        return
    installer_pfad = treffer[0].split(":=", 1)[1].split("}", 1)[0]
    check("Code und Installer nennen denselben Socket", STANDARD_SOCKET, installer_pfad)


# --- 2. Erfundener Socket -------------------------------------------------
class Erfundener:
    """Ein Socket, der eine vorbereitete Antwort gibt und die Anfrage merkt."""

    def __init__(self, antwort: dict | bytes):
        self.dir = Path(tempfile.mkdtemp(prefix="sohelper-fake-"))
        self.pfad = self.dir / "s.sock"
        self.antwort = antwort if isinstance(antwort, bytes) else (
            json.dumps(antwort, ensure_ascii=False).encode() + b"\n")
        self.anfrage: dict | None = None
        self.srv = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.srv.bind(str(self.pfad))
        self.srv.listen(4)
        self.thread = threading.Thread(target=self._lauf, daemon=True)
        self.thread.start()

    def _lauf(self):
        try:
            conn, _ = self.srv.accept()
        except OSError:
            return
        with conn:
            roh = b""
            while not roh.endswith(b"\n"):
                teil = conn.recv(65536)
                if not teil:
                    break
                roh += teil
            try:
                self.anfrage = json.loads(roh.decode())
            except ValueError:
                self.anfrage = None
            conn.sendall(self.antwort)

    def schliessen(self):
        try:
            self.srv.close()
        except OSError:
            pass
        shutil.rmtree(self.dir, ignore_errors=True)


def erfunden():
    print("== Anfrage und Antwort über einen erfundenen Socket ==")
    with tempfile.TemporaryDirectory() as td:
        # Antwort „ok“ -> der Text geht unverändert ans Modell.
        s = Erfundener({"ok": True, "text": "antwort vom ausführer"})
        tb = Toolbox(td, ausfuehrer=Ausfuehrer(s.pfad))
        check("Text kommt durch", tb.call("run_command", {"command": "ls -l"}), "antwort vom ausführer")
        check("op ist 'run'", s.anfrage, {"op": "run", "command": "ls -l"})
        s.schliessen()

        # Antwort „nein“ -> "Abgelehnt: <Begründung>", wie bisher.
        s = Erfundener({"ok": False, "fehler": {"code": "abgelehnt", "text": "'sudo' ist gesperrt."}})
        tb = Toolbox(td, ausfuehrer=Ausfuehrer(s.pfad))
        check("Ablehnung wird durchgereicht", tb.call("run_command", {"command": "sudo ls"}),
              "Abgelehnt: 'sudo' ist gesperrt.")
        s.schliessen()

        # Die Felder heißen so, wie der Ausführer sie erwartet.
        for werkzeug, args, op in (
            ("read_file", {"path": "a.txt"}, "read"),
            ("write_file", {"path": "a.txt", "content": "x"}, "write"),
            ("list_dir", {}, "list"),
        ):
            s = Erfundener({"ok": True, "text": "-"})
            tb = Toolbox(td, ausfuehrer=Ausfuehrer(s.pfad))
            tb.call(werkzeug, args)
            check(f"{werkzeug}: op ist '{op}'", (s.anfrage or {}).get("op"), op)
            s.schliessen()

        # `content` heißt über den Draht `inhalt`.
        s = Erfundener({"ok": True, "text": "-"})
        tb = Toolbox(td, ausfuehrer=Ausfuehrer(s.pfad))
        tb.call("write_file", {"path": "a.txt", "content": "hallo"})
        check("write_file: Feld heißt 'inhalt'", (s.anfrage or {}).get("inhalt"), "hallo")
        s.schliessen()

        # Kaputte Antwort ist ein benannter Fehler, kein stilles Nichts.
        s = Erfundener(b"kein json\n")
        tb = Toolbox(td, ausfuehrer=Ausfuehrer(s.pfad))
        aus = tb.call("read_file", {"path": "a.txt"})
        ok("unlesbare Antwort benannt") if "nicht erreichbar" in aus else bad(f"unlesbar: {aus[:80]}")
        s.schliessen()

        # Der Client wirft, wo er soll.
        c = Ausfuehrer(Path(td) / "fehlt.sock")
        try:
            c.fragen("ping")
            bad("fehlender Socket wurde nicht gemeldet")
        except AusfuehrerFehler:
            ok("fehlender Socket wird gemeldet")


# --- 3. Mit dem echten Ausführer -----------------------------------------
def binary() -> Path | None:
    import os
    for k in (
        os.environ.get("CHIMERA_SOHELPER_BIN"),
        ROOT / "rust" / "target" / "release" / "chimera-sohelper",
        ROOT / "sohelper" / "chimera-sohelper-aarch64",
    ):
        if k and Path(k).is_file():
            p = Path(k)
            p.chmod(0o755)
            try:
                if subprocess.run([str(p), "--version"], capture_output=True, timeout=60).returncode == 0:
                    return p
            except OSError:
                continue
    return None


def echt():
    print("== Mit dem echten Ausführer ==")
    prog = binary()
    if prog is None:
        print("  übersprungen: kein ausführbares Binary auf dieser Maschine")
        return
    d = Path(tempfile.mkdtemp(prefix="sohelper-tools-"))
    arbeit = d / "arbeit"
    arbeit.mkdir()
    sock = d / "s.sock"
    p = subprocess.Popen([str(prog), "--socket", str(sock), "--arbeit", str(arbeit)],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        for _ in range(100):
            if sock.exists():
                break
            time.sleep(0.02)
        tb = Toolbox(arbeit, ausfuehrer=Ausfuehrer(sock))
        ok("schreiben") if "Geschrieben" in tb.call(
            "write_file", {"path": "a.txt", "content": "hallo"}) else bad("write_file kaputt")
        check("lesen", tb.call("read_file", {"path": "a.txt"}), "hallo")
        ok("auflisten") if "a.txt" in tb.call("list_dir", {}) else bad("list_dir kaputt")
        ok("Befehl läuft") if "a.txt" in tb.call("run_command", {"command": "ls"}) \
            else bad("run_command kaputt")
        ok("Ausbruch abgelehnt") if "Abgelehnt" in tb.call("read_file", {"path": "../../etc/passwd"}) \
            else bad("Ausbruch durchgelassen")
    finally:
        p.terminate()
        try:
            p.wait(timeout=5)
        except subprocess.TimeoutExpired:
            p.kill()
        shutil.rmtree(d, ignore_errors=True)


def main() -> int:
    print("== Werkzeuge über den Socket ==")
    struktur()
    socket_pfad_passt()
    erfunden()
    echt()
    print(f"\nErgebnis: {PASS} ok, {FAIL} fehlgeschlagen")
    return 0 if FAIL == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
