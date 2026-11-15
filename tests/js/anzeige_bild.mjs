// Prüft die Bildrechnung des Anzeige-Moduls ohne Browser.
//
// Warum ohne Browser: `anzeige.js` ist eine Web-Komponente, aber die beiden
// Schritte, an denen ein Fehler weh tut, sind reine Rechnung — den Kopf der
// Datei deuten und RGB565 nach RGBA wandeln. Beide werden aus der ECHTEN
// Datei geladen (nicht nachgebaut): ein Test, der die Formel wiederholt,
// besteht auch mit der kaputten Anzeige.
//
// Aufruf: node tests/js/anzeige_bild.mjs   (rc 0 = alles gut)

import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const hier = path.dirname(fileURLToPath(import.meta.url));
// CHIMERA_ANZEIGE_JS laesst die Gegenprobe eine veraenderte Kopie pruefen.
const quelle = process.env.CHIMERA_ANZEIGE_JS
  || path.resolve(hier, "../../rust/crates/tor/web/module/anzeige/anzeige.js");

let klasse = null;
globalThis.HTMLElement = class { attachShadow() {} };
globalThis.customElements = {
  define: (name, k) => { if (name === "chimera-anzeige") klasse = k; },
  get: () => undefined,
};
globalThis.document = { createElement: () => ({}), addEventListener() {} };
globalThis.ImageData = class {
  constructor(data, breite, hoehe) {
    this.data = data;
    this.width = breite;
    this.height = hoehe;
  }
};
globalThis.localStorage = { getItem: () => null, setItem() {} };

new Function(fs.readFileSync(quelle, "utf8"))();

let pass = 0;
let fail = 0;
function check(name, ist, soll) {
  const gleich = JSON.stringify(ist) === JSON.stringify(soll);
  if (gleich) {
    pass += 1;
    console.log(`  ok    ${name} -> ${JSON.stringify(ist)}`);
  } else {
    fail += 1;
    console.log(`  FAIL  ${name} -- erwartet ${JSON.stringify(soll)}, bekam ${JSON.stringify(ist)}`);
  }
}

if (!klasse) {
  console.log("  FAIL  das Modul definiert <chimera-anzeige> nicht");
  process.exit(1);
}
if (typeof klasse.bildMalen !== "function" || typeof klasse.kopfDeuten !== "function") {
  console.log("  FAIL  bildMalen/kopfDeuten fehlen (umbenannt?)");
  process.exit(1);
}

// --- Kopf ---
function kopf(breite, hoehe, zaehler, { magic = "CHSP", fassung = 1, format = 1 } = {}) {
  const b = new Uint8Array(32);
  for (let i = 0; i < 4; i++) b[i] = magic.charCodeAt(i);
  b[4] = fassung;
  b[5] = format;
  b[6] = breite >> 8; b[7] = breite & 0xff;
  b[8] = hoehe >> 8; b[9] = hoehe & 0xff;
  // Zaehler als 64-Bit big-endian an Offset 12 (obere vier Bytes reichen hier).
  const s = new DataView(b.buffer);
  s.setBigUint64(12, BigInt(zaehler), false);
  return b;
}

check("Kopf 240x280, Zaehler 42", klasse.kopfDeuten(kopf(240, 280, 42)),
      { format: 1, breite: 240, hoehe: 280, zaehler: 42 });
check("fremde Kennung ist kein Bild", klasse.kopfDeuten(kopf(240, 280, 1, { magic: "XXXX" })), null);
check("falsche Fassung ist kein Bild", klasse.kopfDeuten(kopf(240, 280, 1, { fassung: 2 })), null);
check("abgeschnittener Kopf ist kein Bild", klasse.kopfDeuten(new Uint8Array(10)), null);
check("Breite 0 ist kein Bild", klasse.kopfDeuten(kopf(0, 280, 1)), null);
check("leere Eingabe ist kein Bild", klasse.kopfDeuten(null), null);

// --- Punkte ---
function wandle(pixel) {
  const bytes = new Uint8Array(pixel.length * 2);
  const s = new DataView(bytes.buffer);
  pixel.forEach((p, i) => s.setUint16(i * 2, p, false));
  let bild = null;
  klasse.bildMalen(bytes, pixel.length, 1, { putImageData: (i) => { bild = i; } });
  return bild;
}

check("Rot 0xF800", Array.from(wandle([0xf800]).data.slice(0, 4)), [255, 0, 0, 255]);
check("Gruen 0x07E0", Array.from(wandle([0x07e0]).data.slice(0, 4)), [0, 255, 0, 255]);
check("Blau 0x001F", Array.from(wandle([0x001f]).data.slice(0, 4)), [0, 0, 255, 255]);
check("Schwarz 0x0000", Array.from(wandle([0x0000]).data.slice(0, 4)), [0, 0, 0, 255]);
check("Weiss 0xFFFF", Array.from(wandle([0xffff]).data.slice(0, 4)), [255, 255, 255, 255]);
// 0x8410 = r 16/31, g 32/63, b 16/31 -> 132 / 130 / 132 (gerundet, nicht 127
// und nicht abgeschnitten auf 131).
check("Mittelton 0x8410", Array.from(wandle([0x8410]).data.slice(0, 4)), [132, 130, 132, 255]);

// Zwei Punkte: Reihenfolge darf nicht verdreht werden.
const zwei = wandle([0xf800, 0x001f]);
check("zwei Punkte: erster rot", Array.from(zwei.data.slice(0, 4)), [255, 0, 0, 255]);
check("zwei Punkte: zweiter blau", Array.from(zwei.data.slice(4, 8)), [0, 0, 255, 255]);

// Der Aufruf bekommt im Betrieb einen Ausschnitt des Puffers (ab Byte 32) --
// ein Uint8Array mit byteOffset, kein eigener ArrayBuffer. Das muss gehen.
const gross = new Uint8Array(32 + 4);
const gs = new DataView(gross.buffer);
gs.setUint16(32, 0x07e0, false);
const ausschnitt = new Uint8Array(gross.buffer, 32, 4);
let ausBild = null;
klasse.bildMalen(ausschnitt, 1, 1, { putImageData: (i) => { ausBild = i; } });
check("Ausschnitt mit byteOffset", Array.from(ausBild.data.slice(0, 4)), [0, 255, 0, 255]);

console.log(`\nErgebnis: ${pass} ok, ${fail} fehlgeschlagen`);
process.exit(fail ? 1 : 0);
