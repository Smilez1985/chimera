// Prüft die Größenrechnung der Eingabe im Chat-Modul ohne Browser.
//
// Befund smilez (15.11.2026): „die prompt Eingabe klebt oben, den Text kann
// man nicht mehr lesen … den prompt Bereich manipulierbar, dynamisch nach
// oben vergrösserbar machen." Die Höhe des Eingabefelds ist eine Rechnung mit
// drei Zahlen (`eingabeHoehe`) bzw. vier (`griffHoehe`) — genau die wird hier
// an der ECHTEN `chat.js` geprüft, nicht nachgebaut.
//
// Aufruf: node tests/js/chat_eingabe.mjs   (rc 0 = alles gut)

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

if (!klasse || typeof klasse.eingabeHoehe !== "function"
    || typeof klasse.griffHoehe !== "function") {
  console.log("  FAIL  eingabeHoehe/griffHoehe fehlen (umbenannt?) — nicht pruefbar");
  process.exit(1);
}
const h = klasse.eingabeHoehe;
const g = klasse.griffHoehe;
const MIN = klasse.EINGABE_MIN;
check("kleinste Hoehe ist zwei Zeilen (42)", MIN, 42);

// Ohne Text: die gezogene Hoehe gilt.
check("leer: gezogene Hoehe", h(120, 0, 400), 120);
check("leer, ohne gezogene Hoehe: Minimum", h(0, 0, 400), MIN);

// Text braucht mehr: das Feld waechst, statt abzuschneiden.
check("Text braucht mehr", h(120, 200, 400), 200);
check("Text braucht mehr, aber ueber der Grenze", h(120, 900, 400), 400);

// Nie unter die gezogene Hoehe, auch wenn der Text kurz ist.
check("kurzer Text schrumpft nicht unter die gezogene Hoehe", h(240, 60, 400), 240);

// Grenzen, die kaputt ankommen, duerfen nicht in eine unsinnige Hoehe fuehren.
check("Grenze kleiner als Minimum", h(0, 10, 5), MIN);
check("kaputte Zahlen", h(NaN, NaN, NaN), MIN);

// Ziehen: nach oben (negatives dy) macht hoeher.
check("ziehen nach oben", g(80, -60, MIN, 400), 140);
check("ziehen nach unten", g(200, 60, MIN, 400), 140);
check("ziehen ueber die Grenze", g(300, -400, MIN, 400), 400);
check("ziehen unter das Minimum", g(80, 400, MIN, 400), MIN);
check("kaputtes dy bleibt beim Startwert", g(100, NaN, MIN, 400), 100);

// --- Systemtext im Verlauf trennen --------------------------------------
// Befund smilez 16.11.: „in der chatbubble wieder die system Nachrichten …
// die sollten ein-/ausblendbar sein". Getrennt wird an der echten Datei.
const z = klasse.zerlegen;
const ohne = z("einfach nur text");
check("ohne Systemblock bleibt alles Text", `${ohne.meta}|${ohne.text}`, "|einfach nur text");
const teile = z("[Kanal: web] Du antwortest im Chat.\nAbsätze sind erlaubt.\n\nhallo\n\n[Gesicht: active=mood_idle]");
check("Kanal- und Gesichtsblock landen im Systemtext",
      teile.meta.includes("[Kanal: web]") && teile.meta.includes("[Gesicht:"), true);
check("der eigene Text bleibt allein stehen", teile.text, "hallo");
const leer = z("");
check("leerer Inhalt stürzt nicht ab", `${leer.meta}|${leer.text}`, "|");
check("Klammern mitten im Text sind kein Systemtext",
      z("das [ist] normal").meta, "");
check("nur Systemtext: leerer Rest", z("[Gesicht: active=idle]").text, "");
check("mehrere Blöcke werden getrennt", z("[Kanal: a]\n\n[Gesicht: b]\n\nrichtig").text, "richtig");

// --- Systemmeldungen als eigene Einträge (16.11.2026) --------------------
// Kanalhinweis und Gesichtsausdruck stehen jetzt als `art: system` im
// Verlauf; sichtbar sind sie nur mit dem Haken „Systemtext".
const b = klasse.blaseSichtbar;
check("Systemmeldung ohne Haken verborgen", b("system", false), false);
check("Systemmeldung mit Haken sichtbar", b("system", true), true);
check("normale Nachricht immer sichtbar", b("nachricht", false), true);
check("Verdichtungsmarke immer sichtbar", b("verdichtet", false), true);
check("unbekannte Art bleibt weg", b("quatsch", true), false);
check("leerer Eintrag bleibt weg", b(undefined, true), false);

console.log(`\nErgebnis: ${pass} ok, ${fail} fehlgeschlagen`);
process.exit(fail ? 1 : 0);
