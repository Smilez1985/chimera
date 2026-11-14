# Messung 2026-11-14 01:40 — Einrichtungsbetrieb am Gerät (Stand `102a65a`)

**Gerät:** chimera-pi (Heimnetz, Adresse im Journal), Binary `45917dd1df91` = Commit
`102a65a`. `chimera-tor` `active`, zuletzt gestartet 01:21:54 nach dem
Neustart durch `web-passwort` bzw. Installer.

## Befund

| Prüfung | Ergebnis |
|---|---|
| `state/web/` | **leer** — kein Passwort-Hash, also Erstanlage |
| `config/geheim/` | nur `ssh/` — **kein Anbieterschlüssel hinterlegt** |
| `GET /api/einrichtung` | `{"noetig":true,"ok":true}` |
| `GET /api/module` ohne Anmeldung | **409** (Sperre greift) |
| `GET /` | Setup-Seite (HTML, `lang="de"`) |
| Journal 01:21:54 | „Web-Oberflaeche auf http://0.0.0.0:8080 -- Einrichtungsbetrieb: noch kein Passwort gesetzt (Code steht oben im Protokoll)." |

## Deutung

Die Zusagen aus `102a65a` halten am Gerät: ohne Hash ist die Oberfläche
gesperrt (409), nur die Seite „Passwort anlegen" ist erreichbar. Das ist
zugleich der Angriffspunkt — solange kein Passwort steht, kann jeder im LAN
die Oberfläche übernehmen.

Die Journal-Zeile nennt weiter „(Code steht oben im Protokoll)". Das ist die
in der Übergabe benannte Unstimmigkeit: `117e05b` (Protokollzeile ohne
Code-Versprechen) liegt im Repo, aber noch in **keinem** Binary auf dem Gerät.
Erledigt sich beim nächsten Deploy.

## Nächster Schritt — hängt am Nutzer, nicht am Code

1. Auf `http://<pi>:8080` das Passwort anlegen (min. 8 Zeichen).
2. Modul 🔌 **Anbieter**: Kennung `deepseek`, Typ `deepseek`, Adresse leer,
   dann „Schlüssel setzen" mit dem echten DeepSeek-Schlüssel.

Danach ist der Erfolgsfall messbar (`op: modelle`, Chat mit `verbrauch`,
`quota_lesen` mit echten Beträgen). Ohne Schlüssel ist Stufe 1 der
Reihenfolge (Guthaben/Kosten) nur gegen Attrappen belegbar.
