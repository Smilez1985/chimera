"""Ein Feld im Statusbereich — die kleinste Einheit, die etwas anzeigt.

Ein Feld bekommt ein **Band** (obere Zeile, Höhe) und zeichnet nur darin.
Damit ist Überlagerung nicht „unwahrscheinlich", sondern nicht darstellbar:
Die Bänder vergibt :mod:`chimera.display.layout`, ein Feld sieht fremde
Zeilen nie (Regel „Anzeigefelder").

Was ein Feld zeigt, entscheidet das Feld. Hier steht nur, was **jedes** Feld
mitbringt: Namen, Höhenwunsch, Priorität und ein Zeichenweg, der den Text
anpasst statt ihn abzuschneiden (Schriftgröße aus der Bandhöhe, dann
„…" oder Umbruch).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

__all__ = ["Feld", "Flaeche", "AUSRICHTUNGEN"]

#: links / mitte / rechts — mehr braucht es nicht, und was es nicht gibt,
#: kann auch nicht auseinanderlaufen.
AUSRICHTUNGEN = ("links", "mitte", "rechts")


def _schrift_pfade():
    """Erst fett, dann normal — an beiden Stellen, an denen DejaVu liegt.

    ``/usr/share/fonts/truetype/dejavu`` ist der Debian-/DietPi-Pfad (das
    Zielgerät), ``/usr/share/fonts/dejavu`` der Alpine-Pfad (Sandkasten und
    Testläufe). Fehlt beides, nimmt Pillow seine eingebaute Schrift -- dann
    fehlen Sonderzeichen (ß, Gedankenstrich), und das sieht man im Bild.
    """
    for verzeichnis in ("/usr/share/fonts/truetype/dejavu",
                        "/usr/share/fonts/dejavu"):
        for datei in ("DejaVuSans-Bold.ttf", "DejaVuSans.ttf"):
            yield f"{verzeichnis}/{datei}"


class Flaeche:
    """Ein Band, in das ein Feld zeichnet. Kennt nur seine eigene Größe.

    Die Klasse kapselt die zwei Dinge, die jedes Feld sonst falsch machen
    würde: die Schriftgröße aus der Höhe ableiten und den Text passend
    machen (kürzen mit „…" oder umbrechen). Wer ``text()`` benutzt, kann
    nicht versehentlich über den Rand schreiben.
    """

    def __init__(self, bild, oben: int, hoehe: int, *, rand: int = 2):
        self.bild = bild
        self.oben = int(oben)
        self.hoehe = max(1, int(hoehe))
        self.breite = bild.size[0]
        self.rand = rand
        self._schriften: dict[int, object] = {}

    # --- Schrift ---------------------------------------------------------

    def schrift(self, groesse: int):
        groesse = max(6, int(groesse))
        if groesse not in self._schriften:
            self._schriften[groesse] = self._laden(groesse)
        return self._schriften[groesse]

    @staticmethod
    def _laden(groesse: int):
        try:
            from PIL import ImageFont
        except ImportError:
            return None
        for pfad in _schrift_pfade():
            try:
                return ImageFont.truetype(pfad, groesse)
            except OSError:
                continue
        try:
            return ImageFont.load_default(size=groesse)
        except TypeError:                      # Pillow < 10.1
            return ImageFont.load_default()

    def groesse_fuer(self, zeilen: int = 1, anteil: float = 0.62) -> int:
        """Schriftgröße, die in ``zeilen`` Zeilen dieses Bandes passt."""
        return max(6, int(self.hoehe * anteil / max(1, zeilen)))

    def _breite(self, text: str, schrift) -> int:
        try:
            from PIL import ImageDraw
            zeichner = ImageDraw.Draw(self.bild)
            links, _, rechts, _ = zeichner.textbbox((0, 0), text, font=schrift)
            return rechts - links
        except Exception:                      # noqa: BLE001 -- ohne Pillow egal
            return len(text) * 6

    def kuerzen(self, text: str, schrift, *, platz: int | None = None) -> str:
        """Text auf die Breite bringen — mit „…", nie mitten im Buchstaben.

        Gekürzt wird **einmal** berechnet und dann zurückgegeben; wer den
        Rückgabewert nicht benutzt, schreibt über den Rand. Deshalb gibt es
        keine Variante, die still kürzt.
        """
        platz = self.breite - 2 * self.rand if platz is None else platz
        if self._breite(text, schrift) <= platz:
            return text
        punkte = "…"
        if self._breite(punkte, schrift) > platz:
            return ""                          # nicht einmal die Punkte passen
        klein, gross = 0, len(text)
        while klein < gross:
            mitte = (klein + gross + 1) // 2
            if self._breite(text[:mitte] + punkte, schrift) <= platz:
                klein = mitte
            else:
                gross = mitte - 1
        return text[:klein].rstrip() + punkte

    def umbrechen(self, text: str, schrift, *, zeilen: int = 2) -> list[str]:
        """Text auf höchstens ``zeilen`` Zeilen verteilen; die letzte kürzt.

        Getrennt wird an Leerzeichen (das Panel zeigt keine Silbentrennung);
        ein Wort, das allein zu breit ist, wird gekürzt statt über den Rand
        geschrieben.
        """
        platz = self.breite - 2 * self.rand
        if self._breite(text, schrift) <= platz or zeilen <= 1:
            return [self.kuerzen(text, schrift)]
        woerter = text.split()
        zeilen_liste: list[str] = []
        rest = ""
        for wort in woerter:
            versuch = (rest + " " + wort).strip()
            if self._breite(versuch, schrift) <= platz:
                rest = versuch
                continue
            if rest:
                zeilen_liste.append(rest)
            rest = wort
            if len(zeilen_liste) == zeilen - 1:
                break
        if rest:
            zeilen_liste.append(rest)
        zeilen_liste = zeilen_liste[:zeilen]
        # Ist etwas übrig geblieben, sagt die letzte Zeile es — sonst
        # verschwände der Rest stumm.
        if len(zeilen_liste) == zeilen and " ".join(zeilen_liste) != " ".join(woerter):
            zeilen_liste[-1] = self.kuerzen(zeilen_liste[-1] + " …", schrift)
        return [self.kuerzen(z, schrift) for z in zeilen_liste]

    # --- Zeichnen --------------------------------------------------------

    def hintergrund(self, farbe) -> None:
        if farbe is None:
            return
        from PIL import ImageDraw

        ImageDraw.Draw(self.bild).rectangle(
            [0, self.oben, self.breite, self.oben + self.hoehe], fill=tuple(farbe))

    def text(self, text: str, *, groesse: int, farbe=(230, 230, 230),
             ausrichtung: str = "mitte", zeilen: int = 1) -> None:
        """Text setzen — gekürzt bzw. umgebrochen, nie über den Rand hinaus."""
        if ausrichtung not in AUSRICHTUNGEN:
            raise ValueError(f"unbekannte Ausrichtung {ausrichtung!r} "
                             f"(bekannt: {', '.join(AUSRICHTUNGEN)})")
        try:
            from PIL import ImageDraw
        except ImportError:
            return
        schrift = self.schrift(groesse)
        if schrift is None:
            return
        zeichner = ImageDraw.Draw(self.bild)
        liste = self.umbrechen(text, schrift, zeilen=zeilen) if zeilen > 1 \
            else [self.kuerzen(text, schrift)]
        zeilen_hoehe = max(1, self.hoehe // max(1, len(liste)))
        for i, zeile in enumerate(liste):
            if not zeile:
                continue
            try:
                links, ob, rechts, un = zeichner.textbbox((0, 0), zeile, font=schrift)
            except Exception:                  # noqa: BLE001
                links = ob = rechts = un = 0
            breite = rechts - links
            if ausrichtung == "links":
                x = self.rand
            elif ausrichtung == "rechts":
                x = self.breite - self.rand - breite
            else:
                x = max(self.rand, (self.breite - breite) // 2)
            # Pillow setzt am **Ascender** an; `ob` kann positiv sein. Ohne
            # das Abziehen steht ein Teil der Glyphen über dem Band -- und
            # bei der letzten Zeile unter dem Bildrand (am Gerät gesehen).
            band_oben = self.oben + i * zeilen_hoehe
            band_unten = band_oben + zeilen_hoehe
            y = band_oben + max(0, (zeilen_hoehe - (un - ob)) // 2)
            y = min(max(band_oben, y), max(band_oben, band_unten - (un - ob)))
            zeichner.text((x - links, y - ob), zeile, fill=tuple(farbe), font=schrift)


@dataclass(frozen=True)
class Feld:
    """Was ein Feld ausmacht. ``zeichnen`` bekommt das Band und den Kontext.

    ``wunsch`` und ``mindestens`` sind Zeilen (Pixel). ``prioritaet``
    entscheidet, wer beim Kürzen zuerst verliert — **kleinere Zahl zuerst**
    (dieselbe Richtung wie in :mod:`chimera.arbiter`).
    """

    name: str
    titel: str
    wunsch: int
    mindestens: int
    prioritaet: int
    zeichnen: Callable[[Flaeche, dict], None]
    ausrichtung: str = "mitte"
    farbe: tuple[int, int, int] = (230, 230, 230)
    hintergrund: tuple[int, int, int] | None = None
    #: Nur zur Anzeige/Prüfung: was dieses Feld braucht. Ein Feld ohne
    #: Quelle zeichnet nichts und kostet kein Band (siehe layout).
    sichtbar: Callable[[dict], bool] = field(default=lambda _k: True)
