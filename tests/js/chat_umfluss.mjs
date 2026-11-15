// Prüft den Umfluss im Chat-Modul ohne Browser.
//
// Das Gesicht liegt fest im Chatfeld (DESIGN, Regel „Anzeigespiegel"); der
// Verlauf scrollt darunter durch. Welche Blase ihm ausweichen muss, ist eine
// Rechnung mit vier Zahlen — genau die wird hier an der ECHTEN Datei geprüft,
// nicht nachgebaut.
//
// Aufruf: node tests/js/chat_umfluss.mjs   (rc 0 = alles gut)

import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const hier = path.dirname(fileURLToPath(import.meta.url));
const quelle = process.env.CHIMERA_CHAT_JS
  || path.resolve(hier, "../../rust/crates/tor/web/module/chat/chat.js");

let klasse = null;
globalThis.HTMLElement = class { attachShadow() {} };
globalThis.customElements = {
  define: (name, k) => { if (name === "chimera-chat") klasse = k; },
  get: () => undefined,
};
globalThis.document = { addEventListener() {} };
globalThis.window = globalThis;
globalThis.localStorage = { getItem: () => null, setItem() {} };

new Function(fs.readFileSync(quelle, "utf8"))();

let pass = 0;
let fail = 0;
function check(name, ist, soll) {
  if (ist === soll) {
    pass += 1;
    console.log(`  ok    ${name}`);
  } else {
    fail += 1;
    console.log(`  FAIL  ${name} -- erwartet ${soll}, bekam ${ist}`);
  }
}

if (!klasse || typeof klasse.weichtAus !== "function") {
  console.log("  FAIL  weichtAus fehlt (umbenannt?) — Umfluss nicht pruefbar");
  process.exit(1);
}
const f = klasse.weichtAus;

// Gesicht oben rechts: x 250..360, y 100..240.
const gesicht = { oben: 100, unten: 240, links: 250, rechts: 360 };

// Eine Blase, die es senkrecht schneidet und rechts bis unter seine Kante
// reicht, muss ausweichen.
check("Blase unter dem Gesicht, rechts",
      f({ oben: 120, unten: 400, links: 0, rechts: 380 }, gesicht, true), true);
check("Blase beginnt darueber und endet darin",
      f({ oben: 40, unten: 130, links: 0, rechts: 380 }, gesicht, true), true);
// ... aber nur, wenn sie es ueberhaupt schneidet.
check("Blase ganz oberhalb", f({ oben: 10, unten: 90, links: 0, rechts: 380 }, gesicht, true), false);
check("Blase ganz unterhalb", f({ oben: 250, unten: 400, links: 0, rechts: 380 }, gesicht, true), false);
// Eine Blase, die senkrecht schneidet, aber weit links bleibt, stoert nicht.
check("Blase endet links vom Gesicht",
      f({ oben: 120, unten: 200, links: 0, rechts: 240 }, gesicht, true), false);
// Beruehren ist kein Ueberdecken.
check("Blase beruehrt die Kante genau",
      f({ oben: 120, unten: 200, links: 0, rechts: 250 }, gesicht, true), false);

// Gesicht auf der linken Seite: dieselbe Logik, andere Richtung.
const links = { oben: 100, unten: 240, links: 10, rechts: 120 };
check("links: Blase reicht bis ins Gesicht",
      f({ oben: 120, unten: 200, links: 0, rechts: 300 }, links, false), true);
check("links: Blase beginnt rechts davon",
      f({ oben: 120, unten: 200, links: 130, rechts: 300 }, links, false), false);

// Grosse Blase, die sich mit dem Gesicht nur in einer Zeile schneidet.
check("ein Punkt Ueberdeckung genuegt",
      f({ oben: 239, unten: 260, links: 0, rechts: 380 }, gesicht, true), true);

console.log(`\nErgebnis: ${pass} ok, ${fail} fehlgeschlagen`);
process.exit(fail ? 1 : 0);
