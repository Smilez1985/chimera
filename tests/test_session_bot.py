"""Tests für Sitzung (Regel 5d) und Telegram-Tür.

Kein Netz: Die API wird durch ein Doppel ersetzt, das dieselben Methoden
anbietet. Geprüft wird der echte Code — die Tests rechnen nichts nach,
sie rufen auf.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from chimera.agent.session import DIRECT, Channel, Session  # noqa: E402
from chimera.bot.telegram import (  # noqa: E402
    CHANNEL, Bot, TelegramAPI, TelegramError, _split, from_env,
)

PASS = FAIL = 0
def ok(m):
    global PASS; PASS += 1; print(f"  ok    {m}")
def bad(m):
    global FAIL; FAIL += 1; print(f"  FAIL  {m}")
def check(m, got, want):
    ok(m) if got == want else bad(f"{m} — erwartet {want!r}, bekam {got!r}")
def raises(m, exc, fn, *a, **kw):
    try:
        fn(*a, **kw)
    except exc:
        ok(m)
    except Exception as e:                            # noqa: BLE001
        bad(f"{m} — falscher Fehler: {type(e).__name__}: {e}")
    else:
        bad(f"{m} — kein Fehler")

# --- Doppel ---------------------------------------------------------------

class FakeResult:
    def __init__(self, text, provider="ollama", model="qwen", calls=0,
                 fell_back=False):
        self.text = text
        self.provider = provider
        self.model = model
        self.tool_calls = calls
        self.fell_back = fell_back

class FakeAgent:
    """Merkt sich, was hereinkam — und hält einen Verlauf wie das Original."""

    def __init__(self, answer="Antwort.", boom=False):
        self.answer = answer
        self.boom = boom
        self.history = []
        self.seen = []

    def run(self, prompt):
        self.seen.append(prompt)
        self.history.append({"role": "user", "content": prompt})
        if self.boom:
            raise RuntimeError("Modell weg")
        text = self.answer(prompt) if callable(self.answer) else self.answer
        self.history.append({"role": "assistant", "content": text})
        return FakeResult(text)

class FakeAPI:
    """Statt HTTPS: eine Liste, die abgearbeitet wird."""

    def __init__(self, batches=None):
        self.batches = list(batches or [])
        self.sent = []
        self.actions = []
        self.offsets = []

    def me(self):
        return {"username": "chimera_test_bot"}

    def updates(self, offset, limit=10):
        self.offsets.append(offset)
        return self.batches.pop(0) if self.batches else []

    def send(self, chat_id, text):
        self.sent.append((chat_id, text))
        return {"message_id": len(self.sent)}

    def typing(self, chat_id):
        self.actions.append(chat_id)

def msg(uid, text, user=7, chat=None, name="smilez"):
    return {"update_id": uid,
            "message": {"text": text,
                        "chat": {"id": chat if chat is not None else user},
                        "from": {"id": user, "first_name": name}}}

# --- Kanal ----------------------------------------------------------------

print("== Kanal ==")
raises("leerer Name abgelehnt", ValueError, Channel, "")
raises("unbekannte Betriebsart abgelehnt", ValueError, Channel, "x", mode="morse")
raises("negative Grenze abgelehnt", ValueError, Channel, "x", limit=-1)
ok("Hinweis nennt den Kanal") if "telegram" in Channel("telegram").hint() \
    else bad("Kanalname fehlt im Hinweis")
voice = Channel("sprache", mode="voice", limit=120)
ok("Sprache verlangt Kürze") if "vorgelesen" in voice.hint() \
    else bad("kein Hinweis auf Vorlesen")
ok("Text erlaubt Absätze") if "Chat" in DIRECT.hint() else bad("Texthinweis fehlt")

print("== Kürzen ==")
check("ohne Grenze unverändert", Channel("a").trim("x" * 5000), "x" * 5000)
check("kurz bleibt kurz", voice.trim("Kurz."), "Kurz.")
lang = ("Erster Satz ist hier. " * 4) + "Und dieser hier ist zu viel."
kurz = voice.trim(lang)
ok("gekürzt") if len(kurz) <= 120 else bad(f"{len(kurz)} Zeichen")
ok("endet an Satzgrenze") if kurz.endswith(".") else bad(repr(kurz[-20:]))
# Gegenprobe: ohne Satzzeichen im hinteren Drittel wird hart geschnitten,
# aber sichtbar markiert — kein stilles Abschneiden.
hart = Channel("h", limit=30).trim("a" * 100)
ok("ohne Satzgrenze markiert") if hart.endswith("…") else bad(repr(hart))
# Das Abbruchzeichen darf die Grenze nicht sprengen — es passt hinein,
# nicht obendrauf. (Fand einen echten Fehler: 3800 + " …" = 3802.)
check("markiert und trotzdem in der Grenze", len(hart) <= 30, True)
check("auch bei Vielfachen exakt",
      all(len(Channel("g", limit=n).trim("a" * 500)) <= n
          for n in (5, 10, 31, 100, 3800)), True)
# Gegenprobe zur Untergrenze: ein frühes Satzende darf NICHT gewählt
# werden, sonst bliebe von 200 Zeichen ein Wort übrig.
fruh = Channel("f", limit=100).trim("Ja. " + "b" * 300)
ok("frühes Satzende nicht genommen") if len(fruh) > 50 else bad(f"{len(fruh)}")

# --- Sitzung --------------------------------------------------------------

print("== Sitzung ==")
agent = FakeAgent()
s = Session(agent)
raises("leerer Auftrag abgelehnt", ValueError, s.ask, "  ")
check("nicht beschäftigt", s.busy, False)

t = s.ask("Hallo", CHANNEL)
check("Antwort kommt an", t.text, "Antwort.")
check("Kanal vermerkt", t.channel, "telegram")
check("Anbieter vermerkt", t.provider, "ollama")
ok("Kanalhinweis vorangestellt") if agent.seen[0].startswith("[Kanal: telegram]") \
    else bad(agent.seen[0][:40])
ok("Auftrag steht dahinter") if agent.seen[0].endswith("Hallo") \
    else bad(agent.seen[0][-40:])
check("danach wieder frei", s.busy, False)

print("== Ein Gespräch, zwei Türen (Regel 5d) ==")
s.ask("Und übrigens", voice)
check("beide Türen, ein Verlauf", len(agent.history), 4)
check("Sitzung protokolliert beide", len(s.turns()), 2)
check("zweiter Umlauf ist Sprache", s.turns()[-1].channel, "sprache")
ok("Sprachkanal im Hinweis") if "sprache" in agent.seen[1] else bad(agent.seen[1][:40])
# Gegenprobe: zwei Sitzungen auf EINEM Agenten teilen den Verlauf auch
# dann — die Trennung liegt im Kanal, nicht in der Sitzung.
zweite = Session(agent)
zweite.ask("Dritte Tür")
check("dritte Tür, selber Verlauf", len(agent.history), 6)

print("== Fehler werden beantwortet, nicht geworfen ==")
kaputt = Session(FakeAgent(boom=True))
t = kaputt.ask("Geht das?")
ok("Antwort trotz Fehler") if "schief" in t.text else bad(t.text)
ok("Fehler vermerkt") if "RuntimeError" in t.error else bad(repr(t.error))
check("nach Fehler wieder frei", kaputt.busy, False)

print("== Protokoll wird begrenzt ==")
klein = Session(FakeAgent(), log_size=3)
for i in range(6):
    klein.ask(f"Frage {i}")
check("nur die letzten drei", len(klein.turns()), 3)
ok("jüngste behalten") if klein.turns()[-1].prompt == "Frage 5" \
    else bad(klein.turns()[-1].prompt)

print("== door() bindet den Kanal ==")
a2 = FakeAgent()
s2 = Session(a2)
tuer = s2.door(voice)
tuer("Durch die Tür")
check("Kanal gesetzt", s2.turns()[-1].channel, "sprache")
check("with_limit ändert nur die Grenze",
      (s2.with_limit(voice, 40).name, s2.with_limit(voice, 40).limit),
      ("sprache", 40))

# --- Telegram -------------------------------------------------------------

print("== API-Zugang ==")
raises("Token ohne Doppelpunkt abgelehnt", ValueError, TelegramAPI, "abc")
raises("leeres Token abgelehnt", ValueError, TelegramAPI, "")
ok("gültige Form angenommen") if TelegramAPI("123:ABC").token == "123:ABC" \
    else bad("Token nicht übernommen")

print("== Bot: nur Eingetragene ==")
agent3 = FakeAgent("Hallo zurück.")
sess = Session(agent3)
api = FakeAPI()
raises("ohne Liste kein Bot", ValueError, Bot, api, sess, frozenset())

bot = Bot(api, sess, {7})
bot.handle(bot.parse(msg(1, "Hallo")))
check("Eingetragener wird beantwortet", api.sent[-1][1], "Hallo zurück.")
check("Schreibanzeige gesetzt", api.actions, [7])

vorher = len(agent3.history)
bot.handle(bot.parse(msg(2, "Und ich?", user=99)))
ok("Fremder abgewiesen") if "kennen uns nicht" in api.sent[-1][1] \
    else bad(api.sent[-1][1])
check("Agent nicht befragt", len(agent3.history), vorher)

print("== Befehle ==")
bot.handle(bot.parse(msg(3, "/status")))
ok("Status meldet bereit") if "Bereit" in api.sent[-1][1] else bad(api.sent[-1][1])
ok("Status nennt Anbieter") if "ollama" in api.sent[-1][1] else bad(api.sent[-1][1])
bot.handle(bot.parse(msg(4, "/hilfe")))
ok("Hilfe erklärt sich") if "/neu" in api.sent[-1][1] else bad(api.sent[-1][1])
bot.handle(bot.parse(msg(5, "/neu")))
check("Verlauf geleert", len(agent3.history), 0)
ok("Leeren bestätigt") if "neu an" in api.sent[-1][1] else bad(api.sent[-1][1])
# Gegenprobe: ein Wort mit Schrägstrich mittendrin ist kein Befehl.
bot.handle(bot.parse(msg(6, "was ist /neu bei dir")))
check("kein Befehl mittendrin", api.sent[-1][1], "Hallo zurück.")
# Befehl mit Bot-Namen (in Gruppen üblich)
bot.handle(bot.parse(msg(7, "/status@chimera_test_bot")))
ok("Befehl mit Botnamen erkannt") if "Bereit" in api.sent[-1][1] or \
    "Zuletzt" in api.sent[-1][1] else bad(api.sent[-1][1])

print("== Updates auspacken ==")
check("Nicht-Nachricht übergangen", bot.parse({"update_id": 1}), None)
check("Bild ohne Text übergangen",
      bot.parse({"update_id": 1, "message": {"chat": {"id": 1}}}), None)
u = bot.parse(msg(9, "Text", user=7, chat=-100))
check("Gruppen-Chat getrennt vom Nutzer", (u.chat_id, u.user_id), (-100, 7))

print("== Abholschleife ==")
api2 = FakeAPI([[msg(10, "eins"), msg(11, "zwei")], [msg(12, "drei")]])
bot2 = Bot(api2, Session(FakeAgent("ok")), {7})
check("erster Durchgang", bot2.poll_once(), 2)
check("Zähler steht vor", bot2._offset, 12)
check("zweiter Durchgang", bot2.poll_once(), 1)
check("leer ist kein Fehler", bot2.poll_once(), 0)
check("Zähler bleibt", bot2._offset, 13)

print("== Störungen werfen den Bot nicht ==")
class BoeseAPI(FakeAPI):
    def updates(self, offset, limit=10):
        raise TelegramError("kein Netz")
check("Netzfehler abgefangen", Bot(BoeseAPI(), Session(FakeAgent()), {7}).poll_once(), 0)

class SendeFehler(FakeAPI):
    def send(self, chat_id, text):
        raise TelegramError("blockiert")
b3 = Bot(SendeFehler([[msg(20, "hi")]]), Session(FakeAgent()), {7})
check("Sendefehler beendet nicht", b3.poll_once(), 1)

# Ein Agent, der abstürzt, darf den Bot nicht mitnehmen — die Sitzung
# fängt das ab, der Bot antwortet trotzdem.
api4 = FakeAPI([[msg(30, "hi")]])
b4 = Bot(api4, Session(FakeAgent(boom=True)), {7})
check("Agentfehler abgefangen", b4.poll_once(), 1)
ok("Nutzer bekommt Bescheid") if api4.sent else bad("nichts gesendet")

print("== Zustand ans Gesicht ==")
zustaende = []
api5 = FakeAPI()
b5 = Bot(api5, Session(FakeAgent()), {7}, on_state=zustaende.append)
b5.handle(b5.parse(msg(40, "hi")))
check("denkt und spricht gemeldet", zustaende, ["denkt", "spricht"])
# Gegenprobe: ein kaputter Rückruf darf nichts umwerfen.
def kaputt_ruf(_):
    raise RuntimeError("Gesicht weg")
b6 = Bot(FakeAPI(), Session(FakeAgent()), {7}, on_state=kaputt_ruf)
b6.handle(b6.parse(msg(41, "hi")))
ok("kaputtes Gesicht stört nicht")
# Und bei einem Fehler meldet der Bot 'fehler', nicht 'spricht'.
z2 = []
b7 = Bot(FakeAPI(), Session(FakeAgent(boom=True)), {7}, on_state=z2.append)
b7.handle(b7.parse(msg(42, "hi")))
check("Fehlerzustand gemeldet", z2, ["denkt", "fehler"])

print("== Lange Antworten teilen ==")
check("kurz bleibt eins", len(_split("abc", 100)), 1)
teile = _split("Zeile eins\n" * 500, 100)
ok("geteilt") if len(teile) > 1 else bad("nicht geteilt")
ok("jedes Stück passt") if all(len(t) <= 100 for t in teile) \
    else bad(max(len(t) for t in teile))
ok("nichts verloren") if "Zeile eins" in teile[-1] else bad(teile[-1][:40])
# Ein Wortungetüm ohne Trennstelle muss hart geteilt werden.
ungetuem = _split("x" * 250, 100)
ok("ohne Trennstelle hart geteilt") if len(ungetuem) == 3 else bad(len(ungetuem))
# Telegram-Grenze wird eingehalten: die Sitzung kürzt schon vorher.
lang_turn = Session(FakeAgent("y" * 9000)).ask("x", CHANNEL)
ok("Telegram-Grenze eingehalten") if len(lang_turn.text) <= 3800 \
    else bad(len(lang_turn.text))

print("== Aufbau aus der Umgebung ==")
raises("ohne Token kein Bot", ValueError, from_env, sess, {})
raises("ohne Absenderliste kein Bot", ValueError, from_env, sess,
       {"CHIMERA_TELEGRAM_TOKEN": "1:a"})
raises("unsinnige Kennung abgelehnt", ValueError, from_env, sess,
       {"CHIMERA_TELEGRAM_TOKEN": "1:a", "CHIMERA_TELEGRAM_ALLOWED": "abc"})
b = from_env(sess, {"CHIMERA_TELEGRAM_TOKEN": "1:a",
                    "CHIMERA_TELEGRAM_ALLOWED": " 7, 8 ;9 "})
check("Kennungen gelesen", sorted(b.allowed), [7, 8, 9])

print()
print(f"Ergebnis: {PASS} ok, {FAIL} fehlgeschlagen")
sys.exit(1 if FAIL else 0)
