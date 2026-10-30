"""Der Sitzungs-Socket (Regel 5s): der eine Weg in die Hauptsitzung.

Zeilenprotokoll (JSON je Zeile) über einen Unix-Socket. Das Gateway ist der
einzige Client; Telegram und Web-Oberfläche sind Türen *im* Gateway.

Anfragen (``op``):

* ``ping``     → ``{"ok":true,"nr":N}``
* ``anmelden`` → ``{"ok":true,"nr":N}``, danach Ereignisse als
                 ``{"ereignis":{...}}``, zuerst der Rest nach ``seit``.
* ``frage``    → ``{"ok":true,"umgeleitet":bool}`` sofort; die Antwort
                 kommt als Ereignis ``antwort`` an *alle* Angemeldeten.
                 ``ref`` (frei, z. B. Briefnummer) steht in allen Ereignissen
                 dieses Umlaufs; wer erst nach dem Turn quittiert (Klingel,
                 Regel 5o), wartet auf ``antwort``/``fehler`` mit seiner
                 ``ref``. Felder: ``tuer`` (Name der Tür), ``text``, optional
                 ``sitzung`` (jede andere als ``haupt`` wird umgeleitet).
* ``status``   → ``{"ok":true,"busy":...,"nr":N}``

Der Server hält keinen Zustand außer der Sitzung selbst (Regel 5i).
"""

from __future__ import annotations

import json
import logging
import os
import queue
import socket
import threading

from .agent.session import Channel, Session

log = logging.getLogger(__name__)

HAUPT = "haupt"
#: Obergrenze einer Zeile; größere Anfragen werden abgewiesen.
MAX_ZEILE = 1 << 20
#: Ein Leser, der so viele Ereignisse nicht abholt, wird abgemeldet.
PUFFER = 256


def aus_umgebung(session: Session, env=None) -> "SitzungsServer | None":
    """Den Server aus der Umgebung bauen, oder ``None`` (kein Socket gewollt).

    1. systemd-Socket-Aktivierung (``LISTEN_PID``/``LISTEN_FDS``): der Socket
       gehört systemd, überlebt einen Neustart des Dienstes (Muster wie das
       Gateway, Regel 5n).
    2. ``CHIMERA_SITZUNG_SOCKET=<pfad>``: selbst binden (Entwicklung, Tests).
    3. sonst keiner.
    """
    env = os.environ if env is None else env
    try:
        if env.get("LISTEN_PID") == str(os.getpid()) and int(env.get("LISTEN_FDS", "0")) >= 1:
            return SitzungsServer(session, sock=socket.socket(fileno=3))
    except (ValueError, OSError):
        log.exception("LISTEN_FDS unbrauchbar -- kein Sitzungs-Socket")
        return None
    pfad = (env.get("CHIMERA_SITZUNG_SOCKET") or "").strip()
    if pfad:
        return SitzungsServer(session, pfad=pfad)
    return None


def _senden(f, obj: dict) -> None:
    f.write((json.dumps(obj, ensure_ascii=False) + "\n").encode("utf-8"))
    f.flush()


class SitzungsServer:
    def __init__(self, session: Session, pfad: str | None = None,
                 sock: socket.socket | None = None,
                 gruppe: str | None = None) -> None:
        if (pfad is None) == (sock is None):
            raise ValueError("entweder pfad oder sock")
        self.session = session
        self.pfad = pfad
        self._sock = sock
        self._gruppe = gruppe
        self._stop = threading.Event()
        self._tueren: dict[str, Channel] = {}

    # --- Aufbau -----------------------------------------------------------

    def _binden(self) -> None:
        if self._sock is not None:
            return
        if os.path.exists(self.pfad):
            # Nur einen toten Socket wegräumen, keinen lebenden.
            probe = socket.socket(socket.AF_UNIX)
            try:
                probe.connect(self.pfad)
            except OSError:
                os.unlink(self.pfad)
            else:
                probe.close()
                raise RuntimeError(f"{self.pfad} wird schon bedient")
            finally:
                probe.close()
        s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        s.bind(self.pfad)
        os.chmod(self.pfad, 0o660)
        if self._gruppe:
            import grp
            os.chown(self.pfad, -1, grp.getgrnam(self._gruppe).gr_gid)
        s.listen(8)
        self._sock = s

    def start(self) -> "SitzungsServer":
        self._binden()
        threading.Thread(target=self._annehmen, daemon=True,
                         name="sitzung-sock").start()
        return self

    def stop(self) -> None:
        self._stop.set()
        try:
            if self._sock is not None:
                self._sock.close()
        finally:
            if self.pfad and os.path.exists(self.pfad):
                os.unlink(self.pfad)

    def _annehmen(self) -> None:
        while not self._stop.is_set():
            try:
                c, _ = self._sock.accept()
            except OSError:
                return
            threading.Thread(target=self._bedienen, args=(c,), daemon=True,
                             name="sitzung-client").start()

    # --- ein Client -------------------------------------------------------

    def _kanal(self, tuer: str) -> Channel:
        if tuer not in self._tueren:
            self._tueren[tuer] = Channel(tuer, mode="text")
        return self._tueren[tuer]

    def _bedienen(self, c: socket.socket) -> None:
        f = c.makefile("rwb", buffering=0)
        out: "queue.Queue[dict | None]" = queue.Queue(PUFFER)
        sende_lock = threading.Lock()
        angemeldet = []
        zu = threading.Event()

        def abo(ev: dict) -> bool:
            try:
                out.put_nowait(ev)
                return True
            except queue.Full:
                log.warning("Leser zu langsam — abgemeldet")
                zu.set()
                return False

        def schreiber() -> None:
            while True:
                try:
                    ev = out.get(timeout=0.5)
                except queue.Empty:
                    if zu.is_set():
                        return
                    continue
                if ev is None:
                    return
                try:
                    with sende_lock:
                        _senden(f, {"ereignis": ev})
                except OSError:
                    return

        def antwort(obj: dict) -> None:
            with sende_lock:
                _senden(f, obj)

        try:
            for zeile in iter(lambda: f.readline(MAX_ZEILE + 1), b""):
                if len(zeile) > MAX_ZEILE:
                    antwort({"ok": False, "fehler": "Zeile zu lang"})
                    break
                try:
                    q = json.loads(zeile)
                    if not isinstance(q, dict):
                        raise ValueError("kein Objekt")
                except ValueError as exc:
                    antwort({"ok": False, "fehler": f"ungültig: {exc}"})
                    continue
                op = q.get("op")
                if op == "ping":
                    antwort({"ok": True, "nr": self.session.nr})
                elif op == "status":
                    antwort({"ok": True, "nr": self.session.nr,
                             "busy": self.session.busy_channel})
                elif op == "anmelden":
                    seit = int(q.get("seit", 0))
                    angemeldet.append(abo)
                    rest = self.session.subscribe(abo, seit)
                    antwort({"ok": True, "nr": self.session.nr})
                    for ev in rest:
                        abo(ev)
                    threading.Thread(target=schreiber, daemon=True).start()
                elif op == "frage":
                    tuer = str(q.get("tuer") or "").strip()
                    text = str(q.get("text") or "").strip()
                    if not tuer or not text:
                        antwort({"ok": False, "fehler": "tuer und text nötig"})
                        continue
                    umgeleitet = str(q.get("sitzung") or HAUPT) != HAUPT
                    if umgeleitet:
                        self.session.emit("umgeleitet", tuer,
                                          f"Eingabe an {q.get('sitzung')} "
                                          "→ Hauptsitzung")
                    antwort({"ok": True, "umgeleitet": umgeleitet})
                    threading.Thread(
                        target=self.session.ask,
                        args=(text, self._kanal(tuer), str(q.get("ref") or "")),
                        daemon=True,
                        name="sitzung-frage").start()
                else:
                    antwort({"ok": False, "fehler": f"unbekannte op {op!r}"})
        except OSError:
            pass
        finally:
            for a in angemeldet:
                self.session.unsubscribe(a)
            zu.set()
            try:
                c.close()
            except OSError:
                pass
