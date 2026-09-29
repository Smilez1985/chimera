# Chimera

**An agentic harness with a face it builds itself — and a voice you can talk to.**

Chimera is an AI agent that runs on a Raspberry Pi with a
[PiSugar Whisplay HAT](https://github.com/PiSugar/Whisplay). It has a colour
LCD, a microphone, a speaker, a button and an RGB LED — and it uses all of
them to show what it is actually doing.

> Status: **pre-alpha.** Nothing is tagged, nothing is released. The design
> documents come first; see `docs/DESIGN.md`.

---

## The idea

Most agent frontends show you a spinner. Chimera shows you a face.

Not a canned set of emoticons, though — Chimera **generates its own
expressions**. Faces are declarative asset definitions (colour, eye shape,
mouth style, physics, particles), and the agent writes, mixes and varies
them itself as it needs them. Over weeks it accumulates a repertoire that
no one designed.

The state it shows is real state:

| What's happening | What you see |
|---|---|
| listening | attentive face, blue LED |
| thinking | particles rising |
| speaking | animated mouth, voice emotion matches the face |
| stuck in a tool loop | visibly agitated, red LED |
| context nearly full | tired eyes |
| CPU hot | tired eyes |

An agent that looks nervous when it gets stuck is the most honest status
display you can build.

## Voice, fully offline

Speech recognition, synthesis, voice activity detection and wake-word
spotting all run locally via [sherpa-onnx](https://github.com/k2-fsa/sherpa-onnx).
No cloud speech service, no per-request billing, nothing leaves the device.

German TTS uses `thorsten_emotional`, a voice with emotion variants — so
the voice carries the same mood as the face.

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

- Raspberry Pi Zero 2 W or Pi 5
- **PiSugar Whisplay HAT — revision V2 only.** On V1 the button line
  carries 5 V and pressing it can cut power to the board.
- 240×280 ST7789-compatible LCD, WM8960/ES8389 codec, mic, speaker,
  button, RGB LED

## Documentation

- [`docs/DESIGN.md`](docs/DESIGN.md) — architecture, decisions, constraints
- [`docs/ROADMAP.md`](docs/ROADMAP.md) — what is missing, by priority
- [`CHANGELOG.md`](CHANGELOG.md) — what has happened

## Licence

MIT — see [LICENSE](LICENSE).
