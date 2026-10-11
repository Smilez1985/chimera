"""Die RGB-LED -- was sie zeigt, entscheidet derselbe Verwalter wie bei der
Statuszeile (DESIGN Regel 7c), und die Zeit bekommt sie gesagt (Regel 7d).

Quellen, Prioritäten, Abstände: wie bei :mod:`chimera.display.statusline`,
nur dass der Inhalt eine Farbe ist und die Darstellung ein **Muster** --
eine reine Funktion ``f(t_ms, farbe) -> farbe`` ohne eigene Uhr.

Die LED hängt am Panel (``panel.led(r, g, b)``), nicht an einem eigenen
Treiber: Auf der Whisplay teilen sich LCD, LED und Taste den GPIO-Satz,
und ein Panel ohne LED (``NullPanel``, E-Paper) nimmt den Aufruf still
entgegen. Deshalb ruft der Renderer ``LedVerwalter.anwenden(panel, jetzt)``
im selben Takt, in dem er zeichnet -- nicht öfter: Die LED-Treiber sind
Software-PWM mit 100 Hz, 15 Farbwechsel je Sekunde reichen.

Grundzustand ohne Meldung: die **Glow-Farbe des Gesichts** (Quelle
``mood``), gedimmt -- die LED sitzt neben dem Panel und soll dessen
Stimmung tragen, nicht mit ihr konkurrieren.
"""

from __future__ import annotations

import math
from typing import Callable

from ..arbiter import Arbiter, Slot

__all__ = ["QUELLEN", "REIHENFOLGE", "MUSTER", "LedVerwalter", "Farbe"]

Farbe = tuple[int, int, int]

# --- Quellenkatalog ---------------------------------------------------------
#
# Abstände ≥ 10 (Regel 7c). Dieselben Namen wie in der Statuszeile, wo
# dieselbe Sache gemeint ist: Wer ``hitze`` auf die Zeile legt, legt es
# auch auf die LED -- ein Katalog, zwei Darstellungen.
QUELLEN: dict[str, int] = {
    "abschaltung":   100,  # geordnetes Herunterfahren: rot, fest
    "hitze":          90,  # Temperaturwarnung: orange, pulsierend
    "anbieter_weg":   80,  # Sprachmodell nicht erreichbar: orange, blinkend
    "spricht":        70,  # Sprachausgabe läuft: Glow, atmend (Pegel kommt später)
    "hoert":          60,  # Mikrofon offen / Wake-Word: blau, fest (DESIGN §3.4)
    "taste":          50,  # Tastendruck quittiert: weiß, schnell blinkend
    "agentenstatus":  40,  # denkt: Glow, pulsierend
    "akku":           30,  # Akku unter Schwelle: gelb, langsam blinkend
    "mood":           10,  # Grundzustand: Glow des Gesichts, gedimmt
}

REIHENFOLGE: tuple[str, ...] = tuple(sorted(QUELLEN, key=lambda q: (-QUELLEN[q], q)))

# --- Muster: reine Funktionen f(t_ms, farbe) -> farbe (Regel 7d) --------------

def _skaliere(farbe: Farbe, faktor: float) -> Farbe:
    f = max(0.0, min(1.0, faktor))
    return (int(round(farbe[0] * f)), int(round(farbe[1] * f)), int(round(farbe[2] * f)))

def fest(t_ms: int, farbe: Farbe) -> Farbe:
    return farbe

def gedimmt(t_ms: int, farbe: Farbe) -> Farbe:
    return _skaliere(farbe, 0.35)

def puls(t_ms: int, farbe: Farbe, *, periode_ms: int = 1600, min_f: float = 0.15) -> Farbe:
    """Weiches Auf und Ab, nie ganz aus."""
    phase = (t_ms % periode_ms) / periode_ms
    f = min_f + (1.0 - min_f) * (0.5 - 0.5 * math.cos(2 * math.pi * phase))
    return _skaliere(farbe, f)

def blink(t_ms: int, farbe: Farbe, *, periode_ms: int = 800) -> Farbe:
    return farbe if (t_ms % periode_ms) < periode_ms // 2 else (0, 0, 0)

def blink_langsam(t_ms: int, farbe: Farbe) -> Farbe:
    return blink(t_ms, farbe, periode_ms=2400)

def blink_schnell(t_ms: int, farbe: Farbe) -> Farbe:
    """Quittung: 120 ms an, 120 ms dunkel.

    Der Kontrast liegt im Wechsel hell/dunkel, nicht in der Farbe. Ein
    fester Weisston hob sich am Geraet nicht vom blauen Grundglow ab --
    smilez sah beim Tastendruck nur "heller, bleibt blau" (11.10.2026).
    """
    return blink(t_ms, farbe, periode_ms=240)

def atmen(t_ms: int, farbe: Farbe) -> Farbe:
    return puls(t_ms, farbe, periode_ms=2400, min_f=0.3)

MUSTER: dict[str, Callable[[int, Farbe], Farbe]] = {
    "fest": fest,
    "gedimmt": gedimmt,
    "puls": puls,
    "blink": blink,
    "blink_langsam": blink_langsam,
    "blink_schnell": blink_schnell,
    "atmen": atmen,
}

# Darstellung je Quelle: (Farbe oder None = Glow des Gesichts, Muster).
DARSTELLUNG: dict[str, tuple[Farbe | None, str]] = {
    "abschaltung":  ((255, 0, 0), "fest"),
    "hitze":        ((255, 120, 0), "puls"),
    "anbieter_weg": ((255, 120, 0), "blink"),
    "spricht":      (None, "atmen"),
    "hoert":        ((0, 90, 255), "fest"),
    "taste":        ((255, 255, 255), "blink_schnell"),
    "agentenstatus": (None, "puls"),
    "akku":         ((255, 200, 0), "blink_langsam"),
    "mood":         (None, "gedimmt"),
}


class LedVerwalter:
    """Hält die LED-Wünsche und setzt den Gewinner auf das Panel.

    Aufruf (im Renderer-Takt):

        led = LedVerwalter()
        led.melden("hoert", jetzt_ms=t, laufzeit_ms=None)
        led.anwenden(panel, jetzt_ms=t, glow=renderer.current_glow_color)
    """

    def __init__(self) -> None:
        self._arbiter = Arbiter(reihenfolge=REIHENFOLGE)
        beanstandungen = Arbiter.abstaende_pruefen(QUELLEN)
        if beanstandungen:
            raise ValueError("LED-Quellenkatalog verletzt die Abstandsregel:\n  "
                             + "\n  ".join(beanstandungen))
        self._letzte: Farbe | None = None
        self._letzte_quelle: str | None = None

    # --- Eintragen --------------------------------------------------------

    def melden(self, quelle: str, *, jetzt_ms: int, laufzeit_ms: int | None = None,
               farbe: Farbe | None = None, muster: str | None = None, erneuern=None) -> None:
        """Einen LED-Wunsch setzen. Verdrängt den vorherigen derselben Quelle.

        ``farbe``/``muster`` überschreiben die Vorgabe der Quelle -- sonst
        gilt :data:`DARSTELLUNG`. Unbekannte Quellen und Muster werden
        abgelehnt, nicht geraten.
        """
        if quelle not in QUELLEN:
            raise KeyError(f"unbekannte LED-Quelle: {quelle!r} -- bekannt: {', '.join(sorted(QUELLEN))}")
        vorgabe_farbe, vorgabe_muster = DARSTELLUNG[quelle]
        m = muster or vorgabe_muster
        if m not in MUSTER:
            raise KeyError(f"unbekanntes LED-Muster: {m!r} -- bekannt: {', '.join(sorted(MUSTER))}")
        self._arbiter.setzen(
            Slot(quelle=quelle, prioritaet=QUELLEN[quelle],
                 inhalt=farbe if farbe is not None else vorgabe_farbe,
                 muster=m, laufzeit_ms=laufzeit_ms, erneuern=erneuern),
            jetzt_ms)

    def zuruecknehmen(self, quelle: str) -> bool:
        return self._arbiter.loeschen(quelle)

    # --- Abfragen ---------------------------------------------------------

    def quelle(self, jetzt_ms: int) -> str | None:
        g = self._arbiter.gewinner(jetzt_ms)
        return None if g is None else g.quelle

    def farbe(self, jetzt_ms: int, *, glow: Farbe) -> Farbe:
        """Die Farbe, die jetzt leuchten soll -- ohne Nebenwirkung.

        Ohne Meldung gilt der Grundzustand ``mood`` (gedimmter Glow).
        ``None`` als Slot-Farbe heißt „Glow des Gesichts".
        """
        g = self._arbiter.gewinner(jetzt_ms)
        if g is None:
            return MUSTER["gedimmt"](jetzt_ms, glow)
        basis = g.inhalt if g.inhalt is not None else glow
        return MUSTER.get(g.muster, fest)(jetzt_ms, tuple(basis))

    # --- Anwenden ---------------------------------------------------------

    def anwenden(self, panel, jetzt_ms: int, *, glow: Farbe) -> Farbe:
        """Gewinnerfarbe auf das Panel setzen -- nur bei Änderung.

        Ein ``led()``-Aufruf je Bild bei unveränderter Farbe wäre 15
        PWM-Umstellungen je Sekunde für nichts. Gibt die gesetzte (oder
        unverändert geltende) Farbe zurück, damit Tests sie prüfen können.
        """
        f = self.farbe(jetzt_ms, glow=glow)
        if f != self._letzte:
            try:
                panel.led(*f)
            except Exception:
                # Eine LED, die nicht geht, hält kein Bild auf (Regel 8a:
                # gemeldet wird es vom Panel beim Öffnen, nicht bei jedem Bild).
                pass
            self._letzte = f
        self._letzte_quelle = self.quelle(jetzt_ms)
        return f

    def aus(self, panel) -> None:
        """Beim Beenden: LED dunkel, Zustand vergessen."""
        try:
            panel.led(0, 0, 0)
        except Exception:
            pass
        self._letzte = None
