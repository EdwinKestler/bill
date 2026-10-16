# Prompt for other agents working on the bill

Copy everything below the line into a new agent. Do not start a second Palimnex.

---

You are working in the Agentic Dollars hackathon workspace
`/media/kestl/andor/github/rgbhackathon`. The cash-bill project is
`ideas/bill/` (PlatformIO WEMOS LOLIN32 firmware + Python Bleak dock).

**Palimnex (mandatory lookup, one silo):** run every non-trivial search from the
hackathon **root**, not from `ideas/bill/`.

```bash
cd /media/kestl/andor/github/rgbhackathon
export PALIMNEX_ROOT=/media/kestl/andor/github/rgbhackathon
palimnex status
palimnex search "<exact symbols>" --limit 8
```

Slug `rgbhackathon`, project_id `c1f0cd81-e63c-45d0-afed-a01b5e9ff764`.
Do **not** `palimnex init` under `ideas/bill/`. Bill files are extra corpus in
that cache (`ideas/bill/**`). After edits: `palimnex index --incremental`.
Operator notes: `docs/palimnex.md`. Skill: `.agents/skills/source-cache/SKILL.md`
and `ideas/bill/.agents/skills/source-cache/SKILL.md`.

**Read first:** `ideas/bill/AGENTS.md`, `ideas/bill/docs/DESIGN.md`,
`ideas/bill/docs/PROTOCOL.md`, `ideas/bill/docs/FOLDER.md`.

**RGB:** rgb-lib `0.3.0-beta.7`, Mutinynet, witness receive, out-of-band
consignment, whole-balance `donation=true`. One wallet, one datadir, one
process per bill. Confirmation gate before any spend. Empty transport
endpoints on the tap path.

**Firmware:** VS Code + PlatformIO. Default `platformio.ini` env `esp32-bill`
targets WEMOS LOLIN32 / ESP32-WROOM-32; `oled-test` is the display diagnostic.
Build with `ideas/bill/.venv-platformio/bin/pio run`. BLE patterns from
`/media/kestl/andor/github/waveshares3` (GATT session, notify, write-with-response).
Do not copy locker UUIDs, `0xA4`, barcodes, or relays.
For the planned wearable profile, read
`ideas/bill/docs/TTGO-WATCH-APP-PLAN.md` and inspect the read-only local
T-Watch 2020 V1 reference at
`/media/kestl/xwing/Old_documents/Documents/PlatformIO/Projects/My-TTGO-Watch`.
Keep the dock, rgb-lib, note vault, QVAC, network, and spend confirmation on
the laptop. The watch target keeps only a basic clock/home screen and RGB Bill
app; exclude the other reference apps and phone/network services. Do not edit
or flash the reference tree without a separate human request.

**Dock radio:** `ideas/bill/.venv` + Bleak. `python -m dock.bill_dock scan`.
**Dock web:** `python -m web.server` (http://127.0.0.1:8788/). Python is the
delivery dock language. `web/rust/` is optional rgb-lib native, not a second
wallet process.
**QVAC:** `./install_qvac.sh` fat wheel in `.venv`. Cache `.qvac/`. Instruct
model `QWEN3_600M_INST_Q4` (`python scripts/qvac_fetch_instruct.py`). Smoke
`python scripts/qvac_smoke.py`. Do not pull extra GGUFs unless a human asks.

**Do not** commit or push unless a human asks. Do not flash firmware unless a
human asks. Do not use mainnet seeds.

Skills: `ideas/bill/.agents/skills/bill-firmware/SKILL.md`,
`bill-dock/SKILL.md`, `source-cache/SKILL.md`.

OpenAI 5.6 active delivery prompt (test baseline + Palimnex + implementation):
`ideas/bill/docs/agents-prompt-openai-56.md`.
