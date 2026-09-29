"""Prüfung und Zurechtstutzen eines Mood-Datensatzes.

Alles, was in den Renderer geht, kommt hier durch — ob es aus einer Datei
stammt, gemischt wurde oder vom Sprachmodell erfunden ist.

Warum das nicht optional ist: Ein Mood geht ohne Umweg ins Zeichnen.
``headbang_amp: 5000`` schickt den Avatar vom Bildschirm, ``rate: 0.99``
erzeugt eine Partikelflut, die auf einem Pi Zero die Bildrate bricht. Ein
Sprachmodell, das plausible Zahlen erfindet, erfindet gelegentlich auch
unplausible.

Grundhaltung: **zurechtstutzen statt ablehnen.** Ein Mood mit einem zu
großen Wert ist brauchbar, sobald der Wert im Rahmen liegt. Abgelehnt wird
nur, was gar nicht zu deuten ist. Jede Korrektur wird vermerkt — stilles
Zurechtbiegen wäre wieder die Fehlerklasse „es hat ja funktioniert"
(Architekturregel 8a).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .schema import (
    SLOTS,
    PRIORITY,
    BoolField,
    ColorField,
    EnumField,
    EnumListField,
    NumField,
    defaults,
)


@dataclass
class Report:
    """Was beim Prüfen auffiel."""

    fixes: list[str] = field(default_factory=list)
    drops: list[str] = field(default_factory=list)

    @property
    def clean(self) -> bool:
        return not self.fixes and not self.drops

    def __str__(self) -> str:
        if self.clean:
            return "ohne Beanstandung"
        parts = []
        if self.fixes:
            parts.append(f"{len(self.fixes)} korrigiert: " + "; ".join(self.fixes))
        if self.drops:
            parts.append(f"{len(self.drops)} verworfen: " + "; ".join(self.drops))
        return " | ".join(parts)


class MoodError(ValueError):
    """Der Datensatz ist nicht zu retten."""


def _as_number(value) -> float | None:
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


def _as_bool(value) -> bool | None:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        v = value.strip().lower()
        if v in ("true", "ja", "yes", "1"):
            return True
        if v in ("false", "nein", "no", "0"):
            return False
    return None


def _as_color(value) -> tuple[int, int, int] | None:
    """RGB aus Liste, Tupel oder ``#rrggbb``."""
    if isinstance(value, str):
        s = value.strip().lstrip("#")
        if len(s) == 6:
            try:
                return tuple(int(s[i : i + 2], 16) for i in (0, 2, 4))  # type: ignore[return-value]
            except ValueError:
                return None
        return None
    if isinstance(value, (list, tuple)) and len(value) == 3:
        # Immer als Tupel zurueck: PIL nimmt Listen nicht als Farbe an,
        # und JSON liefert Listen. Ohne das scheitert erst der Renderer --
        # weit weg von der Ursache.
        out = []
        for c in value:
            n = _as_number(c)
            if n is None:
                return None
            out.append(max(0, min(255, int(round(n)))))
        return tuple(out)  # type: ignore[return-value]
    return None


def validate(raw: dict, *, name: str | None = None) -> tuple[dict, Report]:
    """Einen rohen Datensatz in einen gültigen Mood verwandeln.

    Rückgabe ist der bereinigte Mood und ein Bericht. Nicht genannte Felder
    bekommen ihren Standardwert — ein Mood beschreibt nur seine Abweichung.
    """
    rep = Report()

    if not isinstance(raw, dict):
        raise MoodError(f"Mood muss ein Objekt sein, ist {type(raw).__name__}")

    mood = defaults()

    # --- Name -------------------------------------------------------------
    got_name = raw.get("name", name)
    if not isinstance(got_name, str) or not got_name.strip():
        raise MoodError("Mood ohne Namen")
    mood["name"] = got_name.strip()[:40]

    # --- Priorität --------------------------------------------------------
    prio = _as_number(raw.get("priority", PRIORITY.default))
    if prio is None:
        rep.fixes.append(f"priority unlesbar → {PRIORITY.default}")
        prio = PRIORITY.default
    clamped = PRIORITY.clamp(prio)
    if clamped != prio:
        rep.fixes.append(f"priority {prio:g} → {clamped}")
    mood["priority"] = clamped

    mood["fast_track"] = bool(_as_bool(raw.get("fast_track", False)))

    # --- Slots ------------------------------------------------------------
    for sname, slot in SLOTS.items():
        given = raw.get(sname)
        if given is None:
            continue
        if not isinstance(given, dict):
            rep.drops.append(f"{sname} ist kein Objekt")
            continue

        for fname, value in given.items():
            spec = slot.fields.get(fname)
            if spec is None:
                # Unbekannte Felder werden verworfen, nicht durchgereicht.
                # Sonst landet ein Tippfehler des Modells im Renderer und
                # wirkt dort stillschweigend gar nicht.
                rep.drops.append(f"{sname}.{fname} unbekannt")
                continue

            key = f"{sname}.{fname}"

            if isinstance(spec, NumField):
                n = _as_number(value)
                if n is None:
                    rep.drops.append(f"{key} keine Zahl ({value!r})")
                    continue
                c = spec.clamp(n)
                if abs(c - n) > 1e-9:
                    rep.fixes.append(f"{key} {n:g} → {c:g}")
                mood[sname][fname] = c

            elif isinstance(spec, EnumField):
                if value is None or (isinstance(value, str) and value.strip().lower() in ("", "none", "null", "keine")):
                    if None in spec.choices:
                        mood[sname][fname] = None
                    else:
                        rep.drops.append(f"{key} darf nicht leer sein")
                    continue
                v = str(value).strip().lower()
                if v in spec.choices:
                    mood[sname][fname] = v
                elif spec.strict:
                    rep.drops.append(f"{key} kennt '{value}' nicht")
                else:
                    # Kein Fehler: Der Renderer hat dafür keinen fertigen
                    # Baustein, die Darstellung kommt aus den freien Formen.
                    # Das Modell soll benennen dürfen, was es meint.
                    mood[sname][fname] = v[:32]
                    rep.fixes.append(f"{key} '{v}' ist frei — braucht eigene Formen")

            elif isinstance(spec, EnumListField):
                items = value if isinstance(value, (list, tuple)) else [value]
                good: list[str] = []
                for it in items:
                    if it is None:
                        continue
                    s = str(it).strip().lower()
                    if not s or s in ("none", "null", "keine"):
                        continue
                    if len(good) >= spec.max_items:
                        rep.fixes.append(f"{key} auf {spec.max_items} begrenzt")
                        break
                    if s not in spec.choices:
                        rep.fixes.append(f"{key} '{s}' ist frei — braucht eigene Formen")
                    good.append(s[:32])
                mood[sname][fname] = tuple(good)

            elif isinstance(spec, BoolField):
                b = _as_bool(value)
                if b is None:
                    rep.drops.append(f"{key} kein Ja/Nein ({value!r})")
                    continue
                mood[sname][fname] = b

            elif isinstance(spec, ColorField):
                col = _as_color(value)
                if col is None:
                    rep.drops.append(f"{key} keine Farbe ({value!r})")
                    continue
                mood[sname][fname] = col

    # --- Freie Formen -----------------------------------------------------
    from .draw import validate_shapes

    shapes = validate_shapes(raw.get("shapes"), rep)
    if shapes:
        mood["shapes"] = shapes

    return mood, rep


#: Wenn alles andere scheitert. Ein Gerät ohne Gesicht ist schlimmer als
#: ein Gerät mit einem langweiligen.
def fallback(reason: str = "") -> dict:
    m = defaults()
    m["name"] = "FALLBACK"
    m["priority"] = 0
    m["fast_track"] = False
    m["_reason"] = reason
    return m


def safe_validate(raw: dict, *, name: str | None = None) -> tuple[dict, Report]:
    """Wie :func:`validate`, liefert aber im Zweifel den Rückfall-Mood."""
    try:
        return validate(raw, name=name)
    except MoodError as exc:
        rep = Report(drops=[f"Datensatz unbrauchbar: {exc}"])
        return fallback(str(exc)), rep
