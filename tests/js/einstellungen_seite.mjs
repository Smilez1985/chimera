// Prüft die Auskünfte der Einstellungsseite ohne Browser.
//
// Was schiefgehen kann, ist die Anzeige — eine Seite, die „aus, 0 %" zeigt,
// obwohl 80 % eingestellt sind, behauptet etwas Falsches. Geprüft werden die
// beiden reinen Rechnungen an der ECHTEN `einstellungen.js`:
// `audioText` (Zustand und Lautstärke in Worten) und `passwortFehler`
// (die Vorprüfung des Kennwortwechsels).
//
// Aufruf: node tests/js/einstellungen_seite.mjs   (rc 0 = alles gut)

import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const hier = path.dirname(fileURLToPath(import.meta.url));
const quelle = process.env.CHIMERA_EINSTELLUNGEN_JS
  || path.resolve(hier, "../../rust/crates/tor/web/module/einstellungen/einstellungen.js");

let klasse = null;
globalThis.HTMLElement = class { attachShadow() {} };
globalThis.customElements = {
  define: (name, k) => { if (name === "chimera-einstellungen") klasse = k; },
  get: () => undefined,
};
globalThis.window = globalThis;
globalThis.document = {};
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

if (!klasse || typeof klasse.audioText !== "function"
    || typeof klasse.passwortFehler !== "function") {
  console.log("  FAIL  audioText/passwortFehler fehlen (umbenannt?) — nicht pruefbar");
  process.exit(1);
}
const t = klasse.audioText;
const p = klasse.passwortFehler;

// --- Audio: der Zustand, nicht die Zahl ---------------------------------
const an = { mikrofon_an: true, lautsprecher_an: false,
             lautstaerke_mikrofon: 65, lautstaerke_lautsprecher: 80 };
check("eingeschaltet nennt Lautstärke", t(an, "mikrofon"), "an · 65 %");
// Der Punkt: im Aus bleibt die EINGESTELLTE Lautstärke sichtbar. „aus, 0 %"
// wäre gelogen (der Regler steht auf 80), ein blosses „aus" verschwiege, was
// beim Einschalten kommt.
check("aus zeigt die eingestellte Lautstärke", t(an, "lautsprecher"),
      "aus · 80 % gilt beim Einschalten");
check("lautstaerke 0 ist eine Zahl, kein Fehlen",
      t({ lautsprecher_an: false, lautstaerke_lautsprecher: 0 }, "lautsprecher"),
      "aus · 0 % gilt beim Einschalten");
check("nicht messbar wird gesagt", t({ lautsprecher_an: true,
      lautstaerke_lautsprecher: null }, "lautsprecher"), "an · nicht messbar");
check("nicht messbar im Aus: nur aus", t({ lautsprecher_an: false,
      lautstaerke_lautsprecher: null }, "lautsprecher"), "aus");
check("kein Zustand: nicht lesbar", t(null, "mikrofon"), "nicht lesbar");
// Wahrheitswerte, die als 0/1 ankommen (JSON aus anderen Quellen).
check("getippter Wahrheitswert zählt", t({ mikrofon_an: 0, lautstaerke_mikrofon: 50 },
      "mikrofon"), "aus · 50 % gilt beim Einschalten");

// --- Kennwort: die billige Vorprüfung -----------------------------------
check("alles richtig: keine Beanstandung", p("alt-passwort", "neues-pw-1", "neues-pw-1"), null);
check("ohne altes Kennwort", p("", "neues-pw-1", "neues-pw-1"),
      "Bitte das bisherige Passwort eingeben.");
check("zu kurz", p("alt-passwort", "kurz", "kurz"),
      "Das neue Passwort braucht mindestens 8 Zeichen.");
check("nicht gleich", p("alt-passwort", "neues-pw-1", "neues-pw-2"),
      "Die beiden neuen Eingaben sind nicht gleich.");
// Genau acht Zeichen sind genug — die Grenze ist 8, nicht 9.
check("acht Zeichen genügen", p("alt-passwort", "12345678", "12345678"), null);

console.log(`\nErgebnis: ${pass} ok, ${fail} fehlgeschlagen`);
process.exit(fail ? 1 : 0);
