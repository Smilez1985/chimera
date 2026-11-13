# DeepSeek-API & Kostenmonitoring je API/Modell — Faktenblatt

**Stand aller Abrufe: 2026-11-13 (UTC)**, sofern bei der Angabe nichts anderes steht.
Methode: offizielle Doku (api-docs.deepseek.com, dort auch die Markdown-Fassungen `*.md`),
OpenAI-OpenAPI-Spec, Anthropic-Doku, GitHub-Repos/PyPI/crates.io-Metadaten.
Nichts installiert, nichts committet, keine kostenpflichtigen Aufrufe.

Kontext-Annahme: „chimera" = Rust-Gateway (HTTP via `ureq`) auf einem Raspberry Pi,
bereits angebunden: lokaler Ollama + Anthropic (Cloud). Neu: DeepSeek + lokale Kostenrechnung.

---

## 1. DeepSeek-API — Faktenblatt

| Punkt | Befund | Quelle (Abruf 2026-11-13) |
|---|---|---|
| Basis-URL (OpenAI-Format) | `https://api.deepseek.com` — Pfad `POST /chat/completions` | <https://api-docs.deepseek.com/api/create-chat-completion>; <https://api-docs.deepseek.com/> |
| Basis-URL (Anthropic-Format) | `https://api.deepseek.com/anthropic` | <https://api-docs.deepseek.com/guides/anthropic_api> |
| Auth-Header | `Authorization: Bearer <API_KEY>` (http/bearer) | <https://api-docs.deepseek.com/api/create-chat-completion> (Abschnitt „Authentication") |
| Alternative Auth | Anthropic-Format nutzt dieselbe Key-Logik über `x-api-key`/SDK-Env (`ANTHROPIC_API_KEY`); im Anthropic-Guide nur per SDK-Env beschrieben, Header-Detail siehe Messages-Referenz | <https://api-docs.deepseek.com/guides/anthropic_api>, <https://api-docs.deepseek.com/api/create-message> |
| Aktuelle Modellnamen | `deepseek-flash` (= DeepSeek-V4.1-Flash-1017), `deepseek-v4-pro` (= DeepSeek-V4-Pro-0813) | <https://api-docs.deepseek.com/quick_start/pricing> |
| Legacy-Namen (akzeptiert, umgeleitet) | `deepseek-v4-flash`, `deepseek-v4-flash-vision-exp` → werden von V4.1-Flash bedient, zum Flash-Preis | <https://api-docs.deepseek.com/quick_start/pricing> (Fußnote 1) |
| OpenAI-Kompatibilität | „API uses an API format compatible with OpenAI/Anthropic"; OpenAI-SDK mit geänderter `base_url` nutzbar. Chat Completions, zusätzlich Responses-API und Anthropic-Messages-API | <https://api-docs.deepseek.com/>, <https://api-docs.deepseek.com/guides/responses_api> |
| Kontextfenster | 1M Token (beide Modelle) | <https://api-docs.deepseek.com/quick_start/pricing> |
| Max. Ausgabe | max. 384K Token (`max_tokens` 1…393216); Default 8K (non-thinking), 64K (thinking), 128K bei `reasoning_effort: "max"` | <https://api-docs.deepseek.com/api/create-chat-completion> (`max_tokens`) |
| Thinking-Steuerung | `{"thinking":{"type":"enabled|disabled"}}` bzw. `reasoning_effort: none/low/high/max`; Default = thinking **enabled**, Effort `high`. `medium`/`xhigh` → `high`, `minimal` → `low` | <https://api-docs.deepseek.com/guides/thinking_mode> |
| `reasoning_content` | Denktext steht in `choices[].message.reasoning_content` (Non-Stream) bzw. `delta.reasoning_content` (Stream), gleiche Ebene wie `content` | <https://api-docs.deepseek.com/api/create-chat-completion> (Schema `ChatCompletionResponseMessage`), <https://api-docs.deepseek.com/guides/thinking_mode> |
| Reasoning im Kontext | Mit `tools` im Request muss `reasoning_content` früherer Turns zurückgegeben werden (wird in Kontext eingefügt); ohne `tools` wird es ignoriert | <https://api-docs.deepseek.com/guides/thinking_mode> |
| Tool-/Function-Calling | Ja, OpenAI-Form: `tools[] = {"type":"function","function":{name,description,parameters}}`, Antwort `message.tool_calls[]`, Folge-Message `{"role":"tool","tool_call_id":…,"content":…}`. Parallel-Calling wird unterstützt (LiteLLM-Flag `supports_parallel_function_calling`) | <https://api-docs.deepseek.com/guides/tool_calls>; <https://api-docs.deepseek.com/api/create-chat-completion> |
| Tool-Calling-Einschränkung | `tool_choice: "required"` und benannte Tool-Choice sind im **Thinking-Mode nicht** unterstützt → HTTP 400; mit Web-Tools wird `required` als `auto` behandelt | <https://api-docs.deepseek.com/api/create-chat-completion> (Zeile zu `tool_choice`, ~L916) |
| Sampling | `temperature`, `presence_penalty`, `frequency_penalty` sind im Thinking-Mode wirkungslos (kein Fehler, aber ignoriert); `frequency_penalty`/`presence_penalty` sind generell deprecated. `top_p`-Verhalten modellabhängig | <https://api-docs.deepseek.com/guides/thinking_mode>; <https://api-docs.deepseek.com/api/create-chat-completion> |
| Streaming | `stream: true` → data-only SSE, Terminierung `data: [DONE]`; Chunks sind `chat.completion.chunk`. Keep-Alive: SSE-Kommentarzeilen `: keep-alive` (nicht als JSON parsen). Non-Streaming hält Verbindung mit Leerzeilen. Server schließt nach 10 min ohne Inferenz-Start | <https://api-docs.deepseek.com/api/create-chat-completion>; <https://api-docs.deepseek.com/quick_start/rate_limit> („Request Keep-Alive") |
| Rate Limits | Keine QPS/Tokio-Angabe, sondern **Concurrency-Limits pro Account**: `deepseek-flash` 2500, `deepseek-v4-pro` 500 gleichzeitige Requests; Überschreitung → HTTP 429. Erhöhung per Formular kostenlos. `user_id` für Isolation (KVCache, Scheduling, Safety) | <https://api-docs.deepseek.com/quick_start/rate_limit> |
| Weitere Parameter (DeepSeek-Extensions) | `user_id`, `safety_check{level:low|high}`, `title{enabled}`, `deepseek_web_search`, `deepseek_read_url`, Prefix-/FIM-Completion (Beta) | <https://api-docs.deepseek.com/api/create-chat-completion> |
| Vision | `deepseek-flash` ja (Bilder in user/tool_result), `deepseek-v4-pro` **nicht** (Bild wird durch `[Unsupported Image]` ersetzt). Bild-Token: bis 384 Token je Bild (ältere Vision-Exp-Angabe) | <https://api-docs.deepseek.com/guides/vision>; <https://api-docs.deepseek.com/guides/anthropic_api> |
| Modell-Liste-Endpunkt | `GET /models` existiert (`api/list-models`) | <https://api-docs.deepseek.com/api/list-models> |
| Guthaben-Endpunkt | `GET /user/balance` existiert | <https://api-docs.deepseek.com/api/get-user-balance> |

### Fehlercodes (offizielle Liste)

| Code | Bedeutung | Praxis-Hinweis |
|---|---|---|
| 400 Invalid Format | Request-Body falsch | z. B. `tool_choice: required` im Thinking-Mode |
| 401 Authentication Fails | Key falsch | Key-Rotation im Gateway |
| 402 Insufficient Balance | Guthaben leer | **einziger „Kosten"-Signalpunkt der API** |
| 408 Request Timeout | z. B. langsamer Datei-Upload (OCR/ASR) | Retry |
| 413 Request Too Large | Datei zu groß | — |
| 422 Invalid Parameters | Parameter ungültig | — |
| 429 Rate Limit Reached | Concurrency/QPS überschritten | Backoff; Concurrency-Limit statt RPM beachten |
| 500 / 503 / 504 | Server-/Gateway-Fehler | Retry mit Backoff |

Quelle: <https://api-docs.deepseek.com/quick_start/error_codes> (2026-11-13).

### Wichtige Abweichungen vom OpenAI-Standard (für ein selbstgeschriebenes Gateway)

1. `thinking` und `reasoning_effort` sind zusätzliche Body-Felder; beim OpenAI-SDK müssen sie in `extra_body` (die Doku zeigt das explizit).
2. `frequency_penalty` / `presence_penalty` werden akzeptiert, aber ignoriert (deprecated).
3. `reasoning_content` ist ein Feld **neben** `content` — nicht Teil von `content`.
4. `user_id` ist ein Top-Level-Feld (nicht `user`), im Anthropic-Format unter `metadata.user_id`.
5. Usage enthält DeepSeek-spezifische Felder (`prompt_cache_hit_tokens`, `server_tool_use`, `safety_tokens`) — siehe Abschnitt 2.
6. Anthropic-Format: Claude-Modellnamen werden gemappt (`claude-opus*` → `deepseek-v4-pro`, `claude-haiku*`/`claude-sonnet*` → `deepseek-flash`); unbekannte Nicht-`claude`-Namen → 400. `budget_tokens` wird ignoriert. **Achtung Kostenfalle:** `claude-opus*` wird zum V4-Pro-Preis abgerechnet.
   Quelle: <https://api-docs.deepseek.com/guides/anthropic_api>.

---

## 2. Usage-Felder in der Antwort

Antwort-Beispiel (Non-Stream, offiziell):

```json
"usage": {
  "prompt_tokens": 7,
  "completion_tokens": 11,
  "total_tokens": 18,
  "prompt_tokens_details": { "cached_tokens": 0 },
  "prompt_cache_hit_tokens": 0,
  "prompt_cache_miss_tokens": 7
}
```

Pflichtfelder laut Schema (`required`): `prompt_tokens`, `prompt_tokens_details`,
`prompt_cache_hit_tokens`, `prompt_cache_miss_tokens`, `completion_tokens`, `total_tokens`.

| Feld | Bedeutung | Belegt? |
|---|---|---|
| `prompt_tokens` | Eingabe-Token; **= `prompt_cache_hit_tokens` + `prompt_cache_miss_tokens`** | ja, explizit in der Schema-Beschreibung |
| `prompt_cache_hit_tokens` | Eingabe-Token mit Cache-Treffer (Disk-Cache, automatisch aktiv) | ja |
| `prompt_cache_miss_tokens` | Eingabe-Token ohne Cache-Treffer | ja |
| `prompt_tokens_details.cached_tokens` | identisch zu `prompt_cache_hit_tokens` („Same as") | ja |
| `completion_tokens` | generierte Token (inkl. Denk-Token) | ja |
| `completion_tokens_details.reasoning_tokens` | Denk-Token (optional) | ja (Feld existiert); dass sie **in** `completion_tokens` enthalten sind, ist nur analog OpenAI/Doku-Logik — nicht wörtlich belegt (siehe Abschnitt 6) |
| `completion_tokens_details.safety_tokens` | DeepSeek-Extension; nur bei `safety_check: high`, „already included in `completion_tokens`" | ja, wörtlich |
| `server_tool_use.tool_search` / `.tool_fetch` / `.tool_image_search` | Anzahl **abgerechneter** Suchen/Fetches bei Web-Tools; Feld fehlt, wenn alle Zähler 0 sind | ja |

Quellen: <https://api-docs.deepseek.com/api/create-chat-completion> (Schema `CompletionUsage`),
<https://api-docs.deepseek.com/guides/kv_cache> (Cache-Felder), jeweils 2026-11-13.

### Streaming: braucht es `stream_options.include_usage`?

**Nein — nicht zwingend.** Die Doku (2026-11-13) sagt wörtlich:

> „If set to `true`, all chunks in the stream will include a `usage` field, whose value is `null` on every chunk except the last one. If omitted or set to `false`, the `usage` field is absent from all chunks except the last one.
> Either way, the last chunk before the `data: [DONE]` message carries the token usage statistics for the entire request in its `usage` field. Note that no separate usage-only chunk is emitted: the statistics ride on the last content chunk, whose `choices` array always contains exactly one element that carries no new content and a non-null `finish_reason`."

Praktische Konsequenz für Rust/`ureq`: **Usage hängt am letzten inhaltstragenden Chunk, es gibt keinen separaten Usage-Chunk und kein `choices: []`-Chunk.** Wer wie bei OpenAI einen „usage-only chunk" erwartet, verliert die Zahlen. `include_usage: true` ist trotzdem empfehlenswert, weil dann das Feld garantiert in jedem Chunk vorhanden ist (Wert `null`) und der Parser nicht zwischen „Feld fehlt" und „Feld null" unterscheiden muss.
Quelle: <https://api-docs.deepseek.com/api/create-chat-completion> (Abschnitt `stream_options` → `include_usage`).

---

## 3. Preise (offiziell, USD je 1 Mio. Token)

Abruf **2026-11-13**, Quelle <https://api-docs.deepseek.com/quick_start/pricing>.

| Modell | Input Cache-Hit off-peak | Input Cache-Hit peak | Input Cache-Miss off-peak | Input Cache-Miss peak | Output off-peak | Output peak |
|---|---|---|---|---|---|---|
| `deepseek-flash` (V4.1-Flash-1017) | **0,003** | **0,006** | **0,15** | **0,30** | **0,60** | **1,20** |
| `deepseek-v4-pro` (V4-Pro-0813) | **0,022** | **0,044** | **0,66** | **1,32** | **1,98** | **3,96** |

**Rabattzeiten (wörtlich):** „Off-peak rates are half of the peak rates. Peak hours are 01:00 - 04:00 and 06:00 - 10:00 UTC, Monday through Friday, excluding Chinese public holidays. All other hours are off-peak, including weekends and Chinese public holidays in full."
→ Peak = 01–04 UTC **und** 06–10 UTC, Mo–Fr (chin. Feiertage ausgenommen). Alles andere (inkl. Sa/So und chin. Feiertage) = off-peak = halber Preis.

Zusatzpreise (gleiche Quelle, gleicher Tag):

| Posten | Einheit | Preis |
|---|---|---|
| Search (Text/Bild) | je 1.000 Suchen | 0,75 USD |
| Web-Fetch | je 1.000 Fetches | 0,75 USD |
| File-Parsing / OCR | je 1.000 Seiten | 0,225 USD |
| TTS | je 10.000 Zeichen | 0,45 USD (zeitweise 50 %: 0,225) |
| ASR | je Stunde Audio | 0,116 USD (zeitweise 50 %: 0,058) |

Hinweise: Preise können sich laut Doku jederzeit ändern („Product prices may vary and DeepSeek reserves the right to adjust them").
Preishistorie (Change Log, <https://api-docs.deepseek.com/updates>): Preissenkung zum 2026-09-10 mit V4.1-Flash; Preise seit 2026-10-17 unverändert; Search/Fetch wurden ab 2026-10-31 16:00 UTC kostenpflichtig.

---

## 4. Wie andere Kosten zählen

### 4.1 Anbieter-APIs (Cloud, nur als Referenz — für chimera nicht nutzbar, weil DeepSeek so etwas nicht hat)

**OpenAI — Usage & Costs API** (Admin-Key nötig, `Authorization: Bearer $OPENAI_ADMIN_KEY`):

- `GET /v1/organization/costs?start_time=…&bucket_width=1d` → Buckets mit `results[].amount {value, currency}` und `line_item`, `project_id`, `api_key_id`, `quantity`. `start_time` = Unix-Sekunden, `end_time` exklusiv, `bucket_width` derzeit nur `1d`.
- Parallel `GET /v1/organization/usage/completions` (Token-Zahlen je Bucket, gruppierbar).
- Quelle: OpenAPI-Spec <https://github.com/openai/openai-openapi> (Pfad `/organization/costs`, abgerufen 2026-11-13); Doku-Seite <https://platform.openai.com/docs/api-reference/usage/costs> (Abruf aus der Sandbox 403/Cloudflare, daher Spec als Beleg).

**Anthropic — Usage & Cost API** (Admin-Key):

- Legacy: `GET /v1/organizations/usage_report/messages` (`starting_at`, `ending_at`, `bucket_width` 1d/1h/1m, `group_by` u. a. `model`, `api_key_id`, `workspace_id`, `context_window`) liefert je Bucket `uncached_input_tokens`, `cache_read_input_tokens`, `cache_creation.{ephemeral_1h_input_tokens,ephemeral_5m_input_tokens}`, `output_tokens`, `server_tool_use`.
- Legacy: `GET /v1/organizations/cost_report` (USD, Tages-Buckets, `group_by` `description`/`workspace_id`).
- **Neu:** „Usage and Cost Analytics API" mit `GET /v1/organizations/analytics/usage` und `GET /v1/organizations/analytics/cost`; die alten Endpunkte sind als „[Legacy]" markiert, es gibt eine Migrationsanleitung.
- Quellen: <https://platform.claude.com/docs/en/api/admin-api/usage-cost/get-messages-usage-report> und <https://platform.claude.com/docs/en/api/admin-api/usage-cost/get-cost-report> (Abruf 2026-11-13, API-Version 2026-10-21).

**OpenRouter — Preis- und Usage-Endpunkte (öffentlich, ohne Admin-Key lesbar):**

- `GET /api/v1/models` → je Modell `pricing {prompt, completion, input_cache_read, …}` in **USD pro Token** (Strings). Abruf 2026-11-13: 471 Modelle. Beispiel `deepseek/deepseek-v4.1-flash`: prompt `0.0000003` (= 0,30 USD/M), completion `0.0000012` (= 1,20 USD/M), `input_cache_read` `0.000000006` (= 0,006 USD/M) — deckt sich mit DeepSeeks Peak-Preisen, OpenRouter schlägt also keinen sichtbaren Aufschlag auf.
- `GET /api/v1/generation?id=…` → Usage/Bytes je Generation (Doku-Seite <https://openrouter.ai/docs/api-reference/get-a-generation>, 2026-11-13).
- `GET /api/v1/credits` existiert (ohne Auth 401) — Guthaben-Abfrage.
- Quellen: <https://openrouter.ai/api/v1/models>, <https://openrouter.ai/docs/api-reference/get-a-generation>.

### 4.2 Fertige, offline nutzbare Preis-/Kostentabellen

| Name | Sprache | Lizenz | Preistabelle mitgeliefert? | Aktualität | DeepSeek drin? |
|---|---|---|---|---|---|
| **LiteLLM** `model_prices_and_context_window.json` (Paket `litellm`, PyPI 1.109.1, 2026-11-12) | Python (JSON auch roh nutzbar) | MIT (Repo: „content outside `litellm/enterprise/` is MIT"; GitHub erkennt formal `NOASSERTION`) | ja, ~4,1 MB, ~5.988 Einträge | Datei zuletzt geändert 2026-11-13 (Commit `51679`) — sehr frisch | **ja, inkl. Peak/Off-Peak**: `deepseek-flash`, `deepseek-v4-pro` mit `off_peak_pricing{windows[]}` (Zeitfenster + Wochentage). Werte deckungsgleich mit der Doku. |
| **genai-prices** (Pydantic, PyPI 0.2.3, 2026-11-10) | Python | MIT | ja (`prices/data.json?`-Struktur mit Providern/Modellen, `pricing_urls`, `extractors` für Response-Parsing) | Repo aktiv (Push 2026-11-13) | ja, aber **veraltet**: `deepseek-v4-flash` input 0,14/M, `deepseek-v4-pro` 0,435/M, `cache_read` 0,0028/M; Kommentar nennt Off-Peak „UTC 16:30–00:30" (alte Regel). Aktuell laut Doku: 0,30/1,32/0,006 bzw. Peak 01–04 + 06–10 UTC. **Nicht ungeprüft übernehmen.** |
| **tokencost** (AgentOps) | Python | nicht geprüft | ja (Modelltabelle im Paket) | letztes Release **2025-08-13** → ~15 Monate alt | nicht geprüft, wegen Alter riskant |
| **llm-prices** (crates.io 1.0.0, 2026-10-23) | Rust | MIT | ja („Dated, source-cited LLM API prices (Anthropic, OpenAI, Gemini, DeepSeek) per 1M tokens"), 0 Dependencies | Release 2026-10-23; Repo `Mattbusel/llm-prices`, 0 Stars/12 Downloads — **unbewährt** | laut Beschreibung ja (nicht im Detail verifiziert) |
| **llm-cost-dashboard** (crates.io 1.3.1, 2026-10-21) | Rust | MIT | ja (104 Modelle, Prompt-Caching, Claude-Code-Logs) | Release 2026-10-21; ebenfalls Einzelautor, 143 Downloads | nicht verifiziert |
| **Helicone** | TypeScript/Next.js, selbst hostbar | Apache-2.0 | ja (eigene Modell-Registry; Doku „How We Calculate Cost") | aktiv (Push 2026-11-12) | ja (Integrationsseite „DeepSeek AI") |
| **Langfuse** | TypeScript/Python, selbst hostbar | Kern MIT (GitHub: `NOASSERTION`, Enterprise-Teile separat) | ja, Modell-Definitionen + Preise in der UI/Config pflegbar; „Token & Cost Tracking"-Doku | aktiv (Push 2026-11-13) | nicht einzeln geprüft |

Quellen: <https://github.com/BerriAI/litellm/blob/main/model_prices_and_context_window.json>, <https://pypi.org/project/genai-prices/>, <https://github.com/pydantic/genai-prices>, <https://pypi.org/project/tokencost/>, <https://crates.io/crates/llm-prices>, <https://crates.io/crates/llm-cost-dashboard>, <https://docs.helicone.ai/references/how-we-calculate-cost>, <https://helicone.ai/models>, <https://langfuse.com/docs/observability/features/token-and-cost-tracking>.

**Fazit für chimera:** Für Rust gibt es keine etablierte, breit genutzte Preis-Bibliothek (die zwei Crates sind Einzelautoren-Projekte mit <200 Downloads). Die belastbarste **Datenquelle** ist LiteLLMs JSON (MIT, faktisch täglich aktualisiert, enthält sogar die Peak-Fenster) — als Build-Zeit-Import oder als periodisch geprüfte Referenz, nicht als Laufzeit-Abhängigkeit.

---

## 5. Vorschlag: lokale Kostenrechnung im Gateway

1. **Nichts zur Laufzeit nachladen.** Preise als versionierte Datei `prices/deepseek.toml` im Repo, mit `as_of = "2026-11-13"` und `source = "https://api-docs.deepseek.com/quick_start/pricing"` im Kopf. Bei jedem Start Datum + Alter loggen; Warnung, wenn `as_of` älter als N Tage (z. B. 90).
2. **Pro Request einen Usage-Datensatz schreiben** (append-only JSONL oder SQLite): `ts_utc`, `provider` (`deepseek`/`anthropic`/`ollama`), `model_raw` (wie gesendet) **und** `model_billed` (nach Alias-Mapping! Legacy- und Claude-Namen!), `request_id`/`x-request-id`, `stream` (bool), `prompt_cache_hit_tokens`, `prompt_cache_miss_tokens`, `completion_tokens`, `reasoning_tokens`, `server_tool_use.*`, `http_status`, `latency_ms`, `price_version`. Ollama: `cost = 0`, aber Token/Energie optional mitschreiben.
3. **Rechnen** in Ganzzahl-Mikro-USD (oder `i64` Nano-USD), nicht in `f64`: `cost = hit*p_hit + miss*p_miss + out*p_out`, jeweils in „Token × µUSD pro 1M-Token / 1_000_000". Summe erst am Ende runden, nicht pro Request.
4. **Peak/Off-Peak** aus dem Request-**Startzeitpunkt** in UTC bestimmen (Mo–Fr, 01:00–04:00 und 06:00–10:00 UTC = Peak), Feiertage als kleine Ausnahmeliste in der Preisdationsdatei. Zwei Preissätze je Modell, ein Flag `peak: bool` im Datensatz mitschreiben — sonst ist die Rechnung später nicht nachvollziehbar.
5. **Cache-Treffer** kommen fertig aus `prompt_cache_hit_tokens`/`prompt_cache_miss_tokens` — **nicht** selbst schätzen. `prompt_tokens` ist deren Summe, also nicht zusätzlich addieren.
6. **Streaming:** `stream_options: {"include_usage": true}` setzen und Usage aus dem **letzten** Chunk lesen; Parser muss `: keep-alive`-Zeilen und `usage: null` tolerieren. Fehlt Usage (Abbruch, Timeout), Datensatz mit `usage_missing=true` markieren und getrennt ausweisen — nicht mit 0 buchen.
7. **Fallstricke:** Preise ändern sich (Rabatte, neue Modellgenerationen, Alias-Umleitung → falscher Preis); Rundung (pro Request runden = Drift); Streaming ohne Usage; Retries/429 dürfen nicht doppelt gezählt werden (nur erfolgreiche 200 zählen, Fehlversuche separat); Anthropic-Mapping `claude-opus*` → teureres V4-Pro; Extras (Search/Fetch/OCR/TTS) sind **nicht** Token-basiert und brauchen eigene Zähler; `402` = Guthaben leer als Alarm nutzen (`GET /user/balance`).
8. **Abgleich:** Monatssumme gegen DeepSeek-Dashboard/`/user/balance`-Differenz prüfen (DeepSeek hat keine Usage-API) und gegen Anthropics `cost_report`. Abweichung > X % → Preisdaten veraltet.

---

## 6. Was NICHT belegt ist (offen, nicht geraten)

1. **Kein Usage-/Cost-Report-Endpunkt bei DeepSeek.** Die Doku-Sitemap (2026-11-13) listet für die API u. a. `/user/balance`, aber keinen Usage- oder Kosten-Endpunkt. Ob es einen nicht dokumentierten gibt: unbekannt. → Kosten müssen selbst gezählt werden.
2. **Ob `reasoning_tokens` in `completion_tokens` enthalten sind**, steht nicht wörtlich in der Doku (nur bei `safety_tokens` steht „already included"). Analogie zu OpenAI legt „ja" nahe — vor Produktivbetrieb mit einem echten Request verifizieren.
3. **Ob Denk-Token genauso wie Ausgabe-Token bepreist werden**: aus der Preisstruktur (nur „output tokens") ableitbar, aber nicht explizit zugesagt.
4. **Chinesische Feiertage**: Die Doku nennt sie als Off-Peak-Ausnahme, veröffentlicht aber keine maschinenlesbare Liste. Für korrekte Abrechnung müsste man sie selbst pflegen (Quelle: offizieller chin. Feiertagskalender).
5. **Ob Cache-Treffer-Token zusätzlich als Input gezählt werden**: Doku sagt `prompt_tokens = hit + miss` — also nein; ein doppelt zählender Parser wäre ein Eigenfehler, keine offene Frage.
6. **Konkrete QPS/RPM-Limits**: nur Concurrency-Limits dokumentiert; RPM/TPS-Grenzen sind nicht genannt.
7. **Wartezeit bis Cache-Persistenz**: „Cache construction takes seconds", Lebensdauer „a few hours to a few days" — keine Garantien, Trefferquote nicht planbar.
8. **Preise Drittanbieter (OpenRouter) vs. direkt**: OpenRouter-Preise decken sich aktuell mit DeepSeeks Peak-Preisen; ob OpenRouter eigene Aufschläge/Rabatte zeitlich variiert, ist nicht dokumentiert geprüft.
9. **Lizenzen**: `tokencost`-Lizenz und die Lizenzsituation von Langfuse-Detailmodulen wurden nicht im Detail geprüft (GitHub meldet `NOASSERTION`).
10. **`llm-prices` (Rust)**: DeepSeek-Inhalt und ob Peak/Off-Peak modelliert ist, wurde nicht im Quelltext verifiziert (nur Crate-Beschreibung).
11. **Anthropic „Usage and Cost Analytics API"**: Existenz und Pfade sind belegt, aber Felddetails/Paginierung der neuen Endpunkte wurden nicht im Einzelnen gelesen.

---

## Quellenliste (alle Abruf 2026-11-13)

Offiziell DeepSeek:
- <https://api-docs.deepseek.com/> — Erste Schritte, base_url, Modellnamen
- <https://api-docs.deepseek.com/quick_start/pricing> — Preise, Kontext/Ausgabe, Peak-Fenster
- <https://api-docs.deepseek.com/api/create-chat-completion> — Auth, Parameter, SSE, `usage`-Schema, `stream_options`
- <https://api-docs.deepseek.com/guides/thinking_mode> — `thinking`, `reasoning_effort`, `reasoning_content`
- <https://api-docs.deepseek.com/guides/kv_cache> — Cache-Felder und Trefferregeln
- <https://api-docs.deepseek.com/guides/tool_calls> — Tool-Calling-Form
- <https://api-docs.deepseek.com/guides/anthropic_api> — Anthropic-Format, Modell-Mapping
- <https://api-docs.deepseek.com/guides/vision> — Bild-Token, Modellunterschiede
- <https://api-docs.deepseek.com/quick_start/rate_limit> — Concurrency, `user_id`, Keep-Alive
- <https://api-docs.deepseek.com/quick_start/error_codes> — Fehlercodes
- <https://api-docs.deepseek.com/quick_start/token_usage> — Tokenizer-Download, Hinweis „usage ist Quelle der Wahrheit"
- <https://api-docs.deepseek.com/updates> — Change Log / Preisänderungen
- <https://api-docs.deepseek.com/api/get-user-balance>, <https://api-docs.deepseek.com/api/list-models> — Existenz belegt

Andere Anbieter / Tools:
- <https://github.com/openai/openai-openapi> (`/organization/costs`)
- <https://platform.openai.com/docs/api-reference/usage/costs> (403 aus der Sandbox)
- <https://platform.claude.com/docs/en/api/admin-api/usage-cost/get-messages-usage-report>
- <https://platform.claude.com/docs/en/api/admin-api/usage-cost/get-cost-report>
- <https://openrouter.ai/api/v1/models>, <https://openrouter.ai/docs/api-reference/get-a-generation>
- <https://github.com/BerriAI/litellm/blob/main/model_prices_and_context_window.json>, <https://pypi.org/project/litellm/>
- <https://github.com/pydantic/genai-prices>, <https://pypi.org/project/genai-prices/>
- <https://pypi.org/project/tokencost/>
- <https://crates.io/crates/llm-prices>, <https://crates.io/crates/llm-cost-dashboard>
- <https://docs.helicone.ai/references/how-we-calculate-cost>, <https://helicone.ai/models>, <https://github.com/Helicone/helicone>
- <https://langfuse.com/docs/observability/features/token-and-cost-tracking>, <https://github.com/langfuse/langfuse>
