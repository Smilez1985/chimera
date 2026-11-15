"""Gegenprobe: Die Audio-Einstellungen verlieren ihre Prüfungen.

Vier Verfälschungen an einer Baumkopie (`CHIMERA_ROOT_TEST`), jede bricht
eine andere Zusage aus `tests/test_audio_socket.py`:

1. Das Gateway schickt `audio_lesen` nicht mehr (Op umbenannt) — der Test
   muss es merken, sonst wiederholt sich der Fehler vom 13.11.2026
   (`freigaben_lesen` gegen `freigabe_lesen`).
2. Der Dienst kennt `audio_setzen` nicht mehr.
3. `app.py` verdrahtet die Brücke nicht mehr — dann antwortet der Socket
   „keine Bruecke" statt Werten.
4. Die Grenze 0..100 fällt aus `app.py` — eine Lautstärke von 120 ginge
   durch und am Gerät still auf 100 %.

Aufruf: python3 tests/gegenprobe_audio_socket.py
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HIER = Path(__file__).resolve().parent
ROOT = HIER.parent
TEST = HIER / "test_audio_socket.py"

WEB = "rust/crates/tor/src/web.rs"
SOCKET = "src/chimera/sitzung_socket.py"
APP = "src/chimera/app.py"

def kopiere(ziel: Path, dateien: tuple[str, ...]) -> None:
    """Nur was der Test liest und importiert -- eine ganze Baumkopie wäre
    langsam (2 GB `rust/target`) und würde den Sandkasten füllen."""
    for rel in dateien:
        ziel_datei = ziel / rel
        ziel_datei.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / rel, ziel_datei)
    # Die Python-Seite braucht das Paket `chimera` vollständig.
    ziel_src = ziel / "src/chimera"
    if not ziel_src.exists():
        shutil.copytree(ROOT / "src/chimera", ziel_src,
                        ignore=shutil.ignore_patterns("__pycache__"))
    (ziel / "tests").mkdir(parents=True, exist_ok=True)

VERFAELSCHUNGEN = [
    (
        "Gateway schickt audio_lesen nicht mehr",
        WEB,
        '"op": "audio_lesen"',
        '"op": "audio_lesex"',
    ),
    (
        "Dienst kennt audio_setzen nicht mehr",
        SOCKET,
        'elif op in ("audio_lesen", "audio_setzen"):',
        'elif op in ("audio_lesen",):',
    ),
    (
        "Brücke nicht verdrahtet",
        APP,
        "session.audio_bruecke = chi",
        "pass  # Bruecke fehlt",
    ),
    (
        "Grenze 0..100 in der Brücke entfernt",
        APP,
        'if regler not in ("mikrofon", "lautsprecher"):',
        'if False:',
    ),
]

def lauf(wurzel: Path) -> int:
    env = dict(os.environ, CHIMERA_ROOT_TEST=str(wurzel),
               PYTHONDONTWRITEBYTECODE="1")
    p = subprocess.run([sys.executable, str(TEST)], capture_output=True,
                       text=True, env=env, timeout=300)
    return p.returncode

def main() -> int:
    print("== Grundlauf (unveraendert, muss gruen sein)")
    if lauf(ROOT) != 0:
        print("GEGENPROBE UNBRAUCHBAR: schon der echte Baum ist rot")
        return 2
    print("  ok    unveraendert gruen")

    rot = 0
    with tempfile.TemporaryDirectory() as tmp:
        for i, (name, datei, alt, neu) in enumerate(VERFAELSCHUNGEN, 1):
            quelle = ROOT / datei
            text = quelle.read_text(encoding="utf-8")
            if alt not in text:
                print(f"  FAIL  Stelle {i} nicht gefunden in {datei}")
                return 1
            wurzel = Path(tmp) / f"baum-{i}"
            # Alle Dateien kopieren, damit jede Verfälschung allein steht.
            kopiere(wurzel, tuple({w for _, w, _, _ in VERFAELSCHUNGEN}))
            (wurzel / datei).write_text(text.replace(alt, neu, 1), encoding="utf-8")
            rc = lauf(wurzel)
            if rc != 0:
                rot += 1
                print(f"  ok    {i}/{len(VERFAELSCHUNGEN)} {name} -- Test wurde rot")
            else:
                print(f"  FAIL  {i}/{len(VERFAELSCHUNGEN)} {name} -- Test blieb gruen")
            shutil.rmtree(wurzel, ignore_errors=True)
    print(f"\n{rot}/{len(VERFAELSCHUNGEN)} Verfaelschungen rot")
    return 0 if rot == len(VERFAELSCHUNGEN) else 1

if __name__ == "__main__":
    sys.exit(main())
