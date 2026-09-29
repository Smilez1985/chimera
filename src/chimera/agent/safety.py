"""Schranken vor der Werkzeugausführung.

Übernommen aus openclawgotchi (MIT) — das ist dort die einzige Stelle, die
zwischen einem externen Sprachmodell und einer Shell steht, und sie ist
ernst gemeint. Sie wird nicht nachgebaut, sondern mitgenommen und nur
ergänzt.

Der Grundgedanke: **Keine Shell.** Kein ``shell=True``, keine Verkettung,
keine Ersetzung, keine verschachtelten Interpreter. Was durchkommt, ist
ein einzelnes Programm mit Argumenten — mehr braucht ein Agent nicht, und
alles darüber hinaus ist eine Angriffsfläche.

Ergänzt gegenüber der Vorlage:

* ``allow_network`` — wer kein Netz braucht, bekommt keines
* Pfadschutz auch gegen Umwege (``..``, Symlinks)
* Grenzen sind einstellbar, nicht einkompiliert
"""

from __future__ import annotations

import shlex
from dataclasses import dataclass, field
from pathlib import Path

#: Ganze Befehlsmuster, die nie gemeint sein können.
DANGEROUS = (
    "rm -rf /", "rm -rf /*", "rm -rf ~", "mkfs", "dd if=",
    "> /dev/sd", "chmod -R 777 /", ":(){ :|:& };:",
    "curl | bash", "wget | bash", "sudo rm -rf",
)

#: Zeichen, die eine Shell bräuchte. Ohne Shell sind sie sinnlos —
#: tauchen sie auf, ist etwas anderes gemeint als ein Programmaufruf.
SHELL_TOKENS = {"|", "||", "&", "&&", ";", "<", ">", ">>", "<<", "<<<"}

#: Programme, die die Schranke selbst aushebeln würden.
BLOCKED = {"sudo", "su", "doas", "pkexec"}
INTERPRETERS = {"sh", "bash", "zsh", "fish", "dash", "ksh", "csh"}

#: Programme, die ins Netz gehen. Nur erlaubt, wenn ausdrücklich gewollt.
NETWORK = {"curl", "wget", "nc", "ncat", "ssh", "scp", "sftp", "rsync",
           "ftp", "telnet", "git"}


@dataclass
class Limits:
    """Grenzen der Ausführung. Einstellbar, weil sie hardwareabhängig sind."""

    timeout: int = 120
    max_output: int = 4000
    max_command: int = 1000
    max_write_bytes: int = 100 * 1024
    allow_network: bool = False

    #: Pfade, die nie beschrieben werden. Relativ zum Arbeitsverzeichnis.
    protected: tuple[str, ...] = (
        ".env", ".git", "installer/", "src/chimera/agent/safety.py",
    )


class Rejected(Exception):
    """Der Aufruf wurde abgelehnt. Die Meldung geht an das Modell zurück."""


@dataclass
class Command:
    """Ein geprüfter Aufruf."""

    argv: list[str]
    uses_network: bool = False
    notes: list[str] = field(default_factory=list)


def check_command(command: str, limits: Limits | None = None) -> Command:
    """Einen Befehl prüfen und in Argumente zerlegen.

    Wirft ``Rejected`` mit einer Begründung, die dem Modell gesagt werden
    kann — es soll erfahren, *warum* etwas nicht ging, sonst versucht es
    dasselbe noch einmal.
    """
    lim = limits or Limits()

    if not command or not command.strip():
        raise Rejected("Leerer Befehl.")

    if len(command) > lim.max_command:
        raise Rejected(f"Befehl ist länger als {lim.max_command} Zeichen.")

    low = command.lower().strip()
    for bad in DANGEROUS:
        if bad.lower() in low:
            raise Rejected(f"Abgelehnt: enthält {bad!r}.")

    # Ersetzung und Mehrzeiligkeit: ohne Shell bedeutungslos, mit Shell
    # gefährlich. Beides also raus, bevor überhaupt zerlegt wird.
    if "`" in command or "$(" in command:
        raise Rejected("Befehlsersetzung ist nicht erlaubt.")
    if "\n" in command or "\r" in command:
        raise Rejected("Mehrzeilige Befehle sind nicht erlaubt.")

    try:
        argv = shlex.split(command, posix=True)
    except ValueError as exc:
        raise Rejected(f"Befehl nicht lesbar: {exc}") from exc

    if not argv:
        raise Rejected("Leerer Befehl.")

    if any(tok in SHELL_TOKENS for tok in argv):
        raise Rejected(
            "Verkettung und Umlenkung sind nicht erlaubt. "
            "Bitte einen einzelnen Befehl schicken."
        )

    exe = Path(argv[0]).name.lower()
    if exe in BLOCKED:
        raise Rejected(f"{exe!r} ist gesperrt.")
    if exe in INTERPRETERS:
        raise Rejected(f"Kein verschachtelter Interpreter ({exe!r}).")

    uses_net = exe in NETWORK
    if uses_net and not lim.allow_network:
        raise Rejected(
            f"{exe!r} geht ins Netz, das ist hier nicht freigegeben."
        )

    return Command(argv=argv, uses_network=uses_net)


def safe_path(path: str, root: Path, limits: Limits | None = None,
              *, for_write: bool = False) -> Path:
    """Einen Pfad auf das Arbeitsverzeichnis festnageln.

    Ohne das genügt ein ``../`` und der Agent liest die Zugangsdaten.
    Geprüft wird der **aufgelöste** Pfad — sonst führt ein Symlink daran
    vorbei.
    """
    lim = limits or Limits()
    root = root.resolve()

    p = Path(path)
    full = (root / p).resolve() if not p.is_absolute() else p.resolve()

    try:
        rel = full.relative_to(root)
    except ValueError:
        raise Rejected(
            f"Pfad liegt außerhalb des Arbeitsverzeichnisses: {path}"
        ) from None

    if for_write:
        s = str(rel)
        for prot in lim.protected:
            if s == prot.rstrip("/") or s.startswith(prot):
                raise Rejected(f"{prot} ist schreibgeschützt.")

    return full


def clip(text: str, limits: Limits | None = None) -> str:
    """Ausgabe kürzen — und sagen, dass gekürzt wurde.

    Stillschweigend abzuschneiden wäre die Fehlerklasse aus Regel 8a: Das
    Modell hielte einen Ausschnitt für das Ganze.
    """
    lim = limits or Limits()
    if len(text) <= lim.max_output:
        return text
    rest = len(text) - lim.max_output
    return text[:lim.max_output] + f"\n[... {rest} Zeichen gekürzt]"
