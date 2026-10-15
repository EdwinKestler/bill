# RGB cash bill

Physical digital dollars. A dock funds a disposable $5 RGB note, an ESP32 bill
carries its compact bearer capability, and one tap relays that capability to
another bill with both docks and the Internet unavailable. The final holder
later redeems into a wallet that was unknown when the note was created.
Bitcoin Mutinynet anchors the two real RGB transitions. No QR and no phone app
are required for the offline handoff.

## Hackathon delivery mode

The organizers authorized final-project work on 2026-10-15; this repository is
in active delivery, not planning-only or waiting for Saturday. The submission
must remain transparent about prior work and must be publicly visible to the
judges. Verify repository visibility without credentials before submission;
publishing the website alone does not make a private source repository public.

Official scoring is RGB 25%, local QVAC 20%, execution 20%, UX/UI 15%,
innovation 10%, and marketability 10%. A meaningful WDK integration can add up
to one bonus point. The priority is therefore a clear live RGB + QVAC flow;
WDK follows only if that primary path is stable.

Project/team working name: **RGB Cash Bill**. Repository owner:
**Edwin Kestler ([EdwinKestler](https://github.com/EdwinKestler))**.

### Declared pre-start baseline

The existing Git history is intentional prior-work evidence. Before the final
delivery phase, the repository already contained:

- two ESP32 bill profiles with OLED, touch, BLE inventory, chunking, and tap;
- two isolated rgb-lib Mutinynet wallets and confirmed witness/OOB transfers;
- a confirmation-gated Python web dock with retained-artifact recovery;
- a prepared project website and local QVAC installation/smoke tooling.

QVAC was not yet the accepted user-facing intent layer, WDK was not integrated,
and anonymous multi-hop offline bearer circulation was not implemented. Final
submission documentation must keep implemented, trusted prototype, and future
work clearly separated.

### Current verified deliverable

The bearer-note vertical slice is now live accepted on Mutinynet:

1. Wallet A funded a fresh isolated note wallet N with exactly 5 USDT.
2. Dock A loaded a 603-byte bearer capsule onto WEMOS.
3. WEMOS relayed it to TTGO over local BLE; TTGO persisted it across restart.
4. The destination dock extracted the same SHA-256 and only then created
   Wallet B's fresh transport-free redemption invoice.
5. One exact confirmation authorized one note-wallet redemption broadcast.
6. Wallet B imported the 15,057-byte consignment and settled from 50 to 55
   USDT. The note state is durably `REDEEMED`; its bearer claim is `SPENT`.

The offline hop moves a **bearer capability**, not an RGB state transition.
The two actual RGB transitions are Wallet A → note wallet N and note wallet N
→ Wallet B. The trusted note vault retains N's keys, so this is explicitly a
Mutinynet trusted-custody prototype with first-redemption-wins copy risk—not a
production bearer instrument or an offline double-spend solution.

This folder is a **git project** nested under the Agentic Dollars workspace
(`rgbhackathon/ideas/bill`). Lookup uses that workspace’s Palimnex — **not** a
second silo. See [docs/LOOKUP.md](docs/LOOKUP.md).

## Humans

The public project website is deployed at
<https://edwinkestler.github.io/bill/>. Source, local preview, and deployment
instructions are in [site/README.md](site/README.md).

1. Open **this folder** in VS Code (`File → Open Folder` on `ideas/bill`).
2. Install the **PlatformIO IDE** extension (prompted via `.vscode/extensions.json`).
3. From a terminal in this folder:

```bash
./install_python.sh
./install_qvac.sh                       # fat linux-x64 QVAC wheel; no GGUF
./install_platformio.sh
.venv-platformio/bin/pio run
.venv/bin/python -m dock.bill_dock scan
.venv/bin/python -m dock.bill_dock identity
.venv/bin/python -m dock.bill_dock state
.venv/bin/python -m dock.bill_dock diagnostic
.venv/bin/python -m dock.bill_dock chunk-loopback --address ADDRESS --kind invoice --input PATH
.venv/bin/python -m web.server          # role host/port from .env
.venv/bin/python scripts/qvac_smoke.py  # worker + GPU flags, no model download
.venv/bin/python scripts/qvac_fetch_instruct.py  # QWEN3_600M_INST_Q4 → .qvac
```

Copy `.env.example` to `.env` for dock roles. Mutinynet only.

Design: [docs/DESIGN.md](docs/DESIGN.md). Diagrams:
[docs/diagrams/README.md](docs/diagrams/README.md). Folders:
[docs/FOLDER.md](docs/FOLDER.md). Two-board tap acceptance:
[docs/TAP-GATT-TEST.md](docs/TAP-GATT-TEST.md).
Real wallet tap acceptance: [docs/RGB-TAP-LIVE.md](docs/RGB-TAP-LIVE.md).
Web RGB acceptance: [docs/WEB-RGB-TEST.md](docs/WEB-RGB-TEST.md).
Offline bearer-note decision and proof plan:
[docs/OFFLINE-RGB-DEMO-DESIGN.md](docs/OFFLINE-RGB-DEMO-DESIGN.md).
Accepted bearer-note operator sequence:
[docs/OFFLINE-BEARER-RUNBOOK.md](docs/OFFLINE-BEARER-RUNBOOK.md).
Canonical transaction and acceptance ledger:
[docs/LIVE-EVIDENCE.md](docs/LIVE-EVIDENCE.md). Threat model:
[docs/THREAT-MODEL.md](docs/THREAT-MODEL.md).
Agent rules: [AGENTS.md](./AGENTS.md).

## Agents

Paste [docs/agents-prompt.md](docs/agents-prompt.md). For OpenAI 5.6 bring-up
(test env + Palimnex): [docs/agents-prompt-openai-56.md](docs/agents-prompt-openai-56.md).
For the Sunday offline bearer-note build, use
[docs/agents-prompt-offline-note.md](docs/agents-prompt-offline-note.md).
Search Palimnex from `/media/kestl/andor/github/rgbhackathon`. Skills under
`.agents/skills/`.

## Stack

| Layer | Tech |
| --- | --- |
| Bill radio | WEMOS LOLIN32 / ESP32-WROOM-32, Arduino, PlatformIO `esp32-bill` |
| Dock radio | Python 3.10+, Bleak 3.0.2 (`dock/`) |
| Dock desk | Python HTTP + static UI (`web/`, :8788). Rust sidecar optional (`web/rust/`) |
| Bearer note vault | One ignored rgb-lib datadir and mnemonic per disposable note; one-shot recovery journal |
| Settlement | rgb-lib 0.3.0-beta.7, witness + out-of-band consignment, Mutinynet |
| Voice | QVAC `tetherto-qvac-sdk==0.21.0` + `QWEN3_600M_INST_Q4` in `.qvac` |
| BLE cookbook | `/media/kestl/andor/github/waveshares3` (patterns only) |

Firmware boots at `EMPTY / BLE READY` with no numeric amount and advertises frozen dock-core v1 plus
implemented chunk-v1 GATT. The read-only state command reports
identity/status/denomination; the fixed display diagnostic and byte-exact
chunk loopback do not touch a wallet. Tap GATT v1 reuses the opaque chunk
frames with deterministic sender/receiver roles, a rising-edge one-shot touch,
and a −60 dBm RSSI gate. Bidirectional two-board transport was physically
accepted on 2026-10-11. The isolated wallet-to-BLE bridge was then live
accepted with a confirmed 20 USDT Mutinynet transfer in both wallet directions:
invoice B→A and exact out-of-band consignment A→B. Web-desk integration is
implemented. The human-first inventory-v2 browser flow was physically accepted
on both boards on 2026-10-15 with a settled $5 Mutinynet transfer
(`1f8953866f24f5b64ec02875aa51507fc6c76777646680eddfb573247cf5d45f`).

The web confirmation path now uses that accepted adapter. It exposes the
immutable RGB plan, requires the typed exact phrase, records the broadcast
before BLE staging, and retains exact artifacts for stage/import-only recovery.
Both role servers pass live startup, LAN/localhost binding, balance refresh,
and browser-driven physical transfer acceptance checks.

The newer offline bearer path is currently an accepted operator CLI and
firmware workflow, not yet a public web endpoint. Its funding txid is
`b325cbe40c282e661c40ff8555cb6cb0fc9867a32855feb8b17d7756c9a83963`;
its redemption txid is
`dfe138b0983f6238103d2e5c57bf0848fdd5b7fd733162299fb4c6e5e9f427bf`.
At the recorded settlement check the redemption had 11 confirmations and
Wallet B showed 55,000,000 settled/future/spendable units. Local QVAC model
execution is verified but typed-intent integration and evaluation remain open.
WDK is not integrated.
