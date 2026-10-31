"""Die Sitzungsablage (Regel 8d): der Verlauf liegt auf der Platte.

Aufbau unter ``<wurzel>``::

    haupt                    Zeiger: Name der aktiven Sitzung (atomar ersetzt)
    sitzungen/<id>/verlauf.jsonl
    archiv/<id>.tar.gz

Ein Satz an Sitzungen: ``aktiv`` und ``alt``. Beim Wechsel wird ``alt`` zu
einem Archiv, ``aktiv`` wird ``alt``, die neue wird ``aktiv``. Archive über
3 Tage werden gelöscht. Gelöscht wird erst, was sich wieder auspacken lässt.

``verlauf.jsonl`` ist nur-anhängend. Ein Eintrag ist eine Nachricht
(``{"art":"nachricht","rolle":..,"inhalt":..}``), eine Verdichtung
(``{"art":"verdichtet","zusammenfassung":..,"behalte":N}``) oder ein Leeren
(``{"art":"leer"}``). Nichts wird überschrieben; das Fenster entsteht beim
Laden durch Abspielen. So bleibt der volle Verlauf erhalten, auch wenn das
Fenster des Modells längst verdichtet ist.

Hinweis: Regel 14 sieht für die Ablage Rust vor. Die Schnittstelle
(``anhaengen``, ``laden``, ``wechseln``, ``aufraeumen``, ``lesen``) ist so
klein gehalten, dass sie dorthin umziehen kann.
"""

from __future__ import annotations

import json
import logging
import os
import re
import shutil
import tarfile
import threading
import time
import uuid
from pathlib import Path

log = logging.getLogger(__name__)

#: Archive werden nach so vielen Sekunden gelöscht (3 Tage).
ARCHIV_TTL = 3 * 24 * 3600
_ID = re.compile(r"^[A-Za-z0-9._-]{1,64}$")
MARKE = "[Bisheriges Gespräch]"

class AblageFehler(Exception):
    pass

def _atomar(pfad: Path, text: str) -> None:
    """Über eine Nebendatei schreiben und umbenennen (GLOBAL: nie in place)."""
    tmp = pfad.with_name(pfad.name + ".neu")
    tmp.write_text(text, encoding="utf-8")
    with open(tmp, "rb") as f:
        os.fsync(f.fileno())
    os.replace(tmp, pfad)

def abspielen(eintraege: list[dict]) -> list[dict]:
    """Aus dem Protokoll das Fenster bauen, wie der Agent es zuletzt hatte."""
    fenster: list[dict] = []
    for e in eintraege:
        art = e.get("art")
        if art == "nachricht":
            fenster.append({"role": e["rolle"], "content": e["inhalt"]})
        elif art == "leer":
            fenster = []
        elif art == "verdichtet":
            n = int(e.get("behalte", 0))
            rest = fenster[-n:] if n > 0 else []
            z = e.get("zusammenfassung") or ""
            fenster = ([{"role": "user", "content": f"{MARKE}\n{z}"}] if z else []) + rest
    return fenster

class Ablage:
    def __init__(self, wurzel: str | Path, jetzt=time.time) -> None:
        self.wurzel = Path(wurzel)
        self._jetzt = jetzt
        self._lock = threading.RLock()
        (self.wurzel / "sitzungen").mkdir(parents=True, exist_ok=True)
        (self.wurzel / "archiv").mkdir(exist_ok=True)

    # --- Zeiger -----------------------------------------------------------

    def _dir(self, sid: str) -> Path:
        if not _ID.match(sid or ""):
            raise AblageFehler(f"ungültige Sitzungs-ID {sid!r}")
        return self.wurzel / "sitzungen" / sid

    def aktiv(self) -> str:
        """Name der Hauptsitzung; legt beim ersten Aufruf eine an."""
        with self._lock:
            z = self.wurzel / "haupt"
            try:
                sid = z.read_text(encoding="utf-8").strip()
            except FileNotFoundError:
                sid = ""
            if sid and self._dir(sid).is_dir():
                return sid
            sid = self._neue_id()
            self._dir(sid).mkdir(parents=True)
            _atomar(z, sid + "\n")
            return sid

    def alt(self) -> str | None:
        with self._lock:
            z = self.wurzel / "alt"
            try:
                sid = z.read_text(encoding="utf-8").strip()
            except FileNotFoundError:
                return None
            return sid if sid and self._dir(sid).is_dir() else None

    def _neue_id(self) -> str:
        return time.strftime("%Y%m%d-%H%M%S", time.localtime(self._jetzt())) \
            + "-" + uuid.uuid4().hex[:6]

    def schreibbar(self, sid: str) -> bool:
        """Nur die Hauptsitzung nimmt Eingaben an (Regel 5s)."""
        return sid == self.aktiv()

    # --- Schreiben und Lesen ----------------------------------------------

    def anhaengen(self, eintrag: dict, sid: str | None = None) -> None:
        with self._lock:
            sid = sid or self.aktiv()
            if sid != self.aktiv():
                raise AblageFehler(f"{sid} ist nur lesbar")
            eintrag = dict(eintrag, zeit=round(self._jetzt(), 3))
            zeile = json.dumps(eintrag, ensure_ascii=False) + "\n"
            with open(self._dir(sid) / "verlauf.jsonl", "a", encoding="utf-8") as f:
                f.write(zeile)
                f.flush()
                os.fsync(f.fileno())

    def lesen(self, sid: str) -> list[dict]:
        """Das volle Protokoll einer Sitzung, auch einer alten (nur lesen)."""
        d = self._dir(sid)
        pfad = d / "verlauf.jsonl"
        if not pfad.exists():
            arch = self.wurzel / "archiv" / f"{sid}.tar.gz"
            if arch.exists():
                with tarfile.open(arch) as t:
                    m = t.extractfile(f"{sid}/verlauf.jsonl")
                    return self._zeilen(m.read().decode("utf-8").splitlines()) if m else []
            return []
        return self._zeilen(pfad.read_text(encoding="utf-8").splitlines())

    @staticmethod
    def _zeilen(zeilen: list[str]) -> list[dict]:
        out = []
        for z in zeilen:
            if not z.strip():
                continue
            try:
                out.append(json.loads(z))
            except ValueError:
                # Halb geschriebene letzte Zeile nach einem Absturz: überspringen
                # und melden, nicht den ganzen Verlauf verwerfen.
                log.warning("Verlaufszeile unlesbar, übersprungen")
        return out

    def laden(self) -> list[dict]:
        """Das Fenster der Hauptsitzung (abgespielt)."""
        return abspielen(self.lesen(self.aktiv()))

    def sitzungen(self) -> dict:
        arch = sorted(p.name[:-7] for p in (self.wurzel / "archiv").glob("*.tar.gz"))
        return {"haupt": self.aktiv(), "alt": self.alt(), "archiv": arch}

    # --- Wechsel ----------------------------------------------------------

    def wechseln(self, uebergabe: str) -> str:
        """Neue Hauptsitzung, beginnend mit der Übergabe. Gibt die neue ID zurück.

        Reihenfolge: erst die neue Sitzung samt Übergabe fertig auf die
        Platte, dann der Zeiger (atomar), dann erst das Aufräumen der alten.
        Bricht es dazwischen ab, zeigt ``haupt`` auf eine vollständige Sitzung.
        """
        with self._lock:
            alte_alt = self.alt()
            vorher = self.aktiv()
            neu = self._neue_id()
            d = self._dir(neu)
            d.mkdir(parents=True)
            if uebergabe.strip():
                with open(d / "verlauf.jsonl", "w", encoding="utf-8") as f:
                    f.write(json.dumps({"art": "nachricht", "rolle": "user",
                                        "inhalt": uebergabe, "quelle": "uebergabe",
                                        "zeit": round(self._jetzt(), 3)},
                                       ensure_ascii=False) + "\n")
                    f.flush()
                    os.fsync(f.fileno())
            _atomar(self.wurzel / "alt", vorher + "\n")
            _atomar(self.wurzel / "haupt", neu + "\n")
            if alte_alt and alte_alt not in (vorher, neu):
                self._archivieren(alte_alt)
            self.aufraeumen()
            return neu

    def _archivieren(self, sid: str) -> None:
        d = self._dir(sid)
        ziel = self.wurzel / "archiv" / f"{sid}.tar.gz"
        tmp = ziel.with_name(ziel.name + ".neu")
        n = sum(1 for p in d.rglob("*") if p.is_file())
        with tarfile.open(tmp, "w:gz") as t:
            t.add(d, arcname=sid)
        # Prüfung vor dem Löschen: auspackbar, Zahl der Dateien stimmt.
        with tarfile.open(tmp) as t:
            namen = [m for m in t.getmembers() if m.isfile()]
            for m in namen:
                t.extractfile(m).read()
        if len(namen) != n:
            tmp.unlink()
            raise AblageFehler(f"Archiv {sid}: {len(namen)} von {n} Dateien")
        os.replace(tmp, ziel)
        shutil.rmtree(d)

    def aufraeumen(self) -> list[str]:
        """Archive löschen, die älter als 3 Tage sind. Gibt die Namen zurück."""
        weg = []
        grenze = self._jetzt() - ARCHIV_TTL
        with self._lock:
            for p in (self.wurzel / "archiv").glob("*.tar.gz"):
                if p.stat().st_mtime < grenze:
                    p.unlink()
                    weg.append(p.name[:-7])
        return weg

class Verlauf(list):
    """Eine Liste, die jede neue Nachricht in die Ablage schreibt.

    Der Agent hängt an, ohne es zu wissen. Nur ``append`` schreibt; wer das
    Fenster ersetzt (Verdichten), geht über ``Agent.history = ...``.
    """

    def __init__(self, ablage: Ablage, start=()):
        super().__init__(start)
        self.ablage = ablage

    def append(self, m: dict) -> None:
        self.ablage.anhaengen({"art": "nachricht", "rolle": m["role"],
                               "inhalt": m["content"]})
        super().append(m)

    def clear(self) -> None:
        self.ablage.anhaengen({"art": "leer"})
        super().clear()

    def verdichten(self, zusammenfassung: str, behalte: int) -> None:
        """Fenster verdichten; das Protokoll behält alles (Regel 8d)."""
        self.ablage.anhaengen({"art": "verdichtet",
                               "zusammenfassung": zusammenfassung,
                               "behalte": behalte})
        rest = list(self)[-behalte:] if behalte > 0 else []
        neu = ([{"role": "user", "content": f"{MARKE}\n{zusammenfassung}"}]
               if zusammenfassung else []) + rest
        list.__setitem__(self, slice(None), neu)
