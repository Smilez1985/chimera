#!/usr/bin/env python3
"""Noisys 41 Moods als Startbestand übernehmen.

Die Audio-Kopplung (`labels`, `fingerprint`, `energy`) fällt weg — welcher
Ausdruck zu einem Geräusch passt, entscheidet in Chimera das Sprachmodell
(DESIGN.md §3.4). Was bleibt, sind die Ausdrücke selbst: als Beispiele
dafür, was möglich ist, und als Bestand, aus dem gemischt wird.

Aufruf:  python3 tools/import-noisy-moods.py <pfad-zu-noisy> [ziel.json]
"""
import importlib, json, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
from chimera.mood.validate import validate  # noqa: E402

src = Path(sys.argv[1] if len(sys.argv) > 1 else "/tmp/noisy")
dst = Path(sys.argv[2] if len(sys.argv) > 2 else "data/moods-builtin.json")
sys.path.insert(0, str(src))

import moods as nm  # noqa: E402
for group in ("emotionen", "idle", "koerper", "musik", "umgebung"):
    importlib.import_module(f"moods.{group}")

out, notes = [], []
for _mid, mood in sorted(nm._MOOD_REGISTRY.items()):
    raw = {k: v for k, v in mood.items()
           if k not in ("labels", "fingerprint", "energy", "id", "group")}
    m, rep = validate(raw)
    out.append(m)
    if not rep.clean:
        notes.append(f"{m['name']}: {rep}")

dst.parent.mkdir(parents=True, exist_ok=True)
dst.write_text(json.dumps({"moods": out}, ensure_ascii=False, indent=2),
               encoding="utf-8")
print(f"{len(out)} Moods -> {dst}")
for n in notes:
    print("  " + n)
