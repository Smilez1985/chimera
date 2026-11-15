// Prüft die Avatar-Seite ohne Browser: die Ankündigung einer Vorschau.
//
// Warum das zählt: Die Seite sagt vor dem Klick, was passiert — „läuft einmal
// ganz (13 s)" oder „30 s Vorschau, dann zurück". Stimmt das nicht, ist die
// Auskunft schlimmer als keine, und das Gesicht steht nach der Vorschau
// bewegungslos da (der BONG-Fehler vom 15.11.). Geprüft wird die ECHTE Datei.
//
// Aufruf: node tests/js/avatar_seite.mjs   (rc 0 = alles gut)

import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const hier = path.dirname(fileURLToPath(import.meta.url));
const quelle = process.env.CHIMERA_ANZEIGE_JS
  || path.resolve(hier, "../../rust/crates/tor/web/module/anzeige/anzeige.js");

// Minimaler DOM-Ersatz: Das Skript definiert zwei Klassen und setzt zwei
// Rechnungen an die Klasse -- mehr braucht es hier nicht.
const klassen = {};
globalThis.HTMLElement = class { attachShadow() {} };
globalThis.customElements = {
  define: (name, k) => { klassen[name] = k; },
  get: (name) => klassen[name],
};
globalThis.document = { addEventListener() {}, createElement: () => ({}) };
globalThis.window = globalThis;
globalThis.addEventListener = () => {};
globalThis.document.hidden = false;

new Function(fs.readFileSync(quelle, "utf8"))();

const Seite = klassen["chimera-anzeige-seite"];
if (!Seite) {
  console.log("  FAIL  Klasse chimera-anzeige-seite fehlt");
  process.exit(1);
}
const f = Seite.vorschauText;
if (typeof f !== "function") {
  console.log("  FAIL  vorschauText haengt nicht an der Klasse (Test sähe nichts)");
  process.exit(1);
}

let pass = 0;
let fail = 0;
function check(name, ist, soll) {
  if (ist === soll) {
    pass += 1;
    console.log(`  ok    ${name}`);
  } else {
    fail += 1;
    console.log(`  FAIL  ${name} -- erwartet ${JSON.stringify(soll)}, bekam ${JSON.stringify(ist)}`);
  }
}

// Ein Ausdruck mit eigener Dauer: einmal ganz, mit der Dauer des Ausdrucks.
check("endlich: nennt die eigene Dauer",
  f({ name: "BONG", dauer_s: 13, dauerzustand: false, vorschau_s: 0 }),
  "BONG: läuft einmal ganz (13 s)");
check("endlich ohne Dauer: sagt nur 'einmal ganz'",
  f({ name: "HUSTEN", dauer_s: 0, dauerzustand: false, vorschau_s: 0 }),
  "HUSTEN: läuft einmal ganz");

// Ein Dauerzustand: 30 s, dann zurück.
check("Dauerzustand: 30 s Vorschau",
  f({ name: "ROCK", dauer_s: 0, dauerzustand: true, vorschau_s: 30 }),
  "ROCK: 30 s Vorschau, dann zurück");
check("Dauerzustand: andere Vorgabe wird gesagt, nicht geraten",
  f({ name: "IDLE", dauer_s: 0, dauerzustand: true, vorschau_s: 45 }),
  "IDLE: 45 s Vorschau, dann zurück");

// Kein Eintrag: leerer Text, kein "undefined".
check("ohne Eintrag: leer", f(null), "");
check("ohne Namen: leer", f({ dauer_s: 3 }), "");

// Die Gegenprobe dazu steht nicht hier, sondern in
// tests/gegenprobe_avatar_seite.py: Sie vertauscht die Bedingung in einer
// Kopie von anzeige.js und erwartet, dass DIESER Test rot wird. Ein Test,
// der seine eigene Verfälschung mitbringt, prüft nur sich selbst.

console.log(`\n${pass} ok, ${fail} FAIL`);
process.exit(fail === 0 ? 0 : 1);
