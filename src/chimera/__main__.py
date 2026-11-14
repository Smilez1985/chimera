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

from . import chat_wahl
from .agent.session import Channel
from .app import build
from .protokoll import datei_einrichten
from .provider.base import Unavailable

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
    ap.add_argument("--anbieter", metavar="ID", default=None,
                    help="Anbieter für dieses Gespräch wählen (setzt die Wahl "
                         "für alle Türen, '' = löschen)")
    ap.add_argument("--modell", metavar="NAME", default=None,
                    help="Modell wählen (setzt die Wahl für alle Türen)")
    ap.add_argument("--denken", metavar="STUFE", default=None,
                    help="Denkstufe wählen: aus, an, minimal, niedrig, mittel, "
                         "hoch, max (geprüft wird im Gateway)")
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

    if not _wahl_setzen(args):
        return 2

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
        turn = chi.ask(args.frage, TERMINAL, **chat_wahl.auftrag())
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

def _gateway_hat_telegram() -> bool:
    """Meldet das Gateway, dass seine Telegram-Tuer laeuft?

    Nur ein ausdrueckliches "an" zaehlt. Ein Gateway ohne diese Angabe (aeltere
    Fassung) oder ohne Antwort heisst: der Dienst oeffnet seine eigene Tuer
    wie bisher -- ein Versionsunterschied nimmt Telegram nie weg.
    """
    try:
        from .provider.gateway import anfragen
        from .provider.base import LLMError
    except ImportError:
        # Ein Stand ohne Gateway-Connector: kein Gateway, also keine Tuer dort.
        return False
    try:
        return anfragen({"op": "status"}, warten=5.0).get("telegram") == "an"
    except LLMError:
        return False

def dienst(chi, stop: threading.Event | None = None, env=None) -> int:
    """Als systemd-Dienst laufen (INSTALLER.md, Abschnitt „Modul 98 — Dienst").

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
    if (env.get("CHIMERA_TELEGRAM_TOKEN") or "").strip() and _gateway_hat_telegram():
        # Regel 5s: Die Tuer gehoert dem Gateway. Eine zweite im Dienst wuerde
        # um dieselben Nachrichten streiten (Telegram: ein Abholer je Token).
        log.info("Telegram laeuft im Gateway -- keine eigene Tuer im Dienst.")
    elif (env.get("CHIMERA_TELEGRAM_TOKEN") or "").strip():
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

    # Der eine Weg in die Hauptsitzung (Regel 5s): das Gateway ist der Client.
    from .sitzung_socket import aus_umgebung
    sitzung_srv = aus_umgebung(chi.session, env)
    if sitzung_srv is not None:
        sitzung_srv.start()
        log.info("Sitzungs-Socket bereit.")
    else:
        log.info("Kein Sitzungs-Socket (weder LISTEN_FDS noch "
                 "CHIMERA_SITZUNG_SOCKET).")

    log.info("Dienst bereit.")
    # Anbieter regelmaessig pruefen und das Ergebnis an die Statuszeile geben
    # (Quelle anbieter_weg). Hier und nicht im Renderer: Die Pruefung kann ins
    # Netz gehen. Ein Geraet ohne anbieter_melden (Testdoppel) wartet nur.
    melden = getattr(chi, "anbieter_melden", None)
    # Der Ton erinnert an offene Freigaben (DESIGN, "Kein Ablauf mehr — der Ton
    # erinnert"). Im selben Takt wie die Anbieterpruefung: 30 s ist fein genug
    # fuer den kleinsten Abstand (60 s), und es braucht keinen zweiten Faden.
    erinnern = getattr(chi, "erinnere", None)
    try:
        if melden is not None:
            melden()
        if erinnern is not None:
            erinnern()
        while not stop.wait(ANBIETER_TAKT_S):
            if melden is not None:
                melden()
            if erinnern is not None:
                erinnern()
    finally:
        if bot is not None:
            bot.stop()
        if sitzung_srv is not None:
            sitzung_srv.stop()
    return 0


def _wahl_setzen(args) -> bool:
    """``--anbieter``/``--modell``/``--denken`` in die Wahl schreiben.

    Geprüft wird im Gateway (``daten::wahl_feld_setzen``), nicht hier: eine
    zweite Regel für dieselben Felder liefe auseinander. Ein abgelehnter
    Wert endet mit 2 -- wer eine Wahl ausdrücklich bestellt, soll nicht
    stillschweigend ohne sie weiterlaufen.

    ``None`` heisst "nicht angegeben"; ``''`` heisst "Feld löschen" und ist
    damit etwas anderes als Schweigen.
    """
    gesetzt = []
    for feld in chat_wahl.FELDER:
        wert = getattr(args, feld, None)
        if wert is None:
            continue
        try:
            chat_wahl.setzen(feld, wert)
        except Unavailable as exc:
            print(f"Wahl nicht gesetzt: {exc}", file=sys.stderr)
            return False
        except (chat_wahl.WahlFehler, ValueError) as exc:
            print(f"{feld}: {exc}", file=sys.stderr)
            return False
        gesetzt.append(f"{feld}={wert or '(gelöscht)'}")
    if gesetzt:
        print("Wahl: " + ", ".join(gesetzt))
    return True

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
        # Die Wahl gilt der Sitzung, nicht dem Lauf: was eine andere Tür
        # inzwischen umgestellt hat, soll auch hier gelten.
        turn = chi.ask(prompt, TERMINAL, **chat_wahl.auftrag())
        print(turn.text)
        print()

if __name__ == "__main__":
    sys.exit(main())
