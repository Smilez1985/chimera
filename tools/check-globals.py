#!/usr/bin/env python3
"""Findet Namen, die eine Funktion als global liest, die es aber nicht gibt.

Der Anlass: ``NoisyRenderer.run()`` las ``TARGET_FPS`` und ``FRAME_TIME``
als Modulglobale. Beide existieren nur als Attribute (``self.TARGET_FPS``).
Der Fehler schlug erst beim Aufruf zu — und ``run()`` rief kein Test auf.

Genau solche Stellen sucht dieses Werkzeug: statisch, ohne Ausführung,
über den Syntaxbaum. Es ersetzt keinen Test, aber es findet die Klasse von
Fehlern, die Tests übersehen, weil sie den Zweig nie betreten.

    python3 tools/check-globals.py src/chimera/render/avatar.py
    python3 tools/check-globals.py src/          # rekursiv

Exitcode 1, wenn etwas gefunden wurde — damit es in eine Prüfkette passt.
"""

from __future__ import annotations

import ast
import builtins
import sys
from pathlib import Path

#: Namen, die der Interpreter in jedes Modul legt, ohne dass sie im
#: Syntaxbaum als Zuweisung auftauchen.
MODULE_DUNDER = {
    "__file__", "__name__", "__doc__", "__package__", "__spec__",
    "__loader__", "__builtins__", "__path__", "__debug__",
}

BUILTINS = set(dir(builtins)) | MODULE_DUNDER


class Scope:
    """Was in einem Gültigkeitsbereich gebunden ist."""

    def __init__(self, parent=None, kind="modul"):
        self.parent = parent
        self.kind = kind
        self.names: set[str] = set()

    def bind(self, name: str) -> None:
        self.names.add(name)

    def known(self, name: str) -> bool:
        if name in self.names:
            return True
        # Klassenkörper sind für verschachtelte Funktionen nicht sichtbar —
        # genau deshalb ist self.X kein Ersatz für ein Modulglobal.
        p = self.parent
        while p is not None:
            if p.kind != "klasse" and name in p.names:
                return True
            p = p.parent
        return False


def _targets(node) -> list[str]:
    """Namen, die eine Zuweisung bindet."""
    out = []
    stack = [node]
    while stack:
        n = stack.pop()
        if isinstance(n, ast.Name):
            out.append(n.id)
        elif isinstance(n, (ast.Tuple, ast.List)):
            stack.extend(n.elts)
        elif isinstance(n, ast.Starred):
            stack.append(n.value)
    return out


class Collector(ast.NodeVisitor):
    """Sammelt Bindungen und gelesene Namen je Gültigkeitsbereich."""

    def __init__(self, path: Path):
        self.path = path
        self.module = Scope(kind="modul")
        self.reads: list[tuple[str, int, Scope, str]] = []
        self._scopes = [self.module]
        self._where = ["<modul>"]

    @property
    def scope(self) -> Scope:
        return self._scopes[-1]

    # --- Bindungen --------------------------------------------------------

    def visit_Import(self, node):
        for a in node.names:
            self.scope.bind((a.asname or a.name).split(".")[0])

    def visit_ImportFrom(self, node):
        for a in node.names:
            self.scope.bind(a.asname or a.name)

    def visit_Assign(self, node):
        for t in node.targets:
            for name in _targets(t):
                self.scope.bind(name)
        self.generic_visit(node)

    def visit_AnnAssign(self, node):
        for name in _targets(node.target):
            self.scope.bind(name)
        self.generic_visit(node)

    def visit_AugAssign(self, node):
        for name in _targets(node.target):
            self.scope.bind(name)
        self.generic_visit(node)

    def visit_For(self, node):
        for name in _targets(node.target):
            self.scope.bind(name)
        self.generic_visit(node)

    def visit_Global(self, node):
        for name in node.names:
            self.module.bind(name)
            self.scope.bind(name)

    def visit_Nonlocal(self, node):
        for name in node.names:
            self.scope.bind(name)

    def visit_Try(self, node):
        for h in node.handlers:
            if h.name:
                self.scope.bind(h.name)
        self.generic_visit(node)

    def visit_With(self, node):
        for item in node.items:
            if item.optional_vars is not None:
                for name in _targets(item.optional_vars):
                    self.scope.bind(name)
        self.generic_visit(node)

    visit_AsyncWith = visit_With

    # --- neue Gültigkeitsbereiche ----------------------------------------

    def _function(self, node):
        self.scope.bind(node.name)
        inner = Scope(self.scope, kind="funktion")
        a = node.args
        for arg in (*a.posonlyargs, *a.args, *a.kwonlyargs):
            inner.bind(arg.arg)
        if a.vararg:
            inner.bind(a.vararg.arg)
        if a.kwarg:
            inner.bind(a.kwarg.arg)
        # Vorgabewerte und Dekoratoren gehören zum äußeren Bereich.
        for d in (*a.defaults, *[k for k in a.kw_defaults if k], *node.decorator_list):
            self.visit(d)

        self._scopes.append(inner)
        self._where.append(node.name)
        for stmt in node.body:
            self.visit(stmt)
        self._scopes.pop()
        self._where.pop()

    visit_FunctionDef = _function
    visit_AsyncFunctionDef = _function

    def visit_ClassDef(self, node):
        self.scope.bind(node.name)
        for d in node.decorator_list:
            self.visit(d)
        for b in node.bases:
            self.visit(b)
        inner = Scope(self.scope, kind="klasse")
        self._scopes.append(inner)
        self._where.append(node.name)
        for stmt in node.body:
            self.visit(stmt)
        self._scopes.pop()
        self._where.pop()

    def _comprehension(self, node):
        inner = Scope(self.scope, kind="funktion")
        self._scopes.append(inner)
        for gen in node.generators:
            for name in _targets(gen.target):
                inner.bind(name)
        self.generic_visit(node)
        self._scopes.pop()

    visit_ListComp = _comprehension
    visit_SetComp = _comprehension
    visit_DictComp = _comprehension
    visit_GeneratorExp = _comprehension

    def visit_Lambda(self, node):
        inner = Scope(self.scope, kind="funktion")
        a = node.args
        for arg in (*a.posonlyargs, *a.args, *a.kwonlyargs):
            inner.bind(arg.arg)
        if a.vararg:
            inner.bind(a.vararg.arg)
        if a.kwarg:
            inner.bind(a.kwarg.arg)
        self._scopes.append(inner)
        self.visit(node.body)
        self._scopes.pop()

    # --- Lesezugriffe -----------------------------------------------------

    def visit_Name(self, node):
        if isinstance(node.ctx, ast.Load):
            self.reads.append(
                (node.id, node.lineno, self.scope, ".".join(self._where[1:]))
            )


def check(path: Path) -> list[str]:
    """Meldungen für eine Datei."""
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except SyntaxError as exc:
        return [f"{path}:{exc.lineno}: nicht lesbar ({exc.msg})"]

    c = Collector(path)
    # Zwei Durchläufe: Beim ersten werden Modulglobale gesammelt, die
    # weiter unten stehen als ihr Aufruf. Eine Funktion darf einen Namen
    # benutzen, der nach ihr definiert wird — zur Laufzeit ist er da.
    c.visit(tree)
    c.reads.clear()
    c._scopes = [c.module]
    c._where = ["<modul>"]
    c.visit(tree)

    out = []
    for name, line, scope, where in c.reads:
        if name in BUILTINS or scope.known(name):
            continue
        out.append(f"{path}:{line}: {name!r} in {where or '<modul>'}")
    return out


def main(argv: list[str]) -> int:
    if not argv:
        print(__doc__)
        return 2

    files: list[Path] = []
    for arg in argv:
        p = Path(arg)
        files.extend(sorted(p.rglob("*.py")) if p.is_dir() else [p])

    found = []
    for f in files:
        found.extend(check(f))

    if not found:
        print(f"{len(files)} Datei(en): kein ungebundener Name.")
        return 0

    print(f"{len(found)} Fund(e) in {len(files)} Datei(en):")
    for line in found:
        print(f"  {line}")
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
