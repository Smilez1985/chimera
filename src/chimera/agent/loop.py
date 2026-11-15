"""Die Agent-Schleife: fragen, Werkzeuge benutzen, antworten.

Hier laufen die Teile zusammen. Der Ablauf je Umlauf:

    Kontext prüfen ── gegen das Modell, das WIRKLICH bedient
      ↓
    Modell fragen ── über die Aufgaben-Registry, mit Rückfall
      ↓
    Werkzeugaufruf? ── nein: fertig
      ↓
    reparieren + vorprüfen ── kaputtes JSON retten, Pflichtfelder
      ↓
    Schleife prüfen ── VOR der Ausführung
      ↓
    Sicherheitsschranke ── keine Shell, kein Ausbruch
      ↓
    ausführen, vermerken ── Ergebnis geht zurück ins Gespräch

**Zwei Wege, nativ zuerst** (DESIGN Regel „Aufrufe, nicht Text“, smilet 12.11.): Liefert der
Anbieter strukturierte Werkzeugaufrufe (``Reply.werkzeuge``), werden sie
ausgeführt und die Runde geht zurück ans Modell. Meldet er keine, wird wie
bisher ein ``TOOL: name {json}`` aus dem Text gelesen — das trägt Modelle
ohne Werkzeug-Schnittstelle. Der Textweg bleibt also Rückfall, nicht
Ersatz: zwei Wege gleichzeitig wären die Fehlerklasse aus 10g.
"""

from __future__ import annotations

import json
import logging
import re
import time as _t
from dataclasses import dataclass, field

from .context import Action, estimate_tokens, policy_for
from .loopguard import Config as GuardConfig
from .loopguard import Level, LoopGuard
from .preflight import PreflightError, preflight
from .tools import Toolbox
from .verdichten import schnittindex, verdichte

#: Wie viele native Aufrufe je Runde ausgeführt werden (DESIGN, Regel „Aufrufe, nicht Text“).
MAX_WERKZEUGE_JE_RUNDE = 3

log = logging.getLogger(__name__)

#: Wie viel von Argumenten und Ergebnis ins Protokoll geht. Das Protokoll
#: soll zeigen, *was* lief — es ist kein Verlaufsersatz (DESIGN 8d).
PROTO_OK = 120

def _kurz(text: str, grenze: int = PROTO_OK) -> str:
    """Einen Wert einzeilig und kurz fürs Protokoll (Zeilenumbrüche raus)."""
    s = " ".join(str(text or "").split())
    return s if len(s) <= grenze else s[:grenze] + " …"

#: Die Felder, die ein Anbieter-Verbrauch traegt. Alles andere wird nicht
#: gezaehlt -- ein unbekanntes Feld waere eine Zahl ohne Bedeutung.
VERBRAUCH_FELDER = ("eingabe", "ausgabe", "cache_neu", "cache_treffer", "denken")

def _verbrauch_addieren(summe: dict, meldung: dict) -> dict:
    """Verbrauch einer Runde auf die Summe des Auftrags addieren.

    Nur ganze Zahlen zaehlen; fehlt ein Feld, bleibt die Summe gleich (kein
    ``0`` vortaeuschen, Regel „nichts erfinden"). Ohne Meldung passiert
    nichts -- ein Anbieter, der keinen Verbrauch nennt, wird nicht geschaetzt.
    """
    if not isinstance(meldung, dict) or not meldung:
        return summe
    for feld in VERBRAUCH_FELDER:
        wert = meldung.get(feld)
        if isinstance(wert, bool) or not isinstance(wert, int):
            continue
        summe[feld] = summe.get(feld, 0) + wert
    return summe

def _args_kurz(args: dict | str) -> str:
    """Die Argumente eines Aufrufs fürs Protokoll."""
    if isinstance(args, dict):
        return "{" + ", ".join(f"{k}={_kurz(v, 40)!r}" for k, v in args.items()) + "}"
    return _kurz(args, 80)

#: So ruft das Modell ein Werkzeug auf. Bewusst schlicht, damit auch
#: kleine Modelle es treffen.
CALL_RE = re.compile(
    r"^\s*TOOL:\s*([a-z_]+)\s*(\{.*)$",
    re.MULTILINE | re.DOTALL,
)

SYSTEM_TEMPLATE = """Du bist Chimera, ein Gerät mit einem Gesicht auf einem kleinen Bildschirm.

Du kannst Werkzeuge benutzen. Dafür schreibst du eine Zeile in genau dieser Form:

TOOL: name {"feld": "wert"}

Danach hörst du auf zu schreiben und wartest auf das Ergebnis. Pro Antwort
höchstens ein Werkzeugaufruf. Wenn du kein Werkzeug brauchst, antworte
einfach normal.

Verfügbare Werkzeuge:
{tools}

Halte dich kurz. Du läufst auf einem kleinen Gerät, und deine Antworten
werden vorgelesen."""

#: Der Prompt fuer den **nativen** Weg (smilez, 15.11.2026). Hier steht
#: bewusst **keine** Werkzeugliste und **keine** Aufrufsyntax als Text:
#: Die Werkzeuge gehen als Schnittstelle mit (`tools` im Anfragerumpf), das
#: Modell triggert sie nur, die Arbeit macht der Harness. Zwei Gruende:
#: Erstens kostet eine zweite Beschreibung Tokens in jeder Anfrage — und
#: zwar in jeder Runde. Zweitens war der Textweg die Quelle eines echten
#: Fehlers: ein `TOOL:` im Text ist keine Werkzeugnachricht, DeepSeek
#: lehnte den Verlauf mit HTTP 422 ab (am Pi gemessen, 15.11.2026).
SYSTEM_TEMPLATE_NATIV = """Du bist Chimera, ein Gerät mit einem Gesicht auf einem kleinen Bildschirm.

Du hast Werkzeuge. Sie sind dir als Schnittstelle hinterlegt und werden
aufgerufen, nicht geschrieben: Rufe ein Werkzeug über die Werkzeugschnitt-
stelle auf (tool call). Schreibe einen Aufruf NIE als Text in die Antwort
(kein "TOOL: …") — Text dort wird nicht ausgeführt, kostet nur Platz und
ist ein Fehler.

Rufe ein Werkzeug nur, wenn du es wirklich brauchst. Ohne Werkzeug
antwortest du einfach normal.

Halte dich kurz. Du läufst auf einem kleinen Gerät, und deine Antworten
werden vorgelesen."""

#: Der Prompt fuer den **Textweg** — nur fuer Anbieter ohne
#: Werkzeug-Schnittstelle. Er ist der Rueckfall, nicht der Normalfall.
SYSTEM_TEMPLATE = """Du bist Chimera, ein Gerät mit einem Gesicht auf einem kleinen Bildschirm.

Du kannst Werkzeuge benutzen. Dafür schreibst du eine Zeile in genau dieser Form:

TOOL: name {"feld": "wert"}

Danach hörst du auf zu schreiben und wartest auf das Ergebnis. Pro Antwort
höchstens ein Werkzeugaufruf. Wenn du kein Werkzeug brauchst, antworte
einfach normal.

Verfügbare Werkzeuge:
{tools}

Halte dich kurz. Du läufst auf einem kleinen Gerät, und deine Antworten
werden vorgelesen."""

#: Was das Modell hört, wenn es trotz Schnittstelle einen Textaufruf
#: schreibt. Ohne diese Ruege wiederholte es den Fehler bis zum Ende der
#: Umlaeufe — die Antwort waere nie ausgefuehrt worden.
RUEGE_TEXT_AUFTRAG = """Du hast einen Werkzeugaufruf als TEXT geschrieben. Er wurde NICHT ausgeführt.
Werkzeuge laufen über die Werkzeugschnittstelle (tool call), nicht über Text.
Antworte erneut — mit einem echten Werkzeugaufruf oder mit deiner Antwort."""

#: Was der Nutzer hoert, wenn das Modell auch nach der Ruege nur einen
#: Textaufruf schreibt. Die Behauptung "ich habe X getan" waere gelogen.
NICHT_AUSGEFUEHRT = ("Ich wollte gerade ein Werkzeug benutzen, aber der Aufruf "
                     "kam nicht über die Werkzeugschnittstelle — es wurde "
                     "nichts ausgeführt.")

#: Der feste Teil der Gesichtsanweisung (smilez, 14.11.2026). Er gehört zum
#: **stabilen** Anfang des Prompts: gleiche Werkzeuge, gleiche Reihenfolge,
#: damit der Cache trifft (DESIGN 5q). Der **aktive** Ausdruck steht
#: ausdrücklich NICHT hier -- ein wechselnder Wert im Systemprompt macht
#: jeden Cache ungültig -- sondern als letzte Zeile der neuen Nachricht.
GESICHT_TEMPLATE = """

Dein Gesicht:
Du hast ein Gesicht auf einem kleinen Display. Führe es bei jeder Antwort
bewusst — es ist der einzige Teil von dir, den man sieht.
- Kürzester Weg: set_face <NAME>. Mischen geht mit A+B, gewichten mit A+B:0.3.
- Nur bei einer Änderung: zeigt das Gesicht den Ausdruck schon, ist set_face
  unnötig. Einen neuen Ausdruck (mood_anlegen) nur, wenn keiner der
  vorhandenen passt — nicht jeder Turn braucht einen.
- Namen finden: moods (optional mit "suche"). Eigenen löschen:
  mood_entfernen.
- "active=mood_…" am Ende der Nachricht ist der Ausdruck, der gerade zu
  sehen ist. Er ist der Stand vor deiner Antwort, keine Frage an dich."""


@dataclass
class Step:
    """Was in einem Umlauf passiert ist — fürs Protokoll."""

    kind: str                  # "text", "tool", "blocked", "error"
    detail: str = ""
    tool: str | None = None


@dataclass
class Result:
    text: str
    steps: list[Step] = field(default_factory=list)
    provider: str = ""
    model: str = ""
    fell_back: bool = False
    tool_calls: int = 0
    #: Was dieser Auftrag laut Anbietern gekostet hat (Summe aller Runden,
    #: DESIGN „Verbrauch" 15.11.2026). Leer heißt: niemand hat es gesagt.
    verbrauch: dict = field(default_factory=dict)


class Agent:
    """Ein Auftrag, ein Gespräch, ein Zustand."""

    def __init__(self, registry, toolbox: Toolbox, *, task: str = "gespraech",
                 max_turns: int = 8, guard: GuardConfig | None = None,
                 on_state=None, skills=None, memory=None):
        self.registry = registry
        self.tools = toolbox
        self.task = task
        self.max_turns = max_turns
        self.guard = LoopGuard(guard, known_tools=toolbox.names())
        #: Werkzeugschemas mitschicken? Aus, wenn das Modell sie nicht kann
        #: (fehlt noch: Entscheidung aus dem gemessenen `tools`, ROADMAP Regel „Aufrufe, nicht Text“).
        self._nativ = True
        self.history: list[dict] = []
        #: Rückruf für den Zustand — damit das Gesicht zeigt, was läuft.
        self.on_state = on_state
        self.skills = skills
        self.memory = memory

        # Skills als Werkzeug anmelden, wenn welche da sind. Ein Katalog
        # ohne Abrufmöglichkeit wäre ein offenes Ende (Regel 10h).
        if skills is not None:
            from .preflight import ToolSpec
            toolbox.add(ToolSpec(
                "read_skill",
                "Die Anleitung zu einem Skill lesen, bevor du ihn benutzt.",
                {"name": "Name des Skills"},
                ("name",),
            ), self._read_skill)
            self.guard = LoopGuard(guard, known_tools=toolbox.names())

    def _read_skill(self, name: str) -> str:
        sk = self.skills.get(name) if self.skills else None
        if sk is None:
            verf = ", ".join(s.name for s in self.skills.usable()) if self.skills else ""
            return f"Skill {name!r} gibt es nicht. Verfügbar: {verf}"
        if not sk.usable:
            return f"Skill {sk.name} ist hier nicht nutzbar: {sk.reason}"
        return sk.read()

    # --- Hilfen -----------------------------------------------------------

    def _system(self) -> str:
        if self._nativ:
            # Die Werkzeuge gehen als Schnittstelle mit; eine zweite
            # Aufzaehlung im Prompt kostete Tokens in jeder Runde und lehrte
            # den Textweg, der nicht mehr ausgefuehrt wird (15.11.2026).
            text = SYSTEM_TEMPLATE_NATIV
        else:
            lines = []
            for spec in (t.spec for t in self.tools._tools.values()):
                args = ", ".join(spec.params) or "keine"
                lines.append(f"- {spec.name}({args}): {spec.description}")
            text = SYSTEM_TEMPLATE.replace("{tools}", "\n".join(lines))

        # Die Anweisung, das Gesicht zu führen, gehört nur hinein, wenn es
        # eines gibt — ein Gerät ohne Anzeige hätte sonst ein Werkzeug, das
        # immer "Keine Anzeige angeschlossen" antwortet (Regel 8a).
        if getattr(self.tools, "face", None) is not None:
            text += GESICHT_TEMPLATE

        if self.skills is not None:
            cat = self.skills.catalog()
            if cat:
                text += ("\n\nSkills (Anleitungen, mit read_skill abrufbar):\n"
                         + cat)

        if self.memory is not None:
            ctx = self.memory.context()
            if ctx:
                text += "\n\n" + ctx

        return text

    def _mit_laufzeit(self, prompt: str) -> str:
        """Den Laufzeitstand an die **neue Nachricht** hängen, nicht in den
        Systemprompt (DESIGN 5q: ein wechselnder Wert vorn macht jeden Cache
        ungültig; der Verlauf wird nur angehängt).

        Die Kurzform nennt den Ausdruck so, wie das Modell ihn wieder
        setzen kann: ``active=mood_idle``.
        """
        gesicht = getattr(self.tools, "face", None)
        if gesicht is None:
            return prompt
        name = str(getattr(getattr(gesicht, "state", None), "mood_name", "") or "")
        kurz = re.sub(r"[^a-z0-9]+", "_", name.strip().lower()).strip("_")
        return f"{prompt}\n\n[Gesicht: active=mood_{kurz or 'unbekannt'}]"

    def _state(self, what: str) -> None:
        if self.on_state:
            try:
                self.on_state(what)
            except Exception as exc:       # das Gesicht darf nie stören
                log.debug("Zustandsmeldung fehlgeschlagen: %s", exc)

    def _check_context(self, conn) -> Action:
        pol = policy_for(conn)
        used = estimate_tokens(self.history)
        return pol.check(used)

    # --- der Lauf ---------------------------------------------------------

    def run(self, prompt: str, *, anbieter: str = "", modell: str = "",
            denken: str = "") -> Result:
        """Ein Auftrag. Jede Antwort endet mit ``wartet`` (DESIGN: Regel „Sprechgesicht“) -- auch
        bei einem Fehler, sonst bleibt das Gesicht auf dem letzten Ausdruck
        stehen.

        ``anbieter``/``modell``/``denken`` sind die ausdrueckliche Wahl einer
        Tuer (Web, Telegram, CLI). Sie gilt nur fuer diesen Auftrag und
        **ohne** Rueckfall auf einen anderen Anbieter: Wer DeepSeek waehlt,
        will nicht stillschweigend Ollama bekommen (DESIGN, Modellwahl).
        """
        try:
            return self._run(prompt, anbieter=anbieter, modell=modell, denken=denken)
        finally:
            self._state("wartet")

    def _run(self, prompt: str, *, anbieter: str = "", modell: str = "",
             denken: str = "") -> Result:
        self.guard.reset()
        steps: list[Step] = []
        system = self._system()
        self.history.append({"role": "user", "content": self._mit_laufzeit(prompt)})

        provider = model = ""
        fell_back = False
        text = ""
        geruegt = False          # ein Textaufruf wird einmal geruegt, nicht oefter
        # Was dieser Auftrag gekostet hat: je Runde addiert (DESIGN
        # „Verbrauch" 15.11.2026). Leere Meldung des Anbieters zaehlt nicht.
        kosten: dict = {}

        for turn in range(self.max_turns):
            self._state("denkt")

            targets = self.registry.resolve(self.task)
            if targets:
                action = self._check_context(targets[0][0])
                if action is Action.COMPACT:
                    self._compact()
                    steps.append(Step("compact", "Verlauf verdichtet"))
                elif action is Action.EXHAUSTED:
                    steps.append(Step("error", "Kontext voll"))
                    return Result(
                        "Mein Gedächtnis für dieses Gespräch ist voll. "
                        "Fang bitte ein neues an.",
                        steps, provider, model, fell_back, self.guard.calls)

            # Die Wahl jeder Runde neu: sie gilt fuer den ganzen Auftrag.
            wahl = f"{anbieter}/{modell}" if anbieter and modell else (anbieter or "")
            reply = self.registry.call(
                self.task, "", self.history, system,
                bevorzugt=wahl or None,
                **({"werkzeuge": self.tools.schemas()} if self._nativ else {}),
                **({"denken": denken} if denken else {}))
            provider, model = reply.provider, reply.model
            fell_back = fell_back or reply.fell_back
            text = reply.text
            _verbrauch_addieren(kosten, getattr(reply, "verbrauch", {}))

            # 1. Nativ: das Modell hat Werkzeuge aufgerufen (DESIGN, Regel „Aufrufe, nicht Text“).
            #    Ein Aufruf ohne Text ist gueltig -- hier wird nicht auf
            #    `text` geschaut, sondern auf die Liste.
            aufrufe_nativ = list(getattr(reply, "werkzeuge", ()) or [])
            if aufrufe_nativ:
                aufrufe = aufrufe_nativ[:MAX_WERKZEUGE_JE_RUNDE]
                log.info("Runde %d: %s/%s rief nativ %s", turn + 1, provider,
                         model, ", ".join(a["name"] for a in aufrufe))
                self.history.append({
                    "role": "assistant", "content": text,
                    # Ollama-Form; die Uebersetzung je Anbieter macht das
                    # Gateway (Regel „Aufrufe, nicht Text“), hier steht das neutrale Ergebnis.
                    "tool_calls": [{"function": {"name": a["name"],
                                                 "arguments": a.get("argumente", {})}}
                                   for a in aufrufe],
                })
                for a in aufrufe:
                    out = self._fuehre_aus(a["name"], a.get("argumente") or {}, steps)
                    self.history.append({"role": "tool", "content": out,
                                         "tool_name": a["name"]})
                continue

            # Nativer Weg: Ein Textaufruf wird NICHT ausgefuehrt (smilez,
            # 15.11.2026). Er kostet Tokens in jeder Runde, kommt nie als
            # Werkzeugnachricht an (DeepSeek: HTTP 422 "missing field
            # tool_call_id") und tauescht eine Ausfuehrung vor, die es nicht
            # gibt. Stattdessen eine Ruege und eine neue Runde. Ein **zweiter**
            # Textaufruf wird nicht mehr als Antwort durchgereicht (er
            # behauptet eine Ausfuehrung, die es nicht gab) — der Aufruf fliegt
            # aus dem Text, und der Nutzer hoert, dass es nicht ging.
            if self._nativ:
                if CALL_RE.search(text):
                    if not geruegt:
                        geruegt = True
                        log.warning("Textaufruf statt Werkzeugschnittstelle "
                                    "(geruegt): %s", _kurz(text))
                        self.history.append({"role": "assistant",
                                             "content": text})
                        self.history.append({"role": "user",
                                             "content": RUEGE_TEXT_AUFTRAG})
                        steps.append(Step("error",
                                          "Werkzeugaufruf im Text — nicht ausgeführt"))
                        continue
                    log.warning("Zweiter Textaufruf verworfen: %s", _kurz(text))
                    reste = CALL_RE.sub("", text).strip()
                    steps.append(Step("error",
                                      "Werkzeugaufruf im Text — verworfen"))
                    text = reste or NICHT_AUSGEFUEHRT
                self.history.append({"role": "assistant", "content": text})
                steps.append(Step("text", text[:80]))
                self._state("spricht")
                return Result(text, steps, provider, model, fell_back,
                              self.guard.calls, dict(kosten))

            call = CALL_RE.search(text)
            if not call:
                self.history.append({"role": "assistant", "content": text})
                steps.append(Step("text", text[:80]))
                self._state("spricht")
                return Result(text, steps, provider, model, fell_back,
                              self.guard.calls, dict(kosten))

            name, raw_args = call.group(1), call.group(2)
            before = text[: call.start()].strip()
            self.history.append({"role": "assistant", "content": text})

            # 1. Reparieren und vorprüfen
            spec = self.tools.get(name)
            if spec is None:
                out = (f"Fehler: Werkzeug {name!r} gibt es nicht. "
                       f"Verfügbar: {', '.join(self.tools.names())}.")
                verdict = self.guard.check(name, raw_args)
                if verdict.blocked:
                    out = verdict.message or out
                    steps.append(Step("blocked", out, name))
                    self.guard.record(name, raw_args, out)
                    return Result(before or out, steps, provider, model,
                                  fell_back, self.guard.calls, dict(kosten))
                self.guard.record(name, raw_args, out)
                steps.append(Step("error", out, name))
                self.history.append({"role": "user", "content": out})
                continue

            try:
                args = preflight(spec.spec, raw_args)
            except PreflightError as exc:
                out = str(exc)
                self.guard.record(name, raw_args, out)
                steps.append(Step("error", out, name))
                self.history.append({"role": "user", "content": out})
                continue

            # 2. Schleife prüfen -- vor der Ausführung
            verdict = self.guard.check(name, args)
            if verdict.level is Level.STOP:
                steps.append(Step("blocked", verdict.message or "", name))
                self._state("verwirrt")
                return Result(before or (verdict.message or ""), steps,
                              provider, model, fell_back, self.guard.calls,
                              dict(kosten))
            if verdict.level is Level.BLOCK:
                out = verdict.message or "Aufruf verhindert."
                self.guard.record(name, args, out)
                steps.append(Step("blocked", out, name))
                self._state("verwirrt")
                self.history.append({"role": "user", "content": out})
                continue
            if verdict.level is Level.WARN and verdict.message:
                self.history.append({"role": "user", "content": verdict.message})
                steps.append(Step("warn", verdict.message, name))

            # 3. Ausführen -- die Schranke sitzt in der Toolbox
            self._state("arbeitet")
            out = self.tools.call(name, args)
            self.guard.record(name, args, out)
            steps.append(Step("tool", out[:80], name))
            self.history.append({"role": "user",
                                 "content": f"Ergebnis von {name}:\n{out}"})

        # Umläufe aufgebraucht: das ist eine Auskunft, kein Absturz.
        steps.append(Step("error", f"{self.max_turns} Umläufe aufgebraucht"))
        return Result(
            text or "Ich komme hier nicht weiter.",
            steps, provider, model, fell_back, self.guard.calls,
            dict(kosten))

    def _fuehre_aus(self, name: str, args: dict, steps: list[Step]) -> str:
        """Ein Werkzeug ausführen, das das Modell selbst benannt hat (Regel „Aufrufe, nicht Text“).

        Dieselben Schranken wie im Textweg: unbekanntes Werkzeug, Schleife,
        Sicherheit — die sitzt in der Toolbox. Die Argumente kommen hier
        schon als Objekt; repariert werden muss nichts.
        """
        spec = self.tools.get(name)
        if spec is None:
            out = (f"Fehler: Werkzeug {name!r} gibt es nicht. "
                   f"Verfügbar: {', '.join(self.tools.names())}.")
            self.guard.record(name, args, out)
            steps.append(Step("error", out, name))
            return out
        verdict = self.guard.check(name, args)
        if verdict.level is Level.STOP:
            out = verdict.message or "Angehalten."
            steps.append(Step("blocked", out, name))
            self._state("verwirrt")
            return out
        if verdict.level is Level.BLOCK:
            out = verdict.message or "Aufruf verhindert."
            self.guard.record(name, args, out)
            steps.append(Step("blocked", out, name))
            self._state("verwirrt")
            return out
        if verdict.level is Level.WARN and verdict.message:
            steps.append(Step("warn", verdict.message, name))

        self._state("arbeitet")
        start = _t.monotonic()
        out = self.tools.call(name, args)
        self.guard.record(name, args, out)
        steps.append(Step("tool", out[:80], name))
        # Protokoll (DESIGN, Regel „Aufrufe, nicht Text", Nachtrag 15.11.2026):
        # ohne diese Zeile war "es passiert nichts" nicht prüfbar.
        log.info("Werkzeug %s %s -> %d Zeichen in %.2f s: %s",
                 name, _args_kurz(args), len(out),
                 _t.monotonic() - start, _kurz(out))
        return out

    def _compact(self) -> None:
        """Den Verlauf verdichten — **ohne Modell** (DESIGN, Regel 8d).

        Bis zum 14.11.2026 fasste hier ein billiges Modell fünf Sätze
        zusammen, und der Rest des Verlaufs war weg. Jetzt gilt:
        Gelöscht wird nichts, ins Fenster kommt ein Gerüst mit
        **Fundstellen** (``verlauf.jsonl``, Zeilenbereich), die offenen
        Punkte und Entscheidungen **wörtlich**, und die letzten Turns
        bleiben wörtlich stehen. Das Werkzeug ``nachlesen`` holt den
        Wortlaut zurück.

        Ohne Ablage (Tests, Türen ohne Sitzungsdatei) wird derselbe Text
        gebaut, nur ohne Zeilenbezug — nicht „irgendwie gekürzt".
        """
        if len(self.history) <= 6:
            return
        gesamt = list(self.history)
        # Die Einheit ist die **Runde**, nicht die Nachricht: Ein Schnitt
        # zwischen Werkzeugaufruf und Ergebnis wäre sinnentstellend
        # (Papier OPENMINIS-MUSTER §2.3, Punkt 7).
        schnitt = schnittindex(gesamt)

        von = bis = 0
        if hasattr(self.history, "zeilenbereich"):
            try:
                # Fundstelle der Nachrichten, die verdichtet werden — der
                # wörtliche Rest am Ende bekommt keinen Verweis.
                von, bis = self.history.zeilenbereich(
                    schnitt, abstand=len(gesamt) - schnitt)
            except Exception as exc:            # Ablage kaputt: kein Abbruch
                log.warning("Zeilenbereich nicht lesbar: %s", exc)

        bericht = verdichte(gesamt, von=von or 1, bis=bis or 0)
        if not bericht.vollstaendig:
            log.warning("Verdichtung unvollständig: %d Abschnitte ausgelassen",
                        bericht.ausgelassen)

        if hasattr(self.history, "verdichten"):
            # Auf der Platte: das Protokoll behält alles (Regel 8d).
            self.history.verdichten(bericht.text, len(gesamt) - schnitt,
                                    zeilen_von=bericht.zeilen_von,
                                    zeilen_bis=bericht.zeilen_bis)
        else:
            rest = gesamt[schnitt:]
            self.history = ([{"role": "user", "content": bericht.text}]
                            if bericht.text else []) + rest
