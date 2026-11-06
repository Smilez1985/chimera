//! Messprogramm A: der Mindestumfang mit der Crate `agent-client-protocol`.
//!
//! Es tut genau, was der ACP-Kern tun muss: `initialize` beantworten, sonst
//! nichts. Der Client schickt Zeilen auf stdin, der Agent antwortet auf
//! stdout. Nach dem Schliessen von stdin endet der Prozess -- damit laesst
//! sich Durchsatz und Laufzeit messen, ohne einen zweiten Prozess zu bauen.

use agent_client_protocol::v1::schema::{AgentCapabilities, InitializeRequest, InitializeResponse};
use agent_client_protocol::{Agent, Result, Stdio};

#[tokio::main]
async fn main() -> Result<()> {
    Agent
        .v1()
        .name("mess-agent")
        .on_receive_request(
            async move |initialize: InitializeRequest, responder, _connection| {
                responder.respond(
                    InitializeResponse::new(initialize.protocol_version)
                        .agent_capabilities(AgentCapabilities::new()),
                )
            },
            agent_client_protocol::on_receive_request!(),
        )
        .connect_to(Stdio::new())
        .await
}
