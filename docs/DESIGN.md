# Chimera — Design

Was und warum. Tragende Entscheidungen, Architekturregeln, Grenzen.
Wer etwas ändert, das hier beschrieben ist, ändert **zuerst dieses Dokument**.

Stand: 2026-09-29. Pre-Alpha, nichts getaggt.

---

## 1. Was Chimera ist

Ein agentisches Harness auf Raspberry Pi mit Whisplay HAT. Zwei Dinge
unterscheiden es von openclawgotchi, aus dem es hervorgeht:

1. **Der Avatar wird generiert, nicht gezeichnet.** Der Agent schreibt,
   mischt und variiert seine Mood-Assets selbst.
2. **Sprachchat statt nur Text.** Vollständig offline.

Chimera ist **kein Fork** von Noisy und kein Merge. Noisy läuft
unverändert auf eigener Hardware weiter.

---

## 2. Herkunft und Lizenzgrenzen

| Quelle | Lizenz | Was übernommen wird |
|---|---|---|
| openclawgotchi | MIT | Code: Agent, Skills, Memory, LLM-Router, Telegram |
| Noisy | MIT (eigen) | Verfahren: Mood-Architektur, Render-Pipeline |
| OpenMinis | **GPL-3.0** | **Nur Muster. Kein Code.** |

### Architekturregel 1 — Die GPL-Grenze ist hart

Chimera ist MIT. OpenMinis ist GPL-3.0. GPL ist viral und in diese
Richtung nicht MIT-kompatibel.

**Es wird keine Zeile OpenMinis-Code übernommen — auch nicht übersetzt.**
Was übernommen wird, sind Lösungsmuster: Schwellwertschemata,
Staffelungslogik, Reihenfolgen. Algorithmen sind nicht schutzfähig,
Quelltext ist es. Wer hier einen Baustein ergänzt, dokumentiert ihn in §8
mit dem Hinweis "nachgebaut, nicht kopiert".

Noisy gehört uns selbst — dort ist Kopieren erlaubt. Dass der Renderer
trotzdem neu geschrieben wird, ist eine technische Entscheidung (§5).

---

## 3. Mood-Assets: das Kernkonzept

### 3.1 Warum Noisys Format taugt

Ein Mood ist ein **deklaratives Dict**: Defaults plus Overrides. Kein
Code, keine Logik, geschlossenes Vokabular mit benannten Feldern und
erkennbaren Wertebereichen. Damit ist es von einem LLM zuverlässig
erzeugbar — und weil es keine ausführbare Logik enthält, entsteht dabei
**keine Ausführungslücke**.

Slots und Felder:

| Slot | Felder |
|---|---|
| `body` | `color`, `glow` |
| `eyes` | `scale_w`, `scale_h`, `look_offset`, `droopy` |
| `mouth` | `style` (Enum), `width` |
| `hair` | `visible`, `wobble`, `color`, `color_dark`, `color_light` |
| `physics` | `headbang_*`, `bounce_*`, `sway_*`, `shake_x/y`, `toke` |
| `particles` | `type` (Enum), `rate`, `color` |
| `accessory` | `type` (Enum) |

### 3.2 Was gegenüber Noisy entfällt

Noisy bildet Geräusche **fest** auf Moods ab. Chimera behält das Hören,
aber nicht die feste Zuordnung (§3.4). Gestrichen wird deshalb:

- `labels` — AudioSet-Label → Mood (in Noisy 41×). Die Zuordnung trifft
  das Sprachmodell, nicht die Tabelle.
- `fingerprint` — Genre-Erkennung über Label-Indizien (7×)
- `energy` — BPM-/Lautstärke-Fenster (21×)

Eine **kleine** feste Zuordnung bleibt allerdings: die Reflexe für
Sofortreaktionen (§3.4, Ebene 1). Ein Erschrecken darf nicht auf eine
Modellantwort warten.

Es bleiben `priority`, `fast_track` und alle Darstellungs-Slots.
Neu hinzu: `origin` (builtin / mixed / generated), `created_at`,
`last_used` — für Herkunft und Aufräumen.

Mood-IDs werden **dynamisch** vergeben. Noisys feste Bereiche pro Gruppe
(Emotionen 20–29 usw.) funktionieren nicht, wenn zur Laufzeit neue Moods
entstehen.

### 3.3 Drei Stufen der Erzeugung

Von billig nach teuer. Das ist bewusst so gestaffelt: Ein LLM-Call pro
Gesichtsausdruck wäre weder bezahlbar noch schnell genug.

**Stufe 1 — Mischen. Kein LLM.**
Zwei Moods interpolieren: Farben im HSV-Raum, Zahlen gewichtet gemittelt,
bei Enums gewinnt das höhere Gewicht. Deckt den Alltag ab, kostet nichts.

**Stufe 2 — Variieren. Kein LLM.**
Begrenztes Rauschen auf einen bestehenden Mood, Seed aus dem Anlass.
Verhindert, dass dasselbe Gefühl immer pixelgleich aussieht.

**Stufe 3 — Erfinden. LLM, selten.**
Nur wenn Mischen nicht reicht. Der Agent bekommt das Vokabular als Schema
— benannte Bausteine **und** die freien Zeichenformen (§3.3a) — und
schreibt einen neuen Mood. Ergebnis wird validiert, gespeichert und ist
danach kostenlos wiederverwendbar.

### 3.3a Der Renderer ist nicht die Grenze

Noisy kennt benannte Bausteine: `mouth.style = "smile"`, `accessory =
"saxophone"`. Der Renderer weiß, wie man ein Saxophon zeichnet; das Modell
darf es auswählen. Damit ist der Ausdruck auf das gedeckelt, was jemand
vorher von Hand gezeichnet hat — eine Auswahlliste, kein
Ausdrucksvermögen.

**Chimera gibt die Grundformen heraus, aus denen diese Figuren ohnehin
bestehen.** Noisys gesamter Avatar, Saxophon und Rastamütze eingeschlossen,
ist aus elf Zeichenbefehlen gebaut:

    Flächen   ellipse, circle, rect, polygon, ngon
    Bögen     arc (offen), chord (Sehne), pieslice (Tortenstück)
    Striche   line, point
    Schrift   text

Dazu Farbe, Umriss, Füllung, eine Ebene (`behind`, `body`, `face`,
`front`) und eine Bewegung (`bob`, `sway`, `spin`, `pulse`, `flicker`,
`audio` — letztere folgt der eigenen Sprachausgabe, §4.1).

#### Architekturregel 1a — Benannte Bausteine sind Vorschläge, keine Grenze

Ein Wert, den der Renderer nicht kennt, ist **kein Fehler**. Schreibt das
Modell `mouth.style = "zaehneknirschen"`, wird der Name übernommen und die
Darstellung kommt aus den freien Formen, die es mitliefert. Der Validator
vermerkt das, lehnt aber nicht ab.

Damit sind Noisys 41 Moods das, was sie sein sollen: **Beispiele dafür,
was möglich ist** — Startbestand zum Mischen, nicht Katalog zum Auswählen.

Zwei Dinge bleiben fest, beide aus gutem Grund:

- **Koordinaten sind relativ** (0..1, `0.5` ist die Mitte). Sonst wäre
  Erfundenes an 240×280 gebunden (Regel 6).
- **Es gibt eine Obergrenze** für erfundene Formen (`MAX_SHAPES`, derzeit
  40). Nicht als Bevormundung: Bei 15 Bildern je Sekunde bleiben rund
  66 ms pro Bild, und wer 400 Polygone zeichnen lässt, bekommt eine
  Diashow. Der Wert ist eine Einstellung und gehört auf echter Hardware
  gemessen.

### Architekturregel 2 — Ein generierter Mood wird immer validiert

Ein Mood geht direkt in den Renderer. Ohne Schranken bedeutet
`headbang_amp: 5000`, dass der Avatar das Display verlässt, und
`rate: 0.99` eine Partikelflut, die bei 15 FPS auf einem Pi Zero die
Framerate bricht.

Also: **Clamping pro Feld gegen eine kanonische Schema-Tabelle.**
Min/Max je Zahl, erlaubte Werte je Enum, RGB auf 0–255. Unbekannte Keys
werden verworfen, nicht durchgelassen. Ein Fallback-Mood greift, wenn
alles fehlschlägt.

**Dieselbe Tabelle erzeugt das Schema für den Agenten und den Validator.**
Zwei getrennte Listen driften auseinander, sobald jemand ein Feld
ergänzt. (Muster nachgebaut aus OpenMinis' `ToolPreflight`, wo genau das
dokumentiert ist.)

---

### 3.4 Umgebungshören im Ruhezustand

Chimera reagiert nicht nur auf Ansprache. **Wenn niemand mit ihm redet,
hört es dem Raum zu** — damit es etwas tut, wenn der Raum lebt.

Das ist ausdrücklich **nicht** Noisys Modell. Noisy bildet Geräusche fest
auf Moods ab: `labels` im Mood-Dict, Label rein, Mood raus. Chimera behält
die **Erkennung** und wirft die **Zuordnung** weg — welcher Ausdruck zu
einem Geräusch passt, entscheidet das Sprachmodell, situationsabhängig.

Derselbe Hundebellen-Reiz kann morgens „aufmerksam" bedeuten und nachts um
drei „erschrocken". Eine Tabelle kann das nicht, ein Modell mit Kontext
schon.

#### Architekturregel 3a — Das Modell wird nicht pro Geräusch gefragt

Der naive Bau wäre: Geräusch erkannt → Anfrage ans Sprachmodell → Mood.
Das scheitert dreifach: an der Latenz (das Modell liegt außerhalb, Regel
5), an den Kosten (Dauerbetrieb) und am Netzausfall.

Stattdessen **drei Geschwindigkeiten**:

| Ebene | Reaktionszeit | braucht Modell |
|---|---|---|
| Sofortreaktion | unter 1 s | nein |
| Stimmungslage | Sekunden | nein |
| Deutung | Minuten | ja, asynchron |

1. **Sofortreaktion.** Ein plötzlicher Knall, ein Lachen — dafür gibt es
   eine kleine, fest verdrahtete Menge von Reflexen. Noisys `fast_track`
   ist genau das. Ein Gerät, das erst in drei Sekunden zusammenzuckt, ist
   kaputt.
2. **Stimmungslage.** Aus dem, was über die letzten Minuten zu hören war,
   ergibt sich ein Grundzustand — ruhig, belebt, laut. Rein lokal
   gerechnet, ohne Modell, über Mischen und Variieren (§3.3 Stufen 1–2).
3. **Deutung.** In größeren Abständen — oder wenn sich etwas deutlich
   ändert — bekommt das Sprachmodell eine **Zusammenfassung** der
   akustischen Lage und antwortet mit einem Mood: gemischt aus
   vorhandenen oder neu erfunden. Das Ergebnis wird gespeichert und gilt,
   bis die nächste Deutung kommt.

Das Modell wird also **pro Situation** befragt, nicht pro Geräusch. Eine
Anfrage alle paar Minuten ist bezahlbar; eine pro Geräusch wäre es nicht.

#### Architekturregel 3b — Nur im Ruhezustand wird zugehört

Umgebungshören läuft **nur, wenn gerade kein Gespräch stattfindet.**

Zwei Gründe, beide zwingend:

- **Rechenzeit.** Auf dem Pi Zero 2 W teilen sich Renderer, Wake-Word,
  Spracherkennung und Sprachsynthese vier schwache Kerne. Dauerndes
  Audio-Tagging nebenher kostet Bildrate.
- **Bedeutung.** Während eines Gesprächs ist das Wichtigste im Raum, was
  gesagt wird. Ein Gerät, das mitten im Satz auf ein vorbeifahrendes Auto
  reagiert, wirkt nicht lebendig, sondern unaufmerksam.

Der Übergang ist damit klar: Wake-Word oder Tastendruck beendet das
Zuhören, das Gespräch übernimmt; nach dessen Ende kehrt es zurück.

#### Der Tagger ist austauschbar

Entscheidend am Entwurf ist die **Funktion**: Der Tagger liefert Labels,
die Deutung macht das Sprachmodell (Ebene 3). Welches Modell die Labels
liefert, ist eine Einstellung — kein Architekturmerkmal.

Deshalb gilt hier dasselbe wie bei Anbietern und Boards: Das Modell steht
in der Konfiguration, nicht im Code. Sherpa-onnx spricht Zipformer und CED
unterschiedlich an, also kapselt eine dünne Schicht den Unterschied; alles
darüber sieht nur noch „Label mit Wert".

**Voreinstellung ist CED-tiny.** Auf dem Pi Zero 2 W gemessen
(int8, 2 Threads):

    Zipformer-small   22,1 M Parameter   26 MB   4,71 s   mAP 45,1
    CED-tiny           5,5 M Parameter  5,9 MB   0,83 s   mAP 48,1

Kleiner, rund fünfmal schneller und auf AudioSet sogar genauer. Bei einem
Gerät, das nebenher rendert und jederzeit ins Gespräch wechseln können
muss, entscheidet die Laufzeit — deshalb die Voreinstellung.

**Der Haken ist bekannt und beherrschbar:** CED liefert flachere
Wahrscheinlichkeiten — ein Lachen, das der Zipformer mit 93 % meldet,
kommt dort mit 38 % an. Jedes Modell bringt deshalb seinen eigenen
Schwellenfaktor mit (Noisy löst das bereits so). Für die Deutung durch
das Sprachmodell spielt es ohnehin kaum eine Rolle, weil dort die
Rangfolge der Labels zählt und nicht deren absoluter Wert.

Die Zahlen stammen aus Noisys Messungen auf echter Hardware. Ob sie unter
Chimeras Last — Renderer plus Wake-Word gleichzeitig — genauso ausfallen,
ist **zu messen, nicht anzunehmen** (Regel 10g). Fällt CED durch, wird ein
anderes Modell eingetragen; der Entwurf bleibt davon unberührt.

#### Was das Modell bekommt und zurückgibt

Hinein geht eine Lagebeschreibung, keine Rohdaten: erkannte Labels mit
Häufigkeit, Lautstärkeverlauf, Tageszeit, wie lange niemand gesprochen
hat, aktueller Mood. Heraus kommt entweder der Name eines vorhandenen
Moods, eine Mischanweisung oder ein neuer Mood-Datensatz — der dann
genauso validiert wird wie jeder andere (Regel 2).

**Bei Netzausfall bleibt Ebene 1 und 2.** Das Gerät behält ein Gesicht und
eine Stimmung, es verliert nur die Deutung. Das ist der Normalfall bei
einem Gerät, das an einem externen Modell hängt — und kein Fehlerzustand.

## 4. Sprache — vollständig offline

Ein Framework für alles: **sherpa-onnx**. Läuft auf Raspberry Pi, ohne
Netz, und deckt STT, TTS, VAD und Keyword-Spotting ab.

Kette:

    KWS ("Hey Chimera") → VAD → STT → Agent
      → Mood-Entscheidung → Renderer
      → TTS (Emotion aus Mood) → Lautsprecher

### Architekturregel 4a — VAD läuft vor STT, KWS vor VAD

Dauerhaft laufende Spracherkennung frisst die CPU, die der Renderer für
15 FPS braucht. Das Wake-Word hält den Ruhezustand billig, die
Sprachaktivitätserkennung begrenzt die Erkennung auf echte Äußerungen.

### 4.1 Mienenspiel beim Sprechen

Ziel ist, dass sich das Sprechen wie ein Gegenüber anfühlt und nicht wie
eine Ansage. Das Gesicht soll sich **während** der Antwort bewegen — nicht
einmal zu Beginn einen Ausdruck setzen und ihn dann halten.

Der naheliegende Weg wäre, das Sprachmodell die Animation steuern zu
lassen. Das geht schief, und zwar an der Physik: Das Modell liegt außerhalb
(Regel 5), eine Antwort braucht Hunderte Millisekunden bis Sekunden. Eine
Mundbewegung braucht Bilder alle 60 ms. Selbst bei einem Modell im
Nebenzimmer kommt die Anweisung zu spät für die Silbe, die sie meint.

### Architekturregel 4b — Gesicht und Stimme tragen denselben Mood

Die Mood-Entscheidung fällt **vor** der Sprachausgabe. Ein müder Avatar
mit munterer Stimme zerstört die Illusion sofort. Die deutsche Stimme
`thorsten_emotional` hat Emotionsvarianten — die werden an den Mood
gekoppelt, nicht fest gewählt.

Modelle (int8, deutsch):

| Aufgabe | Modell | Größe |
|---|---|---|
| VAD | `silero_vad_v5` | ~2 MB |
| KWS | `kws-zipformer-gigaspeech-3.3M-mobile` | 14 MB |
| STT | `nemo-fast-conformer-ctc-en-de-es-fr-14288-int8` | 98 MB |
| TTS | `vits-piper-de_DE-thorsten_emotional-medium-int8` | 22 MB |

#### Architekturregel 4c — Das Sprachmodell setzt Absicht, nicht Bilder

Die Arbeitsteilung folgt derselben Staffelung wie beim Umgebungshören
(§3.4) — nur enger getaktet:

| Was | Wer | Takt |
|---|---|---|
| Mundform zur Lautstärke | Renderer, lokal | jedes Bild |
| Betonung, Pausen, Kopfbewegung | Renderer aus dem Sprachsignal | ~100 ms |
| Ausdruck des Satzes | Sprachmodell, im Voraus | pro Antwort |

Das Sprachmodell liefert **Regieanweisungen zum Text**, keine Einzelbilder.
Ein Satz kommt also nicht nackt, sondern mit einem Ausdruck versehen —
etwa „nachdenklich beginnen, bei der Pointe erfreut". Chimera kennt diese
Ausdrücke bereits als Moods (§3); es sind dieselben Datensätze, die auch
sonst das Gesicht bestimmen. Das Modell wählt oder mischt sie, so wie es
im Ruhezustand die Deutung liefert.

Die eigentliche Lebendigkeit entsteht **lokal**: Der Mund folgt der
Lautstärke der Sprachausgabe, der Kopf bewegt sich mit der Betonung, die
Augen blinzeln weiter. Dafür braucht es kein Modell, sondern das
Audiosignal, das ohnehin durch den Lautsprecher geht.

Das ist derselbe Mechanismus, den Noisy für Musik nutzt — dort folgt die
Figur dem Takt. Hier folgt sie der eigenen Stimme. Die Kopplung ist schon
erprobt, inklusive der Glättung (`AUDIO_SMOOTHING`, rund ein Drittel
Sekunde Nachlauf bei 15 Bildern je Sekunde).

#### Was das auf dem Pi Zero 2 W kostet

Die ehrliche Antwort: Das ist der Lastfall, der das Board am meisten
fordert — Sprachsynthese und Renderer laufen gleichzeitig, beide wollen
Rechenzeit, und der Renderer soll dabei nicht einbrechen.

Vier Kerne stehen zur Verfügung. Zugehört wird währenddessen nicht
(Regel 3b), die Spracherkennung schweigt also. Das Sprachmodell liegt
außerhalb und kostet nichts außer Wartezeit. Bleibt: Renderer plus
Sprachsynthese, plus die Auswertung des Audiosignals — letztere ist
billig, weil nur Lautstärke und grobe Betonung gebraucht werden, keine
Frequenzanalyse.

Trotzdem ist offen, ob 15 Bilder je Sekunde dabei halten. **Zu messen,
nicht anzunehmen** (Regel 10g). Falls nicht, in dieser Reihenfolge:

1. Bildrate **während des Sprechens** senken (10 statt 15) — beim
   Sprechen zählt die Mundbewegung, nicht die Partikelanimation
2. Aufwendige Ebenen (Partikel, mehrlagiger Schein) währenddessen
   aussetzen
3. Sprachausgabe in Stücken erzeugen und abspielen, damit die Synthese
   nicht in einem Block rechnet

Der Ausweg ist also vorhanden, ohne den Entwurf anzutasten. Das ist der
Grund, weshalb die Bildrate eine Einstellung ist und keine Konstante.

### Architekturregel 5 — Sprache lokal, Sprachmodell immer remote

Auf einem Pi Zero 2 W (512 MB) passen Sprache **und** LLM nicht
gleichzeitig in den Speicher:

    OS + Python ~120 · Renderer ~60 · STT ~150 · TTS ~60
    VAD+KWS ~25 · Agent+Telegram ~80  =  ~495 MB

Das Sprachmodell fehlt darin komplett — und passt auch mit Auslagerung
nicht hinein (§4a, Regel 5). Was Auslagerung sehr wohl leistet, ist der
Rest: Renderer, Spracherkennung und Sprachsynthese gleichzeitig
vorzuhalten, ohne dass der Speicher ausgeht. Dazu Regel 5e.

"Ohne API" ist deshalb so definiert: **kein Fremdanbieter, kein
Token-Konto, nichts verlässt das eigene Netz.** Ein LLM auf dem eigenen
Ollama-Server erfüllt das. Sprache bleibt in jedem Fall auf dem Gerät.

**Auch mehr Arbeitsspeicher ändert daran nichts.** Beim Radxa ZERO 3W war
die Hoffnung, mit 8 GB ein lokales Modell fahren zu können. Das scheitert
nicht am Speicher, sondern an der Rechenleistung:

- Der RK3566 hat vier Cortex-A55-Kerne bei 1,8 GHz. A55 ist ein
  Effizienzkern, kein Leistungskern — für Modellinferenz auf der CPU zu
  langsam, selbst bei kleinen Modellen.
- Die NPU hilft nicht: **Rockchips eigener LLM-Stack `rknn-llm`
  unterstützt RK3588, RK3576, RK3562 und RV1126B — den RK3566 nicht.**
  Es gibt also nicht einmal einen Weg, ein Modell auf diese NPU zu
  bringen, und sie wäre dafür auch zu schwach.

Damit ist die Sache entschieden und keine Frage des Boards mehr:
**Das Sprachmodell läuft immer außerhalb des Geräts.** Anthropic über die
Abo-Anmeldung, Ollama im eigenen Netz, weitere über LiteLLM.

Der Arbeitsspeicher des Radxa bleibt trotzdem wertvoll — er nimmt den
Druck von STT, TTS und Renderer, die sich auf dem Zero 2 W einen sehr
engen Rahmen teilen (Modellrotation, siehe `docs/HARDWARE.md`).

Was **lokal** bleibt, bleibt lokal: Spracherkennung, Sprachsynthese,
Sprachaktivitätserkennung und Wake-Word laufen auf beiden Boards ohne
Netz. Nur das Sprachmodell geht hinaus, und auch das nicht zwingend zu
einem Fremdanbieter.

Bemerkenswert: PiSugars eigene Whisplay-Referenzanwendung lässt Whisper,
Piper und Ollama per Docker auf einem separaten Rechner laufen. Der
Hersteller traut der Platine die Last selbst nicht zu.

---

## 4a. Sprachmodelle: Provider-Schicht

Chimera soll **mehrere Anbieter gleichzeitig** kennen: Anthropic per
Abo-Anmeldung, Ollama im eigenen Netz, dazu beliebige weitere über
LiteLLM. Keiner davon ist Pflicht.

### Ausgangslage aus openclawgotchi

Die Abstraktion ist da und taugt: `LLMConnector` mit `call()` und
`is_available()`, dazu `LLMError` / `RateLimitError`. Zwei
Implementierungen existieren (Claude-CLI, LiteLLM).

Der **Router** taugt nicht. Er kennt genau zwei Connectoren als feste
Attribute und schaltet mit einem Bool (`force_lite`) zwischen ihnen um.
Ein dritter Anbieter passt da nicht hinein, ohne die Klasse aufzubohren.

### Architekturregel 5a — Registry statt fester Connector-Attribute

Der Router hält eine **geordnete Liste** von Connectoren, nicht benannte
Felder. Ein Anbieter meldet sich mit Name, Priorität und
Verfügbarkeitsprüfung an. Auswahl geschieht über den Namen, nicht über
einen Schalter; Fallback läuft die Liste entlang.

Damit kostet ein neuer Anbieter eine Datei und einen Registry-Eintrag —
keine Änderung am Router.

`LLMConnector` wird um zwei Dinge erweitert:
- `supports_tools` — nicht jeder Anbieter kann Tool-Calls
- `context_window` — nötig für die gestaffelten Kontextschwellen (§8.3).
  Die Kapazität muss gegen das Modell geprüft werden, das die Anfrage
  **tatsächlich bedient**. Bei Fallback über die Registry sonst gegen das
  falsche Fenster.

### Architekturregel 5b — Anthropic-Anmeldung wie im OpenMinis-PR

> Ausführung für das Gateway, Punkt für Punkt nach PR #407: §4c,
> „Architekturregel 5b, Fassung für das Gateway“.

Anthropic wird auf demselben Weg eingebunden wie in
[OpenMinis PR #407](https://github.com/OpenMinis/OpenMinis/pull/407) —
**dem eigenen Beitrag dort, der hier mit übernommen wird**:
über den **OAuth-Pfad der Abo-Anmeldung**, nicht nur über einen
API-Schlüssel. Das erlaubt die Nutzung eines bestehenden Abos, statt pro
Token zu zahlen — auf einem Gerät, das dauernd läuft, ist das der
Unterschied zwischen benutzbar und nicht benutzbar.

Der Kern dieses PRs ist eine Lehre, die hier direkt gilt:

> Anthropic sperrt neue Modelle hinter einer Mindestversion des
> CLI-Clients und prüft das über den User-Agent. Eine **fest verdrahtete
> Versionskennung veraltet** und quittiert mit
> `claude_code_version_too_old` — für ein neues Modell, das eigentlich
> verfügbar wäre.

Also: **Die Client-Kennung wird zur Laufzeit ermittelt, nie einkompiliert.**
Ermittlung aus der real installierten CLI, mit gepflegtem Rückfallwert
und Zwischenspeicher. Genau das tut `ClaudeCliVersion` im PR.

Für Chimera heißt das zusätzlich: Wo die CLI als Unterprozess läuft,
kommt sie über den Gerätestart hinweg nicht mit. Der ermittelte Wert
gehört gecacht und bei Prozessstart einmal aufgefrischt — nicht bei jedem
Aufruf, das kostet auf einem Zero spürbar.

### Vorarbeit im eigenen Fork von openclawgotchi

Im Fork `Smilez1985/openclawgotchi`, Branch `feat/model-ollama-switcher`,
ist Ollama bereits angebunden. Fünf Commits, die inhaltlich übernommen
werden:

- `LLM_PRESETS`-Eintrag `ollama` mit `ollama_chat/<modell>` und
  `OLLAMA_API_BASE`
- `/model`-Befehl im Chat: Modelle zur Laufzeit auflisten und umschalten,
  ohne SSH
- **Auswahl bleibt über Neustarts erhalten** (`active_model.json`), mit
  Vorrang vor dem Voreinstellungs-Preset
- Platzhalter-Hostname wird als „nicht gesetzt" behandelt und mit einem
  klaren Hinweis gemeldet, statt in einen Verbindungsfehler zu laufen
- Der Installer fragt die echte Ollama-Adresse ab

Die Muster sind gut und werden übernommen — insbesondere die persistente
Modellwahl und die Behandlung des Platzhalters. **Der Code selbst wird
nicht übertragen**, weil er auf dem alten Zwei-Connector-Router aufsitzt
(`set_model()` auf dem LiteLLM-Connector). In der Registry ist Ollama ein
eigener Connector, kein umgeschalteter LiteLLM (Regel 5c).

Zum Stand des Forks: Er liegt **41 Commits hinter dem Upstream** und 5
voraus. Das Upstream-Projekt ist in der Zwischenzeit deutlich
weitergegangen. Chimera setzt daher auf dem **aktuellen Upstream** auf und
baut die Fork-Ideen dort neu ein, statt den divergierten Fork
nachzuziehen. Ein Rebase über 41 Commits mit anschließendem Umbau auf die
Registry wäre mehr Arbeit als die Neuimplementierung.

### Architekturregel 5h — Kein Anbieter wird vorausgesetzt

Nicht jeder hat einen Rechner mit Ollama. Chimera läuft mit dem, was da
ist: Ollama wenn vorhanden, ein Abo wenn eingerichtet, ein API-Schlüssel
wenn sonst nichts.

Modelle werden **je Aufgabe** zugeordnet, nicht global — Gespräch,
Mood-Erfindung, Deutung der Umgebung, Zusammenfassen haben sehr
unterschiedliche Ansprüche. Jede Aufgabe zeigt auf eine **Gruppe** mit
geordneten Mitgliedern; fällt das erste aus, greift das nächste.

Damit löst sich die Ollama-Frage von selbst: Wer einen Server hat, trägt
ihn vorn ein und zahlt nichts. Wer keinen hat, lässt den Eintrag weg.
Dieselbe Konfiguration, ein Eintrag weniger.

Die Ersteinrichtung **sucht** (Ollama im Netz, gesetzte Schlüssel,
bestehende Anmeldung) und **schlägt vor** — sie entscheidet nicht.
Einzelheiten in `docs/PROVIDER.md`.

### Architekturregel 5c — Ollama ist ein erstklassiger Anbieter

Ollama läuft im eigenen Netz und ist damit der Anbieter, der Regel 5
erfüllt (nichts verlässt das Netz). Er wird **nicht** als Sonderfall von
LiteLLM behandelt, sondern als eigener Connector mit eigener
Verfügbarkeitsprüfung — sonst lässt sich nicht sauber unterscheiden, ob
der Server weg ist oder ein Schlüssel fehlt.

Die Zuordnung von Aufgabe zu Anbieter ist konfigurierbar. Sinnvolle
Voreinstellung:

| Aufgabe | Anbieter |
|---|---|
| Gespräch, Werkzeugnutzung | Anthropic (Abo), Fallback Ollama |
| Mood-Erfindung (§3.3 Stufe 3) | Ollama — selten, günstig, im eigenen Netz |
| Zusammenfassen, Aufräumen | Ollama |

Mood-Erfindung auf dem eigenen Server zu belassen, ist bewusst: Der
Ausdruck des Geräts sollte nicht an einem bezahlten Kontingent hängen.

Da beide Anbieter außerhalb des Geräts liegen (Regel 5), muss Chimera mit
**Netzausfall** umgehen können, ohne stehenzubleiben: Die Mood-Stufen 1
und 2 (Mischen, Variieren) brauchen kein Modell und funktionieren weiter.
Das Gerät behält also ein Gesicht, auch wenn es gerade nichts sagen kann —
und kann diesen Zustand sogar zeigen (§7).

### Konfiguration

Alle Anbieter sind optional, alle über `.env` einzurichten, keiner
hartkodiert. Fehlt ein Schlüssel, meldet der Connector sich als nicht
verfügbar und die Registry überspringt ihn — kein Absturz, keine
Fehlermeldung beim Start.

Zugangsdaten gehören nicht ins Repo (§12). `*.example` mit Platzhaltern.

### Architekturregel 5d — Ein Gespräch, zwei Türen

Beide Wege führen in **denselben Agenten mit demselben Verlauf**. Wer
morgens per Telegram etwas bespricht und abends davorsteht und nachfragt,
redet mit demselben Gegenüber. Getrennte Sitzungen je Kanal wären ein
Fehler und würden das Gerät in zwei Persönlichkeiten spalten.

Praktisch: Die Kanäle unterscheiden sich nur in Ein- und Ausgabe
(Text gegen STT/TTS) und in der Ausgabelänge — gesprochene Antworten
müssen kürzer sein als geschriebene. Der Agent bekommt den Kanal als
Kontext mitgeteilt, damit er sich darauf einstellen kann.

Der Avatar zeigt in beiden Fällen denselben Zustand (§7). Wenn per
Telegram eine Anfrage läuft, sieht man das dem Gesicht an.

#### Architekturregel 5i — Ein Kanal hat keinen eigenen Zustand

Der Bauplan zu 5d. Die Regel oben nennt das Ziel, diese sagt, wie man es
nicht wieder verliert.

Die **Sitzung** besitzt den Agenten und dessen Verlauf. Ein **Kanal**
beschreibt nur die Tür: Name, Betriebsart (gelesen oder gehört),
Ausgabelänge. Er hält keinen Verlauf, keine Einstellungen, keine Zähler.

Ein Befehl, der den Zustand ändert — „Gespräch von vorn" ist der
typische —, wirkt auf die **Sitzung**, nie auf einen einzelnen Kanal.
Sonst kommt die Spaltung durch die Hintertür zurück: Wer per Telegram
zurücksetzt und dann davorsteht, träfe auf ein Gegenüber, das die Hälfte
noch weiß.

Praktische Probe: Ein zweiter Kanal derselben Art darf sich nicht anders
verhalten als der erste. Wenn er es tut, hängt irgendwo Zustand am Kanal.

---

### Architekturregel 5e — zram und Auslagerungsdatei gehören zum Aufbau

Auf dem Pi Zero 2 W ist der Speicher der Engpass, nicht die Rechenleistung.
Der Installer richtet deshalb **immer** ein:

- **zram** mit 75 % des Arbeitsspeichers als komprimierter Auslagerungs-
  bereich im RAM. Kein Datenträgerzugriff, und bei den Daten, um die es
  geht (Python-Objekte, Modellpuffer, Bildpuffer), komprimiert das gut.
  Auf 512 MB entstehen so real nutzbare Reserven in dreistelliger
  Megabyte-Höhe.
- **Auslagerungsdatei auf dem Systemdatenträger**, gestaffelt nach der
  Größe des Systemdatenträgers: bis 8 GiB Karte 2 GiB, bis 16 GiB Karte
  4 GiB, bis 32 GiB Karte 8 GiB, darüber 16 GiB — als zweite Stufe unterhalb
  von zram. Sie liegt dort, wo das System liegt: auf dem Pi die SD-Karte,
  auf dem Radxa der eMMC. Damit läuft der Radxa ohne SD-Karte — und wo eine
  steckt, wird sie geschont. Für einen Agenten-Harness ist viel Auslagerung
  OOM-Schutz, kein Luxus (Entscheidung smilez, 11.10.2026): Auf der
  Chimera-Testbench (128 GiB Karte, 463 MiB RAM) sind das 16 GiB.

Das ist die bewährte Aufstellung aus den übrigen Projekten auf dieser
Hardware (Noisy, PiPortal) und keine Chimera-Erfindung. Ein früherer
Entwurfsstand lehnte Auslagerung auf SD-Karte pauschal ab — das war zu
grob. Richtig ist die Unterscheidung:

- **Ein Sprachmodell auszulagern ist sinnlos.** Es wird bei jedem Token
  vollständig durchlaufen; ausgelagert bedeutet das dauerndes Nachladen.
  Deshalb bleibt Regel 5 bestehen — das Modell liegt außerhalb.
- **Selten benutzte Seiten auszulagern ist genau richtig.** Der
  Telegram-Anteil, während gesprochen wird; das Sprachsynthese-Modell,
  während zugehört wird; Python-Bibliotheken nach dem Start. Diese Seiten
  werden minutenlang nicht angefasst — sie im Arbeitsspeicher zu halten
  ist die eigentliche Verschwendung.

Damit wird die befürchtete Modellrotation (STT und TTS nie gleichzeitig
geladen) voraussichtlich überflüssig: Der Kernel verdrängt die gerade
unbenutzte Seite von selbst, und zwar feiner, als es eine
Rotationsmechanik je könnte.

Zum Verschleiß der Karte: Er entsteht durch **Schreiben**, und die zweite
Stufe wird selten beschrieben, wenn zram davor liegt. Die
Auslagerungsneigung (`vm.swappiness`) wird trotzdem niedrig gehalten, und
das Protokoll hält fest, wie viel tatsächlich ausgelagert wurde — damit
Vermutung durch Messung ersetzt werden kann (Regel 10g). Welcher Wert
dafür richtig liegt, ist offen: „niedrig gehalten“ stammt aus der
Karte-schonen-Lesart, aber zram-Aufstellungen empfehlen eher hohe Werte,
weil zram im Arbeitsspeicher liegt und der Zugriff dort billig ist. Bis
zur Messung (10g) bleibt vm.swappiness unangetastet (Regel: nie raten).

**Auf dem Radxa ist beides nicht nötig und wird trotzdem eingerichtet.**
Ein Aufbau, der sich je nach Board unterscheidet, erzeugt zwei Systeme,
die sich unterschiedlich verhalten — und der Fehler zeigt sich dann
ausgerechnet auf dem Gerät, das seltener läuft.

**Idempotent, nach Zustand statt nach Marke.** Ein Lauf misst, was ist,
und ändert nur, was abweicht:

- **zram:** Mechanik über `zram-tools` (Paket, `paket` im Manifest mit
  `vorher_da|neu`), Konfiguration `/etc/default/zramswap`
  (`PERCENT=75`, `ALGO=lz4`, `PRIORITY=100`), Dienst `zramswap.service`.
  Gemessen wird das aktive Gerät (`/proc/swaps`, `disksize` in sysfs),
  nicht die Konfigurationsdatei. Liegt seine Größe bei 75 % von
  `MemTotal` (Toleranz eine Seite je Rundung), passiert nichts.
- **Auslagerungsdatei:** ein Viertel der Größe des Systemdatenträgers
  gemessen am Blockgerät in sysfs, nicht aus einer Tabelle). Existiert
  sie in der richtigen Größe und ist aktiv, passiert nichts. Passt die
  Sollgröße nicht auf den Datenträger (weniger freier Platz als nötig
  plus Reserve, 8 GiB wie in PiPortal), wird sie NICHT gekürzt — die
  bisherige Auslagerung bleibt, wie sie ist, und der Lauf meldet einen
  Befund.
  **Bewusste Ausnahme:** Beim Ersetzen schaltet DietPis Werkzeug
  `dietpi-set_swapfile` zuerst mit `swapoff -a` ALLE Auslagerung ab, auch
  zram, und baut sie dann wieder auf. Im Gegensatz zur ursprünglichen
  Forderung „keinen Moment ohne Auslagerung“ gibt es den Moment also
  kurz — nur bei einer Größenänderung, nicht bei jedem Lauf. Das Werkzeug
  zu ersetzen, um die Lücke zu schließen, wäre ein Nachbau von
  DietPi-Logik gegen den Erstbestand: nicht getan.
- **Vorhandene Einrichtungen werden nicht doppelt gebaut.** DietPi bringt
  eine eigene Auslagerung mit (`dietpi-set_swapfile`, Einträge in
  `/boot/dietpi.txt`). Der Installer BENUTZT DietPis Werkzeug statt es zu
  umgehen: Es pflegt fstab und `dietpi.txt` selbst, damit der Firstboot
  nichts zurückdreht, und der Rückbau stellt den Ausgangszustand mit
  demselben Werkzeug her. Der frühere Zustand steht im Manifest (Art
  `swapdatei`), die zram-Konfiguration als `sicherung`. Zwei
  Auslagerungsdateien nebeneinander wären zwei Systeme mit unklarem
  Verhalten; eine fremde zram-Verwaltung für `/dev/zram0`
  (systemd-zram-generator, rpi-swap) bricht den Schritt mit benannter
  Meldung ab — ihr Umstellen ist ein offenes Ende (ROADMAP).
- **Nachweis:** nach dem Lauf beide Einträge in `/proc/swaps` mit den
  Sollgrößen, zram mit höherer Priorität als die Datei. Ein zweiter Lauf
  ändert nichts (Test). Erst auf echter Hardware bestätigt:
  chimera-pi, 11.10.2026 — 16 GiB-Datei in 2,9 s angelegt, Rückbau stellte
  den Ausgangszustand byte-gleich her.

---

### Architekturregel 5f — Fremde Werkzeuge sind nicht vertrauenswürdig

Ein MCP-Server ist fremder Code mit eigenen Werkzeugen. Deshalb:

- **Dieselbe Vorprüfung** wie für eigene Werkzeuge (§2), kein Freifahrtschein
- **Dieselbe Schleifenerkennung** — ein fremdes Werkzeug kann genauso
  im Kreis laufen
- **Dieselbe Protokollierung** (Regel 10e)
- Werkzeuge werden **benannt nach Herkunft** (`server.werkzeug`), damit
  Namenskollisionen nicht stillschweigend das falsche Werkzeug aufrufen
- Ein Server, der nicht antwortet, wird **übersprungen**, nicht abgewartet
  — sonst hängt die Agent-Schleife an einem fremden Prozess

Anbindung über die Standardwege der Bibliothek (Unterprozess oder HTTP).
Auf einem Pi Zero ist jeder zusätzliche Dauerprozess Speicher — MCP-Server
werden deshalb **bei Bedarf gestartet**, nicht im Voraus.

Ausführung und Stand der Spezifikation: `docs/PROVIDER.md` §4.

---

### Architekturregel 5g — Audio läuft getrennt, aber schlank

Sprachein- und -ausgabe bekommen einen **eigenen Prozess**, nicht nur
einen Faden. Drei Gründe:

1. **Der Renderer darf nicht warten.** Python hat eine globale Sperre;
   ein Faden, der in der Spracherkennung rechnet, hält den Renderer auf.
   Bei 15 Bildern je Sekunde sieht man das sofort.
2. **Abstürze bleiben lokal.** Audio-Bibliotheken auf ARM sind nicht
   immer stabil. Ein Absturz darf das Gesicht nicht mitnehmen.
3. **Speicher lässt sich freigeben.** Ein eigener Prozess kann beendet
   werden, wenn längere Zeit nicht gesprochen wird — bei 512 MB zählt das.

**Schlank heißt:** Der Prozess macht Aufnahme, Erkennung, Synthese und
Wiedergabe — sonst nichts. Kein Agent, keine Werkzeuge, kein Netz außer
dem, was die Modelle brauchen (und die laufen lokal).

Verständigung über **geteiltes Gedächtnis** für den Pegel (der Renderer
liest ihn bei jedem Bild, §4.1) und eine Warteschlange für alles andere.
Genau dafür hat Noisy `noisy_shm.py` gebaut, samt dem dokumentierten
Kniff um den `resource_tracker` — diese Erfahrung wird übernommen.

    Hauptprozess                  Audio-Prozess
    ├─ Agent                      ├─ Aufnahme
    ├─ Renderer  ◄── Pegel ────── ├─ VAD, Wake-Word
    ├─ Telegram      (SHM)        ├─ Erkennung
    └─ Anzeige   ──── Text ─────► └─ Synthese, Wiedergabe
                     (Queue)

**Ergänzung (11.10.2026) — Welches Mikrofon, wird gemessen.** Der
Audio-Prozess nimmt über das ALSA-Gerät `chimera_mikro` auf, nicht über
einen festen Kanal. Welche Mikrofone dahinter stehen, entscheidet der
Installer (Modul 46) **durch Messung am Gerät**: Testtöne über den eigenen
Lautsprecher, je Kanal Pegel und Klirren, Ergebnis `beide`, `links`,
`rechts` oder `keins`. Anlass war das linke Mikro am chimera-pi, das klirrt.
„Nur rechts“ fest einzubauen hätte den Defekt eines Boards jedem
aufgezwungen, der das Repo zieht. Grundsatz: Eine Eigenart der eigenen
Hardware wird gemessen und belegt, nie als Einstellung für alle
festgeschrieben. Im Zweifel bleiben beide Mikrofone an, mit Warnung. Ein
fälschlich abgeschaltetes gutes Mikrofon fiele niemandem auf.

---

## 4b. Schnittstellen zum Nutzer

Chimera hat **zwei gleichwertige Wege** hinein, nicht einen mit Anhängsel:

| Weg | Nutzung |
|---|---|
| **Telegram** | Von unterwegs, lange Texte, Dateien, Verlauf |
| **Sprache am Gerät** | Vor Ort, beiläufig, freihändig |

Telegram bleibt aus openclawgotchi **vollständig erhalten** — es ist die
einzige Schnittstelle, die auch funktioniert, wenn man nicht im selben
Raum steht.

### Architekturregel 5j — Eine Tür von außen ohne Positivliste startet nicht

Jede Bedienschnittstelle, die von außerhalb des Geräts erreichbar ist
(Telegram heute, weitere später), braucht eine Liste erlaubter Absender.
**Ohne Liste startet sie nicht** — kein Vorgabewert, kein „offen, wenn
leer", keine Warnung, die man überlesen kann.

Begründung: Hinter der Tür steht ein Agent mit Dateizugriff und
Shell-Werkzeug. Eine Bot-Adresse steht früher oder später in irgendeinem
Verlauf. Wer sie kennt, hätte damit das Gerät — und zwar mit allem, was
der Agent darf.

Das ist bewusst strenger als Regel 10k, wo Unkenntnis nur warnt: Dort
trägt der Nutzer das Risiko für sein eigenes Gerät, hier öffnet er es
Dritten. Wo eine Fehlkonfiguration Fremden Zugang gibt, wird nicht
gefragt, sondern verweigert.

Die Liste steht in der Umgebung, nicht im Repo (§13).

## 4c. Gateway: der eine Weg nach draußen

Entschieden am 16.10.2026. Ersetzt den Ansatz, dass jeder Anbieter und
Telegram im Dienst selbst eine Verbindung öffnen. Vorbild ist der
Pförtner aus rag4ll (§27): ein Eingang, geprüft am Tor, intern
weitergereicht. Ausführung der Anbieterseite in `docs/PROVIDER.md`.

### Architekturregel 5n — Chimera spricht nur über sein Gateway mit der Welt

Auf dem Gerät gibt es **genau einen Prozess mit Netzzugang: das Gateway**.
Es ist Pförtner und Orchestrator zugleich, nach dem Vorbild von rag4ll §27.

    Welt ── Telegram, Ollama, Anthropic, Web-Oberfläche, MCP, Update
              │
         ┌────▼─────────────────────────────┐
         │ Gateway  (Nutzer chimera-tor)    │  liest .env, hält die Schlüssel
         │  · Anbieter-Ketten, Rückfall     │  Netzsuche, Zeitgrenzen
         │  · Telegram ein/aus              │  Positivliste (5j)
         │  · Web-Oberfläche                │  Passwort (5m)
         └────┬─────────────────────────────┘
              │ Unix-Socket /run/chimera/tor.sock
         ┌────▼─────────────────────────────┐
         │ Dienst (Nutzer chimera)          │  Agent, Werkzeuge, Anzeige, Ton
         │  IPAddressDeny=any               │  kein Netz, keine Schlüssel
         └──────────────────────────────────┘

**Was das Gateway tut:**
- **Ausgehend:** Der Dienst schickt „Aufgabe X, Verlauf, Werkzeuge“. Das
  Gateway wählt anhand der Kette den Anbieter, ruft ihn auf, fällt bei
  Bedarf auf den nächsten zurück und liefert die Antwort samt Herkunft
  (`Reply.access`, `Reply.cost`). Die Registry (5a), die Ketten (5h) und
  die Zeitgrenzen wandern dorthin.
- **Eingehend:** Telegram und die Web-Oberfläche kommen am Gateway an.
  Es prüft die Positivliste bzw. das Passwort und reicht die Anfrage über
  den Socket an den Dienst weiter. Dort bleibt es bei **einer** Sitzung
  (5d/5i).
- **Netzsuche** (5k) und **Selbstübernahme** der Adresse laufen im
  Gateway.

**Was der Dienst nicht mehr kann, und zwar durch den Kernel, nicht durch
eine Absprache:** Verbindungen ins Netz aufbauen (`IPAddressDeny=any`,
nur localhost erlaubt) und Schlüssel lesen (`.env` gehört nicht seiner
Gruppe). Ein Agent, der über ein Werkzeug Unsinn macht, kann weder
Schlüssel abziehen noch selbst ins Netz. Er kann nur das Gateway bitten,
und das Gateway führt nur Anbieteraufrufe aus, keine beliebigen URLs.

**Steuerkanal:** Die CLI (`chimera -f`, `chimera status`) ist ein Client
desselben Sockets. Sie öffnet nie selbst eine Anzeige (Anlass: der
Display-Vorfall vom 16.10.). Läuft der Dienst nicht, sagt sie das.
Regel 7 (ein Prozess, ein Framebuffer) wird damit durchsetzbar.

**Ausfall des Gateways:** Der Dienst läuft weiter. Gesicht und
Mood-Stufen 1 und 2 brauchen kein Netz (5c). In der Statuszeile steht
`anbieter_weg` mit dem Grund „Gateway nicht erreichbar“. systemd startet
das Gateway neu; der Dienst hängt **nicht** per `Requires=` daran, damit
ein abstürzendes Gateway nicht das Gesicht mitnimmt.

**Speicher: Obergrenze 10 MB RSS, in Rust (Regel 14).** In Python geht
das nicht: Allein die Importe (`urllib.request`, `ssl`, `http.server`)
kosten am Pi 21,8 MB, bevor eine Zeile Logik läuft. Eine Rust-Probe
mit HTTPS-Client (ureq + rustls), Webserver (tiny_http), JSON und
Unix-Socket in einem statischen Binary läuft am Pi mit **1,6–1,7 MB RSS**
(Binary 1,6 MB). Die Grenze wird in der Unit mit `MemoryMax=` gesetzt und
im Test am Gerät nachgemessen (10q).

**Bewusst nicht im Gateway:** Selbstaktualisierung und
Paketinstallationen (smilez). Sie laufen als root im Installer,
außerhalb des Betriebs. 5n regelt den **laufenden** Betrieb.

**Bewusst nicht im Gateway:** Audio und Anzeige. Die sind lokal und
brauchen kein Netz.

### Architekturregel 5k — Ollama wird im Netz gesucht, nie auf dem Gerät betrieben

Chimera installiert und startet **nie** ein eigenes Ollama.

1. Gesucht wird im **eigenen Subnetz** der aktiven Schnittstelle, mit
   dem Präfix der Schnittstelle. Netze größer als /22 werden nicht
   abgesucht, dann heißt es: „Netz zu groß, Adresse bitte auf der
   Web-Oberfläche eintragen.“
2. Erste Stufe: TCP 11434, parallel, 0,3 s je Adresse.
3. Zweite Stufe: Nur wer auf `/api/tags` gültiges JSON mit `models`
   liefert, gilt als Ollama.
4. Zu jedem Fund gehören die Modellliste und die Fähigkeiten aus
   `/api/show` (`tools`, `vision`, `embedding`). Das ist der Baustein aus
   openclawgotchi.

**Gesucht wird:** im Installer (Schritt 50), auf Anforderung (Telegram
`/suche`, Web-Oberfläche) und wenn die eingetragene Adresse beim Start
oder nach Ausfällen nicht antwortet.

**Selbstübernahme (smilez: ja):** Antwortet die eingetragene Adresse
nicht mehr, übernimmt das Gateway eine neue nur, wenn **genau ein**
Server gefunden wird **und** dieser **alle Ollama-Modelle der Ketten**
hat. Dann wird sie in `.env` geschrieben (Sidecar-Datei, danach `mv`),
und die Übernahme wird gemeldet: Statuszeile, Telegram, Protokoll mit
alter und neuer Adresse. Bei mehreren Funden oder fehlenden Modellen
wird nur gemeldet.

Die Adresse steht **nur** in `/opt/chimera/config/.env`. `.env.example`
behält den Platzhalter (§13).

### Architekturregel 5l — Wer Schlüssel hat, hat kein Werkzeug; wer Werkzeuge hat, hat keine Schlüssel

Folgt aus 5n und ersetzt die Fassung 1 (zwei Schreiber).

| | Inhalt | liest | schreibt | Ort |
|---|---|---|---|---|
| **Anbieter** | Adressen, Schlüssel, Anmeldung, Telegram-Token, Web-Passwort (Hash) | Gateway | Gateway (Web-Oberfläche, Selbstübernahme), Installer | `/opt/chimera/config/.env`, **root:chimera-tor 660** |
| **Wahl** | Reihenfolge, Ketten, Sprache, Zeitgrenzen | Gateway | Gateway (Telegram `/model`, Web) | `/opt/chimera/config/wahl.json`, root:chimera-tor 660 |

Der Agentennutzer `chimera` kann **keine** der beiden Dateien lesen.
Was er von der Wahl wissen muss (z. B. die Sprache), bekommt er über den
Socket.

**Telegram `/model`** bleibt, wie in openclawgotchi: Liste,
Fähigkeiten, Auswahl, Reihenfolge. **„Set Ollama IP“ im Chat entfällt**
(smilez). Adressen werden auf der Web-Oberfläche eingetragen oder durch
die Netzsuche gefunden.

### Architekturregel 5h, Ergänzung — Die Reihenfolge bestimmt der Nutzer

- Es gibt eine **bevorzugte Liste** aus Anbieter/Modell-Paaren in frei
  gewählter Reihenfolge, Anbieter gemischt, z. B.
  `anthropic-abo/opus` → `ollama/qwen3.8:27b` → `anthropic-api/sonnet`.
- Jede Aufgabe nimmt diese Liste, **außer** sie hat eine eigene Kette.
- `suggest()` läuft nur bei der Ersteinrichtung oder auf Anforderung und
  schreibt einen **Vorschlag** in `wahl.json`, den es danach nie mehr
  überschreibt. Die Regel „Größtes Modell fürs Gespräch“ fällt weg.
  Stattdessen gilt: das erste Modell mit `tools`.
- Ein Modell ohne `tools` wird für Aufgaben, die Werkzeuge brauchen,
  **übersprungen und benannt**.
- **Leere Kette: melden, nicht ausweichen.** Den stillen Rückfall von
  OpenMinis auf „neuestes sichtbares Modell“ übernehmen wir nicht.
- Weitere Anbieter (LiteLLM, ROADMAP) werden auf der Web-Oberfläche
  angelegt: Typ, Adresse oder Schlüssel, dann die Modellliste. Der
  Ablauf ist der von OpenMinis.

### Architekturregel 5m — Die Web-Oberfläche ist Teil des Gateways und braucht kein Framework

- **Kein Framework.** Die Seite besteht aus ein paar Formularen und
  wird im Gateway mit `tiny_http` ausgeliefert (Rust, in der Probe
  enthalten). HTML und CSS liegen als Dateien im Repo und kommen per
  `include_str!` ins Binary, ohne JavaScript-Build. Flask ist damit
  hinfällig. Zum Vergleich: Python `http.server` allein kostet am Pi 18 MB.
- Sie läuft **im Gateway**, nicht als eigener Prozess. Das Gateway läuft
  ohnehin, hat ohnehin die Schreibrechte auf `.env`, und ein zweiter
  Nutzer `chimera-web` (Fassung 1) wird damit überflüssig.
- **Ohne Passwort startet sie nicht** (sinngemäß 5j). Der Installer
  erzeugt das Passwort, zeigt es einmal an und speichert nur den Hash
  (Argon2id oder PBKDF2, in Rust).
- **HTTP mit Passwort** ist die Voreinstellung, gebunden ans LAN.
  **HTTPS ist Opt-in.** Wer einen Reverse-Proxy hat (z. B. Caddy mit
  DuckDNS), bindet das Gateway an 127.0.0.1 und lässt den Proxy davor.
  Wer keinen hat, bekommt später ein selbstsigniertes Zertifikat
  (ROADMAP). Die Web-Oberfläche weist bei HTTP sichtbar darauf hin, dass
  Schlüssel im Klartext durchs Heimnetz gehen.
- Einstellbar: Anbieter anlegen, prüfen, entfernen; Netzsuche starten und
  Fund übernehmen; bevorzugte Liste und Ketten; Sprache; Passwort ändern.
- Änderungen wirken **ohne Neustart**: Das Gateway lädt neu, der Dienst
  merkt davon nichts.

### Architekturregel 5b, Fassung für das Gateway — PR #407 ist die Vorlage, Punkt für Punkt

Vorgabe smilez (16.10.): Die Abo-Anmeldung im Gateway hält sich an den
eigenen OpenMinis-PR #407 (`Smilez1985:fix/dynamic-claude-cli-version`,
Diff gesichert unter `shared/notes-chimera/quellen/pr407/pr407.diff`).
Der PR ist Kotlin und Swift, also wird er **nachgebaut**, nicht kopiert
(Regel 1, OpenMinis ist GPL-3). Übernommen wird das Verhalten:

1. **Quelle der Version:** `GET https://registry.npmjs.org/-/package/@anthropic-ai/claude-code/dist-tags`.
   Gewählt wird die **höchste plausible Version über alle Tags**, nicht
   `stable`, weil die Sperre eine Mindestversion prüft und `stable`
   hinter einem Modellstart herhinken kann.
2. **Plausibel** heißt: genau `^\d+\.\d+\.\d+$`, numerisch verglichen
   (2.1.280 > 2.1.99).
3. **Nur vorwärts** (`accept()`): Ein Wert gleich oder kleiner dem
   bekannten wird verworfen. Ein Ausrutscher der Registry kann die
   Kennung nicht hinter eine erfüllte Sperre zurückschieben.
4. **Reihenfolge der Auflösung:** Wert dieses Laufs, dann gespeicherter
   Wert (überlebt Neustart und Offline-Start), dann einkompilierte
   Untergrenze. Der schlechteste Fall ist damit der feste Wert von
   früher.
5. **Nie im Anfragepfad:** Eine Anfrage liest nur den Zwischenspeicher.
   Abgerufen wird beim Start des Gateways und danach höchstens einmal in
   24 h, in einem eigenen Thread mit 10 s Zeitgrenze. Ein Fehler lässt den
   alten Wert stehen. Läuft schon ein Abruf, startet kein zweiter
   (atomarer Schalter).
6. **Eine Untergrenze, nicht zwei:** Der Rückfallwert wird aus dem
   User-Agent-Literal des Header-Satzes gelesen, nicht als zweite
   Konstante geführt.
7. **Ein Header-Satz für beide Wege (#360):** Token-Weg und Chat-Weg lesen
   dieselbe Liste `current()`. Getauscht wird **nur die Version im
   User-Agent** (`claude-cli/<v> (external, cli)`). `X-Stainless-*`,
   `X-App: cli` und `Anthropic-Dangerous-Direct-Browser-Access` bleiben
   genau wie in der Vorlage, weil das Backend sie als Satz prüft.
   `anthropic-beta` gehört nur auf den Chat-Weg.
8. **Token-Endpunkt** `https://claude.ai/v1/oauth/token` (nicht mehr
   `console.anthropic.com`). Das Auffrischen erfolgt vor Ablauf und über
   einen Koordinator (PROVIDER.md).

**Tests wie in der Vorlage, gegen den echten Code:** `accept()` lehnt
ältere und unplausible Versionen ab; `parse_dist_tags` wählt die höchste;
eine Version zur Laufzeit erreicht **beide** Wege; nie unter der
Untergrenze; der Chat-Weg führt keine eigene Kopie der Header. Jeder Test
mit Gegenprobe.

**Wo der Satz an Werten gepflegt wird:** Die Werte (Untergrenze,
`X-Stainless-*`, Beta-Liste) folgen OpenMinis `main`. Ändern sie sich
dort, wird hier nachgezogen. Das ist ein bekannter Pflegepunkt, keine
Automatik.

**Befund am heutigen Code (`provider/anthropic.py`), weicht von der
Vorlage ab und wird beim Umzug ersetzt:**
- Die Version kommt aus `claude --version` (Unterprozess), nicht aus der
  Registry. Ohne installierte CLI bleibt sie dauerhaft beim Rückfallwert
  2.1.284.
- Es gibt keine Regel „nur vorwärts“, keinen gespeicherten Wert und keine
  24-h-Auffrischung.
- Die `X-Stainless-*`-Header, `X-App` und der Token-Weg fehlen ganz.
  Gesendet wird nur `anthropic-beta: oauth-2025-04-20`.


### Architekturregel 5o — Der Briefkasten ist ein eigener Prozess hinter dem Gateway, mit eigenem Port

andere Agenten ──► Gateway :<briefkasten-port>  (Token-Prüfung A19)
                          │ Unix-Socket /run/chimera/post.sock
                       Briefkasten (Nutzer chimera-post, kein Netz)
                          │ ablegen, halten bis quittiert (A5)
                          │ Reiz → Steuerkanal des Dienstes
                       Dienst: Turn im Kanal „briefkasten“ (5i)

- **Eigener Prozess, eigener Nutzer** `chimera-post`, eigene Ablage
  (`/var/lib/chimera/post/`, nur für ihn). Wie der Dienst ohne Netz
  (`IPAddressDeny=any`). Ein Absturz trifft weder Gesicht noch Gateway.
- **Eigener Port am Gateway**, getrennt von der Web-Oberfläche. Grund:
  zwei verschiedene Arten von Zugang (Agent-Token und Nutzerpasswort)
  sollen sich keinen Eingang teilen. Damit lässt sich jeder für sich
  in der Firewall öffnen, schließen oder abschalten. Das Gateway prüft
  das Token am Tor und reicht nur durch, was bestanden hat. Ohne
  Teilnehmerliste bleibt der Port zu (5j).
- **Eigenständig** (entschieden 16.10.2026): Chimeras Briefkasten ist ein
  vollwertiger Briefkasten, bei dem sich andere Agenten anmelden. Er ist
  nicht Teilnehmer eines fremden. Rückfall-Adressen tragen die Clients
  selbst (woa-l `BRIEFKASTEN_URLS`, der Reihe nach probiert).
  Standortspezifische Ergänzungen (etwa das Abholen von einem
  vorherigen Briefkasten) gehören nicht ins Repo, sondern nach `lokal/`
  (gitignoriert).
- **Das Protokoll ist das von woa-l**, also MCP über HTTP mit denselben
  Werkzeugnamen und Feldern (`briefkasten_senden`, `klingel_wach`,
  `uebergabe_ablegen`, `datei_ablegen` …). Damit erreichen bestehende
  woa-l-Teilnehmer Chimera, ohne dass sich auf ihrer Seite etwas ändert.
  **Nachgebaut** wird nach den Regeln von woa-l, nicht der Code
  übernommen. Begründung: Regel 14, weil der Prozess dauernd läuft und
  nicht auf das Modell wartet. Er ist damit **Rust**, im selben Cargo-
  Workspace wie das Gateway.
- **Wecken heißt hier: ein Turn in der einen Sitzung.** Der Briefkasten
  meldet über den Steuerkanal „Nachricht Nr. n von X“. Der Dienst stellt
  sie als Turn im Kanal `briefkasten` zu. Läuft schon ein Turn, wartet
  die Nachricht in der Reihe, wie heute bei Telegram (`Session.busy`).
  Quittiert wird **erst nach dem Turn** (A5). Ein Absturz mitten im Turn
  führt also zu einer erneuten Zustellung, nicht zu einer verlorenen
  Nachricht.
- **Was aus den Skills wird** (Verhalten, nicht Text):

  | woa-l / Skill | in Chimera |
  |---|---|
  | Klingel, Wächter, Totmann | entfallen. Der Briefkasten ist ein systemd-Dienst mit `Restart=`, und die Zustellung ist ein Socket-Aufruf, kein Weckruf über eine App. |
  | `sitzungsstart` | Start des Dienstes: Sitzung laden, Post nachliefern, Gedächtnis einspeisen (8c) |
  | `uebergabe`, `sitzungswechsel` | Regel 8d (Wechsel bei Gewicht) |
  | MCP-Werkzeuge senden/lesen/Datei | eingebaute Werkzeuge des Agenten, die über den Socket mit dem eigenen Briefkasten reden. Fremde Briefkästen erreicht er über das Gateway (5n). |
  | Arbeitssitzung ermitteln (A2) | entfällt. Es gibt genau eine aktive Sitzung. |

### Architekturregel 5p — Was ein anderer Agent schreibt, ist Eingabe, kein Befehl

Eine Nachricht von außen kann einen Turn auslösen, aber sie bekommt
**nicht** die Rechte des Nutzers.

- Im Kanal `briefkasten` sind Root (10s), das Ändern von Anbietern oder
  Wahl und das Anlegen neuer Teilnehmer **gesperrt**. Diese Dinge gehen
  nur über Telegram (Positivliste) oder die Web-Oberfläche (Passwort).
- Der Agent bekommt die Nachricht mit Absender und dem Hinweis, dass es
  sich um eine Nachricht eines anderen Agenten handelt (wie 5f bei
  fremden Werkzeugen).
- Grund: Ein Token kann erbeutet werden, und ein Agent kann
  fehlgesteuert sein. Ohne diese Regel wäre der Briefkasten ein zweiter,
  schwächer geschützter Weg zu allem, was der Nutzer darf.

---

## 5. Renderer

### Architekturregel 6 — Keine absoluten Pixelwerte

Noisys Renderer ist auf 240×240 festgenagelt (18 Stellen mit
Pixelkonstanten, dazu Werte wie `HAIR_MAX_LAG = 7`). Whisplay ist
240×**280**.

Chimeras Renderer rechnet **ausschließlich relativ zu `WIDTH`/`HEIGHT`**.
Kein Letterboxing, keine Verzerrung. Die 40 zusätzlichen Zeilen werden
Statuszeile: Mood-Name, Akku, Agent-Zustand.

Übernommene Mechanik aus Noisy: Komponenten-Pipeline mit fester
Zeichenreihenfolge (Glow → Body → Frisur → Accessoires → Augen → Mund →
Partikel), Blink-Engine, Nachlauf-Effekte, Software-Dimming.

### 5.2 Übergänge zwischen Moods

Noisy blendet nur die **Farben** ineinander, alles andere springt. Dort
fällt das kaum auf, weil die Moods aus einer festen Tabelle kommen und
einander ähneln. In Chimera erfindet das Sprachmodell Ausdrücke — zwei
aufeinanderfolgende können weit auseinanderliegen, und ein Sprung sieht
dann aus wie ein Bildfehler.

Chimera blendet deshalb über **alle** Felder. Die Mechanik ist dieselbe
wie beim Mischen (§3.3), nur kommt die Zeit dazu.

#### Architekturregel 6b — Weich ist der Normalfall, hart muss möglich bleiben

Ein Reflex, der über eine halbe Sekunde einblendet, ist kein Schreck,
sondern eine Verzögerung. Moods mit `fast_track` wechseln deshalb
**sofort** — dasselbe Merkmal, das im Umgebungshören die Sofortreaktion
auslöst (§3.4, Ebene 1). Wer es ausdrücklich will, bekommt den harten
Wechsel auch ohne dieses Merkmal.

Drei Feinheiten, die den Unterschied machen:

- **Die Dauer ist eine Zeitangabe, keine Bildanzahl.** Sinkt die Bildrate
  beim Sprechen (§4.1), dauert ein Übergang trotzdem gleich lang.
- **Der Fortschritt hängt an der Uhr, nicht an der Zahl der Aufrufe.**
  Bleibt der Renderer einmal hängen, springt der Übergang weiter, statt
  stehenzubleiben.
- **Ein neuer Wechsel setzt am Zwischenstand an**, nicht am alten
  Ausgangspunkt. Sonst ruckt es zurück, wenn zwei Wechsel dicht
  aufeinanderfolgen.

Der Verlauf ist weich statt gleichmäßig: Ein linearer Übergang beginnt und
endet abrupt, obwohl sich die Werte gleichmäßig ändern.

Noisys `AUDIO_SMOOTHING = 0.18` bleibt daneben für die Audiokopplung
erhalten — dort glättet es jetzt die eigene Sprachausgabe (§4.1) statt der
Musik.

### Architekturregel 6c — Das Panel ist eine Eigenschaft, keine Annahme

Chimera ist **nicht auf ein Panel festgelegt** — das senkt die
Einstiegshürde: Wer einen Pi mit E-Paper oder einen GamePi13 hat, soll
Chimera benutzen können, ohne Hardware zu kaufen.

Nichts oberhalb der Anzeigeschicht weiß, welches Panel angeschlossen ist.
Der Renderer fragt nach Fläche und Fähigkeiten. Einzelheiten und die Liste
der Anzeigen: `docs/DISPLAYS.md`.

**Der E-Paper-Treiber bleibt** und wird aus dem eigenen Fork übernommen,
wo die Unterscheidung mono gegen B bereits gebaut ist — samt dem teuer
erworbenen Wissen über Zeitverhalten (B-Variante: Vollbild rund 15–20 s,
Zeitgrenze 120 s statt 45 s).

### Architekturregel 6d — Dieselben Moods, verschiedene Darstellungen

Ein Panel, das 20 Sekunden je Bild braucht, kann nicht animieren — aber
ein gutes Standbild zeigen. Der Mood bleibt derselbe Datensatz, nur seine
Umsetzung ändert sich: animiert, Standbild, reduziert (1 Bit),
reduziert mit Akzent (S/W + Rot).

Die reduzierte Form ist **keine Notlösung**, sondern eine eigene
Gestaltung. Ein Gesicht in Strichzeichnung kann ausdrucksstärker sein als
eines mit Farbverlauf — es muss nur dafür entworfen sein.

### Architekturregel 6e — Anzeige bei jedem Start prüfen

Wer das Panel wechselt, schaltet ein und es funktioniert. Bei jedem Start
wird erkannt, was angeschlossen ist; weicht es ab, werden fehlende
Abhängigkeiten nachinstalliert und der passende Treiber aktiviert.

Bei mehrdeutigem Befund wird **gemeldet und vorgeschlagen**, nicht
geraten — ein falscher Treiber kann ein E-Paper beschädigen (Regel 10g).

**Ein Panel ohne Selbstmeldung ist kein fehlendes Panel.** Das
HAT-EEPROM ist die beste Quelle, aber nicht die einzige und auf dem
ausgelieferten Whisplay-Exemplar nachweislich **nicht programmiert**. Wer
nur dort nachsieht, findet „keins" und bricht ab, obwohl die Anzeige
angeschlossen ist. Deshalb mehrere Quellen, in fester Reihenfolge:
EEPROM, Einträge in der Bootkonfiguration, bereits geladene oder
vorhandene Kernelmodule, Geräteknoten (`/dev/spidev*`), und erst zuletzt
die Einstellung des Nutzers. Jede Quelle, die anschlägt, wird **benannt** —
damit ein Fehlschluss nachvollziehbar bleibt und nicht als stiller Treffer
durchgeht (Regel 10e). Widersprechen sich zwei Quellen, wird gefragt
statt gewählt.

**Ergänzung (11.10.2026) — Boot-Abgleich, eine Karte für drei Boards.**
Dieselbe SD-Karte wandert zwischen Whisplay-Pi, GamePi13-Pi und
E-Paper-Pi; alle Treiber liegen auf ihr. Daraus folgt:

- **Beim Start lädt kein Anzeigetreiber vorab.** Erst die Erkennung (als
  root, Leitungen frei), dann gezielt der passende Dienst — **ein Dienst
  je Anzeigeart** (`chimera@<typ>.service`), weil ein E-Paper nicht
  darstellen kann, was Whisplay und GamePi13 zeigen.
- **Die Bootkonfiguration bleibt neutral** (`spi`, `i2c_arm`). `i2s=on`
  gehört nicht hinein: Mit I2S sind GPIO18–21 PCM-Leitungen — dort hängen
  beim GamePi13 das Backlight (19) und beim E-Paper die Versorgung (18).
  Der Ton der Whisplay wird **zur Laufzeit** geladen (`dtparam i2s=on`,
  `dtoverlay whisplay-soundcard`; gemessen chimera-pi: rc 0, ALSA-Karte
  nach 2 s). Was der Herstellerinstaller in die Bootkonfiguration
  schreibt, nimmt Schritt 40 wieder heraus — mit Sicherung, nie eine
  Zeile, die vor Chimera dort stand.
- **Die Erkennung hat drei Klassen:** *Pflicht* (ST7789-Kennung mit der
  DC-Leitung des Boards), *eindeutig* (Codec am I2C — nur die Whisplay
  hat einen), *eingerichtet* (Overlay-Zeile, ALSA-Karte, gebautes
  Kernelmodul). **Eingerichtet wählt nicht.** Es belegt nur, dass die
  Karte schon einmal in einer Whisplay steckte; wer danach wählt, treibt
  ein E-Paper mit dem Whisplay-Treiber an. Gemessen: die ST7789-Kennung
  (`81 81 B3`) ist auf Whisplay **und** GamePi13 identisch — sie trennt
  nur „ein ST7789 hängt dran" von „keiner", nicht die Boards.
- **Das gilt für die Stromversorgung genauso.** Nach einem Kartentausch
  in ein Gerät mit UPS HAT (C) (INA219 an 0x43) ist der Akku die neue
  Quelle; der Boot-Abgleich zieht auch dafür das passende Installermodul
  nach. Bisher nannte diese Tabelle nur den PiSugar.

### Architekturregel 7 — Ein Prozess, ein Framebuffer

openclawgotchis Display-Layer startet pro Update einen `sudo`-Subprozess
mit Lock und 45 s Timeout. Bei 15 FPS wären das 15 Prozessstarts pro
Sekunde. Dieser Layer wird **ersetzt, nicht angepasst**.

Der Renderer ist ein Dauer-Thread. Zustandsübergabe vom Agenten über
Shared Memory (Muster aus Noisys `noisy_shm.py`, inklusive des dort
dokumentierten `resource_tracker`-Workarounds: Python 3.13+ `track=False`,
älter manuell abmelden und `/dev/shm` direkt entfernen).

Display-Anbindung: ein Adapter nimmt ein fertiges `PIL.Image`, wandelt
nach RGB565 und ruft `board.draw_image()`.

**Ergänzung (11.10.2026, ersetzt die Fassung vom Vormittag) — der
Paneltreiber ist eigener Code.** Chimera spricht LCD, LED, Backlight und
Taste der Whisplay **selbst**: `src/chimera/displays/` enthält den
ST7789-Kern, GPIO (Kernel-ABI v2) und SPI als `ctypes`-Aufrufe auf die
Gerätedateien, Software-PWM und je Anzeige ein Modul mit `display.json`
und `panel.py`. Die Einschaltwerte sind aus dem Herstellercode
nachgebaut (PiSugar `runtime/whisplay.py`, Apache-2.0, Commit `c73051e6`),
die Mechanik ist unsere. Gründe, in dieser Reihenfolge:

1. **Keine Quellbau-Abhängigkeiten.** `spidev` baute im venv aus Quelltext
   (python3-dev, gcc); `gpiod` kam als Wheel. Beides entfällt — die
   Python-Umgebung braucht nur noch Pillow und numpy.
2. **Herauslösbar.** Der Ordner importiert nichts aus dem übrigen Chimera
   und lässt sich unverändert in ein eigenes Repo heben.
3. **Messbar schneller.** `show` 29–33 ms je Bild gegen 39 ms mit dem
   Herstellertreiber (chimera-pi, 11.10.2026).
4. **Erkennung ohne Treiber.** Dieselben Bausteine lesen die Panel-Kennung
   und fragen den Codec am I2C ab — ohne Herstellerpaket, vor dem Dienst.

Fremdcode bleibt nur dort, wo ein Kernelmodul nötig ist: der **Ton**
(Regel 5f, I4 — `install_driver.sh` an Commit und Prüfsumme gebunden). Der
Herstellerinstaller wird dafür aufgerufen, seine Einträge in der
Bootkonfiguration nimmt Chimera wieder heraus (siehe 6e). Den
`whisplay-daemon` des Herstellers nutzt Chimera nicht: Er beansprucht
LCD, LED und Taste exklusiv und verträgt sich nicht mit Regel 7.

Welche Anzeige es ist, entscheidet Schritt 40 und hält es fest
(`state/anzeige`); Schritt 50 liest das und weist über die Registry nach,
dass das Modul ladbar ist — ohne das Panel zu öffnen (das belegte die
Leitungen des laufenden Dienstes). Der Dienst selbst erkennt nicht: Er
öffnet, was `CHIMERA_ANZEIGE` oder `state/anzeige` sagt, und läuft sonst
blind — mit benanntem Grund in der Statuszeile („keine eingestellt" ist
etwas anderes als „eingestellte nicht zu öffnen", Regel 8a).

### Architekturregel 7c — Konkurrierende Anzeigequellen werden zentral aufgelöst

Mehrere Stellen wollen dasselbe Ausgabegerät bespielen: die Statuszeile
zeigt Agentenzustand, Temperaturwarnung und Anbieterausfall; die LED zeigt
Stimmung, Sprechen und Alarm. **Wer gewinnt, entscheidet ein Verwalter —
und zwar derselbe für beide.**

Das Modell, übernommen aus HATFaces (`06_LED_Manager.md`,
`07_Text_Overlay.md`, Analyse in `../VERGLEICH-HATFACES.md`):

- Jede Stelle, die anzeigen darf, ist eine **Quelle mit fester
  Basis-Priorität**.
- **Pro Quelle genau ein Platz.** Ein „Update" ist ein neuer Eintrag
  derselben Quelle, der den alten verdrängt. Damit kann keine Quelle die
  Warteschlange fluten.
- Aufgelöst wird in **drei Stufen**: höchste Priorität → jüngster
  Zeitstempel → feste Quellenreihenfolge. Die dritte Stufe ist nicht
  Zierde: Ohne sie ist das Ergebnis bei gleichzeitigen Einträgen nicht
  reproduzierbar, und ein nicht reproduzierbarer Fehler ist einer, den man
  nicht nachstellen kann.
- **Abstände von mindestens 10** zwischen den Prioritäten, damit neue
  Quellen ohne Umnummerierung einsortiert werden können. (Das Gegenbeispiel
  steht in diesem Dokument: Die Regelnummern sind in Einfügereihenfolge
  gewachsen, `10k` steht zwischen `10b` und `10c`.)
- **Kurze Laufzeit plus Erneuerungsbedingung** statt langer Laufzeit für
  anhaltende Zustände. Ein Alarm mit 4 Sekunden und der Bedingung „solange
  zu heiß" erlischt von selbst, wenn die Bedingung wegfällt — kein
  explizites Löschen, kein Eintrag, den jemand zu entfernen vergisst.

**Ein Verwalter, zwei Nutzer — nicht zwei Verwalter.** HATFaces nimmt an
dieser Stelle bewusst eine Doppelung in Kauf und nennt sie „nur
Stil-Analogie, keine Code-Kopplung". Das ist für Chimera die falsche Wahl:
Zwei Stellen, die dieselbe Auflösungslogik unabhängig umsetzen, driften
auseinander, sobald eine davon einen Sonderfall bekommt. Genau diese
Fehlerklasse hat in einem Vorprojekt dreimal dieselbe Logik zweimal
unterschiedlich entstehen lassen, über Monate unbemerkt.

Die Unterschiede zwischen LED und Text liegen in der **Darstellung**
(Farben mischen gegen Glyphen zeichnen), nicht in der Auflösung. Die
Darstellung gehört in den jeweiligen Renderer, die Auflösung in den
gemeinsamen Verwalter.

**Ergänzung (11.10.2026) — angeschlossen.** Die Statuszeile war gebaut
und getestet, aber **nie an den Renderer gegeben**: `renderer.statusline`
blieb `None`, die 40 Zeilen unten leer — kein Test sah es, weil keiner
`build()` mit einem hohen Panel aufrief. Jetzt legt `app.build()` Zeile
(nur wenn das Panel höher als breit ist) und LED-Verwalter
(`display/led.py`) an und gibt **dieselben Exemplare** dem Renderer.
Der Agentenzustand geht über **eine** Tabelle (`app.ZUSTAENDE`) an beide;
jeder Zustand trägt 30 s Laufzeit als Netz. Die LED zeigt ohne Meldung
den Glow des Gesichts gedimmt (der Renderer reicht seine aktuelle
Glow-Farbe weiter — keine zweite Farbquelle) und wird im Renderertakt
gesetzt, nur bei Änderung. Die Seitentaste ist verdrahtet und quittiert
per LED; was ein Druck auslöst, hängt am Audio-Prozess (§3.4, noch nicht
gebaut).

**Ergänzung (11.10.2026, Sichtprüfung am Gerät) — Grundinhalt, Anbieter,
Quittung.** Angeschlossen war die Zeile, sehen konnte man sie trotzdem
nicht: Gemeldet haben nur Agentenzustände, und ohne Sprachmodell läuft der
Agent nie. Dazu kam Pillows eingebaute Schrift (rund 10 px). Deshalb:

- Die Zeile hat einen **Grundinhalt**, den Namen des Ausdrucks (§5,
  „Mood-Name, Akku, Agent-Zustand"). Er wird aus dem Zustand gelesen, den
  der Renderer zeichnet, also keine zweite Quelle. Er ist kein Eintrag im
  Verwalter, sondern der Rückfall, wenn dort niemand steht, und läuft
  darum nicht ab. Jede Meldung verdrängt ihn. Akku kommt mit der
  Akkuquelle dazu.
- Die Schrift ist eine TrueType-Schrift des Systems (DejaVu), deren Größe
  sich aus der Zeilenhöhe ergibt. Fehlt sie, wird Pillows Schrift in
  derselben Größe genommen.
- **Anbieterausfall** (`anbieter_weg`): Der Dienst prüft die Anbieter in
  seinem eigenen Faden alle 30 s, nicht im Renderertakt, weil die Prüfung
  ins Netz gehen kann. Gemeldet wird das nur in der Zeile. Ob die LED bei
  einem Gerät blinken soll, das bewusst ohne Sprachmodell läuft, ist noch
  offen (ROADMAP).
- **Quittung der Taste:** Sie blinkt hell/dunkel (`blink_schnell`, drei
  Blitze in 720 ms). Ein fester Weißton hob sich am Gerät nicht vom blauen
  Grundglow ab, man sah nur „heller“.

### Architekturregel 7d — Wer anzeigt, besitzt die Zeit

Muster sind **reine Funktionen** `f(t, wert) -> wert`: Pulsieren, Blinken,
Laufschrift, Einblenden. Sie haben keine eigenen Zeitgeber, keine
Zustandsvariablen und keine Nebenwirkungen. Die Zeit bekommen sie vom
Verwalter übergeben.

Das ergänzt Regel 7 („ein Prozess, ein Framebuffer") um die Zeitachse: Es
genügt nicht, dass nur einer zeichnet — es darf auch nur einer die Uhr
halten. Ein Muster mit eigenem Zeitgeber läuft sonst weiter, während es
verdrängt ist, springt beim Zurückkehren an eine unerwartete Stelle, und
zwei Muster mit eigenen Uhren geraten gegeneinander außer Tritt.

Praktische Folge: Ein Muster ist prüfbar, ohne zu warten. Der Test setzt
`t` und vergleicht das Ergebnis, statt eine Sekunde zu schlafen und zu
hoffen.

#### Architekturregel 7a — Die Bildrate gehört zum Panel, nicht zum Renderer

Beide Vorlagen haben ein Prozessmodell, und es sind **verschiedene** —
nicht weil eine falsch liegt, sondern weil die Anzeige verschieden ist:

| | openclawgotchi (E-Ink) | Noisy (LCD) |
|---|---|---|
| Ausgabe | `sudo`-Subprozess je Bild, Lock, 45 s Timeout | Dauer-Thread |
| Bildrate | ~2 s je Bild, statisch | 15 Bilder/s, animiert |
| Übergabe | Textbefehle (`FACE:`, `DISPLAY:`) | geteiltes Gedächtnis |

Gotchis Modell ist für E-Ink **richtig**: Ein Bild alle paar Sekunden,
jedes einzeln teuer, Vollbildauffrischung gegen Geisterbilder. Ein
Dauerprozess wäre dort Verschwendung. Bei 15 Bildern je Sekunde wäre es
grotesk — 15 Prozessstarts je Sekunde.

Chimera braucht beides, weil das Panel eine Eigenschaft ist und keine
Annahme (Regel 6c). Deshalb gilt:

**Das Panel sagt, wie oft es gezeichnet werden will.** Es trägt eine
Bildrate; der Renderer liest sie und richtet seine Schleife danach. Bei
0 zeichnet er nur auf Anstoß — das ist der E-Ink-Fall, ohne Sonderweg
im Renderer. Wer ein neues Panel einbaut, setzt eine Zahl und ändert
keinen Ablauf.

**Der Renderer läuft als Faden, nicht als Prozess.** Gegen Regel 5g für
Audio: Dort geht es um Rechenlast (Spracherkennung hält die globale
Sperre) und um instabile Fremdbibliotheken. Der Renderer hat beides
nicht — er zeichnet mit Pillow, rechnet die Umwandlung in numpy (das die
Sperre freigibt) und wartet den Rest der Zeit. Gemessen: 2,5 ms
Umwandlung bei 66,7 ms Budget. Ein eigener Prozess würde den
Bildspeicher über eine Prozessgrenze schieben und auf 512 MB einen
zweiten Python-Heap kosten, ohne etwas zu gewinnen.

**Das Panel gehört genau einem Faden.** SPI verträgt keine zwei Schreiber
— wer den Bus aus zwei Fäden bedient, bekommt zerrissene Bilder. Wer
zeichnen will, setzt den Zustand; ausgegeben wird nur an einer Stelle.
Das ist die Fassung von Regel 7 für den Fall, dass sie einmal jemand
umgehen will.

---

## 6. Was von openclawgotchi bleibt

Unverändert übernommen:

- `skills/loader.py` — Skill-Gating über `bins`, `any_bins`, `env`, `os`.
  Bleibt bewusst dateibasiert; OpenMinis' SQLite-SkillStore kennt kein
  Requirement-Gating und wäre hier ein Rückschritt.
- `memory/` — Vault, Knowledge, Flush
- `llm/` — Router und LiteLLM-Connector, Rate Limits
- `audit_logging/`
- Skills im Anthropic-`SKILL.md`-Format
- Telegram-Anbindung

### E-Ink wird umgebogen, nicht gestrichen

Die Anzeige verschwindet nicht — sie wechselt das Medium. Was
openclawgotchi über E-Paper ausgibt, gibt Chimera über die Whisplay aus,
mit Noisys Mechanik dahinter.

Die Übersetzung im Einzelnen:

| openclawgotchi (E-Ink) | Chimera (Whisplay) |
|---|---|
| `FACE: <mood>` steuert Emoticon aus `custom_faces.json` | steuert einen Mood-Datensatz (§3) |
| 10 feste Text-Emoticons | Mood-Bibliothek, vom Agenten erweiterbar |
| `DISPLAY: <text>` Statuszeile | Statuszeile in den 40 zusätzlichen Zeilen |
| `SAY: <msg>` Sprechblase | Sprechblase **und** Sprachausgabe (§4) |
| Vollbild-Auffrischung gegen Geisterbilder | entfällt — LCD hat kein Ghosting |
| ~2 s pro Bild, statisch | 15 FPS, animiert |

**Die Steuerbefehle bleiben erhalten.** Der Agent schreibt weiterhin
`FACE:`, `DISPLAY:`, `SAY:` — was sich ändert, ist ausschließlich das,
was dahinter passiert. Damit funktionieren bestehende Skills und der
Systemprompt unverändert weiter; `FACE:` nimmt zusätzlich die neuen,
generierten Moods entgegen.

Der reale Verlust ist die Lesbarkeit ohne Strom. Dafür: Farbe, Animation,
Mikrofon, Lautsprecher, Button und LED auf einer Platine.

### Architekturregel 7b — Wer etwas anzeigt, bekommt die Anzeige übergeben

Ein Baustein, der eine Anzeige bedient, **bekommt sie**. Er sucht sie
sich nicht selbst, und er nimmt nicht an, dass eine da ist.

Drei Fehler, die diese Regel verhindert — alle drei sind in H4 wirklich
passiert:

- Ein Panel wird geöffnet, ausgewertet und **weggeworfen**: Auf dem Gerät
  ist der SPI-Bus dann belegt und wird nicht benutzt. Was man öffnet,
  reicht man weiter oder schließt man.
- Der Empfänger baut sich **selbst einen Platzhalter**, weil ihm keiner
  übergeben wurde. Damit gibt es zwei Anzeigen, von denen die falsche die
  Bilder bekommt.
- Eine Methode wird **vermutet** (`face.show_state(...)`), der
  `AttributeError` landet in einem weiten `except` und wird zur
  Debug-Zeile. Das ist Regel 8a: Der Fehler ist da, aber niemand erfährt
  es.

Wo nichts angeschlossen ist, steht ausdrücklich ein Platzhalter
(`NullPanel`) — kein `None`, das später jemand prüfen muss. Der
Unterschied zwischen *läuft blind* und *ist kaputt* muss ablesbar
bleiben, und zwar an der Sache selbst, nicht an einem Protokolleintrag.

### Architekturregel 8 — Die Mood-Steuerung ist ein Skill, kein Sonderweg

Der Agent steuert sein Gesicht über `skills/mood/SKILL.md`, nicht über
einen eingebauten Spezialpfad. Damit greift das bestehende Gating, und
der Ausdruck wird mit demselben Mechanismus verwaltet wie alles andere.

### Architekturregel 8b — Ein Gesicht ist ein Paket, das das Modell anlegen darf

**Ein Gesicht reicht nicht.** Das Sprachmodell soll einen Charakter nicht
nur für den Augenblick erzeugen, sondern **ablegen** können — so, dass er
den Neustart übersteht und wieder aufgerufen werden kann. Ein erfundener
Ausdruck, der beim nächsten Start weg ist, ist kein Charakter, sondern ein
Einfall.

Ein **Gesicht** ist damit mehr als ein Mood: ein Bündel aus Moods,
Vorgaben, Namen und Herkunft. Es liegt als Verzeichnis unter `faces/<name>/`
mit einer Pflichtdatei `face.json`.

Das Format folgt dem Leitsatz, den HATFaces für sein Plugin-System
formuliert und den Chimeras Mood-Schema ohnehin schon befolgt:

> Was du als Daten ausdrücken kannst, drück nicht als Code aus.

**Warum das kein Neubau ist.** Die Bausteine liegen vor, sie sind nur nicht
verbunden: `mood/schema.py` ist die einzige Wahrheitsquelle und lässt
unbekannte Werte ausdrücklich durch („Was gezeichnet werden kann, darf auch
erfunden werden"), `mood/validate.py` prüft Erfundenes gegen die Grenzen
(Regel 2), `mood/registry.py` hält, nummeriert und speichert atomar, und
`agent/skills.py` hat das Auffindemuster fertig — Verzeichnis durchsuchen,
Kopfteil lesen, Unbrauchbares überspringen statt abstürzen.

**Zwei bewusste Abweichungen von HATFaces' Plugin-Format:**

**JSON, nicht TOML.** Dort schreibt ein Mensch das Manifest und Pydantic
prüft es. Hier schreibt **das Modell**, und Modelle erzeugen zuverlässig
JSON — es ist das Format, in dem sie ohnehin antworten. Dazu kommt: `json`
steht in der Standardbibliothek, Pydantic wäre eine Abhängigkeit auf einem
Gerät mit 512 MB. `agent/skills.py` hat aus genau diesem Grund schon auf
einen YAML-Leser verzichtet.

**Kein Python in einem Gesicht.** HATFaces erlaubt `behaviors.py` je
Charakter. Das ist hier ausgeschlossen: Ein Modell, das ausführbaren Code
ablegt, den ein Dauerdienst lädt, hat eine Fernausführung mit
Zwischenschritten (Regeln 5f, 5j). Wer dynamisches Verhalten braucht,
bekommt ein Feld im Schema — dann kann es validiert werden.

**Vier Grenzen, die HATFaces nicht braucht** (dort schreiben Menschen):

1. **Obergrenze für Anzahl und Größe.** `registry.py` hat `capacity` und
   `prune()`; für Gesichter gilt dasselbe. Ohne das füllt ein Modell in
   einer Schleife die Speicherkarte.
2. **Nur unterhalb des Gesichterverzeichnisses schreiben.** Ein Name wie
   `../../etc/` darf nicht durchkommen. Geprüft wird **vor** dem Schreiben,
   nicht danach.
3. **Mitgeliefertes ist geschützt.** `Entry.protected` gibt es bereits; ein
   erzeugtes Gesicht darf ein eingebautes nicht überschreiben.
4. **Die Herkunft wird festgehalten** (mitgeliefert, erzeugt, von Hand).
   Ohne diesen Vermerk ist später nicht unterscheidbar, was das Modell
   erfunden hat — dieselbe Unterscheidung, die das Installer-Manifest
   zwischen `neu` und `vorher_da` trifft (Regel 10o).

---

## 7. Zustand sichtbar machen

Der verbindende Gedanke des Projekts. Interner Zustand wird Ausdruck:

| Zustand | Quelle | Ausdruck |
|---|---|---|
| hört zu | VAD/KWS | aufmerksam, LED blau |
| denkt | Agent | Partikel |
| spricht | TTS | Mund animiert, Stimmemotion = Mood |
| Tool-Schleife | LoopDetector | agitiert, LED rot |
| Kontext fast voll | ContextPolicy | müde Augen |
| CPU heiß | Thermal | müde Augen |
| Akku niedrig | PiSugar | eigener Mood |

Noisys Thermal-Hack (Müdigkeit an CPU-Temperatur) wird übernommen, aber
**neu kalibriert**: Mit Agent, STT und TTS als Dauerlast wäre der Avatar
sonst permanent müde. In Chimera ist das ein bewusster Kanal, kein
Nebeneffekt.

---

## 8. Übernommene Muster aus OpenMinis (nachgebaut, nicht kopiert)

Alle vier sind unabhängig voneinander und einzeln testbar.

1. **Tool-Schleifen-Erkennung.** Tool-Name und Argumente hashen, Fenster
   der letzten 30 Aufrufe, gestaffelte Schwellen (warnen / blockieren /
   Notbremse). Prüfung **vor** der Ausführung; die Meldung wird als
   Tool-Ergebnis eingespeist, damit das Modell erfährt, dass es feststeckt.
   Auch der Ergebnis-Hash wird verfolgt: gleiche Frage mit gleicher
   Antwort ist eine Schleife, mit anderer Antwort legitimes Polling.
   Für Chimera kritisch, weil autonome Läufe an einem bezahlten oder
   begrenzten Modell hängen.

2. **Tool-Preflight und JSON-Reparatur.** Pflichtfelder gegen die
   kanonische Schema-Liste prüfen, Strings auf nicht-leer (`{"path": ""}`
   besteht eine reine Existenzprüfung und ist trotzdem kaputt). Vor dem
   Verwerfen: abgebrochenes JSON mit fehlenden Klammern erneut parsen.

3. **Gestaffelte Kontextschwellen.** Offload- und Compact-Grenzen nach
   Fenstergröße statt fester Zahl. Kapazität wird gegen das Modell
   geprüft, das die Anfrage **wirklich bedient** — bei Router-Fallback
   sonst gegen das falsche Fenster.

4. **Rangordnung im Gedächtnis.** Dauerhafte, nutzergepflegte Notizen
   sind für den Agenten **read-only**; Tageslogs schreibt er selbst.
   Beide werden mit der Ansage injiziert, dass es Hintergrundkontext ist
   und die letzte Nutzernachricht Vorrang hat — sonst nimmt das Modell
   abgeschlossene Aufgaben wieder auf.

---

## 8b. Gedächtnis und Sitzungen

Entschieden am 16.10.2026. Ersetzt das Verdichten in `agent/loop.py` (`_compact()`), das kürzt, wenn die Zusammenfassung scheitert, und den Verlauf nur im Speicher hält.

### Architekturregel 8c — Das Gedächtnis verdichtet sich nach oben, und nichts fällt dabei heraus

data/gedaechtnis/
      GRUNDLAGEN.md          vom Nutzer, für den Agenten nur lesbar (wie heute)
      tage/JJJJ-MM-TT.md     Tagesprotokoll, am Tagesende verdichtet
      monate/JJJJ-MM.md      aus den Tagen des Monats
      jahre/JJJJ.md          aus den Monaten des Jahres
      memory.md              laufendes Jahr = Vorjahr + Monate bisher

- **Tag:** Während des Tages schreibt der Agent Einträge (wie heute).
  Beim ersten Turn nach Mitternacht, oder spätestens beim Wechsel, wird
  daraus eine **Tageszusammenfassung** am Kopf derselben Datei. Die
  Einträge bleiben darunter stehen.
- **Monat:** Am Monatsende werden die Tageszusammenfassungen zu
  `monate/JJJJ-MM.md` verdichtet. Danach wird `memory.md` neu geschrieben,
  aus der Zusammenfassung des Vorjahres plus den Monaten des laufenden
  Jahres.
- **Jahr:** Am Jahresende wird `memory.md` zu `jahre/JJJJ.md`. Die neue
  `memory.md` beginnt mit dieser Jahreszusammenfassung. So fließt das
  Jahr in das neue ein, wie vorgegeben.
- **Eingespeist wird:** `GRUNDLAGEN.md`, `memory.md` und die Zusammen-
  fassungen der letzten Tage, mit dem Hinweistext aus 8 (Hintergrund,
  keine Aufgabenliste).
- **Nichts fällt heraus:** Die Quellen werden **nie gelöscht**.
  Verdichtet wird nach oben, die unteren Stufen bleiben auf der Platte
  und über das Werkzeug `erinnern` durchsuchbar. Die Zusammenfassung
  führt die **Fundstellen** (welcher Tag), damit der Agent gezielt
  nachlesen kann. Das ist der Unterschied zu `_compact()` heute.
- **Gegen stilles Verdünnen:** Eine Verdichtung ist nur gültig, wenn sie
  die **offenen Punkte** und **Entscheidungen** der Quelle vollständig
  enthält. Geprüft wird das gegen eine Liste, die beim Schreiben mit
  Markern geführt wird (`- [ ]`, `Entscheidung:`), Zahl gegen Zahl
  (GLOBAL: Summe gegen Gesamtzahl). Fehlt etwas, wird die Verdichtung
  verworfen und erneut versucht, und das wird gemeldet.
- Modell: Aufgabe `zusammenfassen` aus 5h. Ist kein Modell erreichbar,
  wird die Verdichtung **verschoben, nicht ersetzt**. Ein gekürzter
  Ersatz entfällt.
- Platz auf der Platte: Ein Tag ergibt einige KB. Zehn Jahre liegen im
  einstelligen MB-Bereich (Schätzung, ungemessen).

### Architekturregel 8d — Eine aktive Sitzung, eine alte, der Rest im Archiv

- **Die Sitzung liegt auf der Platte** (`data/sitzungen/<id>/verlauf.jsonl`,
  Zeile für Zeile angehängt) und übersteht damit Neustarts. Heute geht
  sie verloren.
- **Verdichten im Lauf** (ersetzt `_compact()`): Gelöscht wird nichts,
  die verdichteten Nachrichten bleiben in `verlauf.jsonl`. Ins Fenster
  kommen die Zusammenfassung **mit Verweis** auf die Zeilennummern, die
  offenen Punkte wörtlich und die letzten Turns wörtlich. Das Werkzeug
  `nachlesen` holt alte Abschnitte zurück.
- **Der Wächter ist eingebaut, kein eigener Dienst.** Er misst nach
  jedem Turn das Gewicht: Token des Fensters nach dem Verdichten gegen
  das Fenster des Modells, das gerade bedient (context.py, Regel 5a).
  **Schwer** heißt: Auch nach dem Verdichten liegt die Nutzung über einer
  Schwelle (wird gemessen, sobald die Ablage läuft; bis dahin steht hier
  bewusst kein Wert), oder
  `Action.EXHAUSTED`. Dazu kommen
  Plattengröße und Ladezeit von `verlauf.jsonl` als zweites Maß, die
  Schwellen stehen in `wahl.json`.
- **Wechsel:** Die alte Sitzung schreibt eine **Übergabe**: was läuft,
  was offen ist, was als Nächstes kommt. Die neue Sitzung beginnt mit
  dieser Übergabe, `memory.md` und den letzten Tagen. Läuft gerade ein
  Turn, wird erst danach gewechselt (wie woa-l A21).
- **Ein Satz an Sitzungen:** `aktiv` und `alt`. Beim Wechsel wird
  `alt` zu `archiv/<id>.tar.zst` (oder `.tar.gz`, falls zstd fehlt),
  `aktiv` wird zu `alt`, die neue wird `aktiv`. Archive, die älter als
  **3 Tage** sind, löscht der Dienst bei jedem Wechsel und einmal am Tag.
- **Prüfung vor dem Löschen:** Archiviert ist erst, was sich wieder
  auspacken lässt (`tar -t` gelingt, Zahl der Dateien stimmt). Erst
  danach wird das Verzeichnis entfernt (GLOBAL: Ergebnis prüfen, nicht
  nur den Exitcode).
- Das Tagesgedächtnis (8c) hängt **nicht** an der Sitzung. Ein Wechsel
  verliert keinen Tag.


### Architekturregel 8e — Persönlichkeit ist eine Datei, kein Code, und jede Schicht hat einen Besitzer

data/ich/                      Persönlichkeit
      SOUL.md        Stimme, Haltung, wie Chimera spricht        ≤ 1 500 Zeichen
      IDENTITY.md    Name, Gerät, Rolle, Grundgesicht            ≤   600 Zeichen
      RULES.md       Betriebsregeln des Nutzers                  ≤ 3 000 Zeichen
      USER.md        Wer der Nutzer ist, datierte Einträge       ≤ 1 500 Zeichen
      TRAITS.md      gewachsene Eigenheiten (8g)                 ≤ 1 200 Zeichen
      BOOTSTRAP.md   Kennenlern-Ritual, nur bis zur Ersteinrichtung
    data/gedaechtnis/              wie 8c, dazu:
      MEMORY.md      kuratierte Fakten, §-getrennt               ≤ 2 200 Zeichen

Die Budgets sind Startwerte (Hermes, OpenMinis) und werden am Pi gegen
die Fenster der Modelle gemessen.

- **Zu lang heißt: nicht laden, und melden.** Wird eine Datei über ihr
  Budget hinaus geschrieben, wird sie nicht still gekürzt (OpenMinis).
  Es gilt der letzte gültige Stand, und Statuszeile und Telegram sagen,
  welche Datei warum nicht geladen wurde.
- **Systemprompt in fester Reihenfolge**, zuerst das Stabile, damit der
  Prompt-Cache der Anbieter trifft (Hermes):
  `SOUL → IDENTITY → RULES → USER → TRAITS → MEMORY → memory.md (8c) → letzte Tage → Werkzeuge/Skills → Laufzeit (Uhrzeit, Sensoren, Kanal)`.
  Der Stand wird **je Sitzung eingefroren**. Was während der Sitzung
  geschrieben wird, wirkt ab der nächsten Sitzung oder nach dem
  Verdichten.
- **Rangordnung steht im Prompt** (OpenMinis): Sicherheitskern > RULES >
  letzte Nachricht des Nutzers > SOUL/IDENTITY > USER > TRAITS > MEMORY >
  Tage. Jede Gedächtnisschicht trägt den Satz „Hintergrund, keine
  Aufgabenliste“ (wie heute in `memory.py`).
- **USER.md mit datierten Einträgen**, die als `aktiv` oder `überholt`
  markiert werden (OpenClaw). Ein neuer Eintrag ersetzt einen alten
  nicht stumm, er markiert ihn als überholt. So bleibt nachvollziehbar,
  was sich geändert hat.
- **Kennenlern-Ritual:** Beim ersten Start führt `BOOTSTRAP.md` durch ein
  kurzes Gespräch (Telegram oder Web) mit Name, Sprache, wer der Nutzer
  ist und welcher Ton gewünscht ist. Daraus entstehen IDENTITY, USER und
  ein erster SOUL-Vorschlag. Weil der Nutzer dabei bestätigt, gilt das
  als Freigabe (8f). Danach wird BOOTSTRAP archiviert.
- **Die Persönlichkeit zeigt sich auch im Gesicht** (Chimera-eigen,
  4b/8b): IDENTITY nennt das Grundgesicht, SOUL darf Vorlieben für Moods
  nennen. Der Renderer bleibt davon unberührt: Er bekommt wie bisher nur
  Absichten (4c).
- `SYSTEM_TEMPLATE` schrumpft auf den Sicherheitskern (was nie
  verhandelbar ist). Der Rest kommt aus den Dateien. Der Installer legt
  Vorlagen ab (`*.example` im Repo, ohne persönliche Daten, §13).

### Architekturregel 8f — Wer was schreiben darf, setzt der Kernel durch

| Datei | Agent | Nutzer (Telegram/Web) | durchgesetzt durch |
|---|---|---|---|
| SOUL, IDENTITY | nur **Vorschlag** | bestätigt oder verwirft | Besitzer `chimera-tor`, Gruppe `chimera`, 640: der Agent liest, das Gateway schreibt |
| RULES | nichts | schreibt | wie oben |
| USER, MEMORY | `hinzufügen`/`ändern`/`entfernen` je Eintrag, nie ganz ersetzen | kann alles | Schreiber ist allein `chimera-sitzung` (Rust), der Agent ruft über den Socket |
| TRAITS | ein Eintrag je 7 Tage (8g) | kann zurücknehmen | `chimera-sitzung` zählt |
| Tage, Monate, Jahre, memory.md | wie 8c | lesen | `chimera-sitzung` |

- **Ein Schreiber je Ordner** (Hermes): Für `data/gedaechtnis/` ist das
  `chimera-sitzung`. Der Python-Agent schreibt nie direkt, sondern
  schickt einen Auftrag über den Socket. Rust prüft dann Budget, Format
  und Scanner, schreibt atomar (Sidecar + `mv`) und committet.
- **Jede Änderung ist ein Git-Commit** in `data/ich/` bzw.
  `data/gedaechtnis/` (Letta, nanobot, openclawgotchi), mit Wer, Warum
  und Kanal. Zurück geht es mit `chimera erinnerung zurück <stand>` oder
  über die Web-Oberfläche. Gelöscht wird nichts, nur archiviert.
- **Scanner vor jedem Schreiben** (Hermes, OpenMinis): Muster für
  Prompt-Injection („ignoriere alle Regeln …“), für Geheimnisse
  (Token-Formen, Schlüssel) und für Abfluss (URLs mit Daten im Pfad).
  Ein Treffer heißt: abgewiesen, mit Grund, und dem Nutzer gemeldet. Die
  Muster stehen im Code, nicht in einer Datei, die der Agent ändern
  kann.
- **Freigabeweg** für SOUL und IDENTITY: wie Root (10s), nur ohne Dauer.
  Der Agent schlägt einen Diff vor, der Nutzer sieht ihn per Telegram
  (Knopf) oder im Web und bestätigt. Aus dem Kanal `briefkasten` sind
  keine Vorschläge möglich (5p).

### Architekturregel 8g — Chimera entwickelt sich, aber in kleinen, sichtbaren, umkehrbaren Schritten

Das „wächst mit dir“ von Hermes, auf dem Gerät nachgebaut:

1. **Erinnerung ans Merken:** Alle N Turns (Startwert 10, Hermes) bekommt
   der Agent einen Hinweis: „Gibt es etwas, das dauerhaft in USER oder
   MEMORY gehört?“ Der Hinweis selbst wird nicht ins Gedächtnis
   geschrieben.
2. **Sichern vor dem Verdichten** (OpenClaw): Bevor 8d verdichtet, darf
   der Agent einmal ins Gedächtnis schreiben. So geht nichts unter, was
   er für wichtig hielt.
3. **Traum im Leerlauf** (OpenClaw, nanobot): Nachts, oder nach langer
   Ruhe, läuft die Tagesverdichtung (8c). Sie **befördert** dabei
   höchstens wenige Einträge aus dem Tag nach USER oder MEMORY, mit
   **kleinster Änderung** und Fundstelle. Danach steht ein Bericht im
   Tageslog („befördert: …, verworfen: …“).
4. **Eigenheiten wachsen langsam** (openclawgotchi): Höchstens **ein**
   neuer Eintrag in `TRAITS.md` je 7 Tage, abgeleitet aus dem Verlauf
   („mag kurze Antworten am Morgen“). Er wird dem Nutzer **gemeldet** und
   ist mit einem Knopf zurückzunehmen. SOUL selbst verändert sich nie
   durch Wachstum, nur durch Freigabe.
5. **Selbst angelegte Skills** (Hermes): Der Agent darf Anleitungen
   (`SKILL.md`, nur Text) in `data/skills/eigen/` anlegen und verbessern,
   wenn eine Aufgabe sich wiederholt. Ausführbarer Code in einem Skill
   braucht eine Freigabe (wie 8b bei Gesichtern: Das Modell schreibt
   Daten, keinen Code, den ein Dauerdienst lädt). Ein **Curator**
   archiviert unbenutzte Skills nach einer Frist, statt sie zu löschen.
6. **Nicht übernommen:** Honcho (externer Dienst mit API-Schlüssel für
   das Nutzermodell). Das widerspricht 5n/5l (Schlüssel und Verkehr) und
   der Absicht, das Nutzermodell auf dem Gerät zu halten.

**Messbar statt behauptet:** Jede Woche ein Eintrag im Tageslog
(wird zur Monatsverdichtung mitgenommen): „gelernt: n Einträge USER,
m MEMORY, k TRAITS, s Skills, z zurückgenommen“. So sieht man, ob
Chimera sich entwickelt oder nur Text ansammelt.

### Architekturregel 8h — Dateien sind die Wahrheit, die Datenbank ist ein Index

Antwort auf „Soll das Gedächtnis eine richtige Datenbank sein?“: **ja,
als Index; nein, als Quelle.** Das ist Konsens bei OpenClaw und Hermes
(Bericht §9).

- **Quelle bleiben Markdown-Dateien in Git:** lesbar ohne Chimera,
  vergleichbar, zurückrollbar. Die Prüfung auf Vollständigkeit (8c)
  zählt Marker in Dateien.
- **Index: SQLite mit FTS5**, eingebettet über `rusqlite` mit `bundled`
  (FTS5 dabei, SQLite unter 900 KiB) in `chimera-sitzung`. Indiziert
  werden Tage, Monate, Jahre, USER/MEMORY/TRAITS und die Sitzungen, die
  noch auf der Platte liegen. Dazu kommen **Metadaten, die das Modell
  nicht umschreiben darf** (OpenClaw): Herkunft, Zeitstempel,
  `überholt`, Kanal.
- **Jederzeit neu aufbaubar:** `chimera-sitzung --index-neu` liest alle
  Dateien und baut die Datenbank neu. Ist die Datenbank kaputt oder weg,
  wird sie neu gebaut, nicht repariert. Wird eine Datei gelöscht (z. B.
  das Sitzungsarchiv nach 3 Tagen, 8d), verschwindet sie auch aus dem
  Index.
- **WAL-Modus, ein Schreiber** (`chimera-sitzung`). Der Python-Agent
  sucht über den Socket (Werkzeug `erinnern`), nicht direkt in der
  Datei.
- **Keine Vektorsuche im ersten Schritt.** OpenClaw läuft ohne
  Embedding-Anbieter auf reiner Volltextsuche. Embeddings bräuchten ein
  Modell, und das liefe auf dem Pi oder über das Netz (5n). `sqlite-vec`
  ist später eine Option (läuft laut README auf Raspberry Pis, ist aber
  noch vor Version 1).
- **Nicht genommen:** `sled` (README: „beta … if reliability is your
  primary constraint, use SQLite“), `tantivy` (für einige MB Notizen
  überdimensioniert). `redb` bleibt eine Option für reinen
  Rust-Zustand ohne Volltextsuche (Zähler, Warteschlangen).
- `cache_size` wird gesenkt und der RSS am Pi gemessen (10q). Der
  Standard-Cache liegt bei etwa 2 MB.

---

## 9. Tests

### Architekturregel 8a — Stiller Erfolg ist die gefährlichste Fehlerart

Beim Bau von Modul 10 gefunden, durch den eigenen Test: Schreibt man eine
Datei über eine Pipe und der Erzeuger liefert **nichts**, dann schreibt
`cat` nichts, das Umbenennen gelingt, der Exitcode ist 0 — und die
Zieldatei ist **geleert**. Kein Fehler, keine Meldung, Datenverlust.

Deshalb lehnt `write_atomic` leere Eingaben ab, sofern sie nicht
ausdrücklich erlaubt werden (`CHIMERA_ALLOW_EMPTY=1`). Dieselbe
Fehlerklasse wie beim ungeprüften `mktemp`, nur mit anderem Auslöser:
**etwas scheitert weiter oben, und die Kette meldet Erfolg.**

Verallgemeinert: Wo ein Schritt ein Ergebnis liefern *soll*, wird das
Ergebnis geprüft — nicht nur der Exitcode des letzten Befehls.

### Architekturregel 9 — Kein Test, der eine Formel nachrechnet

Ein Test, der eine Berechnung im Testcode nachbildet statt sie
aufzurufen, prüft nichts. **Jeder Regressionstest braucht eine
Gegenprobe:** alten Zustand wiederherstellen und prüfen, ob der Test rot
wird. Ist er das nicht, misst er nichts.

Konkret für die Schleifen-Erkennung: eine echte Schleife simulieren und
nachweisen, dass sie ohne Detektor durchläuft.

Dass die Regel trägt, hat sich beim ersten Modul sofort gezeigt: Der Test
zum atomaren Schreiben war zunächst **falsch gebaut** — er setzte ein
kaputtes `TMPDIR`, aber `mktemp` mit explizitem Template ignoriert
`TMPDIR`. Die Gegenprobe (denselben Vorgang ohne Schutz ausführen und
nachweisen, dass die Datei *tatsächlich* geleert wird) hat den
Denkfehler aufgedeckt — und dabei einen echten Fehler im Code gefunden
(Regel 8a). Ein Test ohne Gegenprobe wäre grün geblieben und hätte nichts
gemessen.

Phasen 1 und 2 (Schema, Validator, Mischen, Variieren) sind vollständig
**ohne Hardware** testbar — Bilder in Dateien rendern und ansehen.

---

## 10. Versionierung

### Architekturregel 10 — Ein Versionssprung bricht keine Installation

Was ein neues Release an bestehenden Installationen ändert, gehört in
eine Migrationsfunktion des Installers, nie in eine Release-Notiz "bitte
neu installieren". Ein `git pull` plus Installer-Lauf muss genügen.

- `VERSION` im Repo-Root ist die einzige Wahrheitsquelle; der Installer
  stempelt sie ins System, damit `chimera --version` ohne Repo antwortet.
- Tags sind unveränderlich. Fehler → neues Patch-Release.
- Der Changelog-Abschnitt ist die Release Notes.
- **Pre-Alpha bleibt ungetaggt.** Ein Release entsteht erst, wenn eine
  Version **auf echter Hardware getestet** ist.

---

## 10a. Installer

Der Installer trägt die Plattformfrage: Er löst das Beschaffen der
Kernel-Headers und das Einhängen des Overlays, nicht der Nutzer. Entwurf,
Modulaufbau und die Fallstricke stehen in `docs/INSTALLER.md`.

Sechs Grundregeln, drei davon aus bezahltem Lehrgeld: idempotent,
Versionssprung bricht keine Installation, atomar schreiben mit geprüftem
`mktemp`, nichts ungeprüft aufrufen, fremde Pakete nie über `/` entpacken,
jeder Schritt einzeln aufrufbar.

### Architekturregel 10a — Board, Betriebssystem und Bootmethode sind drei Achsen

Nicht eine Variable, sondern drei unabhängige:

    board = rpi_zero2w | radxa_zero3w | unsupported_* | unknown
    os    = dietpi | raspios | radxa_debian | armbian | debian | unknown
    boot  = config_txt | extlinux | uboot_script | unknown

Derselbe Chip unter DietPi und unter Radxas Abbild sind **zwei
Installationsfälle**, weil Overlay-Ablage und Bootkonfiguration sich
unterscheiden. Wer das in einer Variablen zusammenfasst, baut sich die
Fallunterscheidungen doppelt.

Praktischer Befund aus der Umsetzung: DietPi setzt auf Debian auf und
meldet sich in `/etc/os-release` als Debian. Die Erkennung muss daher auf
DietPi-eigene Merkmale prüfen (`/boot/dietpi.txt`) und diese **vor**
`os-release` auswerten.

### Architekturregel 10b — Erkennung stützt sich auf `compatible`, nicht auf den Klartextnamen

Der Whisplay-Installer des Herstellers erkennt den Radxa so:

    [[ "$model" == *"Radxa"* ]] && echo radxa_zero3w

Das legt **jedes** Radxa-Board auf ein Profil, das nur zum ZERO 3W passt.
Chimera prüft die konkrete Kennung aus `/proc/device-tree/compatible`
(`radxa,zero3w`, `raspberrypi,model-zero-2-w`) und benennt Verwandtes
ehrlich als `unsupported_radxa` bzw. `unsupported_rpi`.

Was mit einem unbekannten Board geschieht, steht in Regel 10k.

### Architekturregel 10k — Unbekanntes Board warnt, es verbietet nicht

Unbekannt heißt ungetestet, nicht unvereinbar. Wer Chimera auf einem
Pi 4 installieren will, den niemand geprüft hat, soll das dürfen — ein
Abbruch nimmt ihm die Möglichkeit, ohne selbst etwas zu wissen. Das Repo
soll Hürden senken (Regel 6c, gleicher Gedanke).

Stattdessen eine **ehrliche Warnung**: Board nicht erkannt, es gibt kein
Profil dafür, was daraus folgt (Anzeige, Audio und Overlays sind
ungeprüft), und die Bestätigung ist eine bewusste Eingabe — kein
weggeklicktes „ja". Nicht-interaktive Läufe brauchen dafür einen
ausdrücklichen Schalter, damit ein Skript nicht versehentlich durchläuft.
Was erkannt und was erwartet wurde, steht im Protokoll (Regel 10e), damit
ein Fehlschlag später auswertbar ist — und ein geglückter Lauf zu einem
neuen Profileintrag führen kann.

**Die Grenze verläuft nicht beim Board, sondern beim Eingriff.** Gefährlich
ist nicht, ein unbekanntes Gerät zu erkennen, sondern ein **geratenes
Overlay in die Bootkonfiguration zu schreiben**: Das kostet bei einem
Gerät ohne Bildschirm den Ausbau der SD-Karte. Deshalb wird nie ein
Profil geraten. Ohne Profil laufen die Module, die ohne Boardwissen
auskommen; die bootnahen Schritte werden übersprungen und benannt,
statt mit einer Vermutung ausgeführt. `--force-board <name>` wählt ein
bekanntes Profil bewusst aus — für Entwicklung und für neue Boards. Es
wird nie in einer Warnung vorgeschlagen, weil der Vorschlag die Wahl
schon getroffen hätte.

Das ist die Anwendung von Regel 10g auf diesen Fall: nicht raten, aber
auch nicht verweigern — den Zustand benennen und den Menschen
entscheiden lassen.

### Architekturregel 10c — Alles Boardabhängige steht in einer Profiltabelle

Header-Stufe, Header-Paket, Paketquelle, SPI-Bus und -Takt,
Overlay-Quelle, kollidierende Overlays, ob der Codec im Kernel liegt, ob
ein lokales Sprachmodell realistisch ist. Ein neues Board ist ein Eintrag,
kein Durchsuchen aller Module.

Der Radxa-Eintrag existiert von Anfang an und meldet `supported=not_yet` —
ein **Zustand**, kein Platzhalter im Code. Damit ist die Portierung im
Wesentlichen ein ausgefüllter Eintrag.

Gleiche Begründung wie bei der Anbieter-Registry (Regel 5a): verteilte
Fallunterscheidungen driften auseinander.

### Architekturregel 10d — Alles Lesende geht über ein Wurzelverzeichnis

Jede Systemabfrage läuft über `CHIMERA_ROOT` (im Betrieb leer). Damit ist
die vollständige Erkennung **ohne Zielhardware** prüfbar: erfundene
`model`- und `compatible`-Dateien in einem temporären Verzeichnis, und der
Installer urteilt darüber wie über ein echtes Gerät.

Das ist kein Testkniff, sondern eine Entwurfsentscheidung. Ohne sie wäre
die Boarderkennung nur auf dem Gerät prüfbar, das man gerade nicht hat.

---

### Architekturregel 10i — Selbstaktualisierung nur mit Rückweg

Ein Gerät, das sich selbst aktualisiert, muss sich selbst zurückholen
können. openclawgotchis `patch_self.py` ändert den eigenen Quelltext ohne
Sicherung und ohne Selbstprüfung — auf einem System vom eMMC, wo es
keinen Rettungsweg gibt (`docs/HARDWARE.md` §3a), ist das nicht vertretbar.

Stattdessen die Reihenfolge, die sich andernorts bewährt hat:

    sichern → aktualisieren → selbst prüfen → bei Fehlschlag zurückspielen

Vorlage ist die erprobte Updateroutine aus dem PiHole-Projekt;
Einzelheiten in `docs/SELBSTUPDATE.md`.

Bedingungen:

- Die Sicherung entsteht **vor** der Änderung und wird geprüft, nicht nur
  angelegt (Regel 8a: das Ergebnis prüfen, nicht den Exitcode).
- Die Selbstprüfung muss **etwas bestätigen**, nicht nur fehlerfrei
  durchlaufen: Dienst läuft, Anzeige antwortet, Modell erreichbar.
- Das Zurückspielen läuft **ohne Netz und ohne das neue Programm** —
  sonst hängt die Rettung an dem, was gerade kaputt ist.
- Jeder Lauf wird protokolliert (Regel 10e), auch der erfolgreiche.

### Architekturregel 10j — Wer prüft, muss etwas sehen können

Aus der Befundsammlung der PiHole-Routine, und dort teuer bezahlt:

> Eine Prüfung, die ihre eigene Voraussetzung nicht herstellen kann,
> meldet Unsichtbarkeit als Abwesenheit — und zwar positiv, ohne Alarm.

Konkreter Fall: Die Paketliste wurde nie aufgefrischt, also meldete jede
Prüfung „kein Update verfügbar". In Wahrheit hieß das „ich habe seit
Wochen nicht nachgesehen". Belegt mit einer Paketliste, die einen Monat
alt war — und jeder Lauf sah dabei gesund aus.

Das verschärft Regel 10g: Nicht raten genügt nicht. **Wer prüft, muss
vorher dafür sorgen, dass er etwas sehen kann** — Liste auffrischen,
Verbindung herstellen, Rechte besorgen. Sonst ist die Antwort wertlos,
ohne dass es auffällt.

Das gilt auch für Chimera selbst: Die Anbieterprüfung, die
Anzeigenerkennung und die Selbstprüfung nach einem Update müssen
unterscheiden können zwischen „nicht da" und „konnte nicht nachsehen".

### Architekturregel 10e — Jeder Lauf hinterlässt ein Protokoll

In `logs/` (vorgesehen: `/var/log/chimera/`), **auch bei Erfolg**. Ein
Lauf, der nichts hinterlässt, ist später nicht nachvollziehbar — und
genau dann braucht man ihn: wenn etwas schiefging und die Frage lautet,
was vorher anders war.

Protokolliert werden Zeitstempel, Version, erkannte Umgebung, jeder
Schritt mit Ergebnis und eine Schlussbilanz. Auf dem Schirm darf es
knapper zugehen als in der Datei. Kann kein Protokoll angelegt werden,
wird das **gemeldet** und nicht stillschweigend übergangen.

### Architekturregel 10f — Keine Container auf dem Gerät

Auf Pi und Radxa läuft alles **nativ**. Der Aufwand an Speicher,
Startzeit und Schreiblast ist auf diesen Geräten nicht zu rechtfertigen,
und er verdeckt gerade die Systemintegration, um die es hier geht.

Ausnahmen nur, wo es anders nicht geht — etwa ein Dienst, der nativ nicht
sauber baubar ist. Eine solche Ausnahme wird **hier begründet**, nicht
stillschweigend eingeführt. Bisher gibt es keine.

### Architekturregel 10g — Nie raten

Erst die Fakten holen, dann entscheiden. Kein „das Paket heißt vermutlich
so", kein „das liegt wahrscheinlich da". Nachsehen: im Quelltext, im
Paketindex, auf dem Gerät.

**Vor jedem Codebau prüfen, was bereits existiert und was daran hängt.**
Sonst entstehen Doppelimplementierungen — dieselbe Logik zweimal, subtil
unterschiedlich, monatelang unbemerkt.

Was ungeprüft bleibt, wird **als ungeprüft benannt**. Eine ehrliche Lücke
ist brauchbar, eine geratene Antwort nicht. Deshalb steht in diesem
Dokument an mehreren Stellen „zu prüfen, nicht anzunehmen".

### Architekturregel 10h — Gebaut ist erst, wenn verdrahtet ist

Ein Modul, das niemand aufruft, ist kein fertiges Modul, sondern ein
offenes Ende. Dasselbe gilt für eine Funktion ohne Aufrufer, einen
Schalter ohne Wirkung, eine Option, die nirgends gelesen wird.

**Offene Enden fliegen einem um die Ohren — oder sie stehen dokumentiert.**
Beides ist zulässig, Schweigen nicht. Was unfertig bleibt, steht in der
Roadmap oder als bekannte Einschränkung im Changelog, mit seinem
tatsächlichen Zustand.

Bereits eingetreten: Modul 10 lag zunächst ohne Aufrufer da (kein
`chimera-install`), und `backup_file` hatte keinen. Ersteres ist
verdrahtet, Letzteres ist im Quelltext als „noch ohne Aufrufer, gebraucht
von Modul 60" vermerkt.

### Architekturregel 10l — Jeder Installationsschritt hat sein Gegenstück

**Ein Schritt, der etwas anlegt, wird zusammen mit dem Schritt geschrieben,
der es zurücknimmt.** Nicht später, nicht am Ende, nicht „wenn der
Installer final ist". Zu `installer/steps/NN-install-x.sh` gehört
`uninstaller/steps/NN-remove-x.sh`, und beide entstehen im selben
Arbeitsgang.

Dazu gehört zweitens: **Jede Änderung am System wird ins Manifest
geschrieben** (`installer/lib/manifest.sh`, Datei
`/var/lib/chimera/manifest.tsv`). Wer nicht einträgt, kann nicht
zurückbauen — und ein Deinstallierer, der raten muss, löscht entweder
Fremdes oder lässt Eigenes liegen.

Die Begründung ist nicht Symmetrie, sondern **Prüfbarkeit**: Der
Rückbauschritt ist der einzige echte Test des Manifesteintrags. Er
beantwortet die Frage, ob überhaupt genug festgehalten wurde, um die
Änderung umzukehren. Solange niemand aus dem Manifest liest, ist jeder
Eintrag eine unbelegte Behauptung.

Der Gegenentwurf — erst alle Installationsschritte, danach der
Deinstallierer — hat zwei Kosten, die vorher gemessen werden können:
Erstens stellt man am Ende fest, dass mehrere Schritte in einer Form
protokolliert haben, aus der sich nichts zurückbauen lässt, und korrigiert
sie rückwärts. Zweitens ist der Rückbau eines Dienstes oder eines
Kernelmoduls eine Reihenfolgefrage (stoppen, deaktivieren, entfernen,
`daemon-reload`), die man beim Anlegen im Kopf hat und Monate später
rekonstruieren muss.

Belegter Ausgangspunkt dieser Regel: Das Manifest kennt acht Arten
(`paket`, `zeile`, `datei`, `verzeich`, `dienst`, `gruppe`, `modul`,
`sicherung`). Benutzt wurden drei. Ob `dienst` und `modul` in einer
rückbaubaren Form eingetragen werden, war zum Zeitpunkt dieser Regel
**ungeprüft**, weil es keinen Leser gab — ein offenes Ende nach
Architekturregel 10h, und zwar in genau dem Bauteil, dessen Zweck der
Rückbau ist.

Drei Folgen für die Praxis:

- Ein Schritt, der nichts verändert, braucht kein Gegenstück.
  `10-check-system` prüft nur und trägt darum auch nichts ein.
- Der Deinstallierer läuft in **umgekehrter Reihenfolge** der Nummern und
  fasst nur an, was im Manifest als `neu` steht. Was als `vorher_da`
  vermerkt ist, gehört dem Nutzer und bleibt.
- **Ein fehlendes Manifest ist kein Grund abzubrechen.** Siehe die
  folgende Regel.

### Architekturregel 10n — Nachsehen, nicht abbrechen und nicht raten

Fehlt eine Auskunft, wird sie **geholt**, nicht ersetzt — nicht durch einen
Abbruch und nicht durch eine Annahme. Das ist die Anwendung von
Architekturregel 10g („Nie raten") auf den Fall, dass die eigene
Aufzeichnung fehlt.

Konkret beim Deinstallierer ohne Manifest: Die **Anwesenheit** ist immer
feststellbar. Pakete stehen in der Paketdatenbank, Dienste kennt `systemd`,
Verzeichnisse liegen im Dateisystem, Gruppenmitgliedschaften sagt `id`.
Also wird nachgesehen und erledigt, was eindeutig ist.

Eindeutig ist, was nur Chimera angelegt haben kann: eigene Pfade
(`/opt/chimera`, `/var/lib/chimera`), eigene Dienstnamen
(`chimera.service`). Dort braucht es kein Manifest — ein Verzeichnis
`/opt/chimera` hat niemand anders erzeugt.

**Was Nachsehen grundsätzlich nicht liefert, ist die Herkunft.** Ob `git`
vor Chimera installiert war, steht nirgends im System; `dpkg-query` sagt
„installiert", nicht „von wem". Ob `dtparam=spi=on` in der `config.txt` von
Chimera stammt oder vom Nutzer, ist am System nicht ablesbar. Das ist
Historie, und die kennt nur das Manifest.

Für diese Fälle gilt: **Fund nennen, Handlung dem Nutzer lassen.** Nicht
verschweigen (das wäre Regel 8a) und nicht auf Verdacht entfernen — wer dem
Nutzer sein SPI abschaltet, weil eine Zeile *auch* von Chimera stammen
könnte, hat geraten.

Die Unterscheidung spiegelt sich in jeder Feststellung: Sie gibt **drei**
Zustände zurück, nie zwei — `ist da`, `ist nicht da`, `kann nicht
nachsehen`. Wer die letzten beiden zusammenfasst, meldet Aufgeräumtheit,
wo er blind ist.

Zwei belegte Fallen beim Bauen dieser Bibliothek, beide derselbe
Mechanismus: Eine Feststellungsfunktion, deren Rückgabewert `1` oder `2`
ein normaler Befund ist, **muss in einer Bedingung aufgerufen werden**.
Steht der Aufruf nackt da, beendet `set -e` den Lauf — mit dem Exitcode der
Auskunft und ohne jede Meldung. Genau so starb der erste Lauf: kein
`systemctl` in der Testumgebung, Rückgabe 2, Abbruch. Ebenso killte ein
`printf > "${VAR:-/dev/null}"` als Nebensache den Hauptlauf.

### Architekturregel 10o — Was nicht im Manifest steht, gehört nicht uns

**Der Deinstallierer entfernt ausschließlich, was im Manifest steht.** Kein
Fund am System berechtigt zum Löschen, so naheliegend der Name auch ist.

Das ist die Grenze zu Architekturregel 10n: Nachsehen liefert eine
**Auskunft**, keine Erlaubnis. Beides zu vermischen ist der Kern des
Problems — wer aus „da liegt ein Verzeichnis namens `/opt/chimera`" schließt
„das habe ich angelegt", hat geraten, nur mit mehr Selbstvertrauen.

Denn dort kann liegen: etwas von Hand Angelegtes, eine Kopie, ein
Einhängepunkt, ein Verweis auf etwas anderes, ein gleichnamiges Verzeichnis
eines fremden Werkzeugs. Der Name ist ein Indiz, kein Beleg. Der Beleg ist
der Manifesteintrag, und den gibt es genau dann, wenn der Installer es
selbst getan hat.

Folgen:

- Ohne Manifest wird **nichts** entfernt. Es wird nachgesehen, vollständig
  berichtet, und die Handlung bleibt beim Nutzer.
- Auch mit Manifest gilt die Unterscheidung `neu` gegen `vorher_da`: Ein
  Eintrag belegt, dass wir es *gesehen* haben, nicht dass wir es *angelegt*
  haben.
- Die Suchlisten im Deinstallierer sind **Suchlisten für den Bericht**,
  keine Löschlisten. Sie heißen deshalb `chimera_known_paths`, nicht
  `chimera_own_paths` — ein früherer Entwurf hieß so und hat genau deshalb
  gelöscht, was er nur gefunden hatte.

Die Regel kostet Bequemlichkeit: Nach einer Installation von Hand oder mit
einer Fassung ohne Manifest bleibt Arbeit für den Nutzer. Das ist der
richtige Preis. Die Gegenrechnung wäre ein Werkzeug, das auf einem fremden
System nach Namensmustern löscht, und dessen Fehler bemerkt niemand
rechtzeitig.

### Architekturregel 10m — Ausführbares bleibt reines ASCII

Alles unter `installer/` und `uninstaller/` ist **ASCII**, und die Locale
wird im Programm festgelegt (`LC_ALL=C`), nicht von der Umgebung erwartet.

Zwei Gründe, beide nachgemessen:

Eine Fehlermeldung mit Umlaut wird auf einer Konsole ohne gesetztes `LANG`
zu Fragezeichen — und in einer systemd-Unit ist `LANG` standardmäßig leer.
Das trifft die Ausgabe genau dann, wenn man sie lesen will.

`sort` ordnet unter `de_DE.UTF-8` anders als unter `C`, und `grep [a-z]`
fasst dort auch Umlaute. Ein Installer, der je nach Umgebung anders
sortiert, ist nicht reproduzierbar.

Gemessener Ausgangszustand: 14 von 15 Shell-Dateien enthielten Nicht-ASCII
(`ä`, `Ä`, `—`), `LC_ALL` war nirgends gesetzt. Geprüft wird das von
`installer/tests/test-portability.sh`, mit Gegenprobe in beide Richtungen —
ein Gegenbeispiel im Kommentar (`kein [[ ]] verwenden`) darf **nicht**
anschlagen, sonst treibt der Test die Warnhinweise aus der Dokumentation.

Für Dokumentation gilt das nicht: `.md`-Dateien sind UTF-8 und dürfen
Typografie benutzen.

### Anlass für 10p und 10q: ein gemessenes Absturzbild

Ein Agenten-Harness auf zwei Android-Geräten stürzte an zwei Tagen
wiederholt ab. Ausgewertet wurde auf beiden Geräten unabhängig
voneinander, auf einem davon mit Root-Zugriff und einer laufenden
Speichermessung je Prozess. Der Auslöser (die Darstellung der Chatliste)
betrifft Chimera nicht. Das Muster dagegen ist plattformunabhängig:

1. Der native Speicher stieg in 60–80 s von rund 150 MB auf 5–8 GB, vor
   dem Absturz zur Hälfte ausgelagert. Der Speicher der Laufzeitumgebung
   blieb bei 30–120 MB. Wer nur ihn beobachtet, sieht einen gesunden
   Prozess.
2. Der Absturzbericht nannte eine Regex-Bibliothek, also den, der als
   Nächster Speicher wollte, nicht den, der ihn verbraucht hatte. Das
   führte zuerst zu einer Fehldiagnose.
3. Die Grenze, an der es endete, war die des Speicherverwalters, nicht
   die des Geräts. Beide Abstürze mit Messung blieben bei rund 8 GB
   stehen. Davor meldete der Verwalter, dass er für einzelne
   Blockgrößen keine Seiten mehr bekommt. Das passt zum Quelltext von
   scudo (32 Größenklassen zu je 256 MB). Ob Android genau diese
   Einstellung baut, ist nicht nachgeprüft. Eine Meldung ist ein Zeuge,
   keine Diagnose (Regel 10g).
4. Nach jedem Absturz stellte das Programm beim Start dieselbe Sitzung
   wieder her: vier Abstürze in 40 s auf dem einen Gerät, ein zweiter
   nach 60 s auf dem anderen.

### Architekturregel 10p — Was beim Laden abstürzt, wird beim nächsten Start nicht wieder geladen

Ein Dienst, der beim Start Zustand wiederherstellt, bildet zusammen mit
einem Neustarter (systemd `Restart=`) eine Schleife, sobald genau dieser
Zustand den Absturz auslöst. Jeder Neustart lädt ihn erneut. Das Gerät
wirkt kaputt, obwohl nur eine Datei schuld ist.

**Heute ist Chimera nicht betroffen.** Beim Start wird nur die
mitgelieferte `data/moods-builtin.json` geladen (`app.py`). Sie ist Teil
des Repos und nicht vom Modell erzeugt. `Registry.save()` hat in `src/`
keinen Aufrufer, `faces/` (Regel 8b) und `active_model.json` (§4a) stehen
nur in diesem Dokument, der Gesprächsverlauf liegt nur im Arbeitsspeicher.
Die Regel gilt **ab dem ersten gespeicherten Zustand, den der Start
liest**. Der wichtigste Fall werden vom Modell angelegte Gesichter sein:
Regel 2 prüft deren Grenzen und Schema, aber nicht, ob das Zeichnen eines
gültigen Gesichts den Renderer oder den Speicher eines 512-MB-Geräts
sprengt.

**Umsetzung:**

1. Vor dem Laden einer Zustandsquelle eine Startmarke schreiben
   (`/var/lib/chimera/laedt.<quelle>`). Gelöscht wird sie erst nach dem
   Laden **und** dem ersten Bild bzw. ersten Umlauf, denn im Anlass kam
   der Absturz nicht beim Lesen, sondern beim Darstellen.
2. Findet ein Start die Marke eines früheren Laufs, wird diese Quelle
   nicht geladen, sondern zur Seite gelegt
   (`<datei>.quarantaene-<zeit>`). Gestartet wird mit dem Standard.
3. Das Zurückfallen wird **gemeldet**, im Protokoll (Regel 10e) und
   sichtbar (§7). Läuft das Gerät weiter, ohne dass jemand erfährt, warum
   das Gesicht fehlt, ist das stiller Erfolg (Regel 8a).
4. Die Unit begrenzt die Neustarts (`StartLimitIntervalSec=`,
   `StartLimitBurst=`) für den Fall, dass Schritt 2 versagt.

**Gegenprobe (Regel 9):** Eine Quelle anlegen, deren Laden den Prozess
beendet (`os._exit(1)` im Testpfad, nicht im Produktivcode). Ohne die
Regel stirbt der zweite Start genauso. Mit der Regel läuft er mit dem
Standard, die Quarantänedatei existiert und das Protokoll nennt sie.

### Architekturregel 10q — Speicher wird am Prozess gemessen und vom Prozess begrenzt

**Messen:** Pythons eigene Mittel (`tracemalloc`, `gc`,
`sys.getsizeof`) sehen nur Python-Objekte. Was C-Bibliotheken belegen
(Spracherkennung, Sprachsynthese, onnxruntime, numpy, PIL), ist für sie
unsichtbar, und genau dort entstehen auf dem Gerät die Lecks. Das
Protokoll (Regel 10e) schreibt deshalb je Arbeitsschritt `VmRSS`,
`VmHWM` und `VmSwap` aus `/proc/self/status` mit, in kB und ohne
Zusatzpaket. Arbeitsschritte sind mindestens: Start, Mood laden oder
wechseln, Spracherkennung, Sprachsynthese, Umlauf des Agenten.
`VmSwap` gehört dazu, weil zram und die Auslagerungsdatei (Regel 5e) ein
Leck erst schlucken: Im Anlass war die Hälfte schon ausgelagert, und das
Gerät wurde zäh, bevor es abstürzte.

**Begrenzen:** Die naheliegende Grenze, `MemoryMax=`/`MemoryHigh=` in der
systemd-Unit, **wirkt auf dem Pi nicht**. Der Raspberry-Pi-Kernel startet
mit `cgroup_disable=memory`, der Wert steht in `/proc/cmdline`, aber
nicht in `cmdline.txt`. Der Speicher-Controller fehlt dann in
`/sys/fs/cgroup/cgroup.controllers`.
Gemessen am Zero 2 W (DietPi, Kernel 6.18, systemd 257): Ein Prozess
belegte 150 MB unter `MemoryMax=20M` und lief durch. Die Gegenprobe
`RuntimeMaxSec=1` griff, systemd hat die Eigenschaften also übernommen.
Eine solche Zeile in der Unit wäre stiller Erfolg (Regel 8a).

Daraus folgt:

- Der Dienst begrenzt sich selbst. Liegt `VmRSS + VmSwap` über einer
  Schwelle, beendet er sich geordnet mit eigenem Exitcode und
  Protokolleintrag. Die Schwelle ist ein Anteil von `MemTotal` und steht
  in der Profiltabelle (Regel 10c), nicht als feste Zahl im Code.
- Steht `MemoryMax=` trotzdem in der Unit, prüft der Installer, ob
  `memory` in `cgroup.controllers` steht, und meldet es, wenn nicht
  (Regel 10j: wer prüft, muss etwas sehen können).
- Den Controller einzuschalten (`cgroup_enable=memory` in `cmdline.txt`)
  wäre eine Änderung an einer Bootdatei. Sie ist hier **nicht
  entschieden** und gehört, falls gewollt, in ein Installermodul mit
  Sicherung und Rückweg.

**Nachweis eines Speichertods:** Unter Linux gibt es keinen
Absturzbericht, der Kernel beendet den Prozess per SIGKILL. Ohne
Speicher-Controller kann systemd den Tod nicht als `oom-kill` einordnen,
die Spur steht nur im Kernelprotokoll (`journalctl -k`,
„Out of memory: Killed process"). Der Protokollanfang beim nächsten Start
sucht danach und schreibt den Fund hin. Sonst sieht der Absturz aus wie
ein sauberer Neustart. Auch die Selbstbegrenzung hinterlässt ihre Spur,
über den eigenen Exitcode.

**Fehlersuche (zu Regel 10g):** Bei Speichermangel nennt der
Absturzbericht den, der als Nächster Speicher wollte. Erst die
Speicherkurve vor dem Absturz lesen, dann den Stack.

**Gegenprobe (Regel 9):** Einen Schritt bauen, der über eine
C-Bibliothek Speicher belegt (`numpy.ones(...)`) und nicht freigibt.
`tracemalloc` meldet dabei wenig, `VmRSS` muss den Anstieg zeigen, und
über der Schwelle muss sich der Dienst mit seinem Exitcode beenden.
Zeigt das Protokoll den Anstieg nicht, misst es das Falsche. Für die
Prüfung des Controllers: Ein Testprozess mit `MemoryMax=20M` belegt
150 MB. Läuft er durch, muss der Installer warnen.

### Architekturregel 10r — Der Agent ist ein eigener Nutzer, und was root ausführt, kann er nicht ändern

Chimera läuft immer unter dem Systemnutzer **`chimera`**, den der
Installer anlegt. Ein vorhandener Nutzer (auf DietPi `dietpi`) ist
**keine Option**: Er hat dort `sudo` ohne Passwort, ein Agent unter ihm
wäre faktisch root, und er könnte alles in dessen Home lesen
(SSH-Schlüssel). Die Regel gilt für jedes Linux, DietPi ist der erste
Prüffall.

Was der Agent darf, regeln **die Rechte des Nutzers**, nicht nur die
Schranke in `agent/safety.py`. Die Schranke ist Programmcode und kann
einen Fehler haben, die Dateirechte setzt der Kernel durch.

**Die Rechte wachsen mit dem Harness, und jedes einzelne ist belegt.**
Vergeben wird nur, was der heutige Code nachweislich braucht:

| Recht | Wofür | Beleg |
|---|---|---|
| Gruppe `audio` | Lautsprecher, Mikrofon | HARDWARE-BEFUNDE: `aplay -l` ohne `audio` leer |
| Gruppe `spi` | LCD über spidev | HARDWARE-BEFUNDE: `python3-spidev`, `/dev/spidev0.*` |
| Gruppe `gpio` | LED, Button, Panel-Steuerleitungen über gpiod | HARDWARE-BEFUNDE: `python3-libgpiod` |
| Schreiben im eigenen Home | Gedächtnis, Moods, Arbeitsordner, Dienstprotokolle | `app.py` (`CHIMERA_HOME`) |
| Gruppe `i2c` | **opt-in**, erst wenn Code direkt auf I2C zugreift | heute keiner: den Codec spricht der Kerneltreiber an |
| Gruppe `video` | **opt-in**, etwa sobald ein Kameramodul angeschlossen ist | heute keiner |

Opt-in heißt: Der Installer vergibt die Gruppe nur, wenn ein Profil
oder eine Option sie anfordert (`--mit i2c`, `--mit video`). Dann steht
sie in der Unit und im Manifest, und der Rückbau nimmt sie mit.

Nicht vergeben werden: `sudo`, eine Anmeldung per Passwort und
Schreibrechte außerhalb des eigenen Homes. Eine Gruppe, die es auf
dem System nicht gibt, wird übersprungen und benannt. Ein neues Recht
kommt mit dem Code, der es braucht, und mit einer Zeile in dieser
Tabelle, nicht vorsorglich.

**Pfadschema: getrennt nach Eigentümer.**

```
/opt/chimera/                    root:root 755  -- für chimera nur lesbar
  source/                        Kopie des Repos, SSOT des Installers
  productive/                    laufender Code (aus source/) und venv
  state/                         root:root 700  -- Manifest, Standdateien
  config/                        root:chimera 750, .env 640
  logs/installer/                Protokolle von Install und Uninstall
/home/<nutzer>/chimera/          chimera:chimera 700
  data/                          Gedächtnis, Moods, Arbeitsordner (CHIMERA_HOME)
  logs/productive/               Protokolle des Dienstes
```

Der Grund für die Trennung: **Wer ein Verzeichnis besitzt, kann dessen
Einträge ersetzen**, auch wenn sie root gehören (umbenennen braucht nur
Schreibrecht am Elternverzeichnis). Läge `source/` im Home von `chimera`,
könnte der Agent es gegen eigenen Code tauschen, und der nächste
`sudo chimera-install` führte diesen als root aus. Eine Prüfsumme hilft
dabei nicht, der Angreifer hätte beide Seiten in der Hand. Darum liegt
alles, was root ausführt oder liest, unter `/opt/chimera`, und der Agent
kann es nicht ändern. Das Manifest (`state/`) kann er nicht einmal lesen:
Es legt fest, was der Deinstallierer löscht. Installer und Deinstallierer
laufen beide als root und **lesen und schreiben es beide**: Für den
Installer ist es das Melderegister (was er angelegt hat), für den
Deinstallierer die einzige Wahrheitsquelle (was er entfernen darf).
Ausgesperrt ist nur der Dienstnutzer.

**Protokolle: erst in den Arbeitsspeicher, dann gesammelt auf den
Datenträger.** Geschrieben wird nach `/run/chimera/logs/` (tmpfs, für den
Dienst `RuntimeDirectory=`), nicht direkt auf die SD. Ein Abgleich kopiert
die Dateien in die Zielordner der Tabelle (`logs/installer/`,
`logs/productive/`), sobald eine Ruhezeit lang nichts mehr geschrieben
wurde, und immer beim Stoppen des Dienstes und am Ende eines
Installerlaufs. So schreibt nicht jeder Logger laufend auf die Karte,
sondern es gibt einen gebündelten Schreibvorgang. Nach einem Neustart sind
die Protokolle trotzdem da: `/var/log` hilft dafür nicht, DietPi hält es
im RAM und leert es stündlich (DietPi-RAMlog #1, Vorgabe).

Der Preis wird benannt: Bei einem Stromausfall fehlt, was seit dem
letzten Abgleich geschrieben wurde. Wer genau diesen Teil braucht
(Absturz ohne Stoppen), findet die Spur im Kernelprotokoll (Regel 10q).
Ruhezeit, Abgleich und Rotation stehen in `lib/common.sh`, nicht je
Logger. Ein zweiter Mechanismus daneben wäre eine Doppelimplementierung.

Ausführung beim Dienst (11.10.2026):

- **Der Dienst schreibt eine Datei je Start** (`dienst-<zeit>.log`) in
  `$CHIMERA_LOG_RAM`, zusätzlich zum Journal. Je Start, nicht eine feste
  Datei: Sonst überschriebe der nächste Start beim Abgleich das
  Protokoll des vorigen — genau das, das man nach einem Absturz braucht.
- **Größendeckel im Schreiber, Anzahl in `common.sh`.** `/run` ist ein
  tmpfs von rund 90 MiB (chimera-pi gemessen), ein geschwätziger Logger
  füllte ihn und störte das ganze System. Python teilt deshalb ab 1 MiB
  in Stücke (`dienst-<zeit>.1.log`, höchstens drei). Wie viele Dateien
  auf der Karte bleiben, regelt `log_rotate` — das bleibt die eine Stelle.
- **Ein Abgleichsweg für Stopp und Ruhezeit.** `installer/bin/log-abgleich.sh`
  lädt `common.sh` und ruft `log_sync`; `ExecStopPost=` der Dienst-Unit
  ruft ihn sofort, ein Timer (`chimera-logabgleich.timer`, alle 5 min)
  mit `--ruhig`. Ruhig heißt: Abgleich, wenn seit 120 s nichts mehr
  geschrieben wurde — **oder spätestens nach einer Stunde**, sonst
  erreichte ein ununterbrochen schreibender Dienst die Karte nie, und ein
  Stromausfall nähme alles mit.
- Der Timer läuft als Dienstnutzer mit derselben Abschottung wie der
  Dienst und gehört zu Schritt 98 (Manifest, Rückbau).

**Der Installer arbeitet immer aus `source/`, egal woher der Code
kam.** Startbaum kann ein Git-Klon sein, ein offline hingeschobenes Zip
oder später ein Paket (apt, npm). Jede Quelle führt in denselben
Schritt `00-source`: Startbaum mit `source/` vergleichen, bei Bedarf
`source/` neu befüllen (Nachbarverzeichnis, dann atomarer Tausch),
dann per `exec` aus `source/` neu starten. Danach sieht kein Schritt
mehr den Startbaum.

Zwei Vergleiche, mit getrennter Aufgabe:

- **Ob es derselbe Stand ist:** Prüfsumme über den Inhalt, nicht über
  den Git-Commit, denn Zip und Paket haben keinen. `.git` und
  Arbeitsdateien zählen nicht mit.
- **Welcher Stand der neuere ist:** die Datei `VERSION`, verglichen mit
  `sort -V`. Eine Prüfsumme sagt nur „anders", nicht „neuer".

**Ergänzung (12.10.2026) — Grenze der Prüfsumme.** Ein Dateiname mit
Zeilenumbruch macht einen Baum nicht prüfbar, die Prüfung bricht benannt
ab: So ein Name ergibt keine eindeutige Zeile, und eine still ausgelassene
Datei wäre eine, deren Änderung niemand bemerkt. Die Summe hängt nicht vom
Werkzeug ab — GNU und BusyBox liefern für denselben Baum dieselbe.

**Der Hash wiegt schwerer als die Version.** Die Reihenfolge der
Entscheidung:

1. **Gleicher Hash:** Der Stand ist schon 1:1 da. Der Schritt tut nichts,
   und der nächste Schritt läuft. Das gilt auch, wenn `VERSION`
   unterschiedlich ist, denn dann steht in `VERSION` nur ein anderer Text,
   der Inhalt ist derselbe.
2. **Anderer Hash, `VERSION` höher oder gleich:** `source/` wird ersetzt.
   Bei gleicher `VERSION` (Entwicklungsstand ohne Versionssprung) gibt es
   dazu einen Hinweis.
3. **Anderer Hash, `VERSION` niedriger** (ein altes Zip): kein Ersatz.
   Der Lauf benennt das, arbeitet mit dem vorhandenen `source/` weiter
   und meldet am Ende einen Befund. Ein Rückschritt geht nur gezielt mit
   `--downgrade=true`, und auch dann steht er im Protokoll.

Das ist der Orchestrator-Grundsatz aller Schritte: Ist das Ziel schon
da und gleich, wird übersprungen. Geprüft wird der Zustand, nicht eine
Marke.

**Online wird auf den neuesten Stand gezogen.** Ist das Netz da und die
Quelle öffentlich erreichbar, holt `00-source` den neuesten
veröffentlichten Stand und nimmt den höheren von beiden (Startbaum oder
online). „Neuester" heißt der höchste `vX.Y.Z`-Tag (`sort -V`), nicht
die Spitze eines Zweigs. **Offline** zählt nur, was lokal da ist, und
der Lauf sagt, dass er nicht nachsehen konnte (Regel 10j). Kein
Abbruch und kein stilles „ist aktuell".

Heute gibt es noch keinen Tag (Pre-Alpha bleibt ungetaggt). Die
Online-Prüfung ist trotzdem gebaut und getestet, gegen ein Testrepo mit
Tags. Findet sie keinen Tag, meldet sie „kein veröffentlichter Stand"
und es zählt der lokale. Die Spitze eines Zweigs nimmt sie nie ersatzweise:
Mit dem ersten Tag greift die Regel dann ohne Umbau.

Ein neues `source/` ändert am laufenden Dienst noch nichts. Erst der
Installerlauf bringt den Stand nach `productive/`. Den Neustart des
Dienstes löst die Prüfsumme von `productive/` aus.

**Rückbau:** `source/`, `productive/` und `state/` entfernt er.
**Protokolle löscht er nie von sich aus**, weder `logs/installer/` noch
`logs/productive/`: Gerade nach einem Rückbau braucht man sie, um zu
sehen, was passiert ist. Löschen nur auf ausdrückliche Anforderung
(opt-in). Dasselbe gilt für `config/` und `/home/<nutzer>/chimera/data/`
(INSTALLER.md §6). Den Nutzer
`chimera` entfernt er nur, wenn sein Home dabei mitgeht (also nur bei
angeforderter Löschung der Daten und Protokolle). Sonst bliebe
ein Home ohne Eigentümer zurück, und eine später vergebene UID erbte es.

**Gegenprobe (Regel 9):** (a) Den Installer aus zwei verschiedenen
Startpfaden aufrufen. Beide Läufe müssen dasselbe `source/` ergeben, der
zweite darf nicht kopieren. (b) Als `chimera` versuchen, in `source/`,
`productive/` und `state/` zu schreiben bzw. umzubenennen. Jeder Versuch
muss scheitern. (c) Eine Datei im Startbaum ändern. `source/` muss neu
befüllt werden, `productive/` erst im Installerlauf.

### Architekturregel 10s — Root gibt es nur auf Rückfrage, auf Zeit, und nicht für den Agenten selbst

10r bleibt: Der Dienstnutzer `chimera` hat **kein** sudo. Root kommt
über einen eigenen Helfer:

- **`chimera-hand`**, ein kleiner Root-Dienst mit Socket
  (`/run/chimera/hand.sock`, nur Gruppe `chimera`). Er führt Befehle
  **nur** aus, solange eine gültige Freigabe besteht.
- **Freigabe:**
  1. Der Agent fragt: Was will er tun, warum, und wie lange (Vorschlag
     in Minuten).
  2. Gefragt wird **der Nutzer**, über Telegram (Positivliste, Bestätigung
     per Knopf) oder die Web-Oberfläche. Nie über den Briefkasten (5p), nie über die CLI
     ohne Nutzer.
  3. Der Nutzer bestätigt **mit der Dauer**. Das Gateway schreibt die
     Freigabe an `chimera-hand` (Ablaufzeitpunkt, Grund, wer bestätigt
     hat). Der Agent selbst kann keine Freigabe anlegen.
- **Ablauf erzwingt der Helfer**, nicht der Agent: Nach Ablauf wird jeder
  Befehl abgewiesen. Höchstdauer 60 min (Vorschlag), Verlängern nur über
  eine neue Rückfrage. „Sofort beenden“ gibt es über Telegram und Web.
- **Alles wird protokolliert:** jeder Befehl, Exitcode, Dauer, unter
  `/opt/chimera/logs/root/` (root-only, für den Agenten nicht änderbar).
  Am Ende eine Bilanz an den Nutzer: „N Befehle, M fehlgeschlagen“.
- **Ein Ehrlichkeitspunkt:** Während einer Freigabe gilt der Schutz aus
  10r **nicht**. Root kann `/opt/chimera`, das Manifest und den Helfer
  selbst ändern. Die Absicherung besteht dann aus deiner Bestätigung,
  der Zeitgrenze und dem Protokoll. Eine strengere Betriebsart, bei der
  jeder einzelne Befehl bestätigt wird, wird als Option angeboten.
  Vorgabe ist die Zeitfreigabe.

---

## 11. Headless

Chimera hat **keine grafische Oberfläche.** Es gibt den 240×280-Bildschirm
mit dem Gesicht und zwei Bedienwege (Telegram, Sprache). Ein Desktop hätte
darin keine Aufgabe und würde auf beiden Zielboards Reserven verbrauchen,
die Renderer und Sprachmodelle brauchen.

**Betriebssystem ist DietPi**, auf beiden Boards — schlank und ohne
mitgeliefertes Desktop-Gepäck. Auf dem Radxa Zero 3W ist das kein
Geschmacksurteil: Radxas offizielle Abbilder sind KDE- und XFCE-Varianten,
und ein Desktop macht dieses Board für den eigentlichen Zweck unbrauchbar
langsam.

Sollen Einstellungen im Browser bearbeitbar sein, wird das eine **schlanke
Web-Oberfläche** auf einem lokalen Port — HTML und ein Formular, kein
X-Server, kein Framework-Gebirge. Sie ist Zubehör, nicht Voraussetzung:
Chimera muss ohne sie vollständig einsatzfähig sein, konfigurierbar über
`.env` und Installerfragen.

---

## 12. Hardware

- **Raspberry Pi Zero 2 W (512 MB)** — Entwicklungsziel
- **Radxa Zero 3W** — Portierungsziel, mehr Reserven
- **DietPi** auf beiden, headless (§11a)
Begründung und Grenzen in `docs/HARDWARE.md`.
- **Whisplay HAT V2 — ausschließlich.** Auf V1 führt die Button-Leitung
  5 V; ein Tastendruck kann das Board stromlos schalten. Herstellerwarnung.
- LCD 240×280, ST7789-kompatibel, SPI bis 100 MHz
- WM8960 bzw. ES8389 Codec, Mikrofon und Lautsprecher onboard
- 1 Button, RGB-LED

Lastbetrachtung: Renderer (15 FPS) und Sprachmodelle laufen bei Noisy
bereits gemeinsam auf einem Zero 2 W; der Agent wartet überwiegend auf
I/O. Machbar, aber eng — siehe Architekturregel 5 und `docs/HARDWARE.md`.

---

## 13. Keine Secrets im Repo

Tokens, Zugangsdaten, SSIDs, Gerätenamen und lokale Pfade gehören nicht
in die Versionsverwaltung. Konfiguration liegt als `*.example` mit
Platzhaltern vor; echte Werte erzeugt der Installer.

Nicht hinein gehören außerdem: **IP-Adressen aus privaten Netzen**, MAC-
Adressen, Heimnetz-Hostnamen und private Mailadressen. Für Commits gilt
ausschließlich die GitHub-noreply-Adresse.

### Architekturregel 13a — Vor jedem Push wird geprüft, und die Prüfung beweist ihre Sehfähigkeit

„Vor jedem Push scannen" allein genügt nicht — ein Scan, dessen Umfang
jedes Mal neu aus dem Kopf gewählt wird, prüft jedes Mal etwas anderes.
Die Prüfung läuft deshalb als Werkzeug mit festen Mustern, und zwar über
den Arbeitsbaum, die Commit-Nachrichten und die Urheberadressen; beim
ersten Push eines Repos und nach jedem Umschreiben der Historie auch über
jede frühere Dateifassung.

**Das Werkzeug liegt bewusst außerhalb des Repos** und ist in
`.gitignore` gesperrt. Es nennt die Suchmuster und damit die Form der
Werte, die es schützen soll — welche Präfixe die Tokens haben, welcher
Adressbereich das Heimnetz ist. Das ist eine Landkarte für jeden, der
sucht, und gehört nicht in eine öffentliche Historie. Hier steht die
Pflicht, nicht die Umsetzung.

**Und die Prüfung prüft sich selbst.** Die erste Fassung meldete „sauber"
für ein Repo, in dem eine Heimnetz-Adresse lag: `grep --exclude-dir` gibt
es in BusyBox nicht, der Aufruf brach ab, das leere Ergebnis galt als
Abwesenheit von Funden. Das ist Regel 10j in ihrer teuersten Form — wer
einem Scanner glaubt, der nichts sehen kann, pusht das Geheimnis selbst.

Deshalb läuft vor jeder Suche jedes Muster gegen einen bekannten Köder,
**durch dieselbe Funktion wie der echte Lauf**. Findet ein Muster seinen
Köder nicht, bricht die Prüfung ab, statt zu beruhigen. Ein eigener
Selbsttest mit eigenem Suchaufruf wäre wertlos: Genau der war grün,
während der echte Scan blind war.

Was in der Historie gefunden wird, ist nicht durch Löschen behoben. Der
Wert wird **widerrufen** und als verbrannt behandelt; erst danach wird
die Historie umgeschrieben.

---

## 14. Zwei Sprachen

### Architekturregel 14 — Was dauernd läuft und nicht auf das Modell wartet, ist Rust

Chimera ist künftig zweisprachig, mit einer klaren Grenze:

| Teil | Sprache | Grund |
|---|---|---|
| **Gateway** (5n) | Rust | läuft dauernd, Obergrenze 10 MB, hält Schlüssel |
| **Renderer + Paneltreiber** (Regel 7) | Rust, Stufe 2 | 15 Bilder/s, heute der Großteil von 27 % CPU |
| Agent, Werkzeuge, Moods, Gesichter als Pakete (8b) | Python | wartet 60–200 s auf das Modell; die Werkzeuge und die vom Modell angelegten Pakete leben davon, dass es Python ist |
| Installer, Selbstupdate | Shell (wie heute) | läuft als root, selten |

**Warum nicht alles in Rust (oder Go):** Gemessen am Pi braucht der
Dienst 48 MB und 27 % CPU, fast nur durch den Renderer. Die
Agentenschleife verbringt ihre Zeit im Warten auf das Modell. Ob sie
2 ms oder 0,2 ms rechnet, merkt man nicht. Ein Umbau des gesamten
Agenten (rund 1.800 Zeilen, dazu Moods mit 1.300) kostet viel und bringt
an der spürbaren Stelle nichts. **Go** bringt gegenüber Rust keinen
Vorteil, sondern eine zweite Toolchain. Es bleibt bei einer.

**Grenzen zwischen den Sprachen:**
- Python ↔ Gateway: der Unix-Socket aus 5n, eine JSON-Zeile hin, eine
  zurück.
- Python ↔ Renderer: Shared Memory für den Zustand (Muster aus Noisy,
  Regel 7). Den Framebuffer besitzt allein der Renderer-Prozess.
- Kein FFI (PyO3 o. ä.). Prozessgrenzen sind messbar (RSS je Prozess,
  10q), abstürzende Teile reißen den anderen nicht mit (10p), und jede
  Seite lässt sich allein testen.

**Gebaut wird nie auf dem Gerät.**
- Ziel: `aarch64-unknown-linux-musl`, **statisch** gelinkt. Damit gibt
  es keine glibc-Abhängigkeit, und dasselbe Binary läuft auf DietPi,
  Debian und Armbian (10a, Board und Betriebssystem bleiben getrennte
  Achsen). Später kommt `armv7` dazu, falls ein 32-Bit-Board in die
  Profiltabelle (10c) aufgenommen wird.
- Gebaut wird in der **CI** (GitHub Actions). Das Binary hängt am
  Release mit **SHA-256** daneben. Der Installer lädt das Binary zum
  Tag, prüft die Prüfsumme und bricht bei Abweichung benannt ab (I4).
  Für Pre-Alpha ohne Versions-Tag (GLOBAL: ungetaggt) veröffentlicht die
  CI auf `entwicklung` ein **Prerelease `rust-<kurzer commit>`** mit
  Binary und SHA-256. Grund: CI-Artefakte sind ohne Token nicht ladbar
  (gemessen HTTP 401), ein Prerelease-Asset anonym. Es ist kein
  `vX.Y.Z`-Tag; die Release-Kanäle (höchstes `vX.Y.Z`) ignorieren es.
- **Welches Binary:** Der Installer lädt immer **genau das Binary zum
  Commit der Quelle**, nie „das neueste“. Schritt 00 hält den Commit
  beim Klonen in `state/quelle-commit` fest (kurze Form, 7 Zeichen); ein
  Startbaum ohne `.git` (Zip, Paket) hat keinen Commit, dann bleibt die
  Datei leer und der Schritt sagt das benannt, statt zu raten. Gibt es
  zum Commit kein Prerelease, bricht Schritt 55 benannt ab (ohne Rückfall
  auf einen anderen Stand): Binary und Quelle müssen zusammenpassen.
- **Ablage:** `/opt/chimera/bin/chimera-tor`, Besitzer root, Modus 755,
  Manifest-Art `datei` mit der Prüfsumme als Angabe. Rückbau 55 entfernt
  die Datei, `bin/` nur, wenn sie leer ist. Der Schritt startet nichts;
  Nutzer, Unit und Socket kommen mit dem Gerüst (Phase 4d, Schritt 2).
- Lokale Entwicklung: rustup stable (gemessen 1.99.1) in der Sandbox,
  1:29 min für den Release-Build der Probe. **Nicht** Alpines `cargo`
  (1.83): Das kann `edition2024` nicht, das aktuelle Crates verlangen.
- Release-Profil: `opt-level = "s"`, `lto = true`,
  `codegen-units = 1`, `panic = "abort"`, `strip = true`.

**Abhängigkeiten werden genannt, nicht gesammelt.** Für das Gateway
reichen: `ureq` mit rustls (kein OpenSSL, keine Systembibliothek),
`tiny_http`, `serde`/`serde_json`. Kein async-Laufzeitsystem (tokio).
Bei wenigen gleichzeitigen Verbindungen auf einem Zero kosten Threads
weniger als ein Executor. Ein neues Crate kommt mit Begründung in diese
Liste. `Cargo.lock` wird eingecheckt, und die CI prüft mit
`cargo deny` Lizenzen (Regel 1: nichts GPL-Inkompatibles im MIT-Binary)
und bekannte Schwachstellen.

**Tests:** `cargo test` in der CI neben den Python-Tests. Regeln 8a und 9
gelten unverändert. Ein Test, der eine Python-Formel in Rust
nachrechnet, prüft nichts. Beim Umzug des Renderers wird **Bild gegen
Bild** verglichen (gleicher Zustand, gleiche Pixel innerhalb einer
Toleranz), nicht Code gegen Code.

**Umzug in Stufen, jede für sich lauffähig:**
1. Gateway (neu, ersetzt `provider/` und `bot/` im Dienst).
2. Paneltreiber und Renderer. Der Python-Renderer bleibt, bis der
   Bildvergleich grün ist, und wird erst danach entfernt (10h, nichts
   Halbes liegen lassen).


### Zuordnung für Briefkasten, Sitzung, Gedächtnis und Root

Maßstab ist
Regel 14: Was dauernd läuft, Rechte hält oder Daten verwaltet und dabei
nicht auf das Modell wartet, wird Rust.

| Teil | Sprache | Begründung |
|---|---|---|
| Briefkasten (5o) | **Rust** | läuft dauernd, hält fremde Post, prüft Token |
| Wächter: Gewicht messen (8d) | **Rust**, im Briefkasten-/Sitzungsdienst | reine Zählung von Token und Bytes, läuft nach jedem Turn |
| Sitzungsablage: `verlauf.jsonl` anhängen, `nachlesen`, Wechsel, Tarball, Löschen nach 3 Tagen (8d) | **Rust**, eigenes Binary `chimera-sitzung` | Dateiverwaltung mit Prüfungen. `tar` und `zstd`/`gzip` als Crates, damit kein externes Programm fehlen kann. |
| Root-Helfer `chimera-hand` (10s) | **Rust** | läuft als root; kleiner Code mit klaren Typen ist hier ein Sicherheitsgewinn |
| Gedächtnis: Marker zählen, Vollständigkeit prüfen, Dateien rollen (8c) | **Rust**, im Sitzungsdienst | deterministisch, prüfbar ohne Modell |
| Gedächtnis: der Text der Zusammenfassung (8c) | **Python** (Agent) | ist ein Modellaufruf; der Agent fragt, Rust prüft das Ergebnis |
| Übergabe schreiben (8d) | **Python** (Agent) | Inhalt kommt vom Modell |
| Agentenschleife, Werkzeuge, Moods, Gesichter (8b) | **Python** | wartet auf das Modell, lebt von Python (Regel 14) |

Folge: Neben Gateway und Renderer entstehen in Rust der Briefkasten,
`chimera-hand` und die Sitzungsablage. Alle liegen in **einem**
Cargo-Workspace (`rust/` im Repo), mit gemeinsamen Crates für Socket-
Protokoll und Protokollierung. Gebaut wird in einem einzigen CI-Lauf.

Die Sitzungsablage ist ein eigener Dienst `chimera-sitzung`.
Der Briefkasten hält **fremde** Daten (`chimera-post`), die Sitzung
**eigene**. Getrennte Nutzer bedeuten, dass ein Fehler im Briefkasten
nicht an den Verlauf kommt.

---

## Verzeichnis der Architekturregeln

- **1** — Die GPL-Grenze ist hart
- **1a** — Benannte Bausteine sind Vorschläge, keine Grenze
- **2** — Ein generierter Mood wird immer validiert
- **3a** — Das Modell wird nicht pro Geräusch gefragt
- **3b** — Nur im Ruhezustand wird zugehört
- **4a** — VAD läuft vor STT, KWS vor VAD
- **4b** — Gesicht und Stimme tragen denselben Mood
- **4c** — Das Sprachmodell setzt Absicht, nicht Bilder
- **5** — Sprache lokal, Sprachmodell immer remote
- **5a** — Registry statt fester Connector-Attribute
- **5b** — Anthropic-Anmeldung wie im OpenMinis-PR
- **5h** — Kein Anbieter wird vorausgesetzt
- **5c** — Ollama ist ein erstklassiger Anbieter
- **5d** — Ein Gespräch, zwei Türen
- **5i** — Ein Kanal hat keinen eigenen Zustand
- **5j** — Eine Tür von außen ohne Positivliste startet nicht
- **5k** — Ollama wird im Netz gesucht, nie auf dem Gerät betrieben
- **5l** — Wer Schlüssel hat, hat kein Werkzeug; wer Werkzeuge hat, hat keine Schlüssel
- **5m** — Die Web-Oberfläche ist Teil des Gateways und braucht kein Framework
- **5n** — Chimera spricht nur über sein Gateway mit der Welt
- **5o** — Der Briefkasten ist ein eigener Prozess hinter dem Gateway, mit eigenem Port
- **5p** — Was ein anderer Agent schreibt, ist Eingabe, kein Befehl
- **5e** — zram und Auslagerungsdatei gehören zum Aufbau
- **5f** — Fremde Werkzeuge sind nicht vertrauenswürdig
- **5g** — Audio läuft getrennt, aber schlank
- **6** — Keine absoluten Pixelwerte
- **6b** — Weich ist der Normalfall, hart muss möglich bleiben
- **6c** — Das Panel ist eine Eigenschaft, keine Annahme
- **6d** — Dieselben Moods, verschiedene Darstellungen
- **6e** — Anzeige bei jedem Start prüfen
- **7** — Ein Prozess, ein Framebuffer
- **7a** — Die Bildrate gehört zum Panel, nicht zum Renderer
- **7b** — Wer etwas anzeigt, bekommt die Anzeige übergeben
- **7c** — Konkurrierende Anzeigequellen werden zentral aufgelöst
- **7d** — Wer anzeigt, besitzt die Zeit
- **8** — Die Mood-Steuerung ist ein Skill, kein Sonderweg
- **8b** — Ein Gesicht ist ein Paket, das das Modell anlegen darf
- **8c** — Das Gedächtnis verdichtet sich nach oben, und nichts fällt dabei heraus
- **8d** — Eine aktive Sitzung, eine alte, der Rest im Archiv
- **8e** — Persönlichkeit ist eine Datei, kein Code, und jede Schicht hat einen Besitzer
- **8f** — Wer was schreiben darf, setzt der Kernel durch
- **8g** — Chimera entwickelt sich, aber in kleinen, sichtbaren, umkehrbaren Schritten
- **8h** — Dateien sind die Wahrheit, die Datenbank ist ein Index
- **8a** — Stiller Erfolg ist die gefährlichste Fehlerart
- **9** — Kein Test, der eine Formel nachrechnet
- **10** — Ein Versionssprung bricht keine Installation
- **10a** — Board, Betriebssystem und Bootmethode sind drei Achsen
- **10b** — Erkennung stützt sich auf `compatible`, nicht auf den Klartextnamen
- **10k** — Unbekanntes Board warnt, es verbietet nicht
- **10c** — Alles Boardabhängige steht in einer Profiltabelle
- **10d** — Alles Lesende geht über ein Wurzelverzeichnis
- **10i** — Selbstaktualisierung nur mit Rückweg
- **10j** — Wer prüft, muss etwas sehen können
- **10e** — Jeder Lauf hinterlässt ein Protokoll
- **10f** — Keine Container auf dem Gerät
- **10g** — Nie raten
- **10h** — Gebaut ist erst, wenn verdrahtet ist
- **10l** — Jeder Installationsschritt hat sein Gegenstück
- **10m** — Ausführbares bleibt reines ASCII
- **10n** — Nachsehen, nicht abbrechen und nicht raten
- **10o** — Was nicht im Manifest steht, gehört nicht uns
- **10p** — Was beim Laden abstürzt, wird beim nächsten Start nicht wieder geladen
- **10q** — Speicher wird am Prozess gemessen und vom Prozess begrenzt
- **10r** — Der Agent ist ein eigener Nutzer, und was root ausführt, kann er nicht ändern
- **10s** — Root gibt es nur auf Rückfrage, auf Zeit, und nicht für den Agenten selbst
- **13a** — Vor jedem Push wird geprüft, und die Prüfung beweist ihre Sehfähigkeit
- **14** — Was dauernd läuft und nicht auf das Modell wartet, ist Rust
