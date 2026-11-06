//! ACP-Kern für Chimera — der Mindestumfang ohne Laufzeit.
//!
//! Die Regel „ACP" in `docs/DESIGN.md` nennt den Umfang:
//! `initialize`, `session/new`, `session/prompt`, `session/update`,
//! `session/cancel`. Genau das steht hier, sonst nichts.
//!
//! Warum nicht die fertige Crate: gemessen am 6.11.2026
//! (`docs/messungen/2026-11-06-acp-bibliothek.md`) — gleiche Arbeit,
//! 370 ms gegen 5 034 ms für 20 000 Nachrichten, ein Faden statt zehn,
//! 516 kB statt 2,07 MB. Und sie brächte `tokio` in ein Gateway, das ohne
//! Laufzeit läuft.
//!
//! Der Zeilenrahmen ist **nicht** hier: Lesen und Schreiben kommen aus
//! [`gemein::zeile`] — ein zweiter Rahmen wäre eine zweite Wahrheit
//! (Regel 10g).

pub mod kern;
pub mod rpc;
pub mod transport;

pub use kern::{faehigkeiten, Agent, Ausgang, Kern, PROTOKOLL_VERSION};
pub use rpc::{deuten, fehlerantwort, meldung, Nachricht};
pub use transport::{bedienen, Ende, Stdio, Strom};
