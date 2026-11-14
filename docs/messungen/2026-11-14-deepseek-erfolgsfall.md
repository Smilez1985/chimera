# Messung 2026-11-14 09:25 — DeepSeek-Erfolgsfall am Gerät

**Gerät:** chimera-pi (Heimnetz). Stand `102a65a`, Binary `45917dd1df91`,
`chimera-tor` seit 01:21:54 `active` (kein Neustart nötig — Schlüssel wirkt
sofort).

**Voraussetzung, die der Nutzer geschaffen hat:** um 09:16 das erste Passwort
in der Oberfläche angelegt (`state/web/passwort-hash`, 0600, 119 Byte), um
09:21 den Anbieter `deepseek` und den Schlüssel hinterlegt
(`config/geheim/deepseek`, 35 Byte, 0600).

## Befunde

| Prüfung | Ergebnis |
|---|---|
| `GET /api/einrichtung` | `{"noetig":false}` — Einrichtungsbetrieb beendet |
| `GET /api/module` ohne Anmeldung | **401** (vorher 409: Passwort fehlte) |
| `op: modelle` (`anbieter: deepseek`) | `["deepseek-flash","deepseek-v4-pro"]`, `wahl: deepseek-flash` |
| `op: chat` (`deepseek-flash`, „Antworte mit genau: hallo-chimera") | `text: "hallo-chimera"`, `verbrauch: {eingabe 41, ausgabe 26, cache_neu 41, cache_treffer 0, denken 20}` |
| `op: chat` **mit Werkzeug** „Nutze das Werkzeug uhrzeit" | `werkzeuge: [{name: "uhrzeit", argumente: {}}]` — Werkzeugweg läuft über DeepSeek |
| `op: quota_lesen` (id `deepseek`) | `zustand: gut`, `veraltet: false`, `alter_s: 0`, Herkunft „offizielle API", `endpunkt: GET https://api.deepseek.com/user/balance`, `belegtheit: dokumentiert` |

**Guthaben (echte Beträge, je Währung ein Pool — nicht summiert):**

| Währung | gesamt | aufgeladen | geschenkt |
|---|---|---|---|
| CNY | 63.38 | 63.38 | 0.00 |
| USD | 6.98 | 6.98 | 0.00 |

## Was damit belegt ist

1. Der DeepSeek-Adapter (`deepseek.rs`) arbeitet gegen die echte API, nicht
   nur gegen Attrappen: Authentifizierung, Modellliste, Chat, `usage`.
2. Die Werkzeugausgabe ist neutral (`name`/`argumente`), wie für den Agenten
   zugesagt — erstmals mit einem **Cloud**-Anbieter gemessen (bisher nur
   `ollama`).
3. Der Guthaben-Adapter liefert echte Beträge samt Herkunft und Frische.
4. Der Schlüssel wirkt ohne Neustart (Schreiben in `config/geheim/<id>`), und
   er wird bei 401 nicht zurückgegeben.

## Noch offen

- Der Agent setzt `"anbieter": "ollama"` fest (`src/chimera/provider/
  gateway.py`) — im **Gespräch** wird DeepSeek weiterhin nicht benutzt. Das
  ist der ROADMAP-Punkt „DeepSeek im Agenten auswählen" (Stufe 1, offen).
- Stufe 3 (Kosten aus Token × Preis) ist mit diesen Zahlen jetzt messbar.

## Anmerkung zum Bedienfeld

Die Kennung musste der Nutzer von Hand tippen und wusste nicht, was gemeint
ist — sie ist ein interner Name (`config/geheim/<id>`), kein Feld für einen
Menschen. Das Modul bildet sie jetzt aus der Bezeichnung (`kennungAus`), zeigt
sie gedämpft und bietet im Schlüssel-Bereich eine Auswahl statt eines zweiten
Tippfelds; der Server antwortet bei einer ungültigen Kennung mit Regel und
Vorschlag statt nur „ist ungueltig".
