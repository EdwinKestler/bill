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

Binds the role-specific loopback host and port from the environment. On the
current bench, A uses `127.0.0.1:8788` and B uses `127.0.0.1:8789`. Role B
creates/stages the real witness invoice and imports the received consignment.
Role A retrieves the tapped invoice and presents an immutable plan. Broadcast
is unreachable until the operator types the displayed exact
`CONFIRM <plan_id>` phrase.

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

| Path | Job |
| --- | --- |
| `server.py` | HTTP: static files + JSON API |
| `device_registry.py` | Strict BLE discovery, read-only verification, one saved bill |
| `static/` | Desk UI (denomination, status, confirm) |
| `rgb_web.py` | Long-lived role wallet + exact-artifact recovery boundaries |
| `rgb/` | Isolated rgb-lib-python adapter and safe config check |
| `rust/` | Optional native rgb-lib crate; not required to demo |
