"""Avatar-Einstellungen: Frisur, Haarfarbe, Kontrast.

DESIGN, Regel „Avatar-Einstellungen". Der **Dienst** ist der einzige
Schreiber dieser Ablage; das Gateway reicht nur durch (Sitzungs-Socket,
Regel 5s). Warum nicht das Gateway: es besitzt den Renderer nicht, und zwei
Schreiber auf einer Datei sind eine zweite Wahrheit mit Wettlauf.

Die Werte werden vom Renderer über ``state.rt`` gelesen (dieselben drei
Methoden, die aus dem Noisy-Port übrig waren: ``get_hair_style``,
``get_hair_color``, ``get_contrast``) — hier entsteht keine zweite
Zeichenlogik, nur die Ablage davor.
"""

from __future__ import annotations

import json
import os
import re
import tempfile
from pathlib import Path

#: Die Frisuren, die der Renderer wirklich zeichnen kann — abgeleitet aus
#: ``draw_hair_<name>`` in ``render/avatar.py`` (neun, eine mehr als Noisy).
#: Die Liste steht hier, weil sie die **Eingabe** prüft; dass der Renderer
#: jeden Namen kennt, hält ``tests/test_einstellungen.py`` gegen den
#: Quelltext.
FRISUREN = ("mochi", "peruecke", "kurz", "strubbel", "scheitel",
            "locken", "pony", "punk", "zopf")

STANDARD_FRISUR = "mochi"
STANDARD_FARBE = "#8B5A2B"
#: **45, nicht 0.** Der Renderer hebt ohne Einstellung seit jeher um 0.45 an
#: (`DEFAULT_CONTRAST_BOOST`, für helle Räume). Ein Feld mit der Vorgabe 0
#: hätte diese Anhebung beim ersten Start stillschweigend abgeschaltet und
#: alle Farben dunkler gemacht — eine Änderung, die niemand bestellt hat und
#: die man dem Farbwähler nicht ansieht.
STANDARD_KONTRAST = 45
KONTRAST_MAX = 100

#: Vorschau eines Dauerzustands: so lange, dann zurück (Auftrag smilez,
#: 15.11.2026: „moods ohne feste Laufzeit laufen für 30 Sekunden").
VORSCHAU_SEKUNDEN = 30.0

#: Felder, die die Ablage kennt. Alles andere wird abgewiesen, nicht
#: gespeichert -- ein Tippfehler soll nicht als Leiche in der Datei liegen.
FELDER = ("frisur", "farbe", "kontrast")

_HEX = re.compile(r"^#[0-9a-fA-F]{6}$")


def farbe_pruefen(wert) -> str | None:
    """``#RRGGBB`` in Großbuchstaben, oder ``None`` (kein gültiger Wert)."""
    if not isinstance(wert, str):
        return None
    text = wert.strip()
    if not _HEX.match(text):
        return None
    return text.upper()


def hex_zu_rgb(wert) -> tuple[int, int, int]:
    """``#RRGGBB`` → ``(r, g, b)``. Ungültiges fällt auf die Vorgabe zurück."""
    text = farbe_pruefen(wert) or STANDARD_FARBE
    return (int(text[1:3], 16), int(text[3:5], 16), int(text[5:7], 16))


def kontrast_pruefen(wert) -> int | None:
    """0..100 als ganze Zahl, oder ``None``."""
    if isinstance(wert, bool):
        return None
    try:
        zahl = int(str(wert).strip())
    except (TypeError, ValueError):
        return None
    if zahl < 0 or zahl > KONTRAST_MAX:
        return None
    return zahl


def frisur_pruefen(wert) -> str | None:
    """Ein Name aus :data:`FRISUREN`, oder ``None``."""
    if not isinstance(wert, str):
        return None
    text = wert.strip().lower()
    return text if text in FRISUREN else None


def vorschau(mood: dict, vorgabe: float = VORSCHAU_SEKUNDEN) -> tuple:
    """Wie lange eine Vorschau stehen soll — reine Rechnung, kein Zustand.

    Rückgabe ``(dauer, grund)``:

    - ``dauer is None`` → **einmal ganz**: Der Ausdruck bringt seine eigene
      Dauer mit (``BONG`` 13 s), und die wird nicht abgeschnitten. Das ist
      dieselbe Regel, nach der ``Face._dauer_von`` arbeitet.
    - sonst Sekunden → ein Dauerzustand (kein ``dauer_s``) läuft so lange
      und geht dann zurück.

    Ein Ausdruck mit eigener Dauer bekommt **nicht** die Vorschauzeit
    aufgestempelt: ``max(30, 13)`` hieße, die Animation stünde 17 s still
    herum, nachdem sie fertig ist (das war der ``BONG``-Fehler vom 15.11.).
    """
    try:
        eigene = float((mood or {}).get("dauer_s") or 0)
    except (TypeError, ValueError):
        eigene = 0.0
    if eigene > 0:
        return (None, f"eigene Dauer — läuft einmal ganz ({eigene:.0f} s)")
    return (float(vorgabe), f"Dauerzustand — {float(vorgabe):.0f} s Vorschau")


class Avatar:
    """Die Ablage: ``{"frisur", "farbe", "kontrast"}`` in einer Datei.

    Lesen ist nachsichtig (fehlende oder kaputte Datei → Vorgaben, mit
    Hinweis), Schreiben ist streng (ungültige Werte ändern nichts und
    nennen den Grund). Ein stiller Rückfall auf die Vorgabe wäre die
    Fehlerklasse „es hat ja funktioniert".
    """

    def __init__(self, pfad, *, vorgabe: dict | None = None):
        self.pfad = Path(pfad)
        self._vorgabe = dict(vorgabe or {})
        self._werte = self._vorgaben()
        self._hinweise: list[str] = []
        self.laden()

    # --- Lesen ---------------------------------------------------------

    def _vorgaben(self) -> dict:
        return {
            "frisur": frisur_pruefen(self._vorgabe.get("frisur")) or STANDARD_FRISUR,
            "farbe": farbe_pruefen(self._vorgabe.get("farbe")) or STANDARD_FARBE,
            "kontrast": (kontrast_pruefen(self._vorgabe.get("kontrast"))
                         if self._vorgabe.get("kontrast") is not None
                         else STANDARD_KONTRAST),
        }

    def laden(self) -> dict:
        """Die Datei lesen. Kaputte Datei → Vorgaben **und** ein Hinweis."""
        self._hinweise = []
        if not self.pfad.is_file():
            self._werte = self._vorgaben()
            return self._werte
        try:
            roh = json.loads(self.pfad.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            self._hinweise.append(f"Einstellungen unlesbar ({exc}) — Vorgaben")
            self._werte = self._vorgaben()
            return self._werte
        if not isinstance(roh, dict):
            self._hinweise.append("Einstellungen sind kein Objekt — Vorgaben")
            self._werte = self._vorgaben()
            return self._werte
        werte = self._vorgaben()
        for feld in FELDER:
            if feld not in roh:
                continue
            geprueft = self._pruefen(feld, roh[feld])
            if geprueft is None:
                self._hinweise.append(
                    f"{feld}: {roh[feld]!r} ungültig — Vorgabe gilt")
            else:
                werte[feld] = geprueft
        self._werte = werte
        return werte

    # --- Schreiben -----------------------------------------------------

    @staticmethod
    def _pruefen(feld: str, wert):
        if feld == "frisur":
            return frisur_pruefen(wert)
        if feld == "farbe":
            return farbe_pruefen(wert)
        if feld == "kontrast":
            return kontrast_pruefen(wert)
        return None

    def setzen(self, feld: str, wert) -> tuple[bool, str]:
        """Einen Wert setzen und schreiben. Ungültiges ändert **nichts**."""
        if feld not in FELDER:
            return (False, f"unbekanntes Feld {feld!r} — erlaubt: "
                           + ", ".join(FELDER))
        geprueft = self._pruefen(feld, wert)
        if geprueft is None:
            return (False, f"{feld}: {wert!r} ungültig — nichts geändert")
        neu = dict(self._werte)
        neu[feld] = geprueft
        try:
            self._schreiben(neu)
        except OSError as exc:
            return (False, f"nicht schreibbar: {exc}")
        self._werte = neu
        return (True, f"{feld} = {geprueft}")

    def _schreiben(self, werte: dict) -> None:
        """Atomar: ``os.replace`` — der Leser sieht nie eine halbe Datei."""
        self.pfad.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=str(self.pfad.parent),
                                   prefix=".avatar-", suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(werte, f, ensure_ascii=False, sort_keys=True)
                f.write("\n")
                f.flush()
                os.fsync(f.fileno())
            os.chmod(tmp, 0o644)
            os.replace(tmp, self.pfad)
        except BaseException:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise

    # --- Was der Renderer liest (state.rt) ------------------------------

    def get_hair_style(self) -> str:
        return self._werte.get("frisur") or STANDARD_FRISUR

    def get_hair_color(self) -> tuple[int, int, int]:
        return hex_zu_rgb(self._werte.get("farbe"))

    def get_contrast(self) -> int:
        return int(self._werte.get("kontrast") or 0)

    # --- Was die Weboberfläche liest ------------------------------------

    def als_json(self) -> dict:
        """Die Werte plus das, was die Seite zum Anzeigen braucht."""
        return {
            "frisur": self.get_hair_style(),
            "farbe": self._werte.get("farbe") or STANDARD_FARBE,
            "kontrast": self.get_contrast(),
            "frisuren": list(FRISUREN),
            "kontrast_max": KONTRAST_MAX,
            "vorschau_sekunden": VORSCHAU_SEKUNDEN,
            "pfad": str(self.pfad),
            "hinweise": list(self._hinweise),
        }
