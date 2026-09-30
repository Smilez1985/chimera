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
- **Auslagerungsdatei auf dem Systemdatenträger**, ein Viertel von dessen
  Größe, als zweite Stufe unterhalb von zram. Sie liegt dort, wo das
  System liegt: auf dem Pi die SD-Karte, auf dem Radxa der eMMC. Damit
  läuft der Radxa ohne SD-Karte — und wo eine steckt, wird sie geschont.

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
Vermutung durch Messung ersetzt werden kann (Regel 10g).

**Auf dem Radxa ist beides nicht nötig und wird trotzdem eingerichtet.**
Ein Aufbau, der sich je nach Board unterscheidet, erzeugt zwei Systeme,
die sich unterschiedlich verhalten — und der Fehler zeigt sich dann
ausgerechnet auf dem Gerät, das seltener läuft.

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
- **13a** — Vor jedem Push wird geprüft, und die Prüfung beweist ihre Sehfähigkeit
