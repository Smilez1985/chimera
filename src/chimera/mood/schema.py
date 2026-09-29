"""Das Vokabular, aus dem ein Gesicht besteht.

Diese Tabelle ist die **einzige** Wahrheitsquelle. Aus ihr entstehen:

  * der Validator (:mod:`chimera.mood.validate`),
  * das Schema, das dem Sprachmodell geschickt wird,
  * die Grenzen, innerhalb derer gemischt und variiert wird.

Zwei getrennte Listen wären der sichere Weg ins Auseinanderdriften: Wer ein
Feld ergänzt und nur eine davon pflegt, bekommt entweder einen Validator,
der gültige Werte ablehnt, oder ein Schema, das ungültige verspricht.
(Architekturregel 2.)

Die Zahlengrenzen stammen aus Noisys 41 Moods — mit Luft nach oben und
unten, damit generierte Ausdrücke nicht auf das eingeschnürt werden, was
schon einmal jemand von Hand geschrieben hat. Die Aufzählungen kommen
dagegen aus dem **Renderer**, nicht aus den Moods: Er kann mehr zeichnen,
als die Moods nutzen (``sunglasses``, ``frost``, ``ear_muffs``,
``jackhammer``). Was gezeichnet werden kann, darf auch erfunden werden.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class NumField:
    """Ein Zahlenfeld mit Grenzen."""

    default: float
    lo: float
    hi: float
    integer: bool = False
    doc: str = ""

    def clamp(self, value: float) -> float:
        v = max(self.lo, min(self.hi, value))
        return int(round(v)) if self.integer else round(v, 4)


@dataclass(frozen=True)
class EnumField:
    """Ein Feld mit **Vorschlägen**, nicht mit einer festen Auswahl.

    ``choices`` listet, was der Renderer schon fertig kann. Ein Wert, der
    nicht darin steht, ist kein Fehler: Er wird durchgelassen, und die
    Darstellung kommt dann aus den freien Formen (:mod:`chimera.mood.draw`).
    So bleibt der Ausdruck nicht auf das begrenzt, was jemand von Hand
    gezeichnet hat.

    ``strict=True`` kehrt das um, für Felder, bei denen ein unbekannter Wert
    wirklich nichts bedeuten kann.
    """

    default: str | None
    choices: tuple[str | None, ...]
    doc: str = ""
    strict: bool = False


@dataclass(frozen=True)
class BoolField:
    default: bool
    doc: str = ""


@dataclass(frozen=True)
class EnumListField:
    """Mehrere Werte aus derselben Vorschlagsliste.

    Noisy erlaubt an Accessoires bereits mehrere gleichzeitig (Sonnenbrille
    *und* Frost). Ein Feld, das nur eines zulässt, würde Ausdruck
    wegnehmen — also nimmt es eine Liste.
    """

    default: tuple[str, ...]
    choices: tuple[str | None, ...]
    doc: str = ""
    max_items: int = 4


@dataclass(frozen=True)
class ColorField:
    """RGB, drei Werte 0–255."""

    default: tuple[int, int, int]
    doc: str = ""


Field = NumField | EnumField | EnumListField | BoolField | ColorField


@dataclass(frozen=True)
class Slot:
    """Eine Gruppe zusammengehöriger Felder, z. B. ``eyes``."""

    name: str
    fields: dict[str, Field]
    doc: str = ""


# --- Aufzählungen ----------------------------------------------------------
#
# Reihenfolge ist bedeutungslos, aber stabil halten: Sie geht so in das
# Schema für das Sprachmodell.

#: Was der Renderer fertig kann. **Vorschläge, keine Grenze** — eigene
#: Namen sind erlaubt und werden über freie Formen dargestellt.
MOUTH_STYLES = (
    "smile", "grin", "smirk", "neutral", "line", "frown", "concerned",
    "open_round", "focused", "chewing", "sip", "squiggle", "tongue", "yawn",
)

PARTICLE_TYPES = (
    None, "note", "zzz", "exclamation", "heart", "sweat", "star",
    "drop", "smoke", "stink",
)

ACCESSORY_TYPES = (
    None,
    "headphones", "sunglasses", "gold_chain", "rasta_hat", "devil_sign",
    "joint", "bong", "drink", "coffee", "popcorn", "saxophone",
    "sheet_music", "keyboard", "gamepad", "remote", "watch",
    "big_ear", "ear_muffs", "breeze", "frost", "jackhammer",
)

HAIR_STYLES = (None, "peruecke")


# --- Die Tabelle -----------------------------------------------------------

SLOTS: dict[str, Slot] = {
    "body": Slot(
        "body",
        {
            "color": ColorField((30, 180, 220), "Körperfarbe"),
            "glow": ColorField((15, 90, 110), "Farbe des Scheins dahinter"),
        },
        "Grundkörper. Die Farbe trägt den größten Teil der Stimmung.",
    ),
    "eyes": Slot(
        "eyes",
        {
            "scale_w": NumField(1.0, 0.1, 2.5, doc="Breite, 1.0 = normal"),
            "scale_h": NumField(1.0, 0.05, 2.5, doc="Höhe; klein = zusammengekniffen"),
            "look_offset": NumField(0, -20, 20, integer=True, doc="Blick nach links/rechts"),
            "droopy": BoolField(False, "Hängende Lider — müde"),
            "focused": BoolField(False, "Enger Blick — konzentriert"),
            "swirl": BoolField(False, "Spiralaugen — benommen"),
        },
        "Augen. Der ausdrucksstärkste Teil des Gesichts.",
    ),
    "mouth": Slot(
        "mouth",
        {
            "style": EnumField("smile", MOUTH_STYLES),
            "width": NumField(1.0, 0.4, 1.8, doc="Breite des Mundes"),
        },
    ),
    "hair": Slot(
        "hair",
        {
            "visible": BoolField(True),
            "wobble": BoolField(False, "Schwingt nach, wenn der Kopf sich bewegt"),
            "blown": BoolField(False, "Nach hinten geweht"),
            "style": EnumField(None, HAIR_STYLES),
            "color": ColorField((139, 90, 43)),
            "color_dark": ColorField((110, 70, 30)),
            "color_light": ColorField((165, 110, 55)),
        },
    ),
    "physics": Slot(
        "physics",
        {
            "headbang_speed": NumField(0, 0, 2.0, doc="0 = kein Nicken"),
            "headbang_amp": NumField(0, 0, 40),
            "bounce_speed": NumField(0, 0, 1.5),
            "bounce_amp": NumField(0, 0, 45),
            "sway_speed": NumField(0.05, 0, 1.2, doc="Ruhiges Wiegen"),
            "sway_amp": NumField(2.2, 0, 25),
            "shake_x": NumField(0, 0, 15, doc="Zittern waagerecht"),
            "shake_y": NumField(0, 0, 15),
            "stretch_w": NumField(0, -25, 25, doc="Körper breiter/schmaler"),
            "stretch_h": NumField(0, -25, 30),
            "toke": BoolField(False, "Zug-Zyklus für Joint und Bong"),
        },
        "Bewegung. Hier entsteht der Unterschied zwischen Bild und Lebewesen.",
    ),
    "particles": Slot(
        "particles",
        {
            "type": EnumField(None, PARTICLE_TYPES),
            "rate": NumField(0, 0, 0.6, doc="Wie dicht; über 0.6 bricht die Bildrate"),
            "color": ColorField((255, 255, 255), "Ohne Angabe wird die Körperfarbe genommen"),
        },
    ),
    "accessory": Slot(
        "accessory",
        {"type": EnumListField((), ACCESSORY_TYPES,
                               "Mehrere gleichzeitig erlaubt")},
    ),
}


# --- Felder außerhalb der Slots -------------------------------------------

PRIORITY = NumField(30, 0, 100, integer=True, doc="Höher verdrängt Niedrigeres")

#: Zusätzliche, frei erfundene Formen. Hier entsteht alles, wofür es
#: keinen fertigen Baustein gibt.
SHAPES_DOC = (
    "Liste freier Zeichenformen. Siehe chimera.mood.draw — damit lässt sich "
    "darstellen, was die benannten Bausteine nicht hergeben."
)

#: Woher ein Mood stammt. Kein Schmuck: Eingebaute dürfen nicht
#: weggeräumt werden, erfundene schon.
ORIGINS = ("builtin", "mixed", "varied", "generated")


def slot_names() -> tuple[str, ...]:
    return tuple(SLOTS)


def defaults() -> dict[str, dict]:
    """Der Mood, den man bekommt, wenn niemand etwas sagt."""
    out: dict[str, dict] = {}
    for sname, slot in SLOTS.items():
        out[sname] = {fname: f.default for fname, f in slot.fields.items()}
    return out


def describe_for_llm() -> dict:
    """Das Vokabular in der Form, in der es das Sprachmodell bekommt.

    Bewusst keine vollständige JSON-Schema-Fassung: Ein Modell mit einer
    knappen, lesbaren Tabelle und Beispielen trifft zuverlässiger als eines,
    das sich durch eine Schachtelung von ``$ref`` arbeiten muss.
    """
    out: dict = {}
    for sname, slot in SLOTS.items():
        fields: dict = {}
        for fname, f in slot.fields.items():
            if isinstance(f, NumField):
                d = {"typ": "zahl", "von": f.lo, "bis": f.hi, "standard": f.default}
            elif isinstance(f, EnumField):
                d = {"typ": "auswahl (eigene Werte erlaubt)",
                     "vorschlaege": list(f.choices), "standard": f.default}
            elif isinstance(f, EnumListField):
                d = {"typ": "liste (eigene Werte erlaubt)",
                     "vorschlaege": list(f.choices),
                     "hoechstens": f.max_items, "standard": list(f.default)}
            elif isinstance(f, BoolField):
                d = {"typ": "ja/nein", "standard": f.default}
            else:
                d = {"typ": "farbe rgb 0-255", "standard": list(f.default)}
            if f.doc:
                d["bedeutung"] = f.doc
            fields[fname] = d
        entry: dict = {"felder": fields}
        if slot.doc:
            entry["bedeutung"] = slot.doc
        out[sname] = entry
    return out
