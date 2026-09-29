# Fortlaufende Prüfung (CI)

## Warum

Die Tests dieses Projekts sind eigenständige Läufer, die von Hand
gestartet werden. Das funktioniert — solange jemand daran denkt. Genau das
ist zweimal schiefgegangen: Beim `Registry.load()`-Fehler und beim
Renderer-Startbefehl waren alle Tests grün, weil niemand den einen Zweig
aufgerufen hatte.

CI nimmt das *Daran-Denken* aus der Gleichung. Und sie prüft auf einer
**anderen Shell** als die Entwicklungsumgebung: dort BusyBox `ash`, in der
Pipeline zusätzlich `dash`. Beide unterscheiden sich von `bash`, aber
nicht auf dieselbe Weise — was auf einer läuft, muss auf der anderen nicht
laufen.

## Was geprüft wird

| Job | Inhalt |
|---|---|
| `python` | Alle `tests/test_*.py` einzeln, auf Python 3.11 und 3.13. Dazu `tools/check-globals.py` über `src/`, `tests/`, `tools/`. |
| `installer` | Alle `installer/tests/test-*.sh` unter **dash** und **BusyBox**, dazu Syntaxprüfung jedes Skripts. |
| `trockenlauf` | Preflight und Modul 40 gegen ein erfundenes Wurzelverzeichnis (Regel 10d) — und die Prüfung, dass der Trockenlauf wirklich nichts anfasst. |

Die Tests werden **einzeln** aufgerufen, nicht über einen Sammelbefehl:
Ein Fehlschlag soll die übrigen nicht verdecken.

Der Syntaxlauf ist kein Formalismus. Ein Modul, das kein Test aufruft,
fällt sonst erst auf dem Gerät auf — und dort womöglich mitten in einer
Installation.

### Der Trockenlauf-Job ist der wichtigste

Er prüft eine Zusage, die sonst niemand prüft: dass `--dry-run` wirklich
nichts ändert. Konkret wird die Bootkonfiguration vorher und nachher
verglichen, **und** kontrolliert, dass keine Sicherungsdatei entstanden
ist. Eine Sicherung im Trockenlauf wäre selbst eine Änderung — genau der
Fehler, den der erste Lauf auf echter Hardware hatte.

## Die Datei liegt nicht im Repo

`.github/workflows/tests.yml` ist in `.gitignore`. Nicht aus
Nachlässigkeit: **Der Token der Entwicklungsumgebung hat keinen
`workflow`-Scope**, GitHub lehnt einen Push mit Workflow-Änderungen
deshalb ab:

```
refusing to allow an OAuth App to create or update workflow
.github/workflows/tests.yml without `workflow` scope
```

Die Vorlage liegt neben dem Repo unter `ci-vorlage/tests.yml`. Wer sie
aktivieren will, legt sie von Hand an — über die GitHub-Weboberfläche oder
mit einem Token, der den Scope hat.

## Vor dem Push lokal prüfen

Eine Pipeline, die erst auf GitHub rot wird, kostet einen Umlauf und
verrät nichts, was man nicht vorher hätte wissen können. Was der Workflow
ausführt, lässt sich vorher ausführen:

```sh
# Python
for t in tests/test_*.py; do PYTHONPATH=src python3 "$t" || echo "ROT: $t"; done
python3 tools/check-globals.py src/ tests/ tools/

# Installer
cd installer && sh run-tests.sh

# Trockenlauf gegen erfundenes Wurzelverzeichnis
R=$(mktemp -d); mkdir -p "$R/proc/device-tree" "$R/etc" "$R/boot/firmware"
printf 'raspberrypi,model-zero-2-w\0' > "$R/proc/device-tree/compatible"
printf 'ID=debian\n' > "$R/etc/os-release"; : > "$R/boot/firmware/config.txt"
CHIMERA_ROOT="$R" CHIMERA_MODE=dry CHIMERA_ANZEIGE=whisplay \
  sh modules/40-anzeige.sh
```

## Was die CI nicht leistet

**Sie ersetzt keinen Lauf auf der Zielhardware.** Alles, was in der
Pipeline grün ist, lief auf einem x86-Rechner ohne SPI, ohne I2S und ohne
HAT. Die Fehler, die dieses Projekt bisher am meisten gekostet haben —
fehlendes `make` auf DietPi, ein Nachweis der von Gruppenrechten abhängt,
ein EEPROM das nicht programmiert ist — hätte keine CI gefunden.

Sie fängt Regressionen ab. Befunde kommen vom Gerät.
