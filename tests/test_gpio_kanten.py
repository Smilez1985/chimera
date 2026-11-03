#!/usr/bin/env python3
"""Tests für Kantenereignisse auf GPIO (Taste ohne Abfrage im Takt).

Warum: Die Tastenschleife fragte die Leitung alle 5 ms ab — 200 ioctls je
Sekunde, am Pi gemessen 1,3 % eines Kerns im Leerlauf, für einen Taster, der
meistens nicht gedrückt ist. Der Kernel kann Flanken melden (ABI v2):
``event_buffer_size`` und ``GPIO_V2_LINE_FLAG_EDGE_*``. Geprüft wird, was wir
dem Kernel **schicken** (Flags, Maske, Puffergröße) und wie wir lesen (48-Byte
Sätze). Die Hardware wird nicht nachgebaut.
"""

import ctypes
import errno
import os
import sys
from pathlib import Path

SRC = Path(os.environ.get("CHIMERA_SRC")
           or Path(__file__).resolve().parent.parent / "src")
sys.path.insert(0, str(SRC))

from chimera.displays import gpio as G  # noqa: E402

PASS = FAIL = 0

def ok(m):
    global PASS; PASS += 1; print(f"  ok    {m}")

def bad(m):
    global FAIL; FAIL += 1; print(f"  FAIL  {m}")

def check(m, got, want):
    ok(m) if got == want else bad(f"{m} — erwartet {want!r}, bekam {got!r}")


def belege(*, kanten=None, eingaenge=None, ausgaenge=None):
    """Leitungen belegen, ohne echten Kernel: ioctl wird abgefangen."""
    gesehen = {}
    echt = G.fcntl.ioctl

    def falsch(fd, op, anfrage):
        gesehen["event_buffer_size"] = anfrage.event_buffer_size
        gesehen["num_attrs"] = anfrage.config.num_attrs
        gesehen["attrs"] = [(anfrage.config.attrs[i].attr.id,
                             anfrage.config.attrs[i].attr.value,
                             anfrage.config.attrs[i].mask)
                            for i in range(anfrage.config.num_attrs)]
        gesehen["num_lines"] = anfrage.num_lines
        anfrage.fd = os.open(os.devnull, os.O_RDONLY)
        return 0

    # Der Chip selbst lässt sich hier nicht öffnen (kein /dev/gpiochip0 im
    # Sandkasten) — dafür genügt ein gewöhnlicher FD.
    echt_open = os.open

    def falsch_open(pfad, *a, **k):
        if str(pfad).startswith("/dev/gpiochip"):
            return echt_open(os.devnull, os.O_RDWR)
        return echt_open(pfad, *a, **k)

    G.fcntl.ioctl = falsch
    G.os.open = falsch_open
    try:
        l = G.Leitungen("/dev/gpiochip0", verbraucher="test")
        l.request(ausgaenge=ausgaenge or {}, eingaenge=eingaenge or {},
                  kanten=kanten)
        return l, gesehen
    finally:
        G.fcntl.ioctl = echt
        G.os.open = echt_open


print("== 1. Der ABI-Satz stimmt ==")
check("Ereignis ist 48 Byte", ctypes.sizeof(G._LineEvent), 48)
check("steigende Flanke ist 1", G.EREIGNIS_STEIGEND, 1)
check("fallende Flanke ist 2", G.EREIGNIS_FALLEND, 2)
check("Kantenflag steigend", G.FLAG_EDGE_RISING, 1 << 4)
check("Kantenflag fallend", G.FLAG_EDGE_FALLING, 1 << 5)


print("== 2. Was wir dem Kernel schicken ==")
# Ausgänge + Taste mit beiden Flanken (der Aufbau des Panels).
l, gesehen = belege(ausgaenge={17: 1, 22: 1}, eingaenge={27: None},
                    kanten={27: "beide"})
check("Ereignispuffer angefragt", gesehen["event_buffer_size"], 16)
check("beide Leitungen belegt", gesehen["num_lines"], 3)
flags_der_taste = [v for (art, v, m) in gesehen["attrs"]
                   if art == G.ATTR_FLAGS and m == (1 << 2)]
check("Taste traegt Eingang + beide Kanten", flags_der_taste,
      [G.FLAG_INPUT | G.FLAG_EDGE_RISING | G.FLAG_EDGE_FALLING])
check("Kanten sind gemerkt", l._kanten, True)
l.close()

# Ohne Kanten darf nichts vom Ereignispuffer angefordert werden.
l, gesehen = belege(eingaenge={27: "hoch"})
check("ohne Kanten: kein Ereignispuffer", gesehen["event_buffer_size"], 0)
check("ohne Kanten: kein Kantenflag",
      [v for (art, v, m) in gesehen["attrs"] if art == G.ATTR_FLAGS],
      [G.FLAG_INPUT | G.FLAG_BIAS_PULL_UP])
check("ohne Kanten: nichts gemerkt", l._kanten, False)
l.close()

# Nur steigend.
l, gesehen = belege(eingaenge={27: None}, kanten={27: "steigend"})
check("nur steigend", [v for (art, v, m) in gesehen["attrs"]
                       if art == G.ATTR_FLAGS],
      [G.FLAG_INPUT | G.FLAG_EDGE_RISING])
l.close()

# Zwei Eingänge mit verschiedenen Flag-Sätzen: zwei Attribute, richtige Masken.
l, gesehen = belege(eingaenge={5: None, 6: "runter"},
                    kanten={5: "beide"})
_masks = {m: v for (art, v, m) in gesehen["attrs"] if art == G.ATTR_FLAGS}
check("zwei Flagsätze, zwei Masken", len(_masks), 2)
check("Leitung 5 mit Kanten, Leitung 6 mit Bias",
      sorted(_masks.values()),
      sorted([G.FLAG_INPUT | G.FLAG_EDGE_RISING | G.FLAG_EDGE_FALLING,
              G.FLAG_INPUT | G.FLAG_BIAS_PULL_DOWN]))
l.close()

# Eine Kante für einen Ausgang ist ein Denkfehler, kein stiller Fehlschlag.
try:
    belege(ausgaenge={17: 1}, eingaenge={27: None}, kanten={17: "beide"})
    bad("Kante auf einem Ausgang — erwartet ValueError, bekam keinen")
except ValueError:
    ok("Kante auf einem Ausgang wird abgewiesen")
try:
    belege(eingaenge={27: None}, kanten={27: "vielleicht"})
    bad("unbekannte Kantenart — erwartet ValueError, bekam keinen")
except ValueError:
    ok("unbekannte Kantenart wird abgewiesen")


print("== 3. Ereignisse lesen ==")
def rohr():
    r, w = os.pipe()
    l = G.Leitungen("/dev/gpiochip0", verbraucher="test")
    l._fd = r
    l._index = {27: 0}
    l._kanten = True
    return l, w

def satz(offset, art, seqno=1):
    e = G._LineEvent(timestamp_ns=1, id=art, offset=offset, seqno=seqno,
                     line_seqno=seqno)
    return bytes(e)

l, w = rohr()
os.write(w, satz(27, G.EREIGNIS_STEIGEND) + satz(27, G.EREIGNIS_FALLEND))
check("zwei Flanken gelesen", l.ereignisse(timeout=0.5),
      [(27, "steigend"), (27, "fallend")])
check("danach nichts mehr", l.ereignisse(offset=27, timeout=0.05), [])
os.close(w); l.close()

l, w = rohr()
os.write(w, satz(5, G.EREIGNIS_STEIGEND))
check("fremde Leitung wird gefiltert", l.ereignisse(offset=27, timeout=0.1), [])
check("ohne Filter kommt sie", l.ereignisse(timeout=0.1), [(5, "steigend")])
os.close(w); l.close()

# Ohne Kantenangabe darf ereignisse() nicht still nichts liefern.
l = G.Leitungen("/dev/gpiochip0", verbraucher="test")
l._fd = os.open(os.devnull, os.O_RDONLY)
l._kanten = False
try:
    l.ereignisse(timeout=0.01)
    bad("ohne Kanten — erwartet RuntimeError, bekam keinen")
except RuntimeError:
    ok("ohne Kanten: benannter Fehler statt stiller Leere")
l.close()

# Unbekannte Ereignisart wird übersprungen, nicht als Flanke ausgegeben.
l, w = rohr()
e = bytearray(satz(27, G.EREIGNIS_STEIGEND))
e[8:12] = (99).to_bytes(4, "little")     # id = 99
os.write(w, bytes(e))
check("unbekannte id wird übersprungen", l.ereignisse(timeout=0.1), [])
os.close(w); l.close()

print(f"\nErgebnis: {PASS} ok, {FAIL} fehlgeschlagen")
sys.exit(0 if FAIL == 0 else 1)
