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
#: Blockgröße beim Rückwärtslesen der ``verlauf.jsonl``. Klein genug, dass
#: eine Seite selten mehr als einen Block liest, groß genug, dass ein langer
#: Verlauf nicht in 1000 Aufrufen gelesen wird.
LESE_BLOCK = 64 * 1024
_ID = re.compile(r"^[A-Za-z0-9._-]{1,64}$")
MARKE = "[Bisheriges Gespräch]"

def _mit_marke(z: str) -> str:
    """Die Marke vor den Text — aber nicht doppelt.

    Seit dem 14.11.2026 bringt der Verdichtungstext seine eigene Marke mit
    (``verdichten.MARKE``, mit Fundstelle). Ein zweites "[Bisheriges
    Gespräch]" davor wäre Lärm und würde beim Nachlesen stören.
    """
    return z if z.startswith("[Bisheriges Gespräch") else f"{MARKE}\n{z}"

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
            m = {"role": e["rolle"], "content": e["inhalt"]}
            # Werkzeugkennung und Denktext gehoeren zum Verlauf, nicht nur
            # ins Protokoll (15.11.2026): Ohne sie verliert ein Neustart die
            # Verbindung zwischen Aufruf und Ergebnis — und DeepSeek im
            # Denkmodus verlangt den Denktext frueherer Runden zurueck.
            if e.get("werkzeug"):
                m["tool_name"] = e["werkzeug"]
            if e.get("gedacht"):
                m["gedacht"] = e["gedacht"]
            if e.get("werkzeuge"):
                m["tool_calls"] = [
                    {"function": {"name": str(w.get("name") or ""),
                                  "arguments": w.get("argumente") or {}}}
                    for w in e["werkzeuge"] if isinstance(w, dict)]
            fenster.append(m)
        elif art == "leer":
            fenster = []
        elif art == "verdichtet":
            n = int(e.get("behalte", 0))
            rest = fenster[-n:] if n > 0 else []
            z = e.get("zusammenfassung") or ""
            fenster = ([{"role": "user", "content": _mit_marke(z)}] if z else []) + rest
    return fenster_bereinigen(_aufrufe_paaren(fenster))

#: Ein Textaufruf, wie ihn der Textweg schrieb (``TOOL: name {json}``). Er
#: wird im Fenster entfernt: ein Verlauf aus der Textzeit lehrt genau den Weg,
#: den die Schnittstelle verbietet (DESIGN, Regel „Aufrufe, nicht Text",
#: Nachtrag 15.11.2026).
TEXT_AUFRUF = re.compile(r"^\s*TOOL:\s*[a-z_]+\s*\{.*$", re.MULTILINE | re.DOTALL)

#: Das Ergebnis, das der Textweg zu einem Aufruf zurückgab.
TEXT_ERGEBNIS = re.compile(r"^\s*Ergebnis von\s+[A-Za-z0-9_.]+\s*:", re.UNICODE)

def _aufrufe_paaren(fenster: list[dict]) -> list[dict]:
    """Nur Aufrufe behalten, deren Ergebnisse **alle** im Fenster stehen.

    Ein Turn kann mitten im Werkzeugaufruf geendet haben (Absturz, Neustart);
    dann fehlt zu einem Aufruf das Ergebnis. Eine solche Nachricht ist keine
    Wahrheit mehr, und die Schnittstelle weist sie ab ("tool_calls ohne
    tool response"). Der Text bleibt, die Aufrufe gehen.
    """
    raus: list[dict] = []
    for i, m in enumerate(fenster):
        aufrufe = m.get("tool_calls")
        if not aufrufe:
            raus.append(m)
            continue
        ergebnisse = 0
        for folge in fenster[i + 1:]:
            if folge.get("role") != "tool":
                break
            ergebnisse += 1
        if ergebnisse >= len(aufrufe):
            raus.append(m)
        else:
            ohne = {k: v for k, v in m.items() if k != "tool_calls"}
            log.info("Verlauf: %d Aufruf(e) ohne Ergebnis verworfen.", len(aufrufe))
            raus.append(ohne)
    # Verwaiste Ergebnisse (tool ohne Aufruf davor) bleiben -- der Gateway
    # macht daraus eine Nutzernachricht (Regel „Aufrufe, nicht Text").
    return raus

def fenster_bereinigen(fenster: list[dict]) -> list[dict]:
    """Textaufrufe und ihre Ergebnisse aus dem Fenster nehmen.

    Das **Protokoll** bleibt unangetastet (Regel 8d) — hier entsteht nur das,
    was das Modell sieht. Ohne diese Bereinigung kopiert ein starkes Modell
    seine eigene Vergangenheit und schreibt weiter `TOOL:` in den Text, statt
    die Werkzeugschnittstelle zu benutzen (am Pi gemessen, 15.11.2026:
    26 solche Zeilen im Verlauf, die Rüge half genau eine Runde).
    """
    sauber: list[dict] = []
    getilgt = 0
    for m in fenster:
        rolle = m.get("role")
        inhalt = m.get("content") or ""
        if rolle != "assistant" and TEXT_ERGEBNIS.match(inhalt):
            getilgt += 1                    # gehört zu einem Aufruf, der geht
            continue
        if rolle == "assistant" and TEXT_AUFRUF.search(inhalt):
            rest = TEXT_AUFRUF.sub("", inhalt).strip()
            getilgt += 1
            if rest:
                sauber.append({**m, "content": rest})
            continue
        sauber.append(m)
    if getilgt:
        log.info("Fenster bereinigt: %d Textaufruf-Nachrichten aus der "
                 "Textzeit entfernt (Protokoll unveraendert).", getilgt)
    return sauber

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

    # --- Ein Stück statt allem (14.11.2026) --------------------------------
    #
    # Die Oberfläche holt Seiten: ``vor=0`` sind die letzten ``max``
    # Einträge, ``vor=50`` die 50 davor. Bis heute las ``lesen()`` dafür die
    # **ganze** ``verlauf.jsonl`` und parste jede Zeile, nur um danach zu
    # schneiden (``sitzung_socket.seite``). Auf einem Gerät mit 462 MB ist
    # das je Abruf ein vollständiger Verlauf im Speicher — bei einem langen
    # Verlauf der größte Einzelposten des Dienstes.
    #
    # Deshalb zwei Zugänge, beide ohne Liste aller Einträge:
    # ``lesen_seite`` liest **rückwärts** in Blöcken und parst nur, was auf
    # die Seite kommt; ``anzahl`` zählt Zeilen, ohne ein einziges Dict zu
    # bauen. ``lesen()`` bleibt für die Fälle, die wirklich alles brauchen
    # (Export, Übergabe, Abspielen des Fensters).

    def _quelle(self, sid: str) -> tuple[Path | None, Path | None]:
        """(Verlaufsdatei, Archiv) — die Datei hat Vorrang."""
        d = self._dir(sid)
        pfad = d / "verlauf.jsonl"
        if pfad.exists():
            return pfad, None
        arch = self.wurzel / "archiv" / f"{sid}.tar.gz"
        return None, (arch if arch.exists() else None)

    @staticmethod
    def _eine(zeile: bytes) -> dict | None:
        """Eine Zeile zu einem Eintrag. Halbe Zeile nach Absturz: melden."""
        try:
            return json.loads(zeile.decode("utf-8"))
        except ValueError:
            log.warning("Verlaufszeile unlesbar, übersprungen")
            return None

    def anzahl(self, sid: str) -> int:
        """Wie viele Einträge im Protokoll stehen — ohne sie zu erzeugen."""
        pfad, arch = self._quelle(sid)
        if pfad is None:
            if arch is None:
                return 0
            with tarfile.open(arch) as t:
                m = t.extractfile(f"{sid}/verlauf.jsonl")
                if m is None:
                    return 0
                return sum(1 for z in m if z.strip())
        n = 0
        with open(pfad, "rb") as f:
            for zeile in f:
                if zeile.strip():
                    n += 1
        return n

    # --- Zeilenweise, für Verdichten und Nachlesen (14.11.2026) ------------
    #
    # „Verdichten mit Verweis" (DESIGN 8d) braucht **Zeilennummern** statt
    # Nachrichten-Zählungen: Der Agent bekommt ins Fenster die Fundstelle,
    # und das Werkzeug ``nachlesen`` holt genau diese Zeilen zurück. Dafür
    # wird hier nichts eingelesen, was nicht gebraucht wird.

    def nachrichten_zeilen(self, sid: str, anzahl_nachrichten: int,
                           abstand: int = 0) -> tuple[int, int]:
        """Die Zeilenspanne von ``anzahl_nachrichten`` Nachrichten.

        Gezählt wird vom Ende: ``abstand`` Nachrichten werden am Ende
        übersprungen (die bleiben wörtlich im Fenster und gehören nicht in
        den verdichteten Abschnitt). Gibt ``(von, bis)`` zurück; ``(0, 0)``,
        wenn es keine gibt. Nur Zeilen mit ``art == "nachricht"`` zählen —
        die Verdichtungs- und Leer-Einträge stehen dazwischen und
        verschieben sonst den Verweis.
        """
        gesamt = self.anzahl(sid)
        anzahl_nachrichten = int(anzahl_nachrichten)
        abstand = max(0, int(abstand))
        if gesamt <= 0 or anzahl_nachrichten <= 0:
            return (0, 0)
        noetig = anzahl_nachrichten + abstand
        pfad, arch = self._quelle(sid)
        if pfad is None:
            # Archiv: selten und klein — vollständig lesen ist hier billig.
            alle = self.lesen(sid)
            treffer = [i + 1 for i, e in enumerate(alle) if e.get("art") == "nachricht"]
            treffer = treffer[-(anzahl_nachrichten + abstand):]
            treffer = treffer[:anzahl_nachrichten]
            return (treffer[0], treffer[-1]) if treffer else (0, 0)

        nummern: list[int] = []
        nr = gesamt + 1
        with open(pfad, "rb") as f:
            f.seek(0, os.SEEK_END)
            pos = f.tell()
            rest = b""
            while pos > 0 and len(nummern) < noetig:
                n = min(LESE_BLOCK, pos)
                pos -= n
                f.seek(pos)
                stueck = f.read(n) + rest
                zeilen = stueck.split(b"\n")
                rest = zeilen.pop(0)      # angeschnitten: gehört in den Block davor
                for z in reversed(zeilen):
                    if not z.strip():
                        continue
                    nr -= 1
                    e = self._eine(z)
                    if e is not None and e.get("art") == "nachricht":
                        nummern.append(nr)
                        if len(nummern) >= noetig:
                            break
            if len(nummern) < noetig and rest.strip():
                nr -= 1
                e = self._eine(rest)
                if e is not None and e.get("art") == "nachricht":
                    nummern.append(nr)
        if not nummern:
            return (0, 0)
        # ``nummern`` steht von hinten nach vorne; die letzten ``abstand``
        # gehören zum wörtlichen Rest und fallen weg.
        nummern = list(reversed(nummern))[:anzahl_nachrichten]
        return (nummern[0], nummern[-1]) if nummern else (0, 0)

    def lesen_zeilen(self, sid: str, von: int, bis: int) -> list[tuple[int, dict]]:
        """Zeilen ``von``..``bis`` (1-basiert, beide eingeschlossen).

        Liest mit dem Zeileniterator und parst **nur** den gewünschten
        Bereich — die Grundlage für das Werkzeug ``nachlesen``.
        """
        try:
            von = max(1, int(von))
            bis = int(bis)
        except (TypeError, ValueError):
            return []
        if bis < von:
            return []
        pfad, arch = self._quelle(sid)
        if pfad is None:
            if arch is None:
                return []
            with tarfile.open(arch) as t:
                m = t.extractfile(f"{sid}/verlauf.jsonl")
                roh = m.read().splitlines() if m else []
            out = []
            for i, z in enumerate(roh, start=1):
                if von <= i <= bis:
                    e = self._eine(z)
                    if e is not None:
                        out.append((i, e))
            return out
        out: list[tuple[int, dict]] = []
        with open(pfad, "rb") as f:
            for i, z in enumerate(f, start=1):
                if i > bis:
                    break
                if i < von or not z.strip():
                    continue
                e = self._eine(z)
                if e is not None:
                    out.append((i, e))
        return out

    def lesen_seite(self, sid: str, max_n=200, vor=0) -> list[dict]:
        """Ein Stück des Protokolls, von hinten gelesen.

        Gleiche Auswahl wie ``sitzung_socket.seite``: ``vor`` ist der Abstand
        vom **Ende**. Ungültige Werte werden zu Vorgaben, nicht zu Fehlern
        (dieselbe Regel wie dort: ``max`` fällt auf 200, mindestens 1).
        """
        try:
            max_n = max(1, int(max_n if max_n is not None else 200))
        except (TypeError, ValueError):
            max_n = 200
        try:
            vor = max(0, int(vor if vor is not None else 0))
        except (TypeError, ValueError):
            vor = 0

        pfad, arch = self._quelle(sid)
        if pfad is None:
            if arch is None:
                return []
            # Ein Archiv ist eine alte, abgelegte Sitzung: selten und klein.
            with tarfile.open(arch) as t:
                m = t.extractfile(f"{sid}/verlauf.jsonl")
                alle = self._zeilen(m.read().decode("utf-8").splitlines()) if m else []
            return alle[max(0, len(alle) - vor - max_n):max(0, len(alle) - vor)]

        noetig = max_n + vor
        gefunden: list[dict] = []
        with open(pfad, "rb") as f:
            f.seek(0, os.SEEK_END)
            pos = f.tell()
            rest = b""
            while pos > 0 and len(gefunden) < noetig:
                n = min(LESE_BLOCK, pos)
                pos -= n
                f.seek(pos)
                stueck = f.read(n) + rest
                zeilen = stueck.split(b"\n")
                # Die erste Zeile eines Blocks kann vorne angeschnitten sein;
                # sie gehört in den nächsten (früheren) Block.
                rest = zeilen.pop(0)
                for z in reversed(zeilen):
                    if not z.strip():
                        continue
                    e = self._eine(z)
                    if e is not None:
                        gefunden.append(e)
                    if len(gefunden) >= noetig:
                        break
            # Die allererste Zeile der Datei hat keinen Block mehr vor sich.
            if len(gefunden) < noetig and rest.strip():
                e = self._eine(rest)
                if e is not None:
                    gefunden.append(e)
        gefunden.reverse()
        ende = max(0, len(gefunden) - vor)
        anfang = max(0, ende - max_n)
        return gefunden[anfang:ende]

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

    def __init__(self, ablage: Ablage, start=(), sid: str | None = None):
        super().__init__(start)
        self.ablage = ablage
        self.sid = sid

    @property
    def sitzung(self) -> str:
        return self.sid or self.ablage.aktiv()

    def append(self, m: dict) -> None:
        eintrag = {"art": "nachricht", "rolle": m["role"], "inhalt": m["content"]}
        # Werkzeugkennung mitschreiben (15.11.2026): Im Protokoll stand nur
        # Rolle und Text — welches Werkzeug gerufen wurde und was es
        # zurueckgab, war hinterher nicht mehr zu sehen.
        aufrufe = m.get("tool_calls") or ()
        namen = []
        for a in aufrufe:
            fn = (a or {}).get("function") or {}
            namen.append({"name": str(fn.get("name") or ""),
                          "argumente": fn.get("arguments") or {}})
        if namen:
            eintrag["werkzeuge"] = namen
        if m.get("tool_name"):
            eintrag["werkzeug"] = str(m["tool_name"])
        if m.get("gedacht"):
            eintrag["gedacht"] = str(m["gedacht"])
        self.ablage.anhaengen(eintrag, self.sid)
        super().append(m)

    def clear(self) -> None:
        self.ablage.anhaengen({"art": "leer"}, self.sid)
        super().clear()

    def zeilenbereich(self, anzahl_nachrichten: int | None = None,
                      abstand: int = 0) -> tuple[int, int]:
        """Wo die Nachrichten dieses Fensters in ``verlauf.jsonl`` stehen.

        Ohne Angabe: alle Nachrichten, die das Fenster gerade führt.
        ``abstand`` überspringt so viele Nachrichten am Ende — das sind die,
        die beim Verdichten wörtlich im Fenster bleiben.
        """
        return self.ablage.nachrichten_zeilen(
            self.sitzung,
            len(self) if anzahl_nachrichten is None else anzahl_nachrichten,
            abstand)

    def verdichten(self, zusammenfassung: str, behalte: int,
                   zeilen_von: int = 0, zeilen_bis: int = 0) -> None:
        """Fenster verdichten; das Protokoll behält alles (Regel 8d).

        ``zeilen_von``/``zeilen_bis`` sind die Fundstellen des verdichteten
        Abschnitts. Sie werden **mitgeschrieben** — sonst wüsste später
        niemand, worauf sich ein Verweis im Fenster bezog.
        """
        self.ablage.anhaengen({"art": "verdichtet",
                               "zusammenfassung": zusammenfassung,
                               "behalte": behalte,
                               "zeilen_von": zeilen_von,
                               "zeilen_bis": zeilen_bis}, self.sid)
        rest = list(self)[-behalte:] if behalte > 0 else []
        neu = ([{"role": "user", "content": _mit_marke(zusammenfassung)}]
               if zusammenfassung else []) + rest
        list.__setitem__(self, slice(None), neu)
