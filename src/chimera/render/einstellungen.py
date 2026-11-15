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

#: Helligkeit und Nachtfenster (wie bei Noisy: `display` in der
#: RuntimeConfig). **Standardmäßig aus** — `nacht_dimmen` ist ein Schalter,
#: den der Nutzer umlegt. Ein Gerät, das über Nacht von selbst dunkler wird,
#: ohne dass es jemand bestellt hat, sieht wie ein Defekt aus.
STANDARD_HELLIGKEIT_TAG = 255
STANDARD_HELLIGKEIT_NACHT = 80
STANDARD_NACHT_VON = "22:00"
STANDARD_NACHT_BIS = "06:00"
STANDARD_NACHT_DIMMEN = False

#: Felder, die die Ablage kennt. Alles andere wird abgewiesen, nicht
#: gespeichert -- ein Tippfehler soll nicht als Leiche in der Datei liegen.
FELDER = ("frisur", "farbe", "kontrast", "helligkeit_tag",
          "helligkeit_nacht", "nacht_von", "nacht_bis", "nacht_dimmen",
          # Vorübergehende Helligkeit für die **aktuelle** Zone (Regel
          # „Einstellungen am Gerät"): Sie gilt bis zum nächsten Tag/Nacht-
          # Wechsel und fällt dann auf die eingestellte Dimmstufe zurück.
          "helligkeit_jetzt", "helligkeit_jetzt_bis", "helligkeit_jetzt_zone")

_HEX = re.compile(r"^#[0-9a-fA-F]{6}$")
_UHRZEIT = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")


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


def helligkeit_pruefen(wert) -> int | None:
    """0..255 als ganze Zahl, oder ``None``."""
    if isinstance(wert, bool):
        return None
    try:
        zahl = int(str(wert).strip())
    except (TypeError, ValueError):
        return None
    return zahl if 0 <= zahl <= 255 else None


def helligkeit_bis_pruefen(wert) -> int | None:
    """Zeitstempel (Sekunden seit der Epoche), 0 oder positiv, oder ``None``."""
    if isinstance(wert, bool):
        return None
    try:
        zahl = int(str(wert).strip())
    except (TypeError, ValueError):
        return None
    return zahl if 0 <= zahl < 4102444800 else None   # bis 2099


def uhrzeit_pruefen(wert) -> str | None:
    """``HH:MM`` (00:00..23:59), oder ``None``."""
    if not isinstance(wert, str):
        return None
    text = wert.strip()
    return text if _UHRZEIT.match(text) else None


def schalter_pruefen(wert) -> bool | None:
    """Wahrheitswert. ``None`` heißt: kein gültiger Wert (nicht: falsch)."""
    if isinstance(wert, bool):
        return wert
    if isinstance(wert, (int, float)) and wert in (0, 1):
        return bool(wert)
    if isinstance(wert, str):
        text = wert.strip().lower()
        if text in ("an", "ein", "ja", "true", "1"):
            return True
        if text in ("aus", "nein", "false", "0"):
            return False
    return None


def frisur_pruefen(wert) -> str | None:
    """Ein Name aus :data:`FRISUREN`, oder ``None``."""
    if not isinstance(wert, str):
        return None
    text = wert.strip().lower()
    return text if text in FRISUREN else None


def zone(uhrzeit: str, von: str, bis: str) -> str:
    """``"nacht"`` oder ``"tag"`` — dieselbe Regel wie der Renderer.

    Der Renderer entscheidet mit `_is_night` (``start <= now < end``, Fenster
    über Mitternacht: ``now >= start or now < end``). Diese Funktion rechnet
    **genau das** nach, damit die Seite nicht rät, in welcher Zone sie gerade
    schaltet — eine zweite Wahrheit hier wäre ein Schalter, der die falsche
    Zahl ändert.
    """
    if von <= bis:
        return "nacht" if von <= uhrzeit < bis else "tag"
    return "nacht" if (uhrzeit >= von or uhrzeit < bis) else "tag"


def _minuten(text: str) -> int:
    st, mi = text.split(":")
    return int(st) * 60 + int(mi)


def naechster_wechsel(uhrzeit: str, von: str, bis: str) -> int:
    """Sekunden bis zum nächsten Zonenwechsel (immer > 0)."""
    jetzt = _minuten(uhrzeit)
    kandidaten = []
    for grenze in (_minuten(von), _minuten(bis)):
        rest = (grenze - jetzt) % (24 * 60)
        kandidaten.append(rest or 24 * 60)
    return min(kandidaten) * 60


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
        v = self._vorgabe
        tage = schalter_pruefen(v.get("nacht_dimmen"))
        return {
            "frisur": frisur_pruefen(v.get("frisur")) or STANDARD_FRISUR,
            "farbe": farbe_pruefen(v.get("farbe")) or STANDARD_FARBE,
            "kontrast": (kontrast_pruefen(v.get("kontrast"))
                         if v.get("kontrast") is not None
                         else STANDARD_KONTRAST),
            "helligkeit_tag": (helligkeit_pruefen(v.get("helligkeit_tag"))
                               if v.get("helligkeit_tag") is not None
                               else STANDARD_HELLIGKEIT_TAG),
            "helligkeit_nacht": (helligkeit_pruefen(v.get("helligkeit_nacht"))
                                 if v.get("helligkeit_nacht") is not None
                                 else STANDARD_HELLIGKEIT_NACHT),
            "nacht_von": uhrzeit_pruefen(v.get("nacht_von")) or STANDARD_NACHT_VON,
            "nacht_bis": uhrzeit_pruefen(v.get("nacht_bis")) or STANDARD_NACHT_BIS,
            "nacht_dimmen": (STANDARD_NACHT_DIMMEN if tage is None else tage),
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
        if feld in ("helligkeit_tag", "helligkeit_nacht",
                    "helligkeit_jetzt"):
            # "zurueck" löscht die vorübergehende Helligkeit — der einzige
            # Weg zurück zur eingestellten Dimmstufe (0 wäre ein gültiger,
            # also pechschwarzer Wert und dürfte das nicht).
            if wert == "zurueck":
                return "zurueck"
            return helligkeit_pruefen(wert)
        if feld == "helligkeit_jetzt_bis":
            return helligkeit_bis_pruefen(wert)
        if feld == "helligkeit_jetzt_zone":
            return wert if wert in ("tag", "nacht") else None
        if feld in ("nacht_von", "nacht_bis"):
            return uhrzeit_pruefen(wert)
        if feld == "nacht_dimmen":
            return schalter_pruefen(wert)
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
        if feld == "helligkeit_jetzt":
            if geprueft == "zurueck":
                # Zurück auf die eingestellte Dimmstufe: die Überlagerung
                # verschwindet ganz (kein Rest, der später wieder aufwacht).
                for k in ("helligkeit_jetzt", "helligkeit_jetzt_bis",
                          "helligkeit_jetzt_zone"):
                    neu.pop(k, None)
                try:
                    self._schreiben(neu)
                except OSError as exc:
                    return (False, f"nicht schreibbar: {exc}")
                self._werte = neu
                return (True, "Helligkeit zurück auf die Tag/Nacht-Einstellung")
            # Wert setzen **und** die Gültigkeit mitgeben: bis zum nächsten
            # Wechsel, in der Zone, in der gerade geschaltet wird.
            import time
            jetzt_zone = self._jetzt_zone()
            rest = naechster_wechsel(self._uhrzeit(),
                                     self._werte.get("nacht_von") or STANDARD_NACHT_VON,
                                     self._werte.get("nacht_bis") or STANDARD_NACHT_BIS)
            neu["helligkeit_jetzt"] = geprueft
            neu["helligkeit_jetzt_bis"] = int(time.time()) + int(rest)
            neu["helligkeit_jetzt_zone"] = jetzt_zone
            try:
                self._schreiben(neu)
            except OSError as exc:
                return (False, f"nicht schreibbar: {exc}")
            self._werte = neu
            return (True, f"Helligkeit jetzt ({jetzt_zone}) = {geprueft}, "
                          f"gilt bis {self._wechsel_um()}")
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

    def get_display(self) -> dict:
        """Helligkeit und Nachtfenster in der Form, die der Renderer liest.

        ``_apply_brightness`` fragt genau diese Schlüssel (``auto_dim``,
        ``brightness_day``, ``brightness_night``, ``night_mode_start``,
        ``night_mode_end``) — hier entsteht keine zweite Rechnung, nur die
        Ablage davor.
        """
        disp = {
            "auto_dim": bool(self._werte.get("nacht_dimmen")),
            "brightness_day": int(self._werte.get("helligkeit_tag")
                                  or STANDARD_HELLIGKEIT_TAG),
            "brightness_night": int(self._werte.get("helligkeit_nacht")
                                    or STANDARD_HELLIGKEIT_NACHT),
            "night_mode_start": self._werte.get("nacht_von") or STANDARD_NACHT_VON,
            "night_mode_end": self._werte.get("nacht_bis") or STANDARD_NACHT_BIS,
        }
        # Die **vorübergehende** Helligkeit der aktuellen Zone (Regel
        # „Einstellungen am Gerät"). Sie ersetzt nur den Wert der Zone, in der
        # sie gesetzt wurde, und nur bis zum nächsten Wechsel — danach gilt
        # wieder die eingestellte Dimmstufe. Kein Schalter in der Oberfläche
        # muss daran denken: der Renderer fragt `get_display()` je Bild.
        jetzt = self._jetzt_zone()
        override = self._ueberlagerung(jetzt)
        if override is not None:
            if jetzt == "nacht":
                disp["brightness_night"] = override
            else:
                disp["brightness_day"] = override
        return disp

    # --- Vorübergehende Helligkeit --------------------------------------

    @staticmethod
    def _uhrzeit(wann=None) -> str:
        """Ortszeit als ``HH:MM`` (Tests setzen sie über ``wann``)."""
        if wann is None:
            import time
            wann = time.localtime()
        return f"{wann.tm_hour:02d}:{wann.tm_min:02d}"

    def _jetzt_zone(self, wann=None) -> str:
        """In welcher Zone schaltet die Helligkeit **gerade**?

        Ohne Nachtfenster (`nacht_dimmen` aus) gilt immer die Tag-Helligkeit —
        genau wie im Renderer (`if auto_dim and is_night`).
        """
        if not self._werte.get("nacht_dimmen"):
            return "tag"
        return zone(self._uhrzeit(wann),
                    self._werte.get("nacht_von") or STANDARD_NACHT_VON,
                    self._werte.get("nacht_bis") or STANDARD_NACHT_BIS)

    def _wechsel_um(self) -> str:
        """Uhrzeit des nächsten Zonenwechsels als ``HH:MM`` (für die Seite)."""
        jetzt = self._uhrzeit()
        von = self._werte.get("nacht_von") or STANDARD_NACHT_VON
        bis = self._werte.get("nacht_bis") or STANDARD_NACHT_BIS
        jetzt_min = _minuten(jetzt)
        naechste = None
        for grenze in (von, bis):
            rest = (_minuten(grenze) - jetzt_min) % (24 * 60)
            rest = rest or 24 * 60
            if naechste is None or rest < naechste[0]:
                naechste = (rest, grenze)
        return naechste[1] if naechste else bis

    def _ueberlagerung(self, jetzt_zone: str, jetzt_s: float | None = None) -> int | None:
        """Gilt die vorübergehende Helligkeit? Dann ihren Wert, sonst ``None``."""
        wert = self._werte.get("helligkeit_jetzt")
        if wert is None or wert == "zurueck":
            return None
        if self._werte.get("helligkeit_jetzt_zone") != jetzt_zone:
            return None
        bis = self._werte.get("helligkeit_jetzt_bis") or 0
        if jetzt_s is None:
            import time
            jetzt_s = time.time()
        return int(wert) if jetzt_s < float(bis) else None

    # --- Was die Weboberfläche liest ------------------------------------

    def als_json(self) -> dict:
        """Die Werte plus das, was die Seite zum Anzeigen braucht."""
        return {
            "frisur": self.get_hair_style(),
            "farbe": self._werte.get("farbe") or STANDARD_FARBE,
            "kontrast": self.get_contrast(),
            "helligkeit_tag": int(self._werte.get("helligkeit_tag")
                                  or STANDARD_HELLIGKEIT_TAG),
            "helligkeit_nacht": int(self._werte.get("helligkeit_nacht")
                                    or STANDARD_HELLIGKEIT_NACHT),
            "nacht_von": self._werte.get("nacht_von") or STANDARD_NACHT_VON,
            "nacht_bis": self._werte.get("nacht_bis") or STANDARD_NACHT_BIS,
            "nacht_dimmen": bool(self._werte.get("nacht_dimmen")),
            # Wohin die Seite einen Helligkeitsregler gerade schaltet: die
            # aktuelle Zone, der nächste Wechsel und ob eine vorübergehende
            # Helligkeit gilt (Regel „Einstellungen am Gerät").
            "zone": self._jetzt_zone(),
            "wechsel_um": self._wechsel_um(),
            "helligkeit_jetzt": (self._werte.get("helligkeit_jetzt")
                                 if isinstance(self._werte.get("helligkeit_jetzt"), int)
                                 else None),
            "helligkeit_jetzt_gilt": self._ueberlagerung(self._jetzt_zone()) is not None,
            "gilt_bis": int(self._werte.get("helligkeit_jetzt_bis") or 0),
            "frisuren": list(FRISUREN),
            "kontrast_max": KONTRAST_MAX,
            "vorschau_sekunden": VORSCHAU_SEKUNDEN,
            "pfad": str(self.pfad),
            "hinweise": list(self._hinweise),
        }
