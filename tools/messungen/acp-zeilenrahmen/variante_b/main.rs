//! Messprogramm B: der Mindestumfang selbst, nur mit `serde_json`.
//!
//! Derselbe Vertrag wie A, aber ohne Crate und ohne Laufzeit: Zeilenrahmen
//! lesen, `initialize` erkennen, Antwort schreiben. Genau der Umfang, den
//! die DESIGN-Regel „ACP" als Mindestumfang nennt.

use std::io::{self, BufRead, Write};

use serde_json::{json, Value};

fn main() {
    let stdin = io::stdin();
    let mut out = io::stdout().lock();
    for zeile in stdin.lock().lines() {
        let zeile = match zeile {
            Ok(z) => z,
            Err(_) => break,
        };
        if zeile.trim().is_empty() {
            continue;
        }
        let anfrage: Value = match serde_json::from_str(&zeile) {
            Ok(v) => v,
            Err(_) => {
                let _ = writeln!(
                    out,
                    r#"{{"jsonrpc":"2.0","id":null,"error":{{"code":-32700,"message":"Parse error"}}}}"#
                );
                continue;
            }
        };
        let id = anfrage.get("id").cloned().unwrap_or(Value::Null);
        let antwort = if anfrage.get("method").and_then(Value::as_str) == Some("initialize") {
            json!({
                "jsonrpc": "2.0",
                "id": id,
                "result": {
                    "protocolVersion": 1,
                    "agentCapabilities": {
                        "loadSession": false,
                        "promptCapabilities": {
                            "image": false, "audio": false, "embeddedContext": false
                        },
                        "mcpCapabilities": { "http": false, "sse": false },
                        "sessionCapabilities": {},
                        "auth": {}
                    },
                    "authMethods": []
                }
            })
        } else {
            json!({
                "jsonrpc": "2.0",
                "id": id,
                "error": { "code": -32601, "message": "Method not found" }
            })
        };
        let _ = writeln!(out, "{antwort}");
    }
    let _ = out.flush();
}
