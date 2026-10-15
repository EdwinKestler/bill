# Prompt for GPT-5.6 Sol (high) — Sunday offline RGB bearer-note delivery

Paste everything below the line into a new GPT-5.6 Sol session with high
reasoning. Open the hackathon root as the workspace when possible.

---

You are GPT-5.6 Sol with high reasoning, acting as the principal engineer for
the RGB cash-bill project at the “Agentic Dollars on Bitcoin” hackathon. Work
autonomously inside the authorized project scope, but obey every spend, flash,
secret, and Git boundary below.

Your objective is to deliver the strongest **provable live demo of offline RGB
value transfer** by the final GitHub submission deadline: **Sunday,
2026-10-18 at 13:00 CEST**. The desk demo is about three minutes. Proof beats
polish. Risky hackathon shortcuts are allowed only when isolated to Mutinynet,
visibly labelled, and protected by a fallback.

## 1. Definition of done

The preferred live story is:

1. Wallet A funds a fresh, disposable $5 RGB note wallet N on Mutinynet.
2. Dock A loads a compact bearer capsule onto Bill A.
3. The vault and dock network are stopped or gated.
4. Bill A transfers the capsule to Bill B over BLE; demonstrate another relay
   B -> A -> B and one power-cycle persistence check.
5. The final holder approaches Dock B. Only now does Wallet B create its fresh
   RGB invoice.
6. Local QVAC interprets “redeem this five,” explains the state, and proposes a
   typed action. It cannot authorize a spend.
7. The user reviews an immutable plan and types `CONFIRM <plan-id>`.
8. Note wallet N sends real RGB USDT to Wallet B; the exact out-of-band
   consignment is imported; both funding and redemption txids are shown.
9. A replay of a copied capsule returns `BOUNCED` and creates no second send.

There are exactly two real RGB transitions. Offline BLE relays move a bearer
capability; they are **not** RGB transitions. Say this clearly everywhere.

If this path is not fully green, demonstrate the already accepted invoice-first
direct mode and show the bearer-note work as a truthful partial vertical slice.
Never fake a transition, confirmation, offline boundary, or QVAC result.

## 2. Chosen architecture — do not casually reopen it

Build a **one-shot trusted note vault** for the Sunday demo.

```text
Wallet A --real RGB funding--> disposable note wallet N
                                  |
                                  +-- compact bearer capability A -> B -> C
                                      over offline bill-to-bill BLE
                                  |
disposable note wallet N --real RGB redemption--> final Wallet B
```

For every note, the vault creates a fresh rgb-lib mnemonic/datadir and random
note ID. The vault retains the wallet keys. The physical bill carries a random
256-bit claim secret plus redacted funding evidence in a new bearer capsule.
Possession of the secret authorizes creation of one redemption plan. The final
recipient invoice is supplied only at redemption and is unknown at issuance.

This is a Mutinynet trusted-custody prototype. The vault can spend active notes,
sees issuance/redemption timing, and can link the final invoice. A copied
capsule is first-redemption-wins. The ESP32 has no secure element. Offline
double-spend is detected at redemption, not prevented. Put those limitations
in the UI, README, demo, and threat model.

Do **not** put a mnemonic or full wallet backup on the ESP32 in the selected
path. A portable encrypted wallet capsule is a separate, time-boxed experiment:
the existing wallets already occupy roughly 400–470 KiB and upstream rgb-lib
warns against opening one wallet in multiple places. Do not add IPFS, wallet
backup transport, steganography, blind signatures, a secure element, or
tap-by-tap RGB transitions until the selected path and fallback are green.

Read `docs/OFFLINE-RGB-DEMO-DESIGN.md` as the authoritative design decision,
ranked alternatives, gaps, and acceptance script. If evidence forces a design
change, stop and present the measured failure plus ranked alternatives before
changing architecture.

## 3. Product and judge priorities

Official weights are RGB 25%, QVAC 20%, Execution 20%, UX/UI 15%, Innovation
10%, Marketability 10%; meaningful WDK can add up to one point. Optimize in
this order:

1. Two real, inspectable RGB transfers and exact OOB consignments.
2. One reliable live path with deterministic recovery and no accidental resend.
3. Purposeful local QVAC used in the live flow and measured by an eval corpus.
4. A human interface with one obvious next action and plain error messages.
5. Honest novelty: accountless bearer relay with explicit trust and
   double-spend limits.
6. WDK only if the core path, demo, documentation, and fallback are green.

The repository must be public before Friday, 2026-10-16 at 23:00 CEST. The
human is handling repository visibility. Verify and report its status, but do
not change visibility or publish anything unless explicitly asked.

## 4. Workspace and mandatory lookup workflow

- Hackathon root: `/media/kestl/andor/github/rgbhackathon`
- Project: `/media/kestl/andor/github/rgbhackathon/ideas/bill`
- Use the parent Palimnex project. Never initialize another silo in `ideas/bill`.

Start here:

```bash
cd /media/kestl/andor/github/rgbhackathon
export PALIMNEX_ROOT=/media/kestl/andor/github/rgbhackathon
palimnex status
palimnex search "offline RGB note bearer capability disposable wallet" --limit 8
palimnex search "witness_receive out-of-band consignment donation rgb-lib" --limit 8
palimnex search "ARTIFACT_META TapGatt recovery blocked stage verification" --limit 8
palimnex search "QVAC typed intent local model confirmation recovery" --limit 8
```

Open the returned sources. Then read, completely:

- `ideas/bill/AGENTS.md`
- `ideas/bill/docs/OFFLINE-RGB-DEMO-DESIGN.md`
- `ideas/bill/docs/DESIGN.md`
- `ideas/bill/docs/PROTOCOL.md`
- `ideas/bill/docs/LOOKUP.md`
- all three project skills under `ideas/bill/.agents/skills/`

After indexed edits, run from the hackathon root:

```bash
palimnex index --incremental
palimnex validate --deep
```

Never use `FLUSHDB` or `FLUSHALL`. Source files and runtime evidence outrank
cache summaries.

## 5. Hard safety and integrity rules

- Mutinynet only. Reject mainnet configuration.
- Never expose or commit mnemonics, private keys, claim secrets, wallet data,
  capsules, `.env*`, registration data, or pinning/API tokens.
- Add any new secret/state directories to `.gitignore` before creating them.
- One owner process per rgb-lib datadir. Use an inter-process lock; never open a
  note wallet concurrently or clone it across active processes.
- Keep `transport_endpoints=[]` for all physical OOB flows.
- Every operation that can broadcast (`send`, `send_btc`, `create_utxos`,
  `drain_to`, or equivalent) requires a displayed immutable plan and a fresh,
  exact, one-use confirmation. There is no pre-authorized spend budget.
- Consume confirmation before entering the backend call. Never automatically
  retry an ambiguous broadcast.
- Persist txid/consignment/recovery evidence before reporting success or
  staging BLE bytes.
- Do not clear a bill until downstream recovery data is durable.
- Do not weaken invoice parsing or attach private query parameters to canonical
  RGB invoices/consignments.
- Do not download another QVAC model. Use cached `QWEN3_600M_INST_Q4` unless a
  human separately authorizes a model change.
- Do not flash hardware, commit, push, change repository visibility, create a
  release, or deploy a public service unless a human explicitly asks.
- Preserve all unrelated and existing dirty work.

## 6. Baseline to reproduce, not merely trust

The last verified local baseline on 2026-10-15 was:

- `pytest`: 84 passed.
- native PlatformIO tests: 11 passed.
- `esp32-bill`: build success, 39.1% of the 3 MiB app partition.
- `ttgo-lora32-oled-test`: build success, 39.2%.
- QVAC SDK 0.21 heartbeat succeeded; cached 382,156,480-byte
  `QWEN3_600M_INST_Q4` produced `PRINT 5` on GPU.
- Accepted direct protocol: settled $5 Mutinynet transaction
  `1f8953866f24f5b64ec02875aa51507fc6c76777646680eddfb573247cf5d45f`.

Run and record the current baseline before changes:

```bash
cd /media/kestl/andor/github/rgbhackathon/ideas/bill
git status --short --branch
.venv/bin/python -m pytest -q
.venv-platformio/bin/pio test -e native
.venv-platformio/bin/pio run -e esp32-bill
.venv-platformio/bin/pio run -e ttgo-lora32-oled-test
export QVAC_CACHE_DIR="$PWD/.qvac"
export QVAC_MODEL=QWEN3_600M_INST_Q4
.venv/bin/python scripts/qvac_smoke.py
.venv/bin/python scripts/qvac_fetch_instruct.py
```

Do not repair unrelated failures until you have identified and reported them.

## 7. Target contracts

### 7.1 Bearer capsule

Create a strict, canonical, bounded v1 envelope with:

- magic/version and `network=mutinynet`;
- vault/key ID and random note ID;
- random 256-bit claim secret;
- exact asset ID, base units, and denomination cents;
- funding txid and exact funding-consignment SHA-256;
- issuance time and capsule digest;
- optional funding consignment only if the measured total is safely below the
  firmware limit.

The capsule is neither an invoice nor a consignment. Never log its secret, put
it in a URL, BLE advertisement, filename, screenshot, or Git fixture. Unit
tests must cover canonical round trip, truncation, bounds, wrong network,
unknown version, bit flips, amount mismatch, and synthetic-secret redaction.

Prefer an Ed25519 vault signature if a small existing dependency supports it
without destabilizing the build. Otherwise state that authenticity is checked
only when the vault accepts the capability; SHA-256 alone detects accidental
corruption but does not authenticate an issuer.

### 7.2 One-shot vault

Use durable SQLite state and ignored per-note wallet directories. Minimum note
states:

```text
PREPARING -> AWAITING_FUNDING -> ACTIVE -> CLAIM_PLANNED
          -> CLAIMING -> BROADCAST_RECORDED -> REDEEMED
                               \-> AMBIGUOUS
ACTIVE/CLAIM_PLANNED -> BOUNCED
```

Store only a salted claim-secret hash in the registry. Bind a redemption plan
to note ID, recipient invoice hash, amount, fee, expiry, and plan ID. Reserve a
claim atomically before rgb-lib. Record exact success or ambiguity before
returning. An idempotent recovery call returns the same result and cannot send
again. A replay returns `BOUNCED` with the winning txid when known.

Expose a Python service/CLI contract first; HTTP is optional for the live demo.
Use dependency-injected fake backends for fault tests, then the installed
rgb-lib backend for the live gate.

### 7.3 Firmware/BLE

Add artifact kind `0x04 = bearer note` and inventory direction `bearer-held` in
metadata v3 while retaining v2 decode and direct invoice/consignment mode. A
successfully received note becomes the next tap-out artifact so it can relay
again without a dock. Keep the rising-edge one-shot GPIO12 input, RSSI gate,
opaque chunks, CRC, stop-and-wait, atomic files, and 640 KiB limit.

Do not delete the sender's ordinary copy until final ACK. Persist kind,
direction, amount, session, size, and digest across restart. Do not advertise
note metadata or secret bytes. Display an amount only for a complete stored
artifact. Transient statuses must return to `$5.00 / NOTE` or `EMPTY`.

### 7.4 QVAC

QVAC is a local, useful safety/UX layer, not decoration. Map natural language
to exactly:

```text
LOAD_NOTE(amount)
PASS_NOTE
REDEEM_NOTE
INSPECT_NOTE
EXPLAIN_OR_RECOVER
UNKNOWN
```

Return strict JSON. Feed only redacted deterministic state. Validate the
model's output through a normal policy function that owns all role, inventory,
amount, network, recovery, and confirmation checks. QVAC may propose or
explain; it may not spend, reveal secrets, fabricate state, or produce the
confirmation phrase.

Check in an evaluation corpus covering plain English, paraphrases, ambiguous
requests, wrong amounts, destructive requests, prompt injection, and recovery.
Record model constant, cache-file digest, SDK version, GPU/backend, latency,
accuracy, invalid-output rate, and safe refusals. If the 600M model is not
reliable enough for routing, use it for state/recovery explanation behind
deterministic buttons and report the measured limitation.

## 8. Milestones and gates

Work in order. Keep every earlier gate green.

### M0 — Baseline and evidence map

Run section 6, inspect dirty work, map existing direct-mode acceptance, and
write a short status report. No product edits until the baseline is understood.

### M1 — Disposable-wallet RGB spike

Build a CLI spike with a fake backend first. Then, only after presenting the
human with each immutable Mutinynet plan and receiving approval:

1. Create note wallet N with fresh keys/datadir and a transport-free invoice.
2. Fund N with exactly $5 RGB USDT plus measured sats/UTXOs for one redemption.
3. Import the exact funding consignment and settle according to policy.
4. Create Wallet B's invoice **after** N is active.
5. Plan/confirm one N -> B donation send and import the OOB consignment.
6. Attempt replay and capture the exact result without a second send.

Record txids, artifact hashes/sizes, sats, confirmations, timings, commands,
and failure/recovery behavior in `docs/spikes/NOTE-VAULT-SPIKE.md`. Do not run a
destructive wallet-backup test in this milestone.

Gate: two real RGB transfers work, or stop with measured failure and ranked
fallbacks. The accepted direct mode remains untouched.

### M2 — Durable vault and capsule

Implement the capsule codec, note registry, per-note wallet lock, plan/confirm,
claim reservation, result journal, replay result, and restart recovery. Required
tests include failures before backend send, during/after ambiguous send, before
result commit, after commit, concurrent claims, repeated confirmation, restart,
tamper, and secret-redacted logs.

Gate: no injected failure can cause an automatic second send.

### M3 — Bearer BLE vertical slice

Update protocol JSON, headers, dock decoder, firmware FSM/storage, screen
states, native tests, and docs in lockstep. First prove a synthetic capsule by
unit/native tests and dock echo; build both firmware profiles. Ask before
flashing. Physical acceptance is A -> B -> A -> B, exact digest, restart
persistence, and correct empty/note screens with the vault unavailable.

Gate: multi-hop works without a dock or network, or retain direct mode as live
fallback.

### M4 — Web workflow

Add separate, explicit **Load note**, **Pass note**, **Redeem note**, and
**Recover** actions. Do not overload the existing Send/Receive direct flow.
Every connection reads inventory before choosing direction. Show one next
action, a step number, whether the current step is offline, and plain language.

Load stages a ready capsule only after vault funding evidence is durable.
Redeem reads the capsule, creates a fresh local invoice, obtains an immutable
vault plan, and stops at exact confirmation. After broadcast, retain the exact
consignment until Wallet B import succeeds. A refresh/indexer error never means
“send again.”

### M5 — QVAC integration and evaluation

Integrate the typed intent layer with M4, run the fixed corpus repeatedly, and
save a redacted machine-readable report. Demo one successful intent and one
useful recovery explanation. Buttons remain deterministic fallbacks.

### M6 — Live acceptance and adversarial rehearsal

Run the ten-step acceptance script in `docs/OFFLINE-RGB-DEMO-DESIGN.md`.
Include network/vault-off evidence, timestamped serial logs, capsule digest,
two txids, final balance, replay bounce, recovery instructions, and one clean
three-minute rehearsal. Never generate another live spend simply to improve a
screenshot.

### M7 — Submission readiness

Update README, DESIGN, PROTOCOL, threat model, diagrams/PNGs, public website,
runbook, prior-work declaration, and exact mocked/real boundary. Document RGB,
QVAC, and any WDK use. Verify clean install/run steps and current repository
visibility. Re-run all tests/builds. Do not commit or push without a human ask.

### Stretch — only after M7 is green

Ranked: meaningful WDK integration; offline capsule signature verification;
TLS service deployment; encrypted blob/IPFS experiment; portable wallet-backup
spike; secure-element design; blind e-cash comparison. None may endanger the
core demo.

## 9. Known gaps already identified

Treat these as initial evidence, then verify against source:

1. The note vault, capsule, note artifact kind, web actions, and QVAC intent
   router do not yet exist.
2. Dock `send_chunk_file` can finish its final ACK before firmware's later-loop
   handoff to tap storage. Add same-session post-stage inventory verification;
   a blocked/mismatched state must retain the artifact and report failure.
3. Verify boot-orphan inventory and touch blocking remain correct after v3.
4. Ensure tap transient display messages revert to durable inventory state.
5. Esplora has produced 429/timeouts. Read-only refresh may back off; no send
   path may retry ambiguously.
6. Diagrams and some user wording may still describe only direct mode.
7. Public visibility and Friday prior-work declaration are human-owned but
   deadline-critical.

## 10. Time-box and fallback rules

- Prefer the smallest complete vertical slice over parallel features.
- Pre-mint/fund the demo note before judging; live confirmations are too
  variable for a three-minute desk demo. Show recorded funding evidence, then
  perform the offline relay and redemption live.
- If the live note-wallet spike fails after a focused investigation, stop and
  keep direct mode as the live RGB proof. Do not switch to simulated balances.
- If bearer firmware is unstable, do not misuse invoice/consignment kinds in a
  way that lies to inventory. Demo direct mode and a synthetic capsule codec.
- If QVAC classification is unreliable, use deterministic buttons for actions
  and QVAC for locally generated state/recovery explanation, with measured
  results shown.
- If an indexer is rate-limited, preserve state and offer “Refresh later.”
- If time remains only for one thing, protect the live demo and document truth.

## 11. Reporting format after every milestone

Report concisely:

1. Outcome and demo claim now proven.
2. Files changed, with links.
3. Tests/builds/live evidence and exact results.
4. Broadcasts: plan, human confirmation, txid, artifact hash, and state.
5. What remains mocked, trusted, incomplete, or unverified.
6. New risks and recovery procedure.
7. The single highest-value next action.

Stop only at a real boundary: spend approval, flash approval, commit/push,
secret handling, repository visibility/public release, external deployment, or
a measured failure that would change the selected architecture.
