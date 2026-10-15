# AGENTS.md — RGB cash bill

This folder is the bill project and its submission repository. It lives
**inside** the hackathon workspace `/media/kestl/andor/github/rgbhackathon`,
but product code for the bills and docks remains here; do not wait for a move
to `apps/` before implementing the final product.

## Active delivery authorization

The organizers gave the team approval on 2026-10-15 to begin final-project
work before the scheduled on-site clock, provided the project is kept in the
public submission repository and all prior work is declared. There is no
Saturday start gate, planning-only gate, or environment-report gate for work
in this folder. Continue safe implementation, testing, documentation, and live
Mutinynet acceptance whenever a human requests the work.

Optimize the Sunday deliverable against the official scorecard:

- RGB 25%: real, non-trivial RGB behavior in the product.
- QVAC 20%: local AI performs a necessary user-facing job.
- Execution 20%: the primary flow works live end to end.
- UX/UI 15%: a non-technical user understands each action and error.
- Innovation 10% and marketability 10%.
- WDK is optional and may add up to one bonus point.

The repository must be publicly visible for judging. Verify visibility without
GitHub credentials before submission; a public Pages site alone is not proof
that the source repository is public.

## Palimnex (one silo)

Use the **parent** cache. Do not create another Palimnex project.

- Root: `/media/kestl/andor/github/rgbhackathon`
- `export PALIMNEX_ROOT` to that root
- `palimnex status` then `palimnex search "…" --limit 8`
- After edits: `palimnex index --incremental` from that root
- Never `palimnex init` here. Never commit `.palimnex/` or `*.pmem`

Full prompt: `docs/LOOKUP.md` and `docs/agents-prompt.md`.
OpenAI 5.6 active delivery prompt: `docs/agents-prompt-openai-56.md`.
Offline bearer-note delivery prompt: `docs/agents-prompt-offline-note.md`.
Its design decision and ranked fallbacks are in
`docs/OFFLINE-RGB-DEMO-DESIGN.md`.

## What we are building

Two ESP32 bills + two laptop docks. Voice on the dock prints a $5 note. Tap
two bills (button + high RSSI). RGB witness transfer, consignment over BLE,
Mutinynet settles. No QR, no phone-app UI for the tap.

Read `docs/DESIGN.md` then `docs/PROTOCOL.md`.

## Tooling

- VS Code + PlatformIO IDE (recommended extension in `.vscode/extensions.json`)
- Firmware: `.venv-platformio/bin/pio run` (env `esp32-bill`). WEMOS LOLIN32 on
  `/dev/serial/by-id/usb-Silicon_Labs_CP2104_USB_to_UART_Bridge_Controller_014BCF94-if00-port0`
  (env `oled-test` remains the standalone OLED diagnostic).
- Dock radio: `.venv` + `python -m dock.bill_dock scan`
- Dock web: `.venv` + `python -m web.server` → http://127.0.0.1:8788/
- First install: `./install_python.sh`, `./install_qvac.sh`, `./install_platformio.sh`
- QVAC: fat wheel `tetherto-qvac-sdk==0.21.0` in `.venv`. Cache `QVAC_CACHE_DIR` → `.qvac/`. Instruct: `QWEN3_600M_INST_Q4` via `python scripts/qvac_fetch_instruct.py`. Smoke: `python scripts/qvac_smoke.py`. Do not pull extra GGUFs.

## Hard rules

- Mutinynet only
- One rgb-lib wallet per bill (one mnemonic, one datadir, one process)
- Confirmation gate before spends
- Empty RGB transport endpoints on the tap; no Wi‑Fi consignment cheat
- BLE patterns from `/media/kestl/andor/github/waveshares3`; new GATT; no locker code
- Do not commit, push, or flash unless a human asks

These rules protect funds, devices, secrets, and repository history. They are
not instructions to delay ordinary product implementation.

## Skills

`.agents/skills/source-cache`, `bill-firmware`, `bill-dock`.
