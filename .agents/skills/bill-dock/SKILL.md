---
name: bill-dock
description: Laptop dock for an RGB cash bill. Bleak GATT, Python web desk on :8788, rgb-lib-python, QVAC printer voice. Use when changing dock Python, web/server.py, static UI, scanning RgbBill, chunked consignment, witness receive. Triggers: dock, bleak, bill_dock, web dock, /bill-dock.
---

# Bill dock

Python env: `ideas/bill/.venv` (`./install_python.sh`). Runtime: `bleak==3.0.2`.
QVAC: `./install_qvac.sh` → `tetherto-qvac-sdk==0.21.0` fat linux-x64 wheel.
Cache: `QVAC_CACHE_DIR` (default `ideas/bill/.qvac`). Instruct GGUF:
`QWEN3_600M_INST_Q4` via `python scripts/qvac_fetch_instruct.py`.
Smoke (no download): `python scripts/qvac_smoke.py`.

```bash
source .venv/bin/activate
python -m dock.bill_dock scan
python -m web.server
```

Web desk is `web/` (Python HTTP + `static/`). Optional Rust rgb-lib sidecar is
`web/rust/` only if wheels fail. One process per datadir.

- One dock process per bill. `BILL_ROLE=A` or `B` in `.env` (from `.env.example`).
- rgb-lib `0.3.0-beta.7`, Mutinynet, `witness_receive` for empty bills,
  out-of-band consignment, whole-balance `donation=true`.
- Empty `transport_endpoints` on the tap path. Docks do not send consignments
  over Wi‑Fi.
- Confirmation gate before any spend. One mnemonic, one `RGB_DATA_DIR`, one process.
- QVAC stays on the dock. The ESP32 never loads a model.

Palimnex from the hackathon root. Skill `source-cache`.
