"""Gegenprobe zu test_sohelper_gleichheit.py (Regel 9).

Der Gleichheitstest vergleicht zwei Umsetzungen derselben Regel. Bleibt er
grün, weil er nichts vergleicht, sagt er nichts aus. Hier wird die
Rust-Seite deshalb je einmal verfälscht und neu gebaut — der Test muss an
der erwarteten Stelle rot werden.

Gebaut wird in ein eigenes Zielverzeichnis (`CARGO_TARGET_DIR`), damit das
gute Binary liegen bleibt. Die verfälschte Quelle wird **immer** wieder
zurückgeschrieben (try/finally), auch wenn der Bau scheitert.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LIB = ROOT / "rust" / "crates" / "sohelper" / "src" / "lib.rs"
TEST = ROOT / "tests" / "test_sohelper_gleichheit.py"
CARGO = os.environ.get("CARGO") or str(Path.home() / ".cargo" / "bin" / "cargo")

PASS = FAIL = 0


def ok(m):
    global PASS
    PASS += 1
    print(f"  ok    {m}")


def bad(m):
    global FAIL
    FAIL += 1
    print(f"  FAIL  {m}")


def bauen(ziel: Path) -> Path | None:
    env = dict(os.environ)
    env["CARGO_TARGET_DIR"] = str(ziel)
    env["PATH"] = f"{Path(CARGO).parent}:{env.get('PATH', '')}"
    p = subprocess.run(
        [CARGO, "build", "--release", "-p", "chimera-sohelper"],
        cwd=ROOT / "rust", env=env, capture_output=True, text=True,
    )
    if p.returncode != 0:
        print(p.stderr[-1500:])
        return None
    b = ziel / "release" / "chimera-sohelper"
    return b if b.is_file() else None


def mutation(name: str, alt: str, neu: str, erwartete_zeile: str, ziel: Path):
    original = LIB.read_text(encoding="utf-8")
    if alt not in original:
        bad(f"{name}: Mutationsstelle nicht gefunden")
        return
    gestellt = original.replace(alt, neu, 1)
    try:
        LIB.write_text(gestellt, encoding="utf-8")
        b = bauen(ziel)
    finally:
        LIB.write_text(original, encoding="utf-8")
    if b is None:
        bad(f"{name}: verfälschte Fassung baut nicht")
        return
    env = dict(os.environ)
    env["CHIMERA_SOHELPER_BIN"] = str(b)
    p = subprocess.run([sys.executable, str(TEST)], env=env,
                       capture_output=True, text=True, timeout=600)
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
    print("=== Gegenprobe: Gleichheit safety.py <-> chimera-sohelper ===")
    ziel = Path(tempfile.mkdtemp(prefix="sohelper-gp-"))

    env = dict(os.environ)
    gut = subprocess.run([sys.executable, str(TEST)], env=env,
                         capture_output=True, text=True, timeout=600)
    if gut.returncode == 0:
        ok("unverändert grün")
    else:
        bad("unverändert schon rot — Gegenprobe nicht aussagekräftig")
        for zeile in gut.stdout.splitlines():
            if "FAIL" in zeile:
                print("       ", zeile.strip())
        shutil.rmtree(ziel, ignore_errors=True)
        return 1

    try:
        # M-G1: sudo ist nicht mehr gesperrt.
        mutation("sudo-erlaubt",
                 'const GESPERRT: &[&str] = &["sudo", "su", "doas", "pkexec"];',
                 'const GESPERRT: &[&str] = &["su", "doas", "pkexec"];',
                 "run 'sudo ls'", ziel)

        # M-G2: Netzprogramme gehen durch.
        mutation("netz-erlaubt",
                 "if NETZ.contains(&exe.as_str()) {",
                 "if false && NETZ.contains(&exe.as_str()) {",
                 "run 'curl https://example.com'", ziel)

        # M-G3: Der Backslash schützt nicht mehr (Zerlegung driftet gegen
        # shlex.split, das ihn sehr wohl schützt).
        mutation("backslash",
                 """            '\\\\' => {
                hat_wort = true;
                match zeichen.next() {
                    Some(z) => wort.push(z),""",
                 """            '\\\\' => {
                hat_wort = true;
                wort.push('\\\\');
                match zeichen.next() {
                    Some(z) => wort.push(z),""",
                 "gleiche Argumente", ziel)

        # M-G4: Die Sperrliste heisst anders — der Text wird anders.
        mutation("text-anders",
                 'format!("\'{exe}\' ist gesperrt.")',
                 'format!("gesperrt: {exe}.")',
                 "run 'su -'", ziel)
    finally:
        shutil.rmtree(ziel, ignore_errors=True)

    print(f"\nErgebnis: {PASS} ok, {FAIL} fehlgeschlagen")
    return 0 if FAIL == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
