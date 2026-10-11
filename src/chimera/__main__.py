"""Chimera starten.

    python3 -m chimera              # Gespräch im Terminal
    python3 -m chimera --telegram   # zusätzlich die Telegram-Tür
    python3 -m chimera --pruefen    # nur zeigen, was da ist
    python3 -m chimera -f "Frage"   # eine Frage, eine Antwort

Beide Türen führen in dieselbe Sitzung (Regel 5d): Was per Telegram
besprochen wurde, weiß der Agent auch im Terminal.
"""

from __future__ import annotations

import argparse
import logging
import sys
import threading

from .agent.session import Channel
from .app import build
from .protokoll import datei_einrichten

log = logging.getLogger("chimera")

#: Das Terminal ist eine Tür wie jede andere.
TERMINAL = Channel("terminal", mode="text")

#: Wie oft der Dienst die Anbieter prueft (Sekunden). Ollama haelt das
#: Ergebnis selbst 30 s vor (PROBE_TTL); oefter zu fragen braechte nichts.
ANBIETER_TAKT_S = 30.0

def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        prog="chimera", description="Ein Agent, der ein Gesicht macht.")
    ap.add_argument("-f", "--frage", help="Eine Frage stellen und aufhören")
    ap.add_argument("--telegram", action="store_true",
                    help="Die Telegram-Tür öffnen")
    ap.add_argument("--pruefen", action="store_true",
                    help="Nur zeigen, was vorhanden ist")
    ap.add_argument("--offline", action="store_true",
                    help="Nicht im Netz nach Anbietern suchen")
    ap.add_argument("--dienst", action="store_true",
                    help="Als Dienst laufen: ohne Terminal, bis SIGTERM")
    ap.add_argument("-v", "--ausfuehrlich", action="store_true")
    args = ap.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.ausfuehrlich else logging.INFO,
        format="%(levelname)-7s %(name)s: %(message)s")
    if args.dienst:
        # Zusaetzlich zum Journal eine Datei im RAM (Regel 10r); auf die
        # Karte bringt sie der Abgleich der Unit, nicht Python.
        datei_einrichten()

    chi = build(probe_network=not args.offline)
    # Ab hier ist ein Panel moeglicherweise offen. Jeder Ausstieg muss es
    # freigeben, auch der fruehe -- sonst bleibt der SPI-Bus belegt
    # (Regel 7b).
    try:
        return _lauf(chi, args)
    finally:
        chi.stop_display()


def _lauf(chi, args) -> int:
    for note in chi.notes:
        print(note)
    print()
    print(chi.status())
    print()

    if args.pruefen:
        return 0

    if args.dienst:
        return dienst(chi)

    if not chi.registry.available():
        print("Kein Sprachmodell erreichbar — ohne eines gibt es kein "
              "Gespräch.\nZum Einrichten siehe oben.", file=sys.stderr)
        return 2

    # Das Gesicht zeichnen lassen, bevor gearbeitet wird: Wer davor steht,
    # soll sehen, dass das Gerät wach ist (Regel 7a/10h).
    if chi.start_display():
        print("Gesicht zeichnet.")
    elif chi.renderer is not None:
        chi.paint_once()
        print("Gesicht einmalig gezeichnet (Panel ohne Bildrate).")

    if args.frage:
        turn = chi.ask(args.frage, TERMINAL)
        print(turn.text)
        return 1 if turn.error else 0

    bot = None
    if args.telegram:
        try:
            bot = chi.telegram()
        except ValueError as exc:
            print(f"Telegram nicht eingerichtet: {exc}", file=sys.stderr)
            return 2
        threading.Thread(target=bot.run, daemon=True,
                         name="telegram").start()
        print("Telegram läuft mit. Dieselbe Sitzung, dieselbe Erinnerung.")
        print()

    try:
        return _gespraech(chi)
    finally:
        if bot is not None:
            bot.stop()

def dienst(chi, stop: threading.Event | None = None, env=None) -> int:
    """Als systemd-Dienst laufen (INSTALLER.md §4c).

    Ohne Terminal: Das Gespräch im Terminal endet an der ersten leeren
    Eingabe, und unter systemd ist stdin leer — der Dienst wäre sofort
    "erfolgreich" beendet. Hier wird stattdessen gewartet, bis SIGTERM
    oder SIGINT kommt.

    Fehlt ein Sprachmodell, läuft der Dienst trotzdem (``build``: Gesicht
    braucht keines) und sagt es. Ist Telegram **halb** eingerichtet (Token
    da, Absender falsch), endet er mit 2: Das ist eine falsche
    Konfiguration, und die Unit startet bei 2 nicht neu
    (``RestartPreventExitStatus=2``) — eine Schleife hilft da nicht.
    """
    import os
    import signal

    env = os.environ if env is None else env
    stop = stop or threading.Event()

    def _halt(signum, _frame):
        log.info("Signal %s — Dienst endet.", signum)
        stop.set()

    if threading.current_thread() is threading.main_thread():
        signal.signal(signal.SIGTERM, _halt)
        signal.signal(signal.SIGINT, _halt)

    if not chi.registry.available():
        log.warning("Kein Sprachmodell erreichbar — Dienst läuft ohne "
                    "Gespräch weiter (Gesicht). Werte in /opt/chimera/config/.env.")

    if chi.start_display():
        log.info("Gesicht zeichnet.")
    elif chi.renderer is not None:
        chi.paint_once()

    bot = None
    if (env.get("CHIMERA_TELEGRAM_TOKEN") or "").strip():
        try:
            bot = chi.telegram()
        except ValueError as exc:
            log.error("Telegram falsch eingerichtet: %s", exc)
            return 2
        threading.Thread(target=bot.run, daemon=True,
                         name="telegram").start()
        log.info("Telegram läuft.")
    else:
        log.info("Telegram nicht eingerichtet (CHIMERA_TELEGRAM_TOKEN leer).")

    log.info("Dienst bereit.")
    # Anbieter regelmaessig pruefen und das Ergebnis an die Statuszeile geben
    # (Quelle anbieter_weg). Hier und nicht im Renderer: Die Pruefung kann ins
    # Netz gehen. Ein Geraet ohne anbieter_melden (Testdoppel) wartet nur.
    melden = getattr(chi, "anbieter_melden", None)
    try:
        if melden is not None:
            melden()
        while not stop.wait(ANBIETER_TAKT_S):
            if melden is not None:
                melden()
    finally:
        if bot is not None:
            bot.stop()
    return 0


def _gespraech(chi) -> int:
    """Das Terminal als Tür. Leere Zeile oder Strg-D beendet."""
    print("Schreib etwas. Leere Zeile beendet.")
    while True:
        try:
            prompt = input("> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return 0
        if not prompt:
            return 0
        turn = chi.ask(prompt, TERMINAL)
        print(turn.text)
        print()

if __name__ == "__main__":
    sys.exit(main())
