# Changelog

Alle nennenswerten Änderungen an diesem Projekt.
Format nach [Keep a Changelog](https://keepachangelog.com/de/1.1.0/),
Versionierung nach [Semantic Versioning](https://semver.org/lang/de/) mit
einer bewussten Abweichung: **ein Versionssprung bricht keine laufende
Installation** (siehe `docs/DESIGN.md` §10).

---

## [Unreleased]

### Hinzugefügt
- Projekt aufgesetzt. Blaupause aus `docs/DESIGN.md`, `docs/ROADMAP.md`
  und diesem Changelog.
- `VERSION` als einzige Wahrheitsquelle (`0.0.1-pre`).

### Entschieden
- **Eigenes Repo** statt Branch in openclawgotchi. Beide Projekte würden
  sonst den Ballast des anderen tragen (E-Ink gegen LCD).
- **Noisy bleibt unangetastet.** Chimera übernimmt dessen Verfahren, nicht
  dessen Codepfad. Kein Fork, kein Merge.
- **Mood-Assets werden generiert, nicht gezeichnet.** Die Audio-Kopplung
  aus Noisy (`labels`, `fingerprint`, `energy`) entfällt ersatzlos; der
  Agent mischt, variiert und erfindet seine Ausdrücke selbst.
- **Sprache läuft vollständig offline** über sherpa-onnx (VAD, KWS, STT,
  TTS). Das LLM darf im eigenen Netz liegen — "ohne API" heißt hier: kein
  Fremdanbieter, kein Token-Konto, nichts verlässt das eigene Netz.
- **Deutsche Stimme `thorsten_emotional`**, weil sie Emotionsvarianten
  mitbringt und damit an den Mood gekoppelt werden kann.
- **Renderer wird neu geschrieben**, auflösungsrelativ. Noisys Fassung ist
  auf 240×240 festgenagelt, die Whisplay hat 240×280. Da Noisy weiterlebt,
  ist kein Kompromiss nötig.
- **Kein OpenMinis-Code.** Dort GPL-3.0, hier MIT. Übernommen werden nur
  nachgebaute Muster (`docs/DESIGN.md` §8).
- **Mehrere Sprachmodell-Anbieter nebeneinander**, keiner Pflicht. Der
  Router aus openclawgotchi wird dafür auf eine Registry umgebaut — er
  kennt bisher genau zwei Connectoren als feste Attribute und schaltet
  mit einem Bool um; ein dritter Anbieter passt da nicht hinein.
- **Anthropic mit Abo-Anmeldung** nach dem Muster von OpenMinis PR #407.
  Dessen Kernlehre gilt hier unmittelbar: Die Client-Kennung wird zur
  Laufzeit ermittelt, nie einkompiliert — sonst sperrt Anthropic neue
  Modelle mit `claude_code_version_too_old` aus.
- **Ollama ist ein erstklassiger Anbieter**, kein LiteLLM-Sonderfall.
  Mood-Erfindung und Zusammenfassen laufen dort, damit der Ausdruck des
  Geräts nicht an einem bezahlten Kontingent hängt.
- **Telegram bleibt vollständig erhalten** — es ist der einzige Weg, der
  auch funktioniert, wenn man nicht im selben Raum steht. Sprache kommt
  daneben, nicht darüber.
- **Ein Gespräch, zwei Türen.** Telegram und Sprache führen in denselben
  Agenten mit demselben Verlauf. Getrennte Sitzungen je Kanal würden das
  Gerät in zwei Persönlichkeiten spalten.
- **E-Ink wird umgebogen, nicht gestrichen.** Die Steuerbefehle `FACE:`,
  `DISPLAY:` und `SAY:` bleiben; nur das Ziel wechselt auf die Whisplay
  mit Noisys Mechanik. Bestehende Skills laufen unverändert weiter.

### Bekannte Einschränkungen
- Auf einem Pi Zero 2 W (512 MB) passen lokale Sprache und lokales LLM
  nicht gleichzeitig in den Speicher. Rechnung in `docs/DESIGN.md` §4.
- Die verfügbaren Wake-Word-Modelle sind nicht auf deutschem Material
  trainiert. Zuverlässigkeit von "Hey Chimera" ist ungeprüft.
- Whisplay **V1 ist unbrauchbar**: die Button-Leitung führt 5 V und kann
  das Board beim Tastendruck stromlos schalten. Nur V2 verwenden.

---

Noch kein Release. Pre-Alpha bleibt ungetaggt, bis eine Version auf echter
Hardware getestet ist.
