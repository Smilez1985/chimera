"""Gleichheit: die Python-Schranke und der Ausführer (`chimera-sohelper`).

DESIGN, Regel „Wer prüft, führt aus" — „Gegenprobe: die bestehenden Fälle
laufen **gegen den Prozess**, nicht gegen eine nachgebaute Prüfung."

Warum dieser Test: `agent/safety.py` (Python) und `rust/crates/sohelper`
(Rust) prüfen dasselbe. Zwei Umsetzungen derselben Regel können in
Randfällen auseinanderlaufen — und `shlex.split` gegen sein Rust-Gegenstück
ist genau so ein Randfall. Verglichen wird deshalb das **Urteil** (ja/nein)
und der **Text** der Ablehnung, nicht der Quelltext.

Der Test braucht ein gebautes Binary. Fehlt es, wird er übersprungen und
sagt das (kein stiller Erfolg): `CHIMERA_SOHELPER_BIN` oder
`rust/target/release/chimera-sohelper` oder `sohelper/chimera-sohelper-aarch64`.
"""
from __future__ import annotations

import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from chimera.agent.safety import (  # noqa: E402
    Limits, Rejected, check_command, safe_path,
)

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


def binary() -> Path | None:
    for kandidat in (
        os.environ.get("CHIMERA_SOHELPER_BIN"),
        ROOT / "rust" / "target" / "release" / "chimera-sohelper",
        ROOT / "sohelper" / "chimera-sohelper-aarch64",
    ):
        if kandidat and Path(kandidat).is_file():
            p = Path(kandidat)
            p.chmod(0o755)
            return p
    return None


class Ausfuehrer:
    """Ein laufender Ausführer in einem erfundenen Arbeitsordner."""

    def __init__(self, prog: Path):
        self.dir = Path(tempfile.mkdtemp(prefix="sohelper-gleich-"))
        self.arbeit = self.dir / "arbeit"
        self.arbeit.mkdir()
        self.socket = self.dir / "s.sock"
        self.proc = subprocess.Popen(
            [str(prog), "--socket", str(self.socket), "--arbeit", str(self.arbeit)],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        for _ in range(100):
            if self.socket.exists():
                break
            time.sleep(0.02)
        else:
            raise SystemExit("Ausführer hat keinen Socket angelegt")

    def frage(self, anfrage: dict) -> dict:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as s:
            s.settimeout(20)
            s.connect(str(self.socket))
            s.sendall(json.dumps(anfrage).encode() + b"\n")
            roh = b""
            while not roh.endswith(b"\n"):
                teil = s.recv(65536)
                if not teil:
                    break
                roh += teil
        return json.loads(roh.decode())

    def schliessen(self):
        self.proc.terminate()
        try:
            self.proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            self.proc.kill()
        shutil.rmtree(self.dir, ignore_errors=True)


# --- Befehle: Urteil und Text --------------------------------------------
# Je Fall: Befehl, und was die Python-Seite meint (aus der Python-Seite
# selbst geholt, nicht hier nachgeschrieben).
BEFEHLE = [
    "ls -la",
    "echo hallo",
    "git status",
    "cat notes.txt",
    "sudo ls",
    "su -",
    "doas id",
    "pkexec id",
    "sh -c ls",
    "bash -c 'rm -rf x'",
    "python3 -c print(1)",
    "cat /etc/passwd | mail",
    "echo x > /etc/hosts",
    "ls; rm -rf /",
    "ls && rm x",
    "echo `id`",
    "echo $(id)",
    "echo a\necho b",
    "rm -rf /",
    "dd if=/dev/zero of=/dev/sda",
    "mkfs.ext4 /dev/sdb",
    "curl https://example.com",
    "wget https://example.com",
    "ssh host",
    "scp a b",
    "", "   ",
    "echo 'unclosed",
]


def befehle_vergleichen(a: Ausfuehrer):
    print("\n== Befehle: Urteil und Begründung ==")
    for cmd in BEFEHLE:
        # Python-Seite: dieselbe Funktion, die der Dienst heute benutzt.
        try:
            check_command(cmd, Limits())
            py_ok, py_text = True, ""
        except Rejected as exc:
            py_ok, py_text = False, str(exc)

        antwort = a.frage({"op": "run", "command": cmd})
        rs_ok = bool(antwort.get("ok"))
        rs_text = "" if rs_ok else antwort["fehler"]["text"]

        name = f"run {cmd!r}"
        if py_ok != rs_ok:
            bad(f"{name}: Python {'ja' if py_ok else 'nein'}, Rust {'ja' if rs_ok else 'nein'}"
                + (f" (Rust: {rs_text})" if rs_text else ""))
            continue
        if py_ok:
            ok(f"{name}: beide lassen durch")
        elif py_text != rs_text:
            bad(f"{name}: beide lehnen ab, aber Text verschieden — "
                f"Python {py_text!r}, Rust {rs_text!r}")
        else:
            ok(f"{name}: beide lehnen ab, gleicher Text")


# --- Zerlegen: Anführungszeichen und Backslash ---------------------------
# Ein Befehl, dessen Ausgabe das Zerlegen zeigt. Verglichen wird die Ausgabe
# mit dem, was `shlex.split` liefert — nicht eine hier abgeschriebene Liste.
ZERLEGEN = [
    'printf %s| "a b" c',
    "printf %s| a\\ b c",
    "printf %s| '' x",
    'printf %s| "x\'y" z',
    "printf %s| -n --flag=1 wert",
]


def zerlegen_vergleichen(a: Ausfuehrer):
    print("\n== Zerlegen wie shlex.split(posix=True) ==")
    for cmd in ZERLEGEN:
        import shlex
        try:
            argv = shlex.split(cmd, posix=True)
        except ValueError as exc:  # pragma: no cover - kommt hier nicht vor
            bad(f"{cmd!r}: Python zerlegt nicht ({exc})")
            continue
        # Erwartet wird nur die Ausgabe von printf mit genau diesen Argumenten.
        # argv[1] ist das Format fuer printf; verglichen wird, was an
        # Argumenten dahinter ankommt (genau die Zerlegung).
        # printf wiederholt sein Format fuer jedes weitere Argument:
        # aus n Argumenten wird "a|b|c|". Damit zeigt die Ausgabe genau die
        # Zerlegung, ohne dass hier eine Soll-Liste abgeschrieben wird.
        erwartet = "|".join(argv[2:]) + "|"
        antwort = a.frage({"op": "run", "command": cmd})
        if not antwort.get("ok"):
            bad(f"run {cmd!r}: abgelehnt — {antwort['fehler']['text']}")
            continue
        ist = antwort["text"].strip().splitlines()[0] if antwort["text"].strip() else ""
        check(f"run {cmd!r}: gleiche Argumente", ist, erwartet)


# --- Pfade: read, write, list -------------------------------------------
def pfade_vergleichen(a: Ausfuehrer):
    print("\n== Pfade: dieselbe Grenze wie safe_path ==")
    root = a.arbeit
    (root / "unter").mkdir(exist_ok=True)
    (root / "notes.txt").write_text("hallo\n")

    faelle = [
        ("read", "notes.txt", False),
        ("read", "unter", False),
        ("read", "../../etc/passwd", False),
        ("read", "/etc/passwd", False),
        ("read", ".env", False),
        ("write", "neu.txt", True),
        ("write", "../aussen.txt", True),
        ("write", ".env", True),
        ("list", "", False),
        ("list", "unter", False),
        ("list", "../..", False),
    ]
    for op, pfad, schreiben in faelle:
        try:
            safe_path(pfad, root, Limits(), for_write=schreiben)
            py_ok, py_text = True, ""
        except Rejected as exc:
            py_ok, py_text = False, str(exc)

        anfrage = {"op": op, "path": pfad}
        if op == "write":
            anfrage["inhalt"] = "x"
        antwort = a.frage(anfrage)
        rs_ok = bool(antwort.get("ok"))
        rs_text = "" if rs_ok else antwort["fehler"]["text"]

        name = f"{op} {pfad!r}"
        if py_ok != rs_ok:
            bad(f"{name}: Python {'ja' if py_ok else 'nein'}, Rust {'ja' if rs_ok else 'nein'}"
                + (f" (Rust: {rs_text})" if rs_text else ""))
        elif py_ok:
            ok(f"{name}: beide lassen durch")
        elif py_text != rs_text:
            bad(f"{name}: Text verschieden — Python {py_text!r}, Rust {rs_text!r}")
        else:
            ok(f"{name}: beide lehnen ab, gleicher Text")

    # Symlink-Flucht: beide müssen den aufgelösten Pfad prüfen.
    (root / "link").symlink_to("/etc/passwd")
    try:
        safe_path("link", root, Limits())
        py_ok, py_text = True, ""
    except Rejected as exc:
        py_ok, py_text = False, str(exc)
    antwort = a.frage({"op": "read", "path": "link"})
    rs_ok = bool(antwort.get("ok"))
    if py_ok == rs_ok and (py_ok or py_text == antwort["fehler"]["text"]):
        ok("Symlink nach /etc/passwd: beide gleich")
    else:
        bad(f"Symlink: Python {'ja' if py_ok else py_text!r}, "
            f"Rust {'ja' if rs_ok else antwort['fehler']['text']!r}")


def main() -> int:
    prog = binary()
    print("== Gleichheit: safety.py gegen chimera-sohelper ==")
    if prog is None:
        print("  übersprungen: kein Binary (erst bauen: cargo build --release -p chimera-sohelper)")
        return 0
    print(f"  Binary: {prog}")
    a = Ausfuehrer(prog)
    try:
        befehle_vergleichen(a)
        zerlegen_vergleichen(a)
        pfade_vergleichen(a)
    finally:
        a.schliessen()
    print(f"\nErgebnis: {PASS} ok, {FAIL} fehlgeschlagen")
    return 0 if FAIL == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
