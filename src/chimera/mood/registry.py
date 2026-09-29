"""Verwaltung der Mood-Bibliothek.

Noisy vergibt Mood-Nummern fest, in Bereichen je Gruppe. Das geht dort, wo
alle Moods im Quelltext stehen. Chimera erfindet sie zur Laufzeit — also
werden die Nummern vergeben, nicht vergeben *bekommen*.

Jeder Mood trägt seine Herkunft und wann er zuletzt gebraucht wurde. Ohne
das wächst die Bibliothek unbegrenzt, und niemand weiß, was davon je
benutzt wurde.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path

from .validate import Report, safe_validate


@dataclass
class Entry:
    mood_id: int
    mood: dict
    origin: str
    created_at: float
    last_used: float
    uses: int = 0

    @property
    def name(self) -> str:
        return self.mood["name"]

    @property
    def protected(self) -> bool:
        """Eingebautes wird nicht weggeräumt."""
        return self.origin == "builtin"


class Registry:
    """Hält die bekannten Moods und vergibt Nummern."""

    def __init__(self, *, capacity: int = 200) -> None:
        self._by_id: dict[int, Entry] = {}
        self._by_name: dict[str, int] = {}
        self._next_id = 1
        self.capacity = capacity

    # --- Lesen ------------------------------------------------------------

    def __len__(self) -> int:
        return len(self._by_id)

    def __contains__(self, key) -> bool:
        return self.find(key) is not None

    def find(self, key: int | str) -> Entry | None:
        if isinstance(key, int):
            return self._by_id.get(key)
        return self._by_id.get(self._by_name.get(str(key).upper(), -1))

    def get(self, key: int | str) -> dict:
        """Mood holen und als benutzt vermerken."""
        e = self.find(key)
        if e is None:
            raise KeyError(f"Mood unbekannt: {key!r}")
        e.last_used = time.time()
        e.uses += 1
        return e.mood

    def names(self) -> list[str]:
        return [e.name for e in self._by_id.values()]

    def entries(self) -> list[Entry]:
        return list(self._by_id.values())

    # --- Schreiben --------------------------------------------------------

    def add(self, raw: dict, *, origin: str = "generated",
            name: str | None = None) -> tuple[Entry, Report]:
        """Einen Mood aufnehmen. Er wird immer erst geprüft."""
        mood, rep = safe_validate(raw, name=name)

        key = mood["name"].upper()
        if key in self._by_name:
            # Gleicher Name: der neue ersetzt den alten, behält aber dessen
            # Nummer. Sonst zeigen gespeicherte Verweise ins Leere.
            existing = self._by_id[self._by_name[key]]
            existing.mood = mood
            # Die Herkunft wird NICHT herabgestuft. Ein eingebauter Mood,
            # den das Modell überschreibt, bleibt eingebaut -- sonst
            # verliert er den Schutz vor dem Aufräumen und verschwindet
            # beim nächsten Überlauf. Gefunden durch den eigenen Test.
            if existing.origin != "builtin":
                existing.origin = origin
            existing.last_used = time.time()
            return existing, rep

        entry = Entry(
            mood_id=self._next_id,
            mood=mood,
            origin=origin,
            created_at=time.time(),
            last_used=time.time(),
        )
        self._by_id[entry.mood_id] = entry
        self._by_name[key] = entry.mood_id
        self._next_id += 1

        if len(self._by_id) > self.capacity:
            self.prune()
        return entry, rep

    def prune(self, *, keep: int | None = None) -> list[str]:
        """Selten Gebrauchtes entfernen, Eingebautes nie.

        Ohne das läuft eine Bibliothek, die sich selbst füllt, irgendwann
        über — und zwar auf einem Gerät mit 512 MB.
        """
        limit = keep if keep is not None else self.capacity
        removable = [e for e in self._by_id.values() if not e.protected]
        if len(self._by_id) <= limit:
            return []

        # Ältester Gebrauch zuerst weg.
        removable.sort(key=lambda e: (e.last_used, e.uses))
        n_remove = len(self._by_id) - limit
        removed: list[str] = []
        for e in removable[:n_remove]:
            del self._by_id[e.mood_id]
            del self._by_name[e.name.upper()]
            removed.append(e.name)
        return removed

    # --- Ablage -----------------------------------------------------------

    def to_json(self) -> str:
        data = {
            "next_id": self._next_id,
            "moods": [
                {
                    "id": e.mood_id,
                    "origin": e.origin,
                    "created_at": e.created_at,
                    "last_used": e.last_used,
                    "uses": e.uses,
                    "mood": e.mood,
                }
                for e in self._by_id.values()
            ],
        }
        return json.dumps(data, ensure_ascii=False, indent=2)

    def save(self, path: str | Path) -> None:
        """Atomar schreiben — dieselbe Regel wie im Installer.

        Ein abgebrochener Schreibvorgang darf keine halbe Bibliothek
        hinterlassen.
        """
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        payload = self.to_json()
        if not payload.strip():
            raise ValueError("Leere Ausgabe — wird nicht geschrieben")
        tmp = p.with_suffix(p.suffix + ".tmp")
        tmp.write_text(payload, encoding="utf-8")
        tmp.replace(p)

    @classmethod
    def load(cls, path: str | Path, *, capacity: int = 200) -> "Registry":
        reg = cls(capacity=capacity)
        p = Path(path)
        if not p.exists():
            return reg
        data = json.loads(p.read_text(encoding="utf-8"))
        # JSON kennt keine Tupel -- der Validator wandelt beim Aufnehmen
        # zurueck, deshalb laeuft jeder geladene Mood durch add().
        for item in data.get("moods", []):
            entry, _ = reg.add(item["mood"], origin=item.get("origin", "generated"))
            entry.created_at = item.get("created_at", entry.created_at)
            entry.last_used = item.get("last_used", entry.last_used)
            entry.uses = item.get("uses", 0)
        reg._next_id = max(data.get("next_id", reg._next_id), reg._next_id)
        return reg
