"""Python-Abhaengigkeiten im venv messen (importlib.metadata).

Aufruf als Skript (lib/python.sh, pydep_fehlend):
    <venv-python> pydep.py <anforderung> ...
Ausgabe je nicht erfuellter Anforderung eine Zeile
    <anforderung>\t<ist-version oder "fehlt">
rc 0 alles erfuellt, 1 etwas fehlt oder ist zu alt.

Im selben Interpreter (lib/py/nachweis.py): fehlend(anforderungen).

Bis 12.10.2026 stand dieser Code als Heredoc in lib/python.sh. Er liegt
jetzt in einer eigenen Datei, damit der Nachweis von Schritt 50 ihn ohne
eigenen Python-Start benutzt (am Pi Zero 2 W kostet jeder Start 0,1 bis
0,3 s, mit Modulen mehr). Rechenweg unveraendert.
"""
import re, sys
from importlib import metadata

def norm(name):
    return re.sub(r"[-_.]+", "-", name).lower()

def teile(v):
    # "2.5.4" -> (2,5,4); "1.26.0rc1" -> (1,26,0,-1): Vorabfassung < Freigabe
    out = []
    for t in re.split(r"[.]", v):
        m = re.match(r"(\d+)(.*)", t)
        if not m:
            break
        out.append(int(m.group(1)))
        if m.group(2):
            out.append(-1)
            break
    return tuple(out)

def erfuellt(ist, op, soll):
    try:
        from packaging.version import Version
        from packaging.specifiers import SpecifierSet
        return Version(ist) in SpecifierSet(f"{op}{soll}", prereleases=True)
    except Exception:
        a, b = teile(ist), teile(soll)
        n = max(len(a), len(b)); a += (0,) * (n - len(a)); b += (0,) * (n - len(b))
        return {">=": a >= b, ">": a > b, "<=": a <= b, "<": a < b,
                "==": a == b, "!=": a != b, "~=": a >= b}.get(op, False)

def fehlend(anforderungen):
    """Nicht erfuellte Anforderungen als Zeilen '<anf>\t<ist|fehlt>'."""
    aus = []
    for anf in anforderungen:
        m = re.match(r"\s*([A-Za-z0-9][A-Za-z0-9._-]*)\s*(.*)$", anf)
        if not m:
            continue
        name, rest = m.group(1), m.group(2).strip()
        try:
            ist = metadata.version(name)
        except metadata.PackageNotFoundError:
            # Verteilungsname und Importname koennen abweichen (Pillow/PIL);
            # metadata kennt den Verteilungsnamen, der steht in requirements.
            ist = None
            for d in metadata.distributions():
                if norm(d.metadata["Name"] or "") == norm(name):
                    ist = d.version
                    break
        if ist is None:
            aus.append(f"{anf}\tfehlt"); continue
        ok = True
        for op, soll in re.findall(r"(>=|<=|==|!=|~=|>|<)\s*([A-Za-z0-9.*+!-]+)", rest):
            if not erfuellt(ist, op, soll.rstrip(".*")):
                ok = False
        if not ok:
            aus.append(f"{anf}\t{ist}")
    return aus


if __name__ == "__main__":
    _aus = fehlend(sys.argv[1:])
    for _z in _aus:
        print(_z)
    sys.exit(1 if _aus else 0)
