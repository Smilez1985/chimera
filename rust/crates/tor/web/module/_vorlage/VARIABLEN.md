# Vorlage für ein Web-Modul / Template for a web module

Ausfüllen mit `chimera-tor --module-neu <name> [Optionen]`; alles andere setzt
das Werkzeug ein und prüft das Ergebnis. / Fill in with
`chimera-tor --module-neu <name> [options]`; the tool does the rest and checks the result.

| Variable | Option | Bedeutung / Meaning | Beispiel / Example | Erlaubt / Allowed |
|---|---|---|---|---|
| `{{NAME}}` | `<name>` | Verzeichnis und Modulname / directory and module name | `wetter` | a–z, 0–9, `-`, höchstens 32 |
| `{{TITEL_DE}}` | `--titel-de` | Titel im Menü (deutsch) | `Wetter` | Text ohne `"` und `\` |
| `{{TITEL_EN}}` | `--titel-en` | menu title (English); Vorgabe = deutscher Titel | `Weather` | Text ohne `"` und `\` |
| `{{SYMBOL}}` | `--symbol` | ein Zeichen vor dem Titel | `🌤` | ein Emoji oder leer |
| `{{REIHENFOLGE}}` | `--reihenfolge` | Position im Menü (klein = weiter vorn) | `50` | ganze Zahl, Vorgabe 100 |
| `{{RECHTE}}` | `--recht` (mehrfach) | was das Modul vom Gateway will | `status` | nur Rechte aus der Liste des Gateways |
| `{{KLASSE}}` | (abgeleitet) | Klassenname im JavaScript | `Wetter` | wird aus dem Namen gebildet |

Das Modul landet in `<ziel>/<name>/` (Vorgabe: `./<name>`). Danach nach
`/opt/chimera/web/module/<name>/` kopieren (Besitzer root); das Gateway meldet
es als „wartet auf Freigabe“, bis der Nutzer es mit der angezeigten Prüfsumme
freigibt (DESIGN 5v).
