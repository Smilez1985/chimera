"""Telegram als Tür in die Sitzung.

Die erste Bedienschnittstelle, die Chimera bekommt. Sie führt nicht in
einen eigenen Verlauf, sondern in dieselbe ``Session`` wie jede andere
Tür (Regel 5d) — deshalb steht hier auch kein Agent, sondern nur eine
Sitzung, die von außen hereingereicht wird.

**Keine fremde Bibliothek.** Die Bot-API ist HTTPS mit JSON; das kann die
Standardbibliothek. Auf 512 MB ist jede Abhängigkeit, die man nicht
braucht, eine, die man sich spart — und ein Bot, der ohne Netz zur
Installationszeit auskommt, macht den Installer einfacher.

**Nur wer eingetragen ist, darf reden.** Ein Bot-Token steht früher oder
später in irgendeinem Verlauf, und ein Agent mit ``execute_bash`` hinter
einem offenen Chat wäre grob fahrlässig. Ohne Liste erlaubter Absender
läuft der Bot nicht an.
"""

from __future__ import annotations

import json
import logging
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field

from ..agent.session import Channel, Session, Turn

log = logging.getLogger(__name__)

API = "https://api.telegram.org"

#: Telegram nimmt höchstens 4096 Zeichen je Nachricht. Etwas Luft lassen,
#: damit ein angehängter Hinweis nicht über die Grenze kippt.
MAX_MESSAGE = 3800

#: Der Kanal, durch den Telegram in die Sitzung kommt.
CHANNEL = Channel("telegram", mode="text", limit=MAX_MESSAGE)

class TelegramError(RuntimeError):
    """Die API hat Nein gesagt."""

@dataclass
class Update:
    """Eine eingegangene Nachricht, auf das Nötige eingedampft."""

    update_id: int
    chat_id: int
    user_id: int
    text: str
    name: str = ""

class TelegramAPI:
    """Der schmale Zugang zur Bot-API.

    Getrennt vom Bot, damit der Bot ohne Netz geprüft werden kann — ein
    Testdoppel setzt hier an (Regel 8: Tests rufen auf, sie rechnen nicht
    nach).
    """

    def __init__(self, token: str, *, timeout: int = 65, base: str = API):
        if not token or ":" not in token:
            raise ValueError(
                "Kein brauchbares Bot-Token. Erwartet wird die Form "
                "'123456:ABC...' von @BotFather."
            )
        self.token = token
        self.timeout = timeout
        self._base = f"{base}/bot{token}"

    def call(self, method: str, **params) -> dict:
        """Eine Methode aufrufen und das Ergebnis auspacken.

        Alles, was nicht ``ok`` meldet, wird zum Fehler — eine API, die
        höflich ``{"ok": false}`` sagt und die man weiterlaufen lässt, ist
        genau der stille Fehlschlag aus Regel 8a.
        """
        data = urllib.parse.urlencode(
            {k: v for k, v in params.items() if v is not None}
        ).encode()
        req = urllib.request.Request(f"{self._base}/{method}", data=data)
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                payload = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", "replace")[:300]
            raise TelegramError(f"{method}: HTTP {exc.code} — {body}") from exc
        except urllib.error.URLError as exc:
            raise TelegramError(f"{method}: kein Netz — {exc.reason}") from exc
        except json.JSONDecodeError as exc:
            raise TelegramError(f"{method}: unverständliche Antwort") from exc

        if not payload.get("ok"):
            raise TelegramError(
                f"{method}: {payload.get('description', 'abgelehnt')}"
            )
        return payload.get("result", {})

    # --- die drei Methoden, die gebraucht werden --------------------------

    def me(self) -> dict:
        return self.call("getMe")

    def updates(self, offset: int, limit: int = 10) -> list[dict]:
        # long polling: die Verbindung bleibt offen, bis etwas kommt. Das
        # spart auf einem kleinen Gerät die Aufwachzyklen des Pollens.
        result = self.call(
            "getUpdates", offset=offset, limit=limit,
            timeout=max(self.timeout - 5, 1),
            allowed_updates=json.dumps(["message"]),
        )
        return result if isinstance(result, list) else []

    def send(self, chat_id: int, text: str) -> dict:
        return self.call("sendMessage", chat_id=chat_id, text=text)

    def typing(self, chat_id: int) -> None:
        """Die Schreibanzeige setzen. Darf scheitern, ohne zu stören."""
        try:
            self.call("sendChatAction", chat_id=chat_id, action="typing")
        except TelegramError as exc:
            log.debug("Schreibanzeige ging nicht: %s", exc)

@dataclass
class Bot:
    """Der Telegram-Bot als Tür in eine bestehende Sitzung."""

    api: TelegramAPI
    session: Session
    allowed: frozenset[int]
    on_state: object = None
    poll_pause: float = 1.0
    _offset: int = field(default=0, repr=False)
    _stop: threading.Event = field(default_factory=threading.Event, repr=False)

    def __post_init__(self) -> None:
        if not self.allowed:
            raise ValueError(
                "Kein erlaubter Absender eingetragen. Ein offener Bot mit "
                "Werkzeugzugriff wäre ein Fernzugang für jeden, der die "
                "Bot-Adresse kennt."
            )
        self.allowed = frozenset(int(x) for x in self.allowed)

    # --- Eingang ----------------------------------------------------------

    def parse(self, raw: dict) -> Update | None:
        """Aus einem Roh-Update das Nötige ziehen, sonst ``None``.

        Alles, was keine Textnachricht ist (Bilder, Beitritte, Bearbeitungen),
        wird still übergangen — aber der Zähler rückt trotzdem vor, sonst
        bekommt man dieselbe Nachricht endlos wieder.
        """
        msg = raw.get("message")
        if not isinstance(msg, dict):
            return None
        text = msg.get("text")
        chat = msg.get("chat") or {}
        user = msg.get("from") or {}
        if not text or "id" not in chat:
            return None
        return Update(
            update_id=int(raw.get("update_id", 0)),
            chat_id=int(chat["id"]),
            user_id=int(user.get("id", 0)),
            text=str(text),
            name=str(user.get("first_name") or user.get("username") or ""),
        )

    def permitted(self, upd: Update) -> bool:
        return upd.user_id in self.allowed

    # --- Verarbeitung -----------------------------------------------------

    def handle(self, upd: Update) -> str | None:
        """Eine Nachricht beantworten. Gibt den gesendeten Text zurück."""
        if not self.permitted(upd):
            log.warning("Abgewiesen: Nutzer %s (%s)", upd.user_id, upd.name)
            self._send(upd.chat_id,
                       "Wir kennen uns nicht. Ich rede nur mit Eingetragenen.")
            return None

        cmd = upd.text.strip().lower()
        if cmd.startswith("/"):
            answer = self._command(cmd)
            if answer is not None:
                self._send(upd.chat_id, answer)
                return answer

        self.api.typing(upd.chat_id)
        self._state("denkt")
        turn: Turn = self.session.ask(upd.text, CHANNEL)
        self._state("fehler" if turn.error else "spricht")
        self._send(upd.chat_id, turn.text)
        return turn.text

    def _command(self, cmd: str) -> str | None:
        """Die drei Befehle, die ein Bot ohne Bildschirm braucht."""
        head = cmd.split()[0].split("@")[0]
        if head in ("/start", "/hilfe", "/help"):
            return ("Ich bin Chimera. Schreib einfach los.\n"
                    "/status — was gerade läuft\n"
                    "/neu — Gespräch von vorn")
        if head == "/status":
            busy = self.session.busy_channel
            turns = self.session.turns(1)
            last = turns[-1] if turns else None
            lines = [f"Beschäftigt: {busy}" if busy else "Bereit."]
            if last:
                lines.append(
                    f"Zuletzt über {last.channel}: "
                    f"{last.provider or '?'}/{last.model or '?'}, "
                    f"{last.tool_calls} Werkzeugaufrufe"
                    + (" (Rückfall)" if last.fell_back else "")
                )
            return "\n".join(lines)
        if head in ("/neu", "/reset"):
            # Über beide Türen, nicht nur für Telegram — sonst hätte der
            # Kanal einen eigenen Zustand und Regel 5d wäre verletzt.
            self.session.agent.history.clear()
            return "Verlauf geleert. Wir fangen neu an."
        return None

    def _send(self, chat_id: int, text: str) -> None:
        """Senden, notfalls in Stücken. Ein Fehler beendet den Bot nicht."""
        text = text or "(keine Antwort)"
        try:
            for part in _split(text, MAX_MESSAGE):
                self.api.send(chat_id, part)
        except TelegramError as exc:
            log.error("Senden gescheitert: %s", exc)

    def _state(self, what: str) -> None:
        """Den Zustand ans Gesicht melden — eine Anfrage sieht man ihm an."""
        if self.on_state is None:
            return
        try:
            self.on_state(what)
        except Exception as exc:                      # noqa: BLE001
            log.debug("Zustandsmeldung ging nicht: %s", exc)

    # --- Lauf -------------------------------------------------------------

    def poll_once(self) -> int:
        """Einmal abholen und alles Eingegangene verarbeiten."""
        try:
            batch = self.api.updates(self._offset)
        except TelegramError as exc:
            log.warning("Abholen ging nicht: %s", exc)
            return 0

        done = 0
        for raw in batch:
            uid = int(raw.get("update_id", 0))
            self._offset = max(self._offset, uid + 1)
            upd = self.parse(raw)
            if upd is None:
                continue
            try:
                self.handle(upd)
                done += 1
            except Exception:                         # noqa: BLE001
                # Eine kaputte Nachricht darf den Bot nicht mitnehmen —
                # der Zähler steht schon vor, sie kommt nicht wieder.
                log.exception("Nachricht %s nicht verarbeitet", uid)
        return done

    def run(self) -> None:
        """Bis ``stop()`` laufen."""
        who = self.api.me()
        log.info("Telegram bereit als @%s, %d erlaubte Absender",
                 who.get("username", "?"), len(self.allowed))
        self._stop.clear()
        while not self._stop.is_set():
            self.poll_once()
            if self.poll_pause:
                self._stop.wait(self.poll_pause)

    def stop(self) -> None:
        self._stop.set()

def _split(text: str, size: int) -> list[str]:
    """Lange Texte an Zeilengrenzen teilen, statt hart abzuschneiden."""
    if len(text) <= size:
        return [text]
    parts, rest = [], text
    while len(rest) > size:
        cut = rest.rfind("\n", 0, size)
        if cut < size // 2:
            cut = rest.rfind(" ", 0, size)
        if cut < size // 2:
            cut = size
        parts.append(rest[:cut].rstrip())
        rest = rest[cut:].lstrip()
    if rest:
        parts.append(rest)
    return parts

def from_env(session: Session, env: dict | None = None, *, on_state=None) -> Bot:
    """Einen Bot aus der Umgebung bauen.

    Zugangsdaten stehen nicht im Repo (§12): ``CHIMERA_TELEGRAM_TOKEN`` und
    ``CHIMERA_TELEGRAM_ALLOWED`` (Kennungen, durch Komma getrennt).
    """
    import os

    env = os.environ if env is None else env
    token = (env.get("CHIMERA_TELEGRAM_TOKEN") or "").strip()
    if not token:
        raise ValueError(
            "CHIMERA_TELEGRAM_TOKEN ist nicht gesetzt — Token von "
            "@BotFather holen und in die Umgebung legen, nicht ins Repo."
        )

    raw = (env.get("CHIMERA_TELEGRAM_ALLOWED") or "").strip()
    allowed = set()
    for piece in raw.replace(";", ",").split(","):
        piece = piece.strip()
        if not piece:
            continue
        try:
            allowed.add(int(piece))
        except ValueError:
            raise ValueError(
                f"CHIMERA_TELEGRAM_ALLOWED: {piece!r} ist keine Kennung. "
                "Erwartet werden Zahlen, etwa '12345678,87654321'."
            ) from None
    if not allowed:
        raise ValueError(
            "CHIMERA_TELEGRAM_ALLOWED ist leer. Die eigene Kennung nennt "
            "@userinfobot."
        )

    return Bot(TelegramAPI(token), session, frozenset(allowed),
               on_state=on_state)
