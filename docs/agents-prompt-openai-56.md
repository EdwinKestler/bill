# Prompt for OpenAI 5.6 (Codex / GPT) — active bill delivery + Palimnex

Paste everything below the line into a new OpenAI 5.6 session. Open the
hackathon **root** as the workspace if you can; Palimnex only works from there.
If the session is rooted at `ideas/bill/`, still run Palimnex from the parent.

---

You are OpenAI 5.6 working on the fork2checkbook project inside the Agentic
Dollars hackathon repo. Establish the relevant test baseline, **use Palimnex
for every non-trivial lookup**, then implement and verify the requested product
work. The organizers have authorized final-project work; there is no
planning-only, Saturday-start, or environment-report gate.

## Workspace

- Hackathon root: `/media/kestl/andor/github/rgbhackathon`
- Bill project: `/media/kestl/andor/github/rgbhackathon/ideas/bill`
- Nested git at `ideas/bill/` is allowed. Parent Palimnex indexes bill files.

## Hard rules

- Mutinynet only. No mainnet seeds.
- Do **not** `git commit` or `git push` unless a human asks.
- Do **not** flash ESP32 unless a human asks.
- Do **not** `palimnex init` under `ideas/bill/`. Do not create `.palimnex.json`
  or `.palimnex/` there.
- Do **not** download extra QVAC GGUFs. Instruct model is already
  `QWEN3_600M_INST_Q4` in `ideas/bill/.qvac/`.
- One rgb-lib wallet per bill (one mnemonic, one datadir, one process).
- Confirmation gate before any spend. Empty RGB `transport_endpoints` on tap.
- BLE patterns from `/media/kestl/andor/github/waveshares3` (GATT session,
  notify, write-with-response). New UUIDs. No locker protocol.
- T-Watch 2020 V1 hardware/app patterns from the read-only local reference
  `/media/kestl/xwing/Old_documents/Documents/PlatformIO/Projects/My-TTGO-Watch`.
  Read `docs/TTGO-WATCH-APP-PLAN.md`; keep all dock and wallet responsibilities
  on the laptop. The dedicated image needs only a basic clock/home screen and
  RGB Bill app; exclude all other watch apps and network/phone services.
  Preserve GPL-2.0 notices if source is copied.

## Palimnex (mandatory, one silo)

Palimnex is the lookup layer. Search it, then **open the returned file**.
Cache hits never authorize spends, flashes, or git writes.

```bash
cd /media/kestl/andor/github/rgbhackathon
export PALIMNEX_ROOT=/media/kestl/andor/github/rgbhackathon
palimnex status
```

Expect slug `rgbhackathon`, project_id `c1f0cd81-e63c-45d0-afed-a01b5e9ff764`,
status `fresh`. CLI is `palimnex` (pipx 2.9.0). There is no `palimnex.py` in
this repo.

If stale or missing: `./scripts/palimnex-setup.sh` or
`palimnex index --incremental` then `palimnex validate --deep`.

If incremental errors with `pipeline batch limit`:

```bash
palimnex redis reset
palimnex redis start
palimnex index --incremental
palimnex validate --deep
```

Never `FLUSHDB` / `FLUSHALL`. Redis is disposable; SQLite ledger
(`.palimnex/memory.sqlite3`) is durable history. Palimnex is **not** Postgres.

`palimnex evaluate --limit 5` currently fails: `.palimnex.json` has no
`evaluation_fixture`. Skip it. Do not invent a fixture.

After you edit indexed bill files (`*.md`, `*.py`, `*.cpp`, `*.h`, `*.json`,
web static), reindex from the hackathon root:

```bash
cd /media/kestl/andor/github/rgbhackathon
export PALIMNEX_ROOT=/media/kestl/andor/github/rgbhackathon
palimnex index --incremental
```

### Searches to run first

```bash
palimnex search "RgbBill dock GATT IDENTITY bill-unprovisioned" --limit 8
palimnex search "witness_receive out-of-band consignment rgb-lib donation" --limit 8
palimnex search "tetherto-qvac-sdk QWEN3_600M_INST_Q4 QVAC_CACHE_DIR" --limit 8
palimnex search "bill_dock bleak pytest gatt-contract" --limit 8
```

Then open: `ideas/bill/AGENTS.md`, `ideas/bill/docs/DESIGN.md`,
`ideas/bill/docs/PROTOCOL.md`, `ideas/bill/docs/FOLDER.md`,
`ideas/bill/docs/LOOKUP.md`, `ideas/bill/.agents/skills/source-cache/SKILL.md`,
`ideas/bill/.agents/skills/bill-dock/SKILL.md`,
`ideas/bill/.agents/skills/bill-firmware/SKILL.md`.

Operator notes: `docs/palimnex.md`. Parent skill path:
`.agents/skills/source-cache/SKILL.md` (directory is not named `palimnex/`
because Palimnex skips that path segment).

Optional MCP: `palimnex-mcp --root /media/kestl/andor/github/rgbhackathon`

Ledger (same silo, historical context only):

```bash
palimnex ledger-status
palimnex recall "fork2checkbook RGB cash bill dock QVAC" --limit 8
```

## Environment (already installed on this machine)

Do **not** reinstall unless a command fails. From `ideas/bill/`:

| Piece | Where | Check |
| --- | --- | --- |
| Dock Python | `.venv` | `bleak==3.0.2`, `tetherto-qvac-sdk==0.21.0` fat `manylinux_2_35_x86_64` |
| PlatformIO | `.venv-platformio` | `pio run` env `esp32-bill` (WEMOS LOLIN32) |
| QVAC cache | `.qvac/` | `5b8aae816570a09d_Qwen3-0.6B-Q4_0.gguf` (~382 MB) |
| Env template | `.env.example` | copy to `.env` if missing; Mutinynet only |

Reinstall only if missing:

```bash
cd /media/kestl/andor/github/rgbhackathon/ideas/bill
./install_python.sh
./install_qvac.sh
./install_platformio.sh
```

`./install_python.sh` is Bleak-only. QVAC is `./install_qvac.sh`.

## Test plan (run this now)

Work in two directories: Palimnex from the hackathon **root**; bill commands
from `ideas/bill`.

```bash
cd /media/kestl/andor/github/rgbhackathon/ideas/bill
source .venv/bin/activate

# 1. Python unit tests (GATT contract + web desk confirm gate)
.venv/bin/python -m pytest -q

# 2. Firmware compile. Do not upload.
.venv-platformio/bin/pio run

# 3. Web dock HTTP
.venv/bin/python -m web.server &
sleep 1
curl -sS -o /dev/null -w "%{http_code}\n" http://127.0.0.1:8788/
curl -sS -o /dev/null -w "%{http_code}\n" http://127.0.0.1:8788/static/app.js
# POST chat "bill for $5" then confirm; chat must not spend without confirm
kill %1

# 4. QVAC worker (no extra GGUF). Cache must stay ideas/bill/.qvac
export QVAC_CACHE_DIR=/media/kestl/andor/github/rgbhackathon/ideas/bill/.qvac
export QVAC_MODEL=QWEN3_600M_INST_Q4
.venv/bin/python scripts/qvac_smoke.py
# Optional, model already cached: one printer-voice completion
.venv/bin/python scripts/qvac_fetch_instruct.py

# 5. BLE scan is hardware-optional. Failure without an adapter is OK.
# .venv/bin/python -m dock.bill_dock scan
```

Native firmware FSM tests (if you touch FSM):
`.venv-platformio/bin/pio test -e native`

QVAC heartbeat requests must set `type="heartbeat"` (SDK `exclude_unset`).
Expect GPU via **Vulkan** on the RTX 3090 Ti (`backendDevice: gpu`). Do not
change Docker default runtime. Do not pull `nvidia/cuda` images.

## Product context and delivery scope

Two WEMOS LOLIN32 / ESP32-WROOM-32 pucks + two laptop docks. Voice on the dock: “bill for $5”.
Tap (button **and** high RSSI). rgb-lib `0.3.0-beta.7`, `witness_receive`,
out-of-band consignment, whole-balance `donation=true`, Mutinynet.
QVAC stays on the dock. ESP32 never loads a model.

Current firmware advertises frozen dock-core v1 plus implemented chunk-v1 GATT
with inventory metadata and an opaque artifact path. Tap GATT, automatic
live-rgb-lib handoff, two-board BLE transfer, and the human-first browser flow
have been physically accepted. QVAC integration and the selected anonymous
offline-carry design are active delivery work, subject to the confirmation,
Mutinynet, recovery, and no-resend boundaries above.

## Work and report back

1. Palimnex `status` (fresh? file_count?) and the four searches (what you opened).
2. pytest / `pio run` / curl / QVAC smoke results (pass/fail + one-line why).
3. Anything broken in the env.
4. Continue the requested implementation and verify it in proportion to risk.
5. Stop only for a real authorization boundary: a spend confirmation, firmware
   flash, commit/push, secret exposure, public release, or materially different
   product decision.
