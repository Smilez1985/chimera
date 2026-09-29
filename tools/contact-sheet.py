#!/usr/bin/env python3
"""Moods nebeneinander zeichnen, zum Ansehen ohne Gerät.

Auf dem Gerät geht das Bild direkt in den Panelspeicher
(`chimera.display.panel`). Dieses Werkzeug schreibt stattdessen eine Datei
— nicht weil das der Ausgabeweg wäre, sondern weil man während der
Entwicklung sehen will, was herauskommt.

Aufruf:  python3 tools/contact-sheet.py [ziel.png]
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from PIL import Image  # noqa: E402

from chimera.display.panel import NullPanel  # noqa: E402
from chimera.mood import blend  # noqa: E402
from chimera.mood.validate import validate  # noqa: E402
from chimera.render.avatar import NoisyRenderer, State  # noqa: E402

dst = Path(sys.argv[1] if len(sys.argv) > 1 else "contact-sheet.png")

raw = json.loads((ROOT / "data" / "moods-builtin.json").read_text("utf-8"))["moods"]
by = {}
for m in raw:
    v, _ = validate(m)
    by[v["name"]] = v

items = [(n, by[n]) for n in sorted(by)]
for a, b, t in (("ROCK", "CHILL", 0.5), ("SAD", "LAUGH", 0.5),
                ("JAZZ", "ROCK", 0.35)):
    if a in by and b in by:
        items.append((f"{a}+{b}", blend.mix(by[a], by[b], t)))

state = State()
r = NoisyRenderer(state, NullPanel())
cols = 6
rows = (len(items) + cols - 1) // cols
sheet = Image.new("RGB", (r.WIDTH * cols, r.HEIGHT * rows), (10, 10, 14))

for i, (name, mood) in enumerate(items):
    state.mood, state.mood_name = mood, name
    state.intensity, state.beat = 90, 40
    r.frame = 7.0
    sheet.paste(r.render(), ((i % cols) * r.WIDTH, (i // cols) * r.HEIGHT))

sheet.save(dst)
print(f"{len(items)} Moods -> {dst}")
