// Prüft, dass sich die Web-Module EINEN Namensraum teilen dürfen.
//
// Befund smilez (15.11.2026): *„der Reiter Einstellungen ist vorhanden, aber
// leer"*. Ursache: Die Modulskripte sind klassische Skripte — sie laufen alle
// im **selben** globalen Gültigkeitsbereich. `anzeige.js` deklariert
// `const STIL`; `einstellungen.js` deklarierte es ebenfalls. Zwei
// `const`-Deklarationen desselben Namens sind im selben Skriptverbund ein
// SyntaxError — und ein SyntaxError tötet das **ganze** Skript, nicht nur die
// Zeile. `customElements.define` lief nie, das Element wurde nie angelegt,
// der Reiter blieb stumm leer (kein `onerror`, weil die Datei ja geladen
// wurde).
//
// Deshalb werden hier ALLE Module in EIN Skript zusammengefasst und
// ausgeführt — genau wie der Browser es tut. Jedes Manifest muss danach sein
// Element definiert haben.
//
// Aufruf: node tests/js/module_isolierung.mjs   (rc 0 = alles gut)

import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const hier = path.dirname(fileURLToPath(import.meta.url));
const MODULE = process.env.CHIMERA_MODULE_DIR
  || path.resolve(hier, "../../rust/crates/tor/web/module");

const verzeichnisse = fs.readdirSync(MODULE)
  .filter((n) => n !== "_vorlage" && fs.statSync(path.join(MODULE, n)).isDirectory())
  .filter((n) => fs.existsSync(path.join(MODULE, n, "manifest.json")));

let pass = 0;
let fail = 0;
function check(name, ist, soll) {
  if (ist === soll) { pass += 1; console.log(`  ok    ${name}`); }
  else { fail += 1; console.log(`  FAIL  ${name} -- erwartet ${soll}, bekam ${ist}`); }
}

const definiert = new Set();
globalThis.HTMLElement = class { attachShadow() {} };
globalThis.customElements = {
  define: (name) => definiert.add(name),
  get: (name) => (definiert.has(name) ? class {} : undefined),
};
globalThis.document = { addEventListener() {}, createElement: () => ({}) };
globalThis.localStorage = { getItem: () => null, setItem() {} };
globalThis.ImageData = class {};
globalThis.DataView = DataView;
globalThis.window = globalThis;
globalThis.addEventListener = () => {};

const dateien = [];
const erwartet = [];
for (const n of verzeichnisse) {
  const m = JSON.parse(fs.readFileSync(path.join(MODULE, n, "manifest.json"), "utf8"));
  if (!m.einstieg || !m.element) continue;
  const pfad = path.join(MODULE, n, m.einstieg);
  if (!fs.existsSync(pfad)) { console.log(`  FAIL  ${n}: ${m.einstieg} fehlt`); fail += 1; continue; }
  dateien.push({ n, pfad });
  erwartet.push({ n, element: m.element });
}

console.log(`== ${dateien.length} Module in einem Skriptverbund ==`);

// Wie der Browser: alle Skripte hintereinander, EIN globaler Bereich.
const zusammen = dateien.map((d) => fs.readFileSync(d.pfad, "utf8")).join("\n;\n");
let fehler = null;
try {
  new Function(zusammen)();
} catch (e) {
  fehler = e;
}
check("alle Module zusammen laufen ohne Syntaxfehler", fehler === null, true);
if (fehler) console.log(`        (${fehler.name}: ${fehler.message})`);

for (const { n, element } of erwartet) {
  check(`${n}: Element "${element}" wird definiert`, definiert.has(element), true);
}

console.log(`\nErgebnis: ${pass} ok, ${fail} fehlgeschlagen`);
process.exit(fail ? 1 : 0);
