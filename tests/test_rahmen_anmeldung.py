"""Der Rahmen: Anmeldemaske überlebt einen Modulwechsel, Tab hat ein Symbol.

Zwei Mängel, die smilez am 15.11.2026 gemeldet hat, in einem Test:

1. *„wenn die webui einen timeout bekommt und den User abmeldet sollte es auch
   die Anmeldemaske wieder zeigen, statt das Chatfenster in dem man nix mehr
   machen kann"* — die Maske lag IM Modulbereich; `zeigeModul` leerte ihn und
   nahm das Formular mit. Ein 401 zeigte danach ein Element, das nicht mehr im
   Dokument hing.
2. *„der Tab im Browser hat kein Symbol"* — kein `<link rel="icon">`.

Geprüft wird die echte `rahmen.html`: die **Verschachtelung** mit einem
HTML-Parser (nicht mit einem Suchmuster — eine Schnur kann nicht sagen, wer
wessen Kind ist), die Aufrufe im Skript und dass das Skript überhaupt
übersetzt (node --check, sonst übersprungen).

Aufruf: python3 tests/test_rahmen_anmeldung.py
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import tempfile
from html.parser import HTMLParser
from pathlib import Path

HIER = Path(__file__).resolve().parent
ROOT = Path(os.environ.get("CHIMERA_ROOT_TEST") or HIER.parent)
RAHMEN = ROOT / "rust/crates/tor/web/rahmen.html"

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

class Baum(HTMLParser):
    """Eltern-Kind-Verhältnis der Elemente mit id.

    Ein Stapel aus (Tag, id): Beim Öffnen wird die **nächste** id darüber
    zum Elternteil, beim Schließen fällt alles bis zu diesem Tag weg. Die
    frühere Fassung verglich nur Zeichenketten und verlor dabei die
    Elternebene — sie meldete eine Maske ohne Elternteil, die sehr wohl einen
    hatte.
    """

    LEER = {"link", "meta", "br", "img", "input", "hr"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.stapel: list[tuple[str, str]] = []
        self.eltern: dict[str, str] = {}
        self.attribute: dict[str, dict] = {}

    def _eltern_id(self) -> str:
        for _tag, kennung in reversed(self.stapel):
            if kennung:
                return kennung
        return ""

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if a.get("id"):
            self.eltern[a["id"]] = self._eltern_id()
            self.attribute[a["id"]] = a
        if tag not in self.LEER:
            self.stapel.append((tag, a.get("id") or ""))

    def handle_endtag(self, tag):
        if tag in self.LEER:
            return
        for i in range(len(self.stapel) - 1, -1, -1):
            if self.stapel[i][0] == tag:
                del self.stapel[i:]
                return

def eltern_baum(text: str) -> Baum:
    b = Baum()
    b.feed(text)
    return b

def finde_skript(text: str) -> str:
    teile = re.findall(r"<script>(.*?)</script>", text, re.S)
    return "\n".join(teile)

def main() -> int:
    print("=== Rahmen: Anmeldung und Symbol ===")
    if not RAHMEN.is_file():
        print(f"  FAIL  fehlt: {RAHMEN}")
        return 1
    text = RAHMEN.read_text(encoding="utf-8")
    b = eltern_baum(text)

    # --- 1. Die Maske hängt NICHT im Modulbereich -----------------------
    check("#buehne ist da", "buehne" in b.eltern, True)
    check("#anmeldung ist da", "anmeldung" in b.eltern, True)
    check("#einrichtung ist da", "einrichtung" in b.eltern, True)
    check("#anmeldung ist ein Kind von <main>", b.eltern.get("anmeldung"), "inhalt")
    check("#buehne ist ein Kind von <main>", b.eltern.get("buehne"), "inhalt")
    # Der eigentliche Defekt: die Maske lag im Modulbereich.
    check("#anmeldung liegt NICHT in #buehne",
          "buehne" in b.eltern.get("anmeldung", ""), False)
    check("#einrichtung liegt NICHT in #buehne",
          "buehne" in b.eltern.get("einrichtung", ""), False)

    # --- 2. Das Skript räumt die Bühne, nicht die Anmeldung ------------
    skript = finde_skript(text)
    check("zeigeModul räumt die Bühne", 'const buehne = $("buehne");' in skript, True)
    check("zeigeModul räumt NICHT #inhalt",
          'const inhalt = $("inhalt");\n  inhalt.replaceChildren();' in skript, False)
    check("ein 401 ruft die Anmeldemaske",
          'r.status === 401' in skript and 'maskeZeigen("anmeldung"' in skript, True)
    check("ein 409 führt zur Einrichtung",
          'r.status === 409' in skript and 'maskeZeigen("einrichtung")' in skript, True)
    check("die Maske leert die Bühne",
          'if (art !== "") $("buehne").replaceChildren();' in skript, True)
    check("maskeZeigen ist nach außen gereicht (Module können sie rufen)",
          "window.chimera.maskeZeigen = maskeZeigen" in skript, True)
    # Kein Modul soll die Anmeldung über style.display steuern: mit dem
    # hidden-Attribut gibt es genau einen Schalter.
    # display darf nur der Warnstreifen schalten -- die Masken laufen über
    # das hidden-Attribut, sonst gibt es zwei Schalter für einen Zustand.
    ohne_warnung = skript.replace(
        'if (location.protocol === "http:") $("warnung").style.display = "block";', "")
    check("kein style.display an den Masken", "style.display" in ohne_warnung, False)

    # --- 2b. Sitzungswächter --------------------------------------------
    # smilez 15.11.: „wenn ich lange keine Eingabe mache und abgemeldet werde
    # sollte ich zurück auf die Anmeldemaske geleitet werden, aber aktuell
    # muss ich dazu manuell neu laden". Reiter, die nichts abfragen (Status,
    # Einstellungen), merkten das Ablaufen gar nicht.
    check("der Rahmen fragt /api/sitzung", "/api/sitzung" in skript, True)
    check("es gibt einen Takt", "setInterval(sitzungPruefen" in skript, True)
    check("der Takt ist nicht Dauerfeuer (>= 30 s)",
          int(re.search(r"SITZUNG_TAKT_MS = (\d+)", skript).group(1)) >= 30000, True)
    check("ein 401 haelt den Takt an", "sitzungAnhalten();" in skript, True)
    check("Rueckkehr aus dem Hintergrund prueft sofort",
          'visibilitychange' in skript, True)
    check("Abmelden haelt den Takt an",
          "sitzungAnhalten(); await api(\"/api/logout\"" in skript, True)
    check("die Maske haelt den Takt an",
          'if (art !== "") sitzungAnhalten();' in skript, True)
    web_rs = (ROOT / "rust/crates/tor/src/web.rs").read_text(encoding="utf-8")
    check("die Route /api/sitzung gibt es im Gateway",
          '("/api/sitzung")' in web_rs or '"/api/sitzung"' in web_rs, True)

    # --- 2c. Sprache (Deutsch/Englisch) ----------------------------------
    # smilez 15.11.: „in Einstellungen fehlt auch noch die Sprache,
    # deutsch/english". Ein Merker im Browser, kein Zustand im Dienst.
    check("die Sprache kommt aus localStorage", 'chimera.sprache' in skript, True)
    check("ohne Merker entscheidet der Browser", 'navigator.language' in skript, True)
    check("nur de und en werden angenommen",
          'if (g === "de" || g === "en") return g;' in skript, True)
    # Beide Sprachtabellen müssen dieselben Schlüssel haben — sonst bleibt
    # ein Element in einer Sprache leer.
    de = re.search(r"de: \{(.*?)\},\n  en:", skript, re.S)
    en = re.search(r"en: \{(.*?)\},\n\};", skript, re.S)
    check("es gibt zwei Sprachtabellen", de is not None and en is not None, True)
    if de and en:
        # Die Tabellen stehen mit einem Schlüssel je Zeile — so lässt sich
        # der Schlüssel vom Text im Wert unterscheiden ("… Gerät: ").
        schluessel_de = set(re.findall(r"^\s+(\w+):", de.group(1), re.M))
        schluessel_en = set(re.findall(r"^\s+(\w+):", en.group(1), re.M))
        check("de und en nennen dieselben Schlüssel", schluessel_de, schluessel_en)
        # Und jedes Element mit data-t hat einen Text.
        im_markup = set(re.findall(r'data-t="([a-z_]+)"', text))
        check("jede data-t-Kennung hat einen Text", im_markup - schluessel_de, set())
        check("es gibt überhaupt Übersetzungen (Test sieht etwas)", len(im_markup) >= 8, True)

    # --- 3. Das Symbol im Tab ------------------------------------------
    link = re.search(r'<link[^>]*rel="icon"[^>]*>', text)
    check("es gibt ein <link rel=\"icon\">", link is not None, True)
    href = re.search(r'href="([^"]+)"', link.group(0)).group(1) if link else ""
    check("das Symbol ist ein SVG als data:-URI",
          href.startswith("data:image/svg+xml,"), True)
    check("kein rohes '#' im data:-URI (bricht die URL)", "#" in href, False)
    check("nur ASCII im Symbol (keine Kodierungsfallen)",
          all(ord(z) < 128 for z in href), True)

    # --- 4. Das Skript übersetzt -------------------------------------
    node = shutil.which("node")
    if not node:
        print("  uebersprungen: node fehlt -- Skript nicht geprüft")
    else:
        with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False,
                                         encoding="utf-8") as f:
            f.write(skript)
            weg = f.name
        try:
            p = subprocess.run([node, "--check", weg], capture_output=True, text=True)
            check("das Rahmen-Skript ist gültiges JavaScript", p.returncode, 0)
            if p.returncode != 0:
                print(p.stderr[-600:])
        finally:
            os.unlink(weg)

    print(f"\n{PASS} ok, {FAIL} FAIL")
    return 0 if FAIL == 0 else 1

if __name__ == "__main__":
    sys.exit(main())
