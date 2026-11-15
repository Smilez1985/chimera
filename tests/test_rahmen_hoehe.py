"""Der Rahmen gibt der Modulfläche eine Höhe — sonst ist das Chatfenster leer.

Befund smilez (15.11.2026, 23:08): *„leider hat die letzte Version das Chat
Fenster kaputt gemacht, die prompt Eingabe klebt oben, den Text kann man nicht
mehr lesen"*.

Die Ursache war strukturell, nicht kosmetisch: `ddaf8d0` hat die Module in
`<div id="buehne">` gelegt (damit Anmeldemaske und Einrichtung Geschwister
sind). Das Chat-Modul setzt `:host { height:100% }`; gegen ein Elternteil ohne
definite Höhe löst Prozent auf `auto` auf. Folge: `#flaeche` (flex:1, Kinder
absolut) wurde null Pixel hoch — der Verlauf unsichtbar, das Formular direkt
unter der Kopfzeile.

Geprüft wird die echte `rahmen.html`: eine **Höhenkette** von `<main>` über
`#buehne` bis zum Modul. Fehlt ein Glied, ist die Oberfläche wieder kaputt —
und zwar so, dass kein Rust- oder Python-Test es merkt.

Ein HTML-Parser-Check wäre hier blind (er sieht keine Layoutfolgen), deshalb
werden die Deklarationen gelesen. Das ist eine Vereinbarung, keine Messung —
sie steht im DESIGN (Regel „Einstellungen am Gerät", Abschnitt „Höhenkette").

Aufruf: python3 tests/test_rahmen_hoehe.py
Gegenprobe: python3 tests/gegenprobe_rahmen_hoehe.py
"""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path

HIER = Path(__file__).resolve().parent
ROOT = Path(os.environ.get("CHIMERA_ROOT_TEST") or HIER.parent)
RAHMEN = ROOT / "rust/crates/tor/web/rahmen.html"
CHAT = ROOT / "rust/crates/tor/web/module/chat/chat.js"

PASS = 0
FAIL = 0

def check(name, ist, soll):
    global PASS, FAIL
    if ist == soll:
        PASS += 1
        print(f"  ok    {name}")
    else:
        FAIL += 1
        print(f"  FAIL  {name} -- erwartet {soll!r}, bekam {ist!r}")

def regeln(css: str) -> dict[str, str]:
    """Selektor → Deklarationen (nur die einfachen Blöcke dieser Datei).

    Der Rahmen hat keine verschachtelten Regeln; ein Block endet an der
    ersten `}`. Kommentare fliegen vorher raus, damit sie keine Selektorzeile
    vortäuschen.
    """
    ohne = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
    out: dict[str, str] = {}
    for treffer in re.finditer(r"([^{}]+)\{([^{}]*)\}", ohne):
        selektor = " ".join(treffer.group(1).split())
        out[selektor] = " ".join(treffer.group(2).split())
    return out

def hat(text: str, *teile: str) -> bool:
    return all(t in text for t in teile)

def main() -> int:
    print("=== Höhenkette im Rahmen ===")
    if not RAHMEN.is_file() or not CHAT.is_file():
        print(f"  FAIL  Datei fehlt: {RAHMEN} / {CHAT}")
        return 1
    html = RAHMEN.read_text(encoding="utf-8")
    css = "\n".join(re.findall(r"<style>(.*?)</style>", html, re.S))
    r = regeln(css)
    print(f"  ( {len(r)} Regeln gelesen )")

    # 1. html/body tragen die volle Höhe.
    check("html, body: height 100%", hat(r.get("html, body", ""), "height: 100%"), True)
    check("#app: flex-Spalte über die volle Höhe",
          hat(r.get("#app", ""), "display: flex", "flex-direction: column", "height: 100%"), True)

    # 2. <main> ist ein Flex-Element mit definite Höhe …
    main_css = r.get("main", "")
    check("main: flex: 1", "flex: 1" in main_css, True)
    check("main: min-height 0 (darf schrumpfen)", "min-height: 0" in main_css, True)
    # … und ein Flex-Container, damit die Fläche ihre Höhe erben kann.
    check("main: ist Flex-Spalte", hat(main_css, "display: flex", "flex-direction: column"), True)

    # 3. Die Modulfläche wächst in <main> hinein.
    buehne = r.get("#buehne", "")
    check("#buehne: flex: 1", "flex: 1" in buehne, True)
    check("#buehne: min-height 0", "min-height: 0" in buehne, True)
    check("#buehne: ist Flex-Spalte", hat(buehne, "display: flex", "flex-direction: column"), True)

    # 4. Das Modul selbst bekommt diese Höhe (Sternchen-Regel).
    kind = r.get("#buehne > *", "")
    check("#buehne > *: flex: 1", "flex: 1" in kind, True)
    check("#buehne > *: min-height 0", "min-height: 0" in kind, True)

    # 5. Und nur, wenn die Maske leer ist, verschwindet die Fläche — sonst
    #    bliebe ein leerer Kasten mit Flexplatz neben dem Anmeldeformular.
    check("#buehne:empty: display none", "display: none" in r.get("#buehne:empty", ""), True)

    # 6. Die Gegenseite: Das Chat-Modul verlässt sich auf diese Kette.
    js = CHAT.read_text(encoding="utf-8")
    check("chat.js: :host mit height 100%",
          ":host { display:flex; flex-direction:column; height:100%; }" in js, True)
    check("chat.js: Verlauf liegt absolut in der Fläche",
          re.search(r"#liste \{[^}]*position:absolute[^}]*inset:0", js) is not None, True)
    # Eine absolut liegende Liste in einer Fläche ohne Höhe wäre unsichtbar —
    # genau der Befund vom 15.11. Deshalb muss die Fläche wachsen können.
    check("chat.js: #flaeche wächst (flex:1)",
          re.search(r"#flaeche \{[^}]*flex:1", js) is not None, True)

    print(f"\nErgebnis: {PASS} ok, {FAIL} fehlgeschlagen")
    return 0 if FAIL == 0 else 1

if __name__ == "__main__":
    sys.exit(main())
