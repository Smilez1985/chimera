"""Mischen und Variieren — Ausdrücke ohne Sprachmodell.

Die beiden billigen Stufen aus dem Entwurf (§3.3). Sie decken den Alltag
ab: Ein Gerät, das für jeden Gesichtsausdruck ein Modell fragt, wäre weder
bezahlbar noch schnell genug, und bei Netzausfall bliebe es ausdruckslos.

Gemischt wird komponentenweise, aber nicht stumpf:

* **Farben** über den Farbton, nicht über die Kanäle. Rot und Gelb kanalweise
  gemittelt ergibt ein stumpfes Orange; über den Farbton gemischt ergibt es
  ein sattes. Bei Graustufen greift der Farbton nicht, dort wird kanalweise
  gemittelt.
* **Zahlen** gewichtet gemittelt.
* **Aufzählungen und Ja/Nein** können nicht gemittelt werden — dort gewinnt
  das höhere Gewicht. Ein halbes Lächeln gibt es nicht.
"""

from __future__ import annotations

import colorsys
import random

from .schema import (
    SLOTS,
    BoolField,
    ColorField,
    EnumField,
    EnumListField,
    NumField,
)
from .validate import Report, validate


# --- Farben ----------------------------------------------------------------

def mix_color(a: tuple[int, int, int], b: tuple[int, int, int],
              t: float) -> tuple[int, int, int]:
    """Zwei Farben mischen; ``t=0`` ergibt ``a``, ``t=1`` ergibt ``b``."""
    ha, sa, va = colorsys.rgb_to_hsv(*[c / 255 for c in a])
    hb, sb, vb = colorsys.rgb_to_hsv(*[c / 255 for c in b])

    # Bei (fast) grauen Farben ist der Farbton bedeutungslos und zeigt
    # irgendwohin. Ihn mitzumitteln färbt Grau ein.
    if sa < 0.08 or sb < 0.08:
        h = ha if sa >= sb else hb
    else:
        # Kürzerer Weg um den Farbkreis: Rot und Violett liegen nebeneinander,
        # nicht an entgegengesetzten Enden.
        d = hb - ha
        if d > 0.5:
            d -= 1.0
        elif d < -0.5:
            d += 1.0
        h = (ha + d * t) % 1.0

    s = sa + (sb - sa) * t
    v = va + (vb - va) * t
    return tuple(int(round(c * 255)) for c in colorsys.hsv_to_rgb(h, s, v))  # type: ignore[return-value]


# --- Mischen ---------------------------------------------------------------

def mix(a: dict, b: dict, t: float = 0.5, *, name: str | None = None) -> dict:
    """Zwei Moods mischen.

    ``t`` ist das Gewicht von ``b``: 0 liefert ``a``, 1 liefert ``b``.
    """
    t = max(0.0, min(1.0, float(t)))
    out: dict = {
        "name": name or f"{a['name']}~{b['name']}",
        "priority": round(a.get("priority", 30) + (b.get("priority", 30) - a.get("priority", 30)) * t),
        "fast_track": a.get("fast_track", False) if t < 0.5 else b.get("fast_track", False),
    }

    for sname, slot in SLOTS.items():
        sa, sb = a.get(sname, {}), b.get(sname, {})
        merged: dict = {}
        for fname, spec in slot.fields.items():
            va = sa.get(fname, spec.default)
            vb = sb.get(fname, spec.default)

            if isinstance(spec, NumField):
                merged[fname] = spec.clamp(va + (vb - va) * t)
            elif isinstance(spec, ColorField):
                merged[fname] = mix_color(tuple(va), tuple(vb), t)
            elif isinstance(spec, EnumListField):
                # Listen lassen sich vereinigen, statt eine wegzuwerfen --
                # zwei Moods mit je einem Accessoire ergeben einen mit
                # beiden. Reihenfolge nach Gewicht.
                first, second = (va, vb) if t < 0.5 else (vb, va)
                seen: list[str] = []
                for x in list(first) + list(second):
                    if x not in seen and len(seen) < spec.max_items:
                        seen.append(x)
                merged[fname] = tuple(seen)
            else:
                # Auswahl und Ja/Nein: das schwerere Gewicht gewinnt.
                merged[fname] = va if t < 0.5 else vb
        out[sname] = merged

    # Freie Formen: beim Mischen gewinnt die schwerere Seite. Zwei Sätze
    # erfundener Formen ineinanderzurechnen ergäbe Matsch, keine Figur.
    shapes = a.get("shapes") if t < 0.5 else b.get("shapes")
    if shapes:
        out["shapes"] = shapes

    mood, _ = validate(out)
    return mood


def mix_many(parts: list[tuple[dict, float]], *, name: str | None = None) -> dict:
    """Mehrere Moods nach Gewicht mischen.

    Nacheinander, wobei das Gewicht des bereits Gemischten mitwächst —
    sonst würde jeder neue Teil die Hälfte beanspruchen.
    """
    if not parts:
        raise ValueError("Nichts zu mischen")
    total = sum(max(0.0, w) for _, w in parts)
    if total <= 0:
        raise ValueError("Gewichte ergeben null")

    acc, acc_w = parts[0][0], max(0.0, parts[0][1])
    for mood, w in parts[1:]:
        w = max(0.0, w)
        if w == 0:
            continue
        acc = mix(acc, mood, w / (acc_w + w))
        acc_w += w
    if name:
        acc = dict(acc, name=name)
    return acc


# --- Variieren -------------------------------------------------------------

def vary(mood: dict, *, seed=None, strength: float = 0.15,
         name: str | None = None) -> dict:
    """Denselben Ausdruck leicht anders zeichnen.

    Damit dieselbe Stimmung nicht jedes Mal pixelgleich aussieht. Der Seed
    kommt aus dem Anlass, nicht aus dem Zufall — derselbe Anlass soll
    denselben Ausdruck ergeben, sonst flackert das Gesicht.

    Verändert werden nur Zahlen und Farben. Aus einem Lächeln ein Stirnrunzeln
    zu würfeln wäre keine Variation, sondern ein anderer Mood.
    """
    rng = random.Random(seed)
    strength = max(0.0, min(1.0, strength))
    out: dict = {
        "name": name or f"{mood['name']}'",
        "priority": mood.get("priority", 30),
        "fast_track": mood.get("fast_track", False),
    }

    for sname, slot in SLOTS.items():
        src = mood.get(sname, {})
        merged: dict = {}
        for fname, spec in slot.fields.items():
            v = src.get(fname, spec.default)

            if isinstance(spec, NumField):
                span = (spec.hi - spec.lo) * strength * 0.25
                merged[fname] = spec.clamp(v + rng.uniform(-span, span))
            elif isinstance(spec, ColorField):
                h, s, val = colorsys.rgb_to_hsv(*[c / 255 for c in v])
                h = (h + rng.uniform(-0.04, 0.04) * strength) % 1.0
                s = max(0.0, min(1.0, s + rng.uniform(-0.12, 0.12) * strength))
                val = max(0.0, min(1.0, val + rng.uniform(-0.10, 0.10) * strength))
                merged[fname] = tuple(
                    int(round(c * 255)) for c in colorsys.hsv_to_rgb(h, s, val)
                )
            else:
                merged[fname] = v
        out[sname] = merged

    if mood.get("shapes"):
        out["shapes"] = mood["shapes"]

    m, _ = validate(out)
    return m
