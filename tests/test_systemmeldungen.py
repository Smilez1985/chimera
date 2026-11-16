"""Kanalhinweis und Gesichtsausdruck als eigene Systemmeldung (16.11.2026).

smilez' Entscheidung: *„Kanal im prompt aber nicht als prompt Text, sondern
als system Meldung, Gesicht nur opt-in der Antwort ausgeben, als Systemmeldung
behandeln"*. Bis heute hing beides am Nutzertext
(``f"{channel.hint()}\\n\\n{text}"`` bzw. ``prompt + "\\n\\n[Gesicht: …]"``).

Geprüft wird, was ohne Gerät prüfbar ist:

* die Ablage führt Systemmeldungen als ``art: system`` **mit Herkunft** und
  gibt sie beim Abspielen als ``role: system`` zurück,
* der Marker ``_quelle`` bleibt in der Ablage und geht **nicht** an die
  Anbieter (er wäre dort ein fremdes Feld),
* Anthropic bekommt keine ``system``-Nachricht in ``messages`` (HTTP 400),
  sondern im Top-Level-``system``,
* das Verdichten hält eine Systemmeldung nicht für einen Rundenbeginn.

Aufruf: python3 tests/test_systemmeldungen.py
Gegenprobe: python3 tests/gegenprobe_systemmeldungen.py
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

HIER = Path(__file__).resolve().parent
SRC = Path(os.environ.get("CHIMERA_SRC") or (HIER.parent / "src"))
sys.path.insert(0, str(SRC))

from chimera import ablage as ab                                    # noqa: E402
from chimera.agent import verdichten                                 # noqa: E402
from chimera.provider.anthropic import _system_nach_oben             # noqa: E402

ok = 0
fehler = 0


def check(name: str, ist, soll) -> None:
    global ok, fehler
    if ist == soll:
        ok += 1
        print(f"  ok    {name}")
    else:
        fehler += 1
        print(f"  FAIL  {name} -- erwartet {soll!r}, bekam {ist!r}")


print("== Ablage: Herkunft und Rückweg ==")
with tempfile.TemporaryDirectory() as td:
    a = ab.Ablage(td)
    sid = a.aktiv()
    v = ab.Verlauf(a, a.laden())
    v.append({"role": "user", "content": "hallo"})
    v.append({"role": "system", "content": "[Kanal: web] Chat.",
              "_quelle": "kanal"})
    v.append({"role": "system", "content": "[Gesicht: active=mood_idle]",
              "_quelle": "gesicht"})
    v.append({"role": "assistant", "content": "antwort"})

    # Der Marker ist eine Angabe für die Ablage, kein Verlaufsfeld.
    check("kein _quelle im Verlauf",
          any(k.startswith("_") for m in v for k in m), False)

    zeilen = a.lesen(sid)
    arten = [z.get("art") for z in zeilen]
    check("vier Einträge", len(zeilen), 4)
    check("Arten in Reihenfolge", arten,
          ["nachricht", "system", "system", "nachricht"])
    check("Herkunft der ersten Systemmeldung", zeilen[1].get("quelle"), "kanal")
    check("Herkunft der zweiten Systemmeldung", zeilen[2].get("quelle"), "gesicht")
    check("Inhalt unverändert", zeilen[2].get("inhalt"),
          "[Gesicht: active=mood_idle]")

    # Neustart: das Fenster muss die Systemmeldungen wieder als `system` führen.
    fenster = ab.Ablage(td).laden()
    check("Fenster nach Neustart", [m["role"] for m in fenster],
          ["user", "system", "system", "assistant"])
    check("kein _quelle im abgespielten Fenster",
          any(k.startswith("_") for m in fenster for k in m), False)

    # Die Seite für die Oberfläche (op "lesen") zeigt sie ebenfalls.
    seite = a.lesen_seite(sid, 10, 0)
    check("Seite kennt die Systemart",
          [z.get("art") for z in seite].count("system"), 2)

print("== Anthropic: system gehört nicht in messages ==")
rest, system = _system_nach_oben(
    [{"role": "system", "content": "S1"},
     {"role": "user", "content": "frage"},
     {"role": "system", "content": "S2"},
     {"role": "assistant", "content": "antwort"}], "prompt")
check("keine Systemnachricht in messages",
      [m["role"] for m in rest], ["user", "assistant"])
check("Top-Level-system trägt alles", system, "prompt\n\nS1\n\nS2")
check("Reihenfolge der Systemtexte bleibt",
      system.split("S1")[1].split("S2")[0], "\n\n")

ohne, system2 = _system_nach_oben([{"role": "user", "content": "f"}], None)
check("ohne Systemmeldung bleibt system leer", system2, None)
check("ohne Systemmeldung bleibt der Verlauf", len(ohne), 1)

leer, system3 = _system_nach_oben([{"role": "system", "content": "   "}], "S")
check("leere Systemmeldung erfindet nichts", system3, "S")

print("== Verdichten: Systemmeldung ist kein Rundenbeginn ==")
check("system ist kein Rundenbeginn",
      verdichten._ist_rundenbeginn({"role": "system", "content": "[Kanal: x]"}), False)

mit = [{"role": "user", "content": "frage 1"},
       {"role": "system", "content": "[Kanal: web] Chat."},
       {"role": "assistant", "content": "antwort 1"},
       {"role": "user", "content": "frage 2"},
       {"role": "system", "content": "[Gesicht: active=mood_idle]"},
       {"role": "assistant", "content": "antwort 2"},
       {"role": "user", "content": "frage 3"},
       {"role": "assistant", "content": "antwort 3"}]
ohne_sys = [m for m in mit if m["role"] != "system"]
# Der Index verschiebt sich durch die Systemmeldungen; gleich sein muss der
# **Inhalt** ab dem Schnitt -- sonst zerschnitte das Verdichten eine Runde.
_i_mit = verdichten.schnittindex(mit, 2)
_i_ohne = verdichten.schnittindex(ohne_sys, 2)
check("Schnitt lässt dieselben Nachrichten wörtlich",
      [m["content"] for m in mit[_i_mit:] if m["role"] != "system"],
      [m["content"] for m in ohne_sys[_i_ohne:]])
check("Schnitt beginnt bei einer Nutzernachricht",
      mit[verdichten.schnittindex(mit, 2)]["role"], "user")
# Die Systemmeldung der **ersten** Runde fällt in den verdichteten Teil, die
# der zweiten bleibt wörtlich — der Schnitt liegt auf einer Runde, nicht
# zwischen Systemmeldung und Antwort.
_schnitt = verdichten.verdichte(mit, runden=2).schnitt
check("Systemmeldung der alten Runde wird verdichtet", 1 < _schnitt, True)
check("Systemmeldung der letzten Runde bleibt wörtlich", 4 >= _schnitt, True)

print(f"\nErgebnis: {ok} ok, {fehler} fehlgeschlagen")
sys.exit(1 if fehler else 0)
