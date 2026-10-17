# Web dock application

Laptop desk for one physical bill. Python HTTP + static UI. Bleak radio stays
in `../dock/`. The isolated rgb-lib-python 0.3.0b7 adapter is in `rgb/`; it is
enabled through the role-scoped service in `rgb_web.py`.

**Python, not Rust, for the weekend path.** Bleak and `rgb-lib-python` are
already in this language. QVAC is `tetherto-qvac-sdk==0.21.0` in the same
`.venv` (fat linux-x64 wheel, `./install_qvac.sh`). Rust rgb-lib is optional —
see `rust/README.md`.

```bash
cd /media/kestl/andor/github/rgbhackathon/ideas/bill
source .venv/bin/activate
python -m web.server
```

By default it binds the role-specific loopback host and port from the
environment. On the current bench, A uses port `8788` and B uses port `8789`.
In the primary bearer flow, A/B select isolated wallet and device-registration
profiles; either profile can issue a note it funded or redeem a received note.
The older direct-mode fallback remains role-specific: B creates the invoice and
A sends to it. Broadcast is unreachable until the operator types the displayed
exact `CONFIRM <plan_id>` phrase.

For a trusted LAN demo that must remain reachable through both localhost and
the Wi-Fi address, set `DOCK_HTTP_HOST=0.0.0.0` in both role environments.
Keep role A on port `8788` and role B on port `8789`, then open either
`http://127.0.0.1:<port>/` locally or `http://<wifi-ip>:<port>/` from the LAN.
The wildcard listens on every host interface, including VPN interfaces. Do not
forward these ports: the prototype has no web-user authentication, so any
client that can reach them can operate the dock UI.

## Wallet identity and selection

Every dock page shows the non-secret identity of the rgb-lib wallet currently
owned by that process: its configurable label, A/B role, Mutinynet network,
master fingerprint, RGB asset, and bearer purpose. Issuance funds a fresh
disposable note wallet, not the physical ESP32 or a known recipient. The final
wallet is chosen only when the eventual holder redeems at a compatible dock.

Configure the human-readable names with `RGB_WALLET_LABEL_A` and
`RGB_WALLET_LABEL_B`. The actual wallet selection remains the existing
role-scoped `RGB_DATA_DIR_*`, `RGB_MASTER_FINGERPRINT_*`, and
`RGB_MNEMONIC_FILE_*` configuration. Stop the dock before changing those
settings, then restart it. The browser deliberately cannot switch an open
wallet: rgb-lib holds one process lock per datadir, and the trusted-LAN UI has
no user authentication. Mnemonics, mnemonic paths, and full data-directory
paths are never returned to the browser.

This web application now drives the accepted disposable bearer-note flow. The
primary local-QVAC box maps **“Prepare a $5 note”** to `LOAD_NOTE(500)` and
hands that typed output to deterministic policy, which creates a fresh
no-broadcast funding plan. QVAC cannot confirm, broadcast, create confirmation
text, or write hardware. After exact human confirmation and one Mutinynet
confirmation, **Load note** refreshes exact settlement and loads the funded
capsule onto the empty registered bill. **Pass note** explains the dock-free whole-value BLE handoff.
Any eventual holder's dock exposes **Redeem note**, which extracts the capsule,
verifies its exact SHA-256, creates that dock wallet's fresh
transport-free invoice, and stops at the immutable confirmation dialog.
**Recover** can re-import only a recorded consignment or safely supersede an
expired, unconsumed plan; it never repeats an RGB send. **Refresh settlement**
performs the exact txid/assignment/balance closure. A fresh disposable wallet
still needs Mutinynet fee sats, but the browser now prepares an immutable
Bitcoin top-up from the issuing dock wallet instead of directing the human to
a faucet. The top-up and RGB funding remain separate broadcasts with separate
exact confirmations; after the top-up confirms, **“Check my note”** creates a
fresh RGB plan. Exceptional capacity recovery remains a guarded operator
procedure in [`OFFLINE-BEARER-RUNBOOK.md`](../docs/OFFLINE-BEARER-RUNBOOK.md).

The web bearer adapter borrows the already-open role wallet under
`RgbWebService`'s lock. Its `close()` is deliberately a no-op, so the web dock
remains the only owner of that wallet datadir. Disposable note wallet N keeps
its independent process lock. Received capsule files are private (`0600`),
content-addressed under ignored `.note-vault/incoming/`, and retained across a
plan/indexer failure.

Post-broadcast staging failure retains the exact consignment and exposes a
stage-only retry that cannot send again. Import failure similarly retains and
reuses the received artifact. See
[WEB-RGB-TEST.md](../docs/WEB-RGB-TEST.md) for the two-dock procedure.

## Physical bill registration

Each role-specific dock page has **Scan**, **Connect**, and **Register
selected** controls. Scan lists only advertisements carrying the frozen
RgbBill dock service UUID and an RgbBill-family name. Connect performs a
read-only `IDENTITY` / `STATUS` / `DENOMINATION` / `ARTIFACT_META` check.
Register repeats that check and atomically stores one selection in the ignored role file
`.dock-registration-a.json` or `.dock-registration-b.json` with mode `0600`.

The saved address is resolved immediately before every BLE operation, so the
dock reconnects on demand after restarts; startup never waits for the radio
and does not keep a permanent BLE connection open. `BLE_DEVICE_ADDRESS`
remains a migration fallback until a browser selection is registered.
Registration is rejected while a transfer, confirmation, or recovery boundary
is active. There is currently no web-user account layer: “one per user” means
one physical bill per role-specific dock process.

The primary UI is deliberately state-driven around **Load note**, **Pass
note**, **Redeem note**, **Recover**, and **Refresh settlement**. Bearer actions
are profile-neutral; each action
inventories the registered bill before choosing a BLE direction. The older
role-A **Send USDT** / role-B **Receive USDT** direct mode and text commands
remain under an Advanced disclosure as a fallback, not the main demo.
Inventory v2 also exposes `recovery-blocked`; both primary actions fail closed
in that state so a retained DockGatt artifact can never be mistaken for an
empty bill and produce a second invoice.

The browser layout uses a cash-note balance card, one prominent next-action
card, responsive desktop/mobile spacing, and an inline recovery card. Recovery
buttons call only the retained-artifact endpoints; they never repeat an RGB
send. The visual layer deliberately keeps the existing **bill** terminology
and manual Send/Receive actions—there is no background BLE transfer trigger.

| Path | Job |
| --- | --- |
| `server.py` | HTTP: static files + JSON API |
| `device_registry.py` | Strict BLE discovery, read-only verification, one saved bill |
| `static/` | Desk UI (denomination, status, confirm) |
| `rgb_web.py` | Long-lived role wallet + exact-artifact recovery boundaries |
| `bearer_web.py` | Web-to-note-vault bridge; private extraction and borrowed wallet ownership |
| `rgb/` | Isolated rgb-lib-python adapter and safe config check |
| `rust/` | Optional native rgb-lib crate; not required to demo |
