// Prüft die Kennungs-Ableitung des Anbieter-Moduls ohne Browser.
//
// Warum ohne Browser: `anbieter.js` ist eine Web-Komponente, aber die
// Umformung "Bezeichnung → Kennung" ist reine Zeichenarbeit. Sie wird hier
// aus der ECHTEN Datei geladen (nicht nachgebaut) — ein Test, der die Regel
// wiederholt, besteht auch mit der kaputten Funktion.
//
// **Anlass (14.11.2026):** Das Feld "Kennung" stand als Pflichtfeld vor dem
// Nutzer, obwohl es ein interner Name ist (`config/geheim/<id>`). Es wird
// jetzt aus der Bezeichnung gebildet; diese Datei hält die Regel fest, und
// zwar gegen `daten::id_gueltig` (a-z, 0-9, "-", max 32, kein "-" vorn).
//
// Aufruf: node tests/js/anbieter_kennung.mjs   (rc 0 = alles gut)

import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const hier = path.dirname(fileURLToPath(import.meta.url));
// CHIMERA_ANBIETER_JS laesst die Gegenprobe eine veraenderte Kopie pruefen,
// ohne die echte Datei anzufassen.
const quelle = process.env.CHIMERA_ANBIETER_JS
  || path.resolve(hier, "../../rust/crates/tor/web/module/anbieter/anbieter.js");

let klasse = null;
globalThis.HTMLElement = class {
  attachShadow() {}
};
globalThis.customElements = {
  define: (name, k) => {
    if (klasse) throw new Error("mehr als eine Komponente definiert: " + name);
    klasse = k;
  },
};
// Die Datei ist kein ES-Modul (sie laeuft im Browser als klassisches Script).
// Node kapselt sie beim eval nicht, also wird sie hier als Funktionsrumpf
// ausgewertet -- so bleibt `class` im lokalen Scope und landet ueber
// customElements in `klasse`.
new Function(fs.readFileSync(quelle, "utf8"))();

if (!klasse) throw new Error("anbieter.js hat keine Komponente definiert");
const kennungAus = klasse.kennungAus;
if (typeof kennungAus !== "function") throw new Error("kennungAus fehlt an der Komponente");

let fehler = 0;
let geprueft = 0;

// Dieselbe Regel wie `daten::id_gueltig` in Rust (daten.rs:50).
function gueltig(id) {
  return typeof id === "string"
    && id.length > 0
    && id.length <= 32
    && !id.startsWith("-")
    && /^[a-z0-9-]+$/.test(id);
}

function fall(text, erwartet, warum) {
  geprueft++;
  const ist = kennungAus(text);
  if (ist !== erwartet) {
    fehler++;
    console.log(`  FAIL ${JSON.stringify(text)} -> ${JSON.stringify(ist)}, erwartet ${JSON.stringify(erwartet)}  [${warum}]`);
  } else {
    console.log(`  ok   ${JSON.stringify(text)} -> ${JSON.stringify(ist)}`);
  }
  if (erwartet && !gueltig(ist)) {
    fehler++;
    console.log(`  FAIL ${JSON.stringify(ist)} ist keine gueltige Kennung (daten::id_gueltig)  [${warum}]`);
  }
}

console.log("Kennungs-Ableitung (echte anbieter.js):");

// Der Fall aus der Praxis: der Nutzer tippt den Namen des Anbieters.
fall("DeepSeek", "deepseek", "Bezeichnung des Anbieters");
fall("Deep Seek", "deep-seek", "Leerzeichen wird zum Trenner");
fall("Mein Anbieter", "mein-anbieter", "mehrere Woerter");
fall("Konto (privat)", "konto-privat", "Klammern fliegen raus, kein Trenner doppelt");
fall("ÄÖÜ Änderung", "aeoeue-aenderung", "Umlaute werden ausgeschrieben, nicht verschluckt");
fall("Straße", "strasse", "scharfes S");

// Grenzen von `daten::id_gueltig`.
fall("  --Test--  ", "test", "kein Trenner vorn, keiner am Ende");
fall("aB9", "ab9", "gross wird klein, Ziffern bleiben");
fall("", "", "leere Bezeichnung ergibt eine leere Kennung (der Aufrufer setzt den Typ ein)");
fall("ä", "ae", "einzelner Umlaut bleibt nicht als leerer Wert");
fall("x".repeat(40), "x".repeat(32), "hoechstens 32 Zeichen");
fall("Sehr langer Name mit vielen Woertern", "sehr-langer-name-mit-vielen-woer", "harte Kuerzung bei 32 Zeichen");
fall("Test-", "test", "Trenner am Ende faellt weg");

// Was NICHT passieren darf: eine Zahl oder ein Sonderzeichen vorn.
for (const roh of ["1Password", "-x", "@home", "Öl 2024"]) {
  geprueft++;
  const ist = kennungAus(roh);
  if (!gueltig(ist)) {
    fehler++;
    console.log(`  FAIL ${JSON.stringify(roh)} -> ${JSON.stringify(ist)} ist ungueltig`);
  } else {
    console.log(`  ok   ${JSON.stringify(roh)} -> ${JSON.stringify(ist)} (gueltig: ${gueltig(ist)})`);
  }
}

console.log(`\n${geprueft} Faelle, ${fehler} rot.`);
process.exit(fehler ? 1 : 0);
