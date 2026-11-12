"""Ablagen und Schreibrecht (DESIGN Regel 5t).

Der Fehler, den dieser Test verhindert (am Gerät gefunden, 12.11.2026): Der
Code legte die Freigaben nach `config/freigaben.json`, die Unit erlaubte dem
Gateway aber nur `config/anbieter`, `config/geheim`, `config/wahl` und
`state/katalog`. Am Pi endete jedes Speichern mit "Read-only file system" --
die Freigabe war eine Anzeige ohne Wirkung, und kein Test hat es gemerkt,
weil beide Seiten für sich stimmten.

Prüfung: Jeder Ordner, den der Gateway-Code unter `config/` oder `state/`
anspricht, steht in `ReadWritePaths` der Unit (und damit auch in der Liste,
die der Installer anlegt).

Prüfaufbauten im `#[cfg(test)] mod tests` (immer am Dateiende) bleiben außen
vor: sie schreiben in einen temporären Ordner, nicht auf das Gerät. Der
Schnitt liegt an der Zeile `#[cfg(test)]`, auf die `mod tests` folgt — ein
einzelnes `#[cfg(test)]` über einer Hilfsfunktion (netzsuche.rs) ist damit
nicht der Schnitt.

Gegenprobe: `python3 tests/gegenprobe_ablagen_wirksam.py`.
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
QUELLEN = ROOT / "rust" / "crates" / "tor" / "src"
GATEWAY = ROOT / "installer" / "lib" / "gateway.sh"

# "p.config.join("wahl")", "self.state.join("katalog")" -- der erste Ordner
# unterhalb von config/ bzw. state/.
MUSTER = re.compile(r'\.(config|state)\s*\.join\("([^"]+)"\)')
RW_ZEILE = re.compile(r'^ReadWritePaths=(.*)$', re.MULTILINE)


def erlaubte_ordner(text=None):
    """Die Ordner aus der ReadWritePaths-Zeile der Unit (Fortsetzungen mit \\)."""
    if text is None:
        text = GATEWAY.read_text(encoding="utf-8")
    # Fortsetzungszeilen (Backslash am Zeilenende) zusammenziehen.
    text = re.sub(r"\\\n\s*", " ", text)
    m = RW_ZEILE.search(text)
    if not m:
        return set(), None
    ordner = set()
    for eintrag in m.group(1).split():
        eintrag = eintrag.lstrip("-")
        for wurzel in ("$CHIMERA_CONFIG", "$CHIMERA_STATE"):
            if eintrag == wurzel:
                # config/ oder state/ als Ganzes -- genau das verbietet 5t.
                ordner.add("<GANZES>")
            elif eintrag.startswith(wurzel + "/"):
                ordner.add(eintrag[len(wurzel) + 1:].split("/")[0])
    return ordner, m.group(1)


def ohne_pruefaufbau(zeilen):
    """Zeilen bis zum Testmodul am Dateiende."""
    for i, zeile in enumerate(zeilen):
        if zeile.strip() != "#[cfg(test)]":
            continue
        folge = [z for z in zeilen[i + 1:i + 3] if z.strip()]
        if folge and folge[0].lstrip().startswith(("mod tests", "pub mod tests")):
            return zeilen[:i]
    return zeilen


def pfade_im_code(quellen=None):
    """(fund, datei, zeile) für jeden angesprochenen Ordner."""
    if quellen is None:
        quellen = sorted(QUELLEN.rglob("*.rs"))
    funde = []
    for datei in quellen:
        zeilen = ohne_pruefaufbau(datei.read_text(encoding="utf-8").splitlines())
        for nr, zeile in enumerate(zeilen, 1):
            if zeile.lstrip().startswith("//"):
                continue
            for m in MUSTER.finditer(zeile):
                funde.append((m.group(2), datei.relative_to(ROOT), nr))
    return funde


def pruefen(ordner, funde):
    """Liste der Verstöße: (ordner, datei, zeile)."""
    stoerungen = []
    for name, datei, nr in funde:
        if name not in ordner:
            stoerungen.append((name, datei, nr))
    return stoerungen


def main():
    ordner, rw = erlaubte_ordner()
    if not ordner:
        print("ROT: keine ReadWritePaths-Zeile in installer/lib/gateway.sh")
        return 1
    if "<GANZES>" in ordner:
        print("ROT: ReadWritePaths nennt config/ oder state/ als Ganzes (Regel 5t)")
        return 1
    funde = pfade_im_code()
    if not funde:
        print("ROT: kein Pfad im Gateway-Code gefunden -- die Suche ist blind")
        return 1
    stoerungen = pruefen(ordner, funde)
    for name, datei, nr in stoerungen:
        print(f"ROT: {datei}:{nr} spricht {name} an, das nicht in ReadWritePaths steht ({rw.strip()})")
    if stoerungen:
        return 1
    namen = sorted({f[0] for f in funde})
    print(f"ok: {len(funde)} Pfade, {len(namen)} Ordner ({', '.join(namen)}), "
          f"{len(ordner)} in ReadWritePaths")
    return 0


if __name__ == "__main__":
    sys.exit(main())
