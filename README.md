# RGB cash bill

Physical digital dollars. You tell the dock assistant “bill for $5”. The puck
shows $5. You tap it to an empty puck. Value moves between hands. Bitcoin
Mutinynet settles underneath. No QR. No pulling a phone app for the transfer.

This folder is a **git project** nested under the Agentic Dollars workspace
(`rgbhackathon/ideas/bill`). Lookup uses that workspace’s Palimnex — **not** a
second silo. See [docs/LOOKUP.md](docs/LOOKUP.md).

## Humans

The project website is ready for GitHub Pages at the intended address
<https://edwinkestler.github.io/bill/>. Deployment is awaiting an eligible
Pages configuration. Source, local preview, and deployment instructions are
in [site/README.md](site/README.md).

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
.venv/bin/python -m web.server          # http://127.0.0.1:8788/
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
Agent rules: [AGENTS.md](./AGENTS.md).

## Agents

Paste [docs/agents-prompt.md](docs/agents-prompt.md). For OpenAI 5.6 bring-up
(test env + Palimnex): [docs/agents-prompt-openai-56.md](docs/agents-prompt-openai-56.md).
Search Palimnex from `/media/kestl/andor/github/rgbhackathon`. Skills under
`.agents/skills/`.

## Stack

| Layer | Tech |
| --- | --- |
| Bill radio | WEMOS LOLIN32 / ESP32-WROOM-32, Arduino, PlatformIO `esp32-bill` |
| Dock radio | Python 3.10+, Bleak 3.0.2 (`dock/`) |
| Dock desk | Python HTTP + static UI (`web/`, :8788). Rust sidecar optional (`web/rust/`) |
| Settlement | rgb-lib 0.3.0-beta.7, witness + out-of-band consignment, Mutinynet |
| Voice | QVAC `tetherto-qvac-sdk==0.21.0` + `QWEN3_600M_INST_Q4` in `.qvac` |
| BLE cookbook | `/media/kestl/andor/github/waveshares3` (patterns only) |

Firmware boots at `$0.00 / BLE READY` and advertises frozen dock-core v1 plus
implemented chunk-v1 GATT. The read-only state command reports
identity/status/denomination; the fixed display diagnostic and byte-exact
chunk loopback do not touch a wallet. Tap GATT v1 reuses the opaque chunk
frames with deterministic sender/receiver roles, a rising-edge one-shot touch,
and a −60 dBm RSSI gate. Bidirectional two-board transport was physically
accepted on 2026-10-11. The isolated wallet-to-BLE bridge was then live
accepted with a confirmed 20 USDT Mutinynet transfer in both wallet directions:
invoice B→A and exact out-of-band consignment A→B. Web-desk integration is
implemented; browser-driven physical acceptance is the next gate.

The web confirmation path now uses that accepted adapter. It exposes the
immutable RGB plan, requires the typed exact phrase, records the broadcast
before BLE staging, and retains exact artifacts for stage/import-only recovery.
Both role servers pass live startup and balance smoke checks; the first
browser-driven physical transfer is the remaining web acceptance gate.
