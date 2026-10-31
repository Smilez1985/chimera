"""Tests für den Dienstmodus (``python -m chimera --dienst``).

Geprüft wird der echte Code aus ``chimera.__main__`` — mit einem
Gerätedoppel statt ``build()``, damit weder Netz noch Panel nötig sind.

Der Kern: Unter systemd ist stdin leer. Das Terminalgespräch endet dort
sofort mit 0, und die Unit hielte das für ein sauberes Ende. Der
Dienstmodus muss deshalb **laufen, bis ein Stoppsignal kommt**.
"""
import sys
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

import chimera.__main__ as cm  # noqa: E402

PASS = FAIL = 0
def ok(m):
    global PASS; PASS += 1; print(f"  ok    {m}")
def bad(m):
    global FAIL; FAIL += 1; print(f"  FAIL  {m}")
def check(m, got, want):
    ok(m) if got == want else bad(f"{m} — erwartet {want!r}, bekam {got!r}")


class Registry:
    def __init__(self, n=0): self.n = n
    def available(self): return [object()] * self.n


class Bot:
    def __init__(self): self.lief = threading.Event(); self.gestoppt = False
    def run(self): self.lief.set()
    def stop(self): self.gestoppt = True


class Geraet:
    """Doppel für das zusammengebaute Gerät."""
    def __init__(self, telegram_fehler=None):
        self.registry = Registry()
        self.renderer = None
        self.bot = Bot()
        self.fehler = telegram_fehler
        self.notes = []
        from chimera.agent.session import Session
        self.session = Session(object())
    def start_display(self): return False
    def paint_once(self): pass
    def stop_display(self): pass
    def status(self): return ""
    def telegram(self):
        if self.fehler: raise ValueError(self.fehler)
        return self.bot


def im_faden(fn):
    """fn im Faden starten, Ergebnis in einer Liste zurückgeben."""
    erg = []
    t = threading.Thread(target=lambda: erg.append(fn()), daemon=True)
    t.start()
    return t, erg


print("=== Dienstmodus ===")

# 1. Läuft, bis gestoppt wird — kein Ende an leerem stdin.
stop = threading.Event()
t, erg = im_faden(lambda: cm.dienst(Geraet(), stop=stop, env={}))
time.sleep(0.3)
check("läuft ohne Stoppsignal weiter", t.is_alive(), True)
stop.set(); t.join(2)
check("endet nach Stoppsignal", t.is_alive(), False)
check("Ende nach Stopp ist rc 0", erg, [0])

# 2. Telegram halb eingerichtet -> rc 2 (Unit startet dann nicht neu).
stop = threading.Event()
t, erg = im_faden(lambda: cm.dienst(
    Geraet(telegram_fehler="CHIMERA_TELEGRAM_ALLOWED ist leer"),
    stop=stop, env={"CHIMERA_TELEGRAM_TOKEN": "x"}))
t.join(2)
check("falsche Telegram-Konfiguration: rc 2, sofort", erg, [2])

# 3. Telegram eingerichtet -> Bot läuft, wird beim Ende gestoppt.
g = Geraet()
stop = threading.Event()
t, erg = im_faden(lambda: cm.dienst(g, stop=stop,
                                    env={"CHIMERA_TELEGRAM_TOKEN": "x"}))
check("Telegram-Bot gestartet", g.bot.lief.wait(2), True)
stop.set(); t.join(2)
check("Telegram-Bot beim Ende gestoppt", g.bot.gestoppt, True)
check("rc 0", erg, [0])

# 3b. Sitzungs-Socket (Regel 5s): konfiguriert -> gebunden, beim Ende weg.
import os as _os, socket as _so, tempfile as _tf
_pfad = _os.path.join(_tf.mkdtemp(), "sitzung.sock")
g = Geraet()
stop = threading.Event()
t, erg = im_faden(lambda: cm.dienst(g, stop=stop,
                                    env={"CHIMERA_SITZUNG_SOCKET": _pfad}))
for _ in range(20):
    if _os.path.exists(_pfad): break
    time.sleep(0.1)
check("Sitzungs-Socket gebunden", _os.path.exists(_pfad), True)
try:
    _c = _so.socket(_so.AF_UNIX); _c.settimeout(3); _c.connect(_pfad)
    _c.sendall(b'{"op":"ping"}\n')
    _antwort = b'"ok": true' in _c.recv(200)
    _c.close()
except OSError:
    _antwort = False
check("Sitzungs-Socket antwortet", _antwort, True)
stop.set(); t.join(3)
check("Sitzungs-Socket beim Ende entfernt", _os.path.exists(_pfad), False)
check("Ende rc 0", erg, [0])
stop = threading.Event(); stop.set()
check("ohne Konfiguration kein Socket, rc 0", cm.dienst(Geraet(), stop=stop, env={}), 0)

# 3c. Das Gateway hat die Telegram-Tuer (Regel 5s): der Dienst oeffnet keine zweite.
_alt = cm._gateway_hat_telegram
cm._gateway_hat_telegram = lambda: True
g = Geraet(telegram_fehler="darf nicht gerufen werden")
stop = threading.Event(); stop.set()
check("Gateway hat Telegram: keine eigene Tuer, rc 0",
      cm.dienst(g, stop=stop, env={"CHIMERA_TELEGRAM_TOKEN": "x"}), 0)
check("Gateway hat Telegram: Bot nie gestartet", g.bot.lief.is_set(), False)
# Ohne Gateway (oder ohne Angabe): wie bisher die eigene Tuer.
cm._gateway_hat_telegram = lambda: False
g = Geraet()
stop = threading.Event()
t, erg = im_faden(lambda: cm.dienst(g, stop=stop, env={"CHIMERA_TELEGRAM_TOKEN": "x"}))
check("ohne Gateway-Tuer: eigener Bot startet", g.bot.lief.wait(2), True)
stop.set(); t.join(2)
cm._gateway_hat_telegram = _alt
# Die echte Pruefung: ohne erreichbares Gateway heisst es nein, nie eine Ausnahme.
import os as _os2
_os2.environ["CHIMERA_TOR_SOCKET"] = "/nonexistent/tor.sock"
check("kein Gateway erreichbar: keine Tuer dort", cm._gateway_hat_telegram(), False)
del _os2.environ["CHIMERA_TOR_SOCKET"]

# 4. Ohne Token wird Telegram nicht versucht (kein Fehler, kein Bot).
g = Geraet(telegram_fehler="darf nicht gerufen werden")
stop = threading.Event(); stop.set()
check("ohne Token: rc 0", cm.dienst(g, stop=stop, env={}), 0)

# 5. main() leitet --dienst in den Dienstmodus, nicht ins Gespräch.
gerufen = []
alt_build, alt_dienst, alt_gespraech = cm.build, cm.dienst, cm._gespraech
try:
    cm.build = lambda **kw: Geraet()
    cm.dienst = lambda chi, **kw: gerufen.append("dienst") or 0
    cm._gespraech = lambda chi: gerufen.append("gespraech") or 0
    rc = cm.main(["--dienst", "--offline"])
finally:
    cm.build, cm.dienst, cm._gespraech = alt_build, alt_dienst, alt_gespraech
check("--dienst führt in den Dienstmodus", gerufen, ["dienst"])
check("main rc", rc, 0)

print(f"\nErgebnis: {PASS} ok, {FAIL} fehlgeschlagen")
sys.exit(1 if FAIL else 0)
