"""Anzeigespiegel — das fertige Bild für die Web-Oberfläche veröffentlichen.

Entwurf: DESIGN, Regel „Anzeigespiegel". Der Renderer rechnet **nichts** nach:
``to_rgb565()`` ist für das Panel ohnehin gelaufen, der Puffer liegt im
Panel bereit (``Panel.bild_bytes``). Dieses Modul schreibt ihn an einen Ort,
aus dem das Gateway lesen darf.

Drei Zusagen, an denen alles andere hängt:

1. **Nie ein halbes Bild.** Geschrieben wird nach ``bild.neu``, dann per
   ``os.replace`` umbenannt. Ein Leser sieht entweder das alte oder das neue
   Bild — auch dann, wenn er die Datei öffnet, während schon das nächste
   Bild entsteht (er hält dann einen vollständigen älteren Stand).
2. **Der Zähler steht im Kopf, nicht in der Zeit.** Die Geräteuhr ist
   unzuverlässig (Regel 7d); ein monotoner Zähler ist vergleichbar, und das
   Gateway antwortet damit „unverändert" ohne ein einziges Pixel zu lesen.
3. **Fehler werden einmal gesagt, nicht im Bildtakt.** Ein fehlendes
   Verzeichnis ist ein Defekt, kein Rauschen (Regel 8a) — aber 15-mal je
   Sekunde ins Protokoll zu schreiben macht die Logdatei unlesbar.
"""

from __future__ import annotations

import logging
import os
import struct
from pathlib import Path

log = logging.getLogger(__name__)

#: Kennung im Kopf. Ein Leser, der sie nicht findet, liefert kein Bild
#: (Regel 10g: nicht raten, was in der Datei steht).
MAGIC = b"CHSP"
VERSION = 1

#: Bildformate im Kopf. Nur was hier steht, darf ein Leser deuten.
FORMAT_RGB565_BE = 1

#: 4 Kennung + 1 Fassung + 1 Format + 2 Breite + 2 Höhe + 2 Reserve
#: + 8 Zähler + 12 Reserve. Fest, damit Gateway und Renderer nicht
#: auseinanderlaufen können.
KOPF_LAENGE = 32

#: Wohin veröffentlicht wird. ``/run`` ist tmpfs: 134 KB je Bild bei 15
#: Bildern/s wären auf einer SD-Karte Gift, im Arbeitsspeicher sind sie
#: nichts. Der Pfad ist übersteuerbar, damit Tests nicht ins echte
#: Verzeichnis schreiben.
STANDARD_PFAD = Path("/run/chimera/anzeige/bild")


def kopf_bauen(breite: int, hoehe: int, zaehler: int,
               format: int = FORMAT_RGB565_BE) -> bytes:
    """Der 32-Byte-Kopf vor den Pixeln. Big-Endian, wie der Panelspeicher."""
    return struct.pack(">4sBBHHHQ12x", MAGIC, VERSION, format,
                       int(breite), int(hoehe), 0, int(zaehler))


def kopf_lesen(daten: bytes) -> dict | None:
    """Kopf deuten — ``None``, wenn er nicht passt. Prüft die Länge mit."""
    if len(daten) < KOPF_LAENGE:
        return None
    magic, fassung, format, breite, hoehe, _, zaehler = struct.unpack(
        ">4sBBHHHQ", daten[:20])
    if magic != MAGIC or fassung != VERSION:
        return None
    return {"format": format, "breite": breite, "hoehe": hoehe,
            "zaehler": zaehler}


class Spiegel:
    """Veröffentlicht das zuletzt gezeigte Bild, wenn es sich geändert hat.

    ``zeige()`` gibt ``True`` zurück, wenn wirklich geschrieben wurde. Ein
    gleiches Bild wird **nicht** veröffentlicht — der Zähler bleibt dann
    stehen, und das Gateway antwortet dem Browser „unverändert", statt
    134 KB über die Leitung zu schicken.
    """

    def __init__(self, pfad: Path | str | None = None) -> None:
        # ``CHIMERA_SPIEGEL=0`` schaltet den Spiegel ab (Tests, Messungen,
        # und wer keine Datei in /run will).
        aus = os.environ.get("CHIMERA_SPIEGEL", "").strip() == "0"
        self.aktiv = not aus
        self.pfad = Path(pfad or os.environ.get("CHIMERA_SPIEGEL_PFAD")
                         or STANDARD_PFAD)
        self.zaehler = 0
        self.bilder = 0
        self._zuletzt: bytes | None = None
        self._zuletzt_groesse: tuple[int, int] | None = None
        self._verzeichnis_ok = False
        self._fehler: str | None = None

    # ------------------------------------------------------------------
    def zeige(self, bild: bytes | None, breite: int, hoehe: int) -> bool:
        """Ein Bild veröffentlichen. ``False`` heißt: nichts geschrieben."""
        if not self.aktiv or not bild or not breite or not hoehe:
            return False
        erwartet = int(breite) * int(hoehe) * 2
        if len(bild) != erwartet:
            # Kein stilles Zurechtschneiden: Eine falsche Länge heißt, dass
            # Breite/Höhe und Puffer nicht zusammengehören (Regel 8a).
            self._melden(f"Bildgröße passt nicht: {len(bild)} Byte, "
                         f"erwartet {erwartet} für {breite}x{hoehe}")
            return False
        if (bild is self._zuletzt or bild == self._zuletzt) and \
                (breite, hoehe) == self._zuletzt_groesse:
            return False
        self.zaehler += 1
        try:
            self._schreiben(kopf_bauen(breite, hoehe, self.zaehler) + bild)
        except OSError as exc:
            # Der Zähler ist schon hochgezählt — das ist Absicht: der nächste
            # Versuch bekommt eine neue Nummer, ein alter Stand wird nie als
            # „der neueste" ausgegeben.
            self._melden(f"{self.pfad} nicht schreibbar: {exc}")
            return False
        self._zuletzt = bild
        self._zuletzt_groesse = (breite, hoehe)
        self.bilder += 1
        if self._fehler is not None:
            log.warning("Anzeigespiegel schreibt wieder (%s Bilder).",
                        self.bilder)
            self._fehler = None
        return True

    # ------------------------------------------------------------------
    def _schreiben(self, daten: bytes) -> None:
        if not self._verzeichnis_ok:
            self.pfad.parent.mkdir(parents=True, exist_ok=True)
            self._verzeichnis_ok = True
        neu = self.pfad.with_name(self.pfad.name + ".neu")
        with open(neu, "wb") as f:
            f.write(daten)
        # Das Bild ist kein Geheimnis (DESIGN): 0644, damit das Gateway unter
        # seinem eigenen Nutzer lesen darf, ohne dass jemand Gruppen pflegt.
        os.chmod(neu, 0o644)
        os.replace(neu, self.pfad)

    def _melden(self, text: str) -> None:
        if text != self._fehler:
            log.warning("Anzeigespiegel: %s", text)
            self._fehler = text

    def schliessen(self) -> None:
        """Die Datei stehen lassen, aber nichts mehr veröffentlichen.

        Bewusst **kein** Löschen: Ein verschwundenes Bild wäre für die
        Oberfläche nicht von „es gibt keine Anzeige" zu unterscheiden. Der
        Dienst schreibt beim Beenden ein schwarzes Bild (``avatar``), das
        ist der ehrliche Endstand.
        """
        self.aktiv = False
