# M0 baseline and evidence map

Captured: 2026-10-15 17:15 CEST
Re-evaluated: 2026-10-15 18:26 CEST
Commit inspected: `303134c8ff153baf509a4f9cdff67d40231a727c`
Network: Mutinynet/custom signet only

This is the pre-change evidence gate for the offline bearer-note work. No
wallet spend, transfer refresh, firmware flash, commit, push, or staged-device
mutation was performed while collecting it.

## Result

The existing direct invoice/consignment flow is preserved and the local
software, firmware, QVAC, wallets, physical bills, public repository, and
GitHub Pages site are in a usable baseline state. Every M0 gate passes. The
human authorized entry into M1 after this re-evaluation.

## Reproducible gates

| Gate | Result | Evidence |
| --- | --- | --- |
| Palimnex parent cache | PASS | Incremental index at `/media/kestl/andor/github/rgbhackathon`; deep validation fresh; 2,769 files, 12,440 chunks, 211,940 edges, 64,663 symbols |
| Python | PASS | `88 passed in 0.16s` |
| Native firmware tests | PASS | 11 tests passed |
| WEMOS firmware build | PASS | `esp32-bill`; RAM 12.5%; flash 39.1% (`1,231,401 / 3,145,728`) |
| TTGO firmware build | PASS | `ttgo-lora32-oled-test`; RAM 12.5%; flash 39.2% (`1,231,897 / 3,145,728`) |
| QVAC local inference | PASS | SDK 0.21.0; cached `QWEN3_600M_INST_Q4` (382,156,480 bytes); GPU/RTX 3090 Ti; output `PRINT 5`; approximately 19.5 ms first token and 379 tokens/s |
| Wallet A | PASS | 50,000,000 base units settled/future/spendable = 50 USDT |
| Wallet B | PASS | 50,000,000 base units settled/future/spendable = 50 USDT |
| RgbBill inventory | PASS | `idle`; denomination `0`; `artifact=empty:empty` |
| RgbBill-TTGO inventory | PASS | `idle`; denomination `0`; `artifact=empty:empty` |
| Repository visibility | PASS | Authenticated and anonymous GitHub metadata report `PUBLIC`; unauthenticated repository API returns HTTP 200 |
| GitHub Pages | PASS | The allowlisted build and deploy jobs passed at commit `303134c`; after the repository rebrand and transfer, the current site is <https://fork2checkbook.github.io/fork2checkbook/> |

## Existing direct-mode RGB evidence

The installed wallets agree that these transport-free RGB transfers are
settled. Wallet A records each as `SEND`; Wallet B records the same transaction
as `RECEIVE_WITNESS`. Each transfer has a durable consignment path and zero RGB
transport endpoints.

| Transaction | Wallet A | Wallet B |
| --- | --- | --- |
| `72b6d753eaf788032cdd72ebd9e0c831380fc4e4c97ef5d66f538e62c5e460de` | settled send | settled witness receive |
| `97885ddffc2305aabf1574d78be8cf102d0afb1f104529c817fc4dcff541a1fb` | settled send | settled witness receive |
| `109d2d24c572d0b74fbd50c1dd2911b3030f0fc963f6018916397d9891b650e3` | settled send | settled witness receive |
| `1f8953866f24f5b64ec02875aa51507fc6c76777646680eddfb573247cf5d45f` | settled send | settled witness receive |

Wallet A also records the original 100 USDT faucet receive as settled at
`921614229c1420fa75bf4f2f5aeb3a925b705a1b4a99f4797b5218fc121c3f85`.

## Historical non-settled rows

Wallet A has two and Wallet B has five `WAITING_COUNTERPARTY` witness-receive
rows. Every one is an unused, transport-free invoice whose expiration is in the
past. They have no txid and no consignment. They are historical cleanup debt,
not an ambiguous broadcast, retained consignment, or locked recovery state.

Do not reuse those invoices. M1 must create fresh note-wallet and final-wallet
invoices at the prescribed state transitions.

## Physical and process inventory

- `RgbBill` — `30:AE:A4:07:2D:2E`, identity `bill-unprovisioned`, empty and
  idle at the current read-only inventory.
- `RgbBill-TTGO` — `30:AE:A4:4C:B1:6A`, identity
  `bill-ttgo-v1.3-test`, empty and idle at the current read-only inventory.
- Both expected USB serial adapters are present.
- No dock web server or rgb-lib wallet process was running during wallet
  inspection.
- Existing serial monitor processes were left untouched.

## Worktree boundary

The current worktree contains preserved documentation and dock-visual changes
outside the published Pages commit:

```text
M  AGENTS.md
M  README.md
M  docs/DESIGN.md
M  docs/agents-prompt-openai-56.md
M  docs/agents-prompt.md
M  web/README.md
M  web/static/app.css
M  web/static/app.js
M  web/static/index.html
?? docs/OFFLINE-RGB-DEMO-DESIGN.md
?? docs/agents-prompt-offline-note.md
?? docs/spikes/
?? pytests/test_web_static.py
```

Those files were preserved and were not included in the Pages publication
commit.

## M1 entry boundary

M0 is closed locally. The human authorized entry into M1 on 2026-10-15 after
all current gates passed. M1 may implement and test the disposable-wallet spike
with fake backends and prepare immutable Mutinynet plans. No live funding or
redemption broadcast is authorized by this report. Each live spend still
requires its own displayed plan and exact `CONFIRM <plan-id>` response.
