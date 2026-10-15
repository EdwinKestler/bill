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
Role B
creates/stages the real witness invoice and imports the received consignment.
Role A retrieves the tapped invoice and presents an immutable plan. Broadcast
is unreachable until the operator types the displayed exact
`CONFIRM <plan_id>` phrase.

For a trusted LAN demo that must remain reachable through both localhost and
the Wi-Fi address, set `DOCK_HTTP_HOST=0.0.0.0` in both role environments.
Keep role A on port `8788` and role B on port `8789`, then open either
`http://127.0.0.1:<port>/` locally or `http://<wifi-ip>:<port>/` from the LAN.
The wildcard listens on every host interface, including VPN interfaces. Do not
forward these ports: the prototype has no web-user authentication, so any
client that can reach them can operate the dock UI.

This web application implements the accepted direct invoice/consignment flow.
The disposable offline bearer-note path is currently operated through
`scripts/note_wallet_live.py` and is documented in
[`OFFLINE-BEARER-RUNBOOK.md`](../docs/OFFLINE-BEARER-RUNBOOK.md). Do not imply
that the browser can yet fund, load, or redeem a bearer note.

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

The primary UI is deliberately state-driven: role A exposes **Send USDT** and
role B exposes **Receive USDT**. Each action inventories the registered bill
before choosing a BLE direction. Text commands remain under an Advanced
disclosure for diagnostics and recovery, not as the normal human procedure.
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
| `rgb/` | Isolated rgb-lib-python adapter and safe config check |
| `rust/` | Optional native rgb-lib crate; not required to demo |
