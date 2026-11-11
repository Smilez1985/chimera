"""Gegenprobe zu test_tools_socket.py (Regel 9).

Der Test behauptet: „der Dienst startet nichts mehr selbst" und „ohne
Ausführer wird nichts getan". Beides ist nur etwas wert, wenn der Test rot
wird, sobald jemand den zweiten Weg zurückholt. Hier wird `tools.py`
deshalb je einmal verfälscht; die Datei wird **immer** zurückgeschrieben.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TOOLS = ROOT / "src" / "chimera" / "agent" / "tools.py"
TEST = ROOT / "tests" / "test_tools_socket.py"

PASS = FAIL = 0


def ok(m):
    global PASS
    PASS += 1
    print(f"  ok    {m}")


def bad(m):
    global FAIL
    FAIL += 1
    print(f"  FAIL  {m}")


def mutation(name: str, alt: str, neu: str, erwartete_zeile: str):
    original = TOOLS.read_text(encoding="utf-8")
    if alt not in original:
        bad(f"{name}: Mutationsstelle nicht gefunden")
        return
    try:
        TOOLS.write_text(original.replace(alt, neu, 1), encoding="utf-8")
        p = subprocess.run([sys.executable, str(TEST)], capture_output=True,
                           text=True, timeout=600)
    finally:
        TOOLS.write_text(original, encoding="utf-8")
    aus = p.stdout + p.stderr
    if p.returncode == 0:
        bad(f"{name}: Test blieb grün")
    elif erwartete_zeile in aus:
        ok(f"{name}: rot bei '{erwartete_zeile}'")
    else:
        bad(f"{name}: rot, aber nicht an der erwarteten Stelle")
        for zeile in aus.splitlines():
            if "FAIL" in zeile:
                print("       ", zeile.strip())
                break


def main() -> int:
    print("=== Gegenprobe: Werkzeuge über den Socket ===")
    if subprocess.run([sys.executable, str(TEST)], capture_output=True).returncode != 0:
        bad("unverändert schon rot — Gegenprobe nicht aussagekräftig")
        return 1
    ok("unverändert grün")

    # M-T1: subprocess wird wieder importiert.
    mutation("subprocess-importiert",
             "import logging\nfrom dataclasses import dataclass",
             "import logging\nimport subprocess\nfrom dataclasses import dataclass",
             "kein Programmstart in tools.py")

    # M-T2: read_file liest wieder selbst (ein zweiter Weg neben dem
    # Ausführer -- ohne Programmstart, damit diese Zusage einzeln gemessen
    # wird und nicht am Import haengen bleibt).
    mutation("read-liest-selbst",
             '    def _read_file(self, path: str) -> str:\n        return self._frage("read", path=path)',
             '    def _read_file(self, path: str) -> str:\n'
             '        return (self.root / path).read_text()',
             "_read_file geht NICHT über den Ausführer")

    # M-T3: Ohne Ausführer wird stillschweigend nichts getan (kein Grund).
    mutation("fehler-verschluckt",
             "        except AusfuehrerFehler as exc:\n            log.warning",
             "        except AusfuehrerFehler as exc:\n            return ''\n            log.warning",
             "unlesbar:")

    print(f"\nErgebnis: {PASS} ok, {FAIL} fehlgeschlagen")
    return 0 if FAIL == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
