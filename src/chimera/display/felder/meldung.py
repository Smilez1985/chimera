"""Das Feld, das den Text zeigt: Meldung des Verwalters oder der Ausdruck.

Höchste Priorität im Bereich, weil es das Einzige ist, was man lesen *muss*:
Was Chimera gerade tut oder sagt. Lange Texte (eine Antwort) werden auf zwei
Zeilen verteilt und dann gekürzt — nicht abgeschnitten.
"""

from __future__ import annotations

from ..feld import Feld


def _zeichnen(flaeche, kontext: dict) -> None:
    text = str(kontext.get("text") or kontext.get("mood") or "")
    if not text:
        return
    # Kurz bleibt einzeilig und groß; erst was nicht in eine Zeile passt,
    # wird auf zwei verteilt -- dann kleiner, aber nie unter 10 px.
    zwei = len(text) > 20
    groesse = max(11, int(flaeche.hoehe * (0.44 if zwei else 0.62)))
    flaeche.text(text, groesse=groesse,
                 farbe=kontext.get("farbe") or FELD.farbe,
                 ausrichtung="mitte", zeilen=2 if zwei else 1)


FELD = Feld(
    name="meldung",
    titel="Meldung / Ausdruck",
    wunsch=27,          # zwei Zeilen, die man aus einem Meter liest
    mindestens=20,      # eine Zeile bleibt immer
    prioritaet=10,      # verliert zuletzt
    zeichnen=_zeichnen,
    ausrichtung="mitte",
    farbe=(235, 235, 235),
    hintergrund=(0, 0, 0),
    sichtbar=lambda k: bool(k.get("text") or k.get("mood")),
)
