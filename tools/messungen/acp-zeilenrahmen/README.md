# Messaufbau: ACP-Bibliothek gegen eigenen Zeilenrahmen

Zwei Programme mit demselben Vertrag (JSON-RPC 2.0, Zeilenrahmen,
`initialize` beantworten), damit sich die Crate `agent-client-protocol` und
ein eigener Kern mit `serde_json` vergleichen lassen. Zahlen und Bewertung:
`docs/messungen/2026-11-06-acp-bibliothek.md`.

| Datei | Was |
|---|---|
| `variante_a/main.rs` | Agent mit der Crate (`stdio`-Feature, `tokio` als Laufzeit) |
| `variante_b/main.rs` | eigener Zeilenrahmen mit `serde_json`, ohne Laufzeit |
| `messen.sh` | erzeugt die Anfragen, misst Größe, Durchsatz, Speicher, Startzeit |

## Nachmessen

```sh
# A
mkdir -p /tmp/a/src && cp variante_a/main.rs /tmp/a/src/
cd /tmp/a && cargo init --name acp_a --bin . 2>/dev/null
cargo add agent-client-protocol --features stdio
cargo add tokio --features rt-multi-thread,macros
cargo build --release && strip target/release/acp_a

# B (nur serde_json, siehe Cargo.toml dort)
mkdir -p /tmp/b/src && cp variante_b/main.rs /tmp/b/src/
cd /tmp/b && cargo init --name acp_b --bin . 2>/dev/null && cargo add serde_json
cargo build --release && strip target/release/acp_b

# Messung (A=/tmp/acp_a B=/tmp/acp_b vorher dorthin kopieren)
sh messen.sh
```

`messen.sh` erwartet die beiden Binärdateien unter `/tmp/acp_a` und
`/tmp/acp_b`; `N` überschreibt die Zahl der Anfragen (Vorgabe 20 000).

**Warum gestrippt gemessen wird:** Symbole sind für die Laufzeit irrelevant
und würden die Dateigröße verzerren — beide Seiten gleich behandelt.
