"""Claude — getrennt nach Abo und API-Schlüssel.

Zwei Anbieter, nicht einer mit zwei Betriebsarten. Der Unterschied ist
nicht technisch, sondern für den Nutzer wesentlich:

* **Abo** (Claude Code / Cowork): belastet ein Kontingent, keine
  Einzelabrechnung, kann aber erschöpft sein.
* **API-Schlüssel**: wird abgerechnet, dafür keine Kontingentgrenze.

Wer beides eingerichtet hat, soll beides benutzen können — und **sehen,
was gerade zieht** (Regel 5h). Deshalb zwei Einträge in der Registry,
zwei Zeilen in der Übersicht, und in der Antwort steht die Herkunft.

Ein sinnvoller Aufbau nutzt genau das aus:

    gespraech → [ claude-abo/sonnet-5, claude-api/sonnet-5, ollama/qwen ]

Erst das Kontingent, dann bezahlt, dann lokal. Oder umgekehrt, je nachdem
was einem lieber ist.

## Die Client-Kennung

Für den Abo-Weg gilt, was der eigene Beitrag an OpenModels/OpenMinis
(PR #407) behebt: Anthropic sperrt neue Modelle hinter einer
**Mindestversion des CLI-Clients** und prüft das über die Kennung im
Anfragekopf. Eine fest einkompilierte Kennung veraltet — und ein Modell,
das eigentlich verfügbar wäre, wird mit ``claude_code_version_too_old``
abgelehnt.

Die Kennung wird deshalb **zur Laufzeit ermittelt** (Regel 5b): aus der
installierten CLI, mit gepflegtem Rückfallwert. Auf einem Pi Zero kostet
das spürbar, also einmal beim Prozessstart und danach aus dem
Zwischenspeicher.
"""

from __future__ import annotations

import json
import logging
import os
import re
import shutil
import subprocess
import urllib.error
import urllib.request

from .base import Access, Connector, CostClass, LLMError, RateLimitError, Unavailable

log = logging.getLogger(__name__)

#: Wird benutzt, wenn sich die installierte CLI nicht befragen lässt.
#: Gepflegt, nicht geraten -- und bewusst an einer Stelle, damit klar ist,
#: wo nachgezogen werden muss.
FALLBACK_CLI_VERSION = "2.1.284"

_VERSION_RE = re.compile(r"(\d+\.\d+\.\d+)")

_cached_version: str | None = None


def claude_cli_version(*, refresh: bool = False) -> str:
    """Die Version der installierten Claude-CLI.

    Ermittelt einmal je Prozess. ``refresh=True`` erzwingt eine neue
    Abfrage — sinnvoll nach einer Aktualisierung, nicht bei jedem Aufruf.
    """
    global _cached_version
    if _cached_version and not refresh:
        return _cached_version

    version = None
    exe = shutil.which("claude")
    if exe:
        try:
            out = subprocess.run([exe, "--version"], capture_output=True,
                                 text=True, timeout=10)
            m = _VERSION_RE.search((out.stdout or "") + (out.stderr or ""))
            if m:
                version = m.group(1)
        except Exception as exc:
            log.debug("claude --version fehlgeschlagen: %s", exc)

    if not version:
        version = FALLBACK_CLI_VERSION
        log.info("Claude-CLI nicht befragbar, nutze Rückfallkennung %s", version)

    _cached_version = version
    return version


def user_agent() -> str:
    return f"claude-cli/{claude_cli_version()}"


class _AnthropicBase(Connector):
    """Gemeinsames für beide Zugangsarten."""

    API = "https://api.anthropic.com/v1/messages"
    API_VERSION = "2023-06-01"
    supports_tools = True
    supports_streaming = True
    context_window = 200_000

    def __init__(self, default_model: str | None = None, *,
                 timeout: float = 120.0):
        self.default_model = default_model or os.environ.get(
            "ANTHROPIC_MODEL", "claude-sonnet-4-5")
        self.timeout = timeout

    def _headers(self) -> dict:
        raise NotImplementedError

    def call(self, prompt: str, history: list[dict],
             system: str | None = None, *, model: str | None = None,
             max_tokens: int = 2048, **kw) -> str:
        if not self.is_available():
            raise Unavailable(f"{self.label} ist nicht eingerichtet.")

        messages = list(history)
        messages.append({"role": "user", "content": prompt})

        payload: dict = {
            "model": model or self.default_model,
            "max_tokens": max_tokens,
            "messages": messages,
        }
        if system:
            payload["system"] = system

        req = urllib.request.Request(
            self.API, data=json.dumps(payload).encode("utf-8"),
            headers=self._headers(),
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as r:
                data = json.loads(r.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            body = ""
            try:
                body = exc.read().decode("utf-8")[:400]
            except Exception:
                pass
            if exc.code == 429:
                raise RateLimitError(f"{self.label}: Grenze erreicht") from exc
            if "claude_code_version_too_old" in body:
                # Genau der Fall, gegen den die Laufzeitermittlung gebaut
                # ist. Wenn er trotzdem auftritt, ist die Kennung veraltet.
                raise LLMError(
                    f"{self.label}: Client-Kennung zu alt "
                    f"(gemeldet: {user_agent()}). Claude-CLI aktualisieren "
                    f"oder FALLBACK_CLI_VERSION nachziehen."
                ) from exc
            raise LLMError(f"{self.label}: HTTP {exc.code} {body}") from exc
        except Exception as exc:
            raise Unavailable(f"{self.label} nicht erreichbar: {exc}") from exc

        parts = [b.get("text", "") for b in data.get("content", [])
                 if b.get("type") == "text"]
        text = "".join(parts).strip()
        if not text:
            raise LLMError(f"{self.label} lieferte eine leere Antwort.")
        return text


class ClaudeApiConnector(_AnthropicBase):
    """Claude über einen API-Schlüssel — wird abgerechnet."""

    name = "claude-api"
    access = Access.API_KEY
    cost = CostClass.METERED

    def __init__(self, api_key: str | None = None, **kw):
        super().__init__(**kw)
        self.api_key = api_key or os.environ.get("ANTHROPIC_API_KEY", "")

    def is_available(self) -> bool:
        return bool(self.api_key.strip())

    def why_unavailable(self) -> str | None:
        if not self.api_key.strip():
            return "ANTHROPIC_API_KEY ist nicht gesetzt."
        return None

    def _headers(self) -> dict:
        return {
            "content-type": "application/json",
            "x-api-key": self.api_key,
            "anthropic-version": self.API_VERSION,
        }


class ClaudeSubscriptionConnector(_AnthropicBase):
    """Claude über die Abo-Anmeldung — belastet das Kontingent.

    Die Marke wird nicht hier erzeugt: Die Erstanmeldung läuft über die
    Claude-CLI, die sie ablegt. Dieser Anbieter benutzt sie nur.

    Noch nicht gebaut ist das **Auffrischen vor Ablauf** samt Koordinator
    (``docs/PROVIDER.md``). Solange fehlt, läuft der Zugang, bis die Marke
    abläuft — dann greift der Rückfall auf das nächste Ziel. Das ist keine
    stille Lücke, sondern eine benannte (Regel 10h).
    """

    name = "claude-abo"
    access = Access.SUBSCRIPTION
    cost = CostClass.SUBSCRIPTION

    def __init__(self, token: str | None = None, **kw):
        super().__init__(**kw)
        self.token = token or os.environ.get("ANTHROPIC_OAUTH_TOKEN", "")

    def is_available(self) -> bool:
        return bool(self.token.strip())

    def why_unavailable(self) -> str | None:
        if not self.token.strip():
            return ("Keine Abo-Anmeldung gefunden. Mit der Claude-CLI "
                    "anmelden, dann ANTHROPIC_OAUTH_TOKEN setzen.")
        return None

    def _headers(self) -> dict:
        return {
            "content-type": "application/json",
            "authorization": f"Bearer {self.token}",
            "anthropic-version": self.API_VERSION,
            "anthropic-beta": "oauth-2025-04-20",
            # Zur Laufzeit ermittelt, nie einkompiliert (Regel 5b, PR #407)
            "user-agent": user_agent(),
        }
