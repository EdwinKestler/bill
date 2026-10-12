# AGENTS.md — RGB cash bill

This folder is the bill project. It lives **inside** the hackathon workspace
`/media/kestl/andor/github/rgbhackathon`. Product code for the pucks and docks
stays here until a human moves it to `apps/`.

## Palimnex (one silo)

Use the **parent** cache. Do not create another Palimnex project.

- Root: `/media/kestl/andor/github/rgbhackathon`
- `export PALIMNEX_ROOT` to that root
- `palimnex status` then `palimnex search "…" --limit 8`
- After edits: `palimnex index --incremental` from that root
- Never `palimnex init` here. Never commit `.palimnex/` or `*.pmem`

Full prompt: `docs/LOOKUP.md` and `docs/agents-prompt.md`.
OpenAI 5.6 test-env bring-up: `docs/agents-prompt-openai-56.md`.

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

## Skills

`.agents/skills/source-cache`, `bill-firmware`, `bill-dock`.
