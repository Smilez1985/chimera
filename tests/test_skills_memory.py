"""Tests für Skill-Gating und Gedächtnis-Rangordnung."""
import sys, tempfile
from datetime import date, timedelta
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from chimera.agent.memory import Memory, install_tools  # noqa: E402
from chimera.agent.skills import Requires, SkillStore, parse_skill  # noqa: E402
from chimera.agent.tools import Toolbox  # noqa: E402

PASS = FAIL = 0
def ok(m):
    global PASS; PASS += 1; print(f"  ok    {m}")
def bad(m):
    global FAIL; FAIL += 1; print(f"  FAIL  {m}")
def check(m, got, want):
    ok(m) if got == want else bad(f"{m} — erwartet {want!r}, bekam {got!r}")

def skill(d: Path, name: str, meta: str = "{}") -> Path:
    p = d / name.lower(); p.mkdir(parents=True)
    (p / "SKILL.md").write_text(
        f'---\nname: {name}\ndescription: Beschreibung von {name}\n'
        f'metadata:\n  {meta}\n---\n\nAnleitung für {name}.', encoding="utf-8")
    return p / "SKILL.md"

print("== Skill-Gating ==")
check("kein Bedarf", Requires().check()[0], True)
check("Programm da", Requires(bins=("sh",)).check()[0], True)
usable, why = Requires(bins=("gibtsnichtxyz",)).check()
check("fehlendes Programm", usable, False)
ok("Grund genannt") if "gibtsnichtxyz" in why else bad(f"unklar: {why}")
check("eines von mehreren", Requires(any_bins=("gibtsnicht", "sh")).check()[0], True)
check("keines davon", Requires(any_bins=("nixa", "nixb")).check()[0], False)
check("Variable fehlt", Requires(env=("GIBTS_NICHT_XYZ",)).check()[0], False)
check("falsches System", Requires(os_names=("win32",)).check()[0], False)
# always hebt alles auf — dafür ist es da.
check("always überspringt Prüfung",
      Requires(bins=("gibtsnichtxyz",), always=True).check()[0], True)

print("== Skills lesen ==")
with tempfile.TemporaryDirectory() as td:
    d = Path(td)
    skill(d, "Wetter", '{"openclaw": {"emoji": "W", "requires": {"bins": ["sh"]}}}')
    skill(d, "Unmoeglich", '{"openclaw": {"requires": {"bins": ["gibtsnichtxyz"]}}}')
    skill(d, "Einfach")
    store = SkillStore(d)
    check("alle gefunden", len(store.all()), 3)
    check("nutzbare", len(store.usable()), 2)
    s = store.get("wetter")
    ok("Name unabhängig von Groß/Klein") if s else bad("nicht gefunden")
    check("Beschreibung gelesen", s.description, "Beschreibung von Wetter")
    check("Emoji gelesen", s.emoji, "W")
    check("Text vorhanden", "Anleitung" in s.read(), True)

    cat = store.catalog()
    ok("Katalog nennt nutzbare") if "Wetter" in cat else bad("fehlt")
    # Nicht Nutzbares wird MIT Grund genannt, nicht verschwiegen.
    ok("Katalog nennt Grund") if "nicht verfügbar" in cat and "gibtsnichtxyz" in cat \
        else bad("Grund fehlt")

    # Kaputte Dateien dürfen den Rest nicht mitreißen.
    kaputt = d / "kaputt"; kaputt.mkdir()
    (kaputt / "SKILL.md").write_text("kein Kopfteil", encoding="utf-8")
    store.reload()
    check("Kaputtes übersprungen", len(store.all()), 3)

print("== Gedächtnis ==")
with tempfile.TemporaryDirectory() as td:
    m = Memory(Path(td))
    check("leer ist leer", m.context(), "")

    m.permanent_path.write_text("# Regeln\n- Kurz antworten.", encoding="utf-8")
    ctx = m.context()
    ok("Grundlagen drin") if "Kurz antworten" in ctx else bad("fehlt")
    # Ohne diesen Hinweis hält ein Modell Notizen für Aufträge.
    ok("Hintergrund-Hinweis drin") if "Hintergrund" in ctx and "letzte Nachricht" in ctx \
        else bad("Hinweis fehlt")

    m.write("Erste Notiz", heading="Test")
    ctx = m.context()
    ok("Notiz drin") if "Erste Notiz" in ctx else bad("fehlt")
    ok("Überschrift drin") if "## Test" in ctx else bad("fehlt")
    ok("Zeitstempel") if "<!--" in m.read_day() else bad("kein Zeitstempel")

    m.write("Zweite Notiz")
    ok("angehängt, nicht ersetzt") if "Erste" in m.read_day() and "Zweite" in m.read_day() \
        else bad("überschrieben")

    try:
        m.write("   "); bad("leere Notiz durchgelassen")
    except ValueError: ok("leere Notiz abgelehnt")

    # Leere Tage überspringen, sonst liefert eine ruhige Woche nichts.
    (Path(td) / f"{date.today() - timedelta(days=1)}.md").write_text("", encoding="utf-8")
    (Path(td) / f"{date.today() - timedelta(days=2)}.md").write_text("Vorgestern", encoding="utf-8")
    tage = [d for d, _ in m.recent()]
    ok("leerer Tag übersprungen") if len(tage) == 2 else bad(f"Tage: {tage}")

    # Kürzen wird gesagt, nicht stillschweigend gemacht.
    m2 = Memory(Path(td), max_daily_lines=5)
    m2.write("\n".join(f"Zeile {i}" for i in range(50)))
    ok("Kürzung wird gemeldet") if "nicht mitgeschickt" in m2.context() \
        else bad("stillschweigend gekürzt")

print("== Gedächtnis als Werkzeug ==")
with tempfile.TemporaryDirectory() as td:
    m = Memory(Path(td, "mem"))
    tb = Toolbox(td)
    install_tools(tb, m)
    ok("remember angemeldet") if "remember" in tb.names() else bad("fehlt")
    ok("recall angemeldet") if "recall" in tb.names() else bad("fehlt")
    # Kein Werkzeug zum Schreiben der Grundlagen — die gehören dem Nutzer.
    ok("Grundlagen nicht beschreibbar") if not any(
        "grundlagen" in n for n in tb.names()) else bad("Agent kann Grundlagen ändern")

    out = tb.call("remember", {"text": "Die Bildrate lag bei 15."})
    ok("schreiben geht") if "Notiert" in out else bad(out)
    found = tb.call("recall", {"query": "bildrate"})
    ok("finden geht") if "15" in found else bad(found)
    check("nichts gefunden wird gesagt",
          "Nichts zu" in tb.call("recall", {"query": "quatschbegriffxyz"}), True)
    ok("ohne Suchwort: letzte Tage") if "Bildrate" in tb.call("recall", {}) \
        else bad("leere Abfrage liefert nichts")

print()
print(f"Ergebnis: {PASS} ok, {FAIL} fehlgeschlagen")
sys.exit(1 if FAIL else 0)
