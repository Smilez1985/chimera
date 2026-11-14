# Chimera

**An agentic harness with a face it builds itself — and a voice it is being
built to speak with.**

Chimera is an AI agent that runs on a Raspberry Pi with a
[PiSugar Whisplay HAT](https://github.com/PiSugar/Whisplay). It has a colour
LCD, a microphone, a speaker, a button and an RGB LED. Screen, LED and
button show what it is actually doing; microphone and speaker are there for
the voice layer, which has no code yet (see below).

> Status: **pre-alpha.** No release is tagged — the only tags in the repo are
> CI prereleases (`rust-<sha>`, see `docs/CI.md`), and `VERSION` says
> `0.1.0-pre`. The design documents come first; see `docs/DESIGN.md`.
>
> **Honest status.** Chimera is built in layers, and not every layer exists
> yet. What exists today and runs on a Pi Zero 2 W: the agent loop, the
> gateway, the web UI (port 8080), the tool layer with its grants, SSH and
> the face renderer. The Telegram door is built but only speaks once a token
> is configured; the voice layer does not exist. What does **not** exist yet is
> marked as such wherever it is described — the voice path above all
> (`docs/ROADMAP.md` lists everything open with evidence).

---

## The idea

Most agent frontends show you a spinner. Chimera shows you a face.

Not a canned set of emoticons, though — faces are declarative asset
definitions (colour, eye shape, mouth style, physics, particles), so an
expression is data, not code. The renderer blends one mood into the next
over all fields (`mood/transition.py`), and the agent chooses which one to
show (`set_face`). **Inventing** new expressions — the task
`mood_erfindung` exists in the planner — has no caller and no tool yet;
that is the part that would let a repertoire nobody designed grow.

**What exists today:** the mood library — 43 expressions inherited from
[Noisy](https://github.com/Smilez1985/Noisy) (`data/moods-builtin.json`),
plus two Chimera's own (`SPEAK`, `UPDATE`) — the validator for invented
shapes, the renderer, and the internal states (`wartet`, `hoert`, `denkt`,
`spricht`, `fehler`). **What is designed but not built:** the sources that
set a mood from outside — an MQTT broker and an MCP route (DESIGN, rule
"MQTT"). The expressions are there; the wires to a broker are not.

The state it shows is real state:

| What's happening | What you see | Built? |
|---|---|---|
| thinking | particles rising | yes |
| speaking | animated mouth | yes (text; there is no voice to carry emotion) |
| stuck in a tool loop | visibly agitated, red LED | yes |
| CPU hot | drooping eyelids, sweat — the expression is part of the inherited mood set | yes (`render/avatar.py`, thermal coupling to `/sys/class/thermal`) |
| listening | attentive face, blue LED | state and face exist, but nothing can listen yet |
| context nearly full | tired eyes | no — compaction exists (`agent/context.py`), the face does not show it |

An agent that looks nervous when it gets stuck is the most honest status
display you can build.

## Two ways in, one conversation

Chimera talks over **Telegram** and **by voice**, and both lead into the
same agent with the same history. Discuss something on the way home, walk
up to the device and continue — it is the same counterpart, not two.

Telegram stays because it is the only channel that works when you are not
in the room. Voice is added beside it, not on top of it.

> **Status:** Telegram is built (`src/chimera/bot/telegram.py`, the gateway's
> own door in `rust/crates/tor/src/telegram.rs`) and **one conversation** is
> real: every door asks the same session, the same memory, the same history
> (DESIGN 5d). Voice is **not built** — see the next-but-one section.

## Bring your own model

No provider is mandatory. Every call leaves the device through the gateway
(`chimera-tor`), which owns the keys and the only network connection — the
agent itself has no network at all (DESIGN 5l/5n).

- **DeepSeek** — OpenAI-compatible, built and in use
  (`rust/crates/tor/src/deepseek.rs`); streaming, tool calls, usage, balance
- **Ollama** on your own network — first-class, not a special case
- **Anthropic** — the connector exists (`src/chimera/provider/anthropic.py`,
  runtime client identifier, API key *and* subscription) but is **not
  usable in operation yet**: the gateway has no Anthropic chat module, and
  the service has no network of its own. Listed here because it is next in
  line, not because it answers today (ROADMAP)
- **anything else through LiteLLM** — **planned, not built**. There is no
  LiteLLM connector; an `litellm` provider entry is rejected with its name
  instead of being silently ignored
- **MCP tools** — **planned, not built** (see `docs/PROVIDER.md`)

Cheap tasks (`mood_erfindung`, `umgebung`, `zusammenfassen`, `titel`) go to
the local model first, so the device's own expression does not depend on a
paid quota. Access and cost belong to the provider *type*
(`provider/gateway.py`, `TYP_KLASSEN`): Ollama is local and free, DeepSeek
is a metered API key, and an unknown type counts as metered — which keeps it
out of the cheap chain rather than quietly making it free.

## How it is put together

Three processes, and one rule that explains all of them: **whoever has
network has no tools, whoever has tools has no network** (DESIGN 5l/5n).
They talk over Unix sockets in `/run/chimera/`, started by systemd.

| process | user | network | job |
|---|---|---|---|
| `chimera` (Python) | `chimera` | none (`IPAddressDeny=any`) | agent loop, face, renderer, memory, skills |
| `chimera-tor` (Rust) | `chimera-tor` | yes | gateway: model calls, web UI, Telegram, grants, SSH hosts |
| `chimera-sohelper` (Rust) | `chimera-sohelper` | none (`IPAddressDeny=any`) | the only process that runs commands |

Sockets: `tor.sock`, `sitzung.sock`, `sohelper.sock`. The installer brings
13 modules, three services, three sockets and two timers; `chimera-tor
--mojo` checks the health of all of it and names the cause before repairing
anything. Settings and state live in `/opt/chimera` (`config/`, `state/`),
each directory with exactly one writer (DESIGN 5t).

## Voice — designed, **not built**

> **Status: nothing of this exists in code.** There is no audio process, no
> recorder, no model file in the repo (`rg sherpa` finds only documents).
> The only audio in the code today is the installer's test beep
> (`src/chimera/displays/mikro.py`), aplay/arecord. The design stands
> (`docs/DESIGN.md` §4, `docs/PROVIDER.md`); the work is open in
> `docs/ROADMAP.md`.

The plan: speech recognition, synthesis, voice activity detection and
wake-word spotting all run locally via
[sherpa-onnx](https://github.com/k2-fsa/sherpa-onnx). No cloud speech
service, no per-request billing, nothing leaves the device.

German TTS is meant to use `thorsten_emotional`, a voice with emotion
variants — so the voice carries the same mood as the face. The cost is
real: four int8 models (VAD 2 MB, wake-word 14 MB, STT 98 MB, TTS 22 MB)
have to fit next to the renderer on a 462 MB Pi Zero 2 W. That is why this
is the last layer, not the first.

## Lineage

Chimera is a new project, not a fork. It stands on three shoulders:

| Project | Licence | Role |
|---|---|---|
| [openclawgotchi](https://github.com/Smilez1985/openclawgotchi) | MIT | Base: agent loop, skills, memory, LLM router |
| [Noisy](https://github.com/Smilez1985/Noisy) | MIT | Rendering technique and mood architecture |
| [OpenMinis](https://github.com/OpenMinis/OpenMinis) | GPL-3.0 | Agent-loop hardening — **patterns only, no code** |

Noisy continues to live unchanged on its own hardware. Chimera borrows its
technique, not its code path.

OpenMinis is GPL-3.0 and Chimera is MIT, so no OpenMinis code is copied —
only independently reimplemented ideas. See `docs/DESIGN.md` for the full
account.

## Hardware

**Several displays are planned, one is built.** Only the Whisplay panel
exists as code today (`src/chimera/displays/whisplay/`, 240×280, 15 fps).
An E-Paper Pi or a GamePi13 is designed for — the installer is supposed to
detect the panel at every boot — but `docs/DISPLAYS.md` says it plainly:
design, nothing built beyond Whisplay. The panel is a property, not an
assumption (DESIGN 6c), so adding one is a new panel module, not a rewrite.

Two boards are planned; **one runs today**:

- **Raspberry Pi Zero 2 W** — the development target, and the only board
  Chimera has run on. 462 MB RAM, 331 MB available.
- **Radxa Zero 3W** — more headroom (up to 8 GB, enough to run the language
  model locally). Profile exists (`installer/lib/profiles.sh`), marked
  `not_yet`: the installer refuses it by name instead of half-installing.

Both run **DietPi** — Chimera is headless. There is a 240×280 screen showing
a face and two ways to talk to it; a desktop would only eat the headroom the
renderer and speech models need.

**The web UI is not a future idea any more.** It is part of the gateway
(`chimera-tor`, port 8080), asks for a password before anything else, and
carries nine modules: chat, status, providers, balance, grants, choice,
SSH hosts, network and the Ollama catalogue. No framework, no X server.

Plus:

- **PiSugar Whisplay HAT — revision V2 only.** On V1 the button line
  carries 5 V and pressing it can cut power to the board.
- 240×280 ST7789-compatible LCD, WM8960/ES8389 codec, mic, speaker,
  button, RGB LED

Everything board-dependent lives in a single profile table, so adding a
board is one entry rather than a hunt through every module.

## Documentation

- [`docs/DESIGN.md`](docs/DESIGN.md) — architecture, decisions, constraints
- [`docs/HYBRID-PLAN.md`](docs/HYBRID-PLAN.md) — how the three sources fit together
- [`docs/HERKUNFT.md`](docs/HERKUNFT.md) — what is taken from where, and what isn't
- [`docs/research/MOJO.md`](docs/research/MOJO.md) — research: health checks and self-repair (Mojo)
- [`docs/research/ACP.md`](docs/research/ACP.md) and [`ACP-MCP.md`](docs/research/ACP-MCP.md) — research: the Agent Client Protocol and how it differs from MCP
- [`docs/DISPLAYS.md`](docs/DISPLAYS.md) — supported panels and how they are detected
- [`docs/PROVIDER.md`](docs/PROVIDER.md) — model providers, MCP, audio process
- [`docs/CLI.md`](docs/CLI.md) — every command and option, by category (checked by a test)
- [`docs/ROADMAP.md`](docs/ROADMAP.md) — what is missing, by priority
- [`CHANGELOG.md`](CHANGELOG.md) — what has happened

## Licence

MIT — see [LICENSE](LICENSE).
