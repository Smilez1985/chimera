"""Die Zeichenebene — was das Sprachmodell erfinden darf.

Der Unterschied zu Noisy steckt hier, nicht im Mood-Format.

Noisy kennt benannte Bausteine: ``mouth.style = "smile"``, ``accessory =
"saxophone"``. Der Renderer weiß, wie man ein Saxophon zeichnet; das Modell
darf es nur auswählen. Damit ist der Ausdruck auf das gedeckelt, was jemand
vorher von Hand gezeichnet hat — eine Auswahlliste, kein Ausdrucksvermögen.

Chimera gibt stattdessen die **Grundformen** heraus, aus denen jede dieser
Figuren ohnehin besteht. Der Renderer stellt nicht Begriffe bereit, sondern
Striche: Ellipse, Bogen, Linie, Polygon, Rechteck, Kreissegment, Text. Was
daraus wird — ein Mund, ein Hut, ein Instrument, etwas, das noch niemand
gezeichnet hat — entscheidet das Modell.

Noisys 41 Moods bleiben als **Beispiele** erhalten, nicht als Grenze: Sie
zeigen, was möglich ist, und sind der Startbestand, aus dem gemischt wird.

Zwei Dinge bleiben trotzdem fest:

* **Koordinaten sind relativ** (0..1 auf die Bildfläche bezogen, ``0.5`` ist
  die Mitte). Damit ist eine Figur unabhängig von der Bildschirmgröße —
  sonst wäre das Erfundene an 240×280 gebunden (Architekturregel 6).
* **Es gibt eine Obergrenze.** Nicht als Bevormundung, sondern weil ein Pi
  Zero 2 W bei 15 Bildern je Sekunde rund 66 ms pro Bild hat. Wer 400
  Polygone zeichnen lässt, bekommt eine Diashow. Die Grenze steht in
  ``MAX_SHAPES`` und ist eine Einstellung, keine Konstante.
"""

from __future__ import annotations

from dataclasses import dataclass

#: Wie viele Formen ein Mood zusätzlich mitbringen darf. Messwert, kein
#: Dogma: auf stärkerer Hardware höher setzen.
MAX_SHAPES = 40

#: Ebenen, damit Erfundenes sich in die bestehende Zeichenreihenfolge
#: einfügen kann, statt immer obenauf zu liegen.
LAYERS = ("behind", "body", "face", "front")

#: Die Grundformen — **alles**, was die Zeichenebene hergibt.
#:
#: Bewusst vollständig statt sparsam: Jede Form, die das Werkzeug kann und
#: die sich sinnvoll auf einem 240×280-Schirm darstellen lässt, steht dem
#: Modell zur Verfügung. Was hier fehlt, kann später niemand erfinden.
#:
#: Die drei Bogenformen unterscheiden sich in dem, was geschlossen wird:
#: ``arc`` ist die nackte Linie, ``chord`` schließt Anfang und Ende direkt,
#: ``pieslice`` schließt über den Mittelpunkt — Tortenstück.
SHAPES: dict[str, tuple[str, ...]] = {
    # Flächen und Umrisse
    "ellipse":   ("x", "y", "w", "h"),
    "circle":    ("x", "y", "r"),
    "rect":      ("x", "y", "w", "h", "radius"),
    "polygon":   ("points",),
    "ngon":      ("x", "y", "r", "sides", "rotation"),

    # Bögen
    "arc":       ("x", "y", "w", "h", "start", "end", "width"),
    "chord":     ("x", "y", "w", "h", "start", "end"),
    "pieslice":  ("x", "y", "w", "h", "start", "end"),

    # Striche und Punkte
    "line":      ("points", "width", "joint"),
    "point":     ("points",),

    # Schrift
    "text":      ("x", "y", "text", "size", "anchor"),
}

#: Womit eine Form sich bewegen darf. Ohne das wäre alles Erfundene starr,
#: während der gezeichnete Körper atmet.
MOTIONS = (
    None,
    "bob",      # auf und ab
    "sway",     # seitlich
    "spin",     # drehen
    "pulse",    # größer/kleiner
    "flicker",  # Helligkeit
    "audio",    # folgt der Lautstärke der Sprachausgabe (§4.1)
)


@dataclass(frozen=True)
class ShapeSpec:
    """Grenzen für die Felder einer Form."""

    numeric = {
        "x": (-0.5, 1.5), "y": (-0.5, 1.5),
        "w": (0.0, 1.5), "h": (0.0, 1.5),
        "r": (0.0, 0.75),
        "radius": (0.0, 0.5),
        "width": (0.0, 0.2),
        "start": (-720.0, 720.0), "end": (-720.0, 720.0),
        "rotation": (-360.0, 360.0),
        "sides": (3, 24),
        "size": (0.0, 0.5),
        "amp": (0.0, 0.5), "speed": (0.0, 5.0), "phase": (0.0, 6.2832),
    }

    #: Felder, die ganzzahlig sein müssen.
    integer = ("sides",)

    #: Felder mit fester Auswahl.
    choices = {
        "joint": (None, "curve"),
        "anchor": (None, "la", "lm", "ld", "ma", "mm", "md", "ra", "rm", "rd"),
    }


def _num(value) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value.strip())
        except ValueError:
            return None
    return None


def _clamp(field: str, value: float) -> float:
    lo, hi = ShapeSpec.numeric.get(field, (-2.0, 2.0))
    v = max(lo, min(hi, value))
    return int(round(v)) if field in ShapeSpec.integer else round(v, 4)


def _color(value):
    from .validate import _as_color
    return _as_color(value)


def validate_shapes(raw, report=None) -> list[dict]:
    """Eine Liste erfundener Formen prüfen und zurechtstutzen.

    Gleiche Haltung wie beim übrigen Mood: zurechtstutzen statt ablehnen,
    Unbrauchbares verwerfen, alles vermerken.
    """
    out: list[dict] = []
    if raw is None:
        return out
    if not isinstance(raw, (list, tuple)):
        if report is not None:
            report.drops.append("shapes ist keine Liste")
        return out

    for i, item in enumerate(raw):
        if len(out) >= MAX_SHAPES:
            if report is not None:
                report.fixes.append(
                    f"shapes auf {MAX_SHAPES} begrenzt ({len(raw)} angefragt)"
                )
            break
        if not isinstance(item, dict):
            if report is not None:
                report.drops.append(f"shapes[{i}] ist kein Objekt")
            continue

        kind = str(item.get("kind", "")).strip().lower()
        if kind not in SHAPES:
            if report is not None:
                report.drops.append(f"shapes[{i}] kennt Form '{kind}' nicht")
            continue

        shape: dict = {"kind": kind}

        # Punkte (für line/polygon/point)
        if kind in ("line", "polygon", "point"):
            pts = item.get("points")
            good: list[tuple[float, float]] = []
            if isinstance(pts, (list, tuple)):
                for p in pts:
                    if isinstance(p, (list, tuple)) and len(p) == 2:
                        px, py = _num(p[0]), _num(p[1])
                        if px is not None and py is not None:
                            good.append((_clamp("x", px), _clamp("y", py)))
            need = {"line": 2, "polygon": 3, "point": 1}[kind]
            if len(good) < need:
                if report is not None:
                    report.drops.append(f"shapes[{i}] {kind} braucht {need} Punkte")
                continue
            shape["points"] = good[:24]

        if kind == "text":
            txt = item.get("text")
            if not isinstance(txt, str) or not txt.strip():
                if report is not None:
                    report.drops.append(f"shapes[{i}] text ist leer")
                continue
            shape["text"] = txt[:24]

        for fname in SHAPES[kind]:
            if fname in ("points", "text") or fname in ShapeSpec.choices:
                continue
            v = _num(item.get(fname))
            if v is not None:
                shape[fname] = _clamp(fname, v)

        col = _color(item.get("color"))
        if col is not None:
            shape["color"] = col
        outline = _color(item.get("outline"))
        if outline is not None:
            shape["outline"] = outline

        fill = item.get("fill")
        if fill is not None:
            shape["fill"] = bool(fill)

        # Auswahlfelder (joint, anchor)
        for fname in SHAPES[kind]:
            if fname not in ShapeSpec.choices:
                continue
            v = item.get(fname)
            if v is None:
                continue
            v = str(v).strip().lower()
            if v in ShapeSpec.choices[fname]:
                shape[fname] = v
            elif report is not None:
                report.fixes.append(f"shapes[{i}].{fname} '{v}' unbekannt → weggelassen")

        layer = str(item.get("layer", "front")).strip().lower()
        shape["layer"] = layer if layer in LAYERS else "front"

        motion = item.get("motion")
        motion = str(motion).strip().lower() if motion is not None else None
        if motion in ("", "none", "null"):
            motion = None
        if motion is not None and motion not in MOTIONS:
            if report is not None:
                report.fixes.append(f"shapes[{i}] Bewegung '{motion}' unbekannt → keine")
            motion = None
        if motion:
            shape["motion"] = motion
            for fname in ("amp", "speed", "phase"):
                v = _num(item.get(fname))
                if v is not None:
                    shape[fname] = _clamp(fname, v)

        out.append(shape)

    return out


def describe_for_llm() -> dict:
    """Die Zeichenebene, wie sie dem Modell erklärt wird."""
    return {
        "hinweis": (
            "Formen sind frei kombinierbar. Die benannten Moods sind "
            "Beispiele, keine Auswahlliste — was sich aus diesen Formen "
            "bauen lässt, darf gebaut werden."
        ),
        "koordinaten": "0..1 auf die Bildflaeche bezogen, 0.5 ist die Mitte",
        "obergrenze": MAX_SHAPES,
        "ebenen": list(LAYERS),
        "bewegungen": [m for m in MOTIONS if m],
        "gemeinsame_felder": {
            "color": "Farbe, RGB-Liste oder #rrggbb",
            "outline": "Umrissfarbe, optional",
            "fill": "true = ausgefuellt, false = nur Umriss",
            "layer": "behind | body | face | front",
            "motion": "Bewegung, siehe oben; dazu amp, speed, phase",
        },
        "formen": {
            k: {"felder": list(v)} for k, v in SHAPES.items()
        },
        "unterschied_boegen": (
            "arc = offene Linie, chord = Sehne schliesst direkt, "
            "pieslice = ueber den Mittelpunkt geschlossen (Tortenstueck)"
        ),
        "beispiel": [
            {"kind": "arc", "x": 0.5, "y": 0.62, "w": 0.22, "h": 0.14,
             "start": 20, "end": 160, "width": 0.012, "layer": "face"},
            {"kind": "ellipse", "x": 0.30, "y": 0.44, "w": 0.09, "h": 0.12,
             "color": [20, 20, 35], "fill": True, "layer": "face"},
        ],
    }
