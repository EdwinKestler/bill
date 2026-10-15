# Live web-dock RGB acceptance

The web desk now owns the same accepted `TapWalletFlow` used by
`scripts.rgb_tap`. It keeps one role-scoped wallet open for the server's
lifetime, so do not run `scripts.rgb_wallet` or `scripts.rgb_tap` against that
role while its web server is running.

## Start both isolated docks

Terminal A — funded wallet and TTGO:

```bash
set -a; source .env.a; set +a
.venv/bin/python -m web.server
```

Open <http://127.0.0.1:8788/>. The startup balance should match wallet A.

Terminal B — receiving wallet and WEMOS:

```bash
set -a; source .env.b; set +a
.venv/bin/python -m web.server
```

Open <http://127.0.0.1:8789/>. The startup balance should match wallet B.

Each server opens only its own wallet datadir.

## Register one physical bill per dock

Do this once on each role page before the transfer:

1. Select **Scan**. Only an RgbBill-family advertisement carrying service UUID
   `7c3e9a10-4b1e-4c8f-9d2a-00b111d0c001` should appear.
2. Select the intended device and choose **Connect**. Expect its address,
   identity, status, denomination, and artifact inventory to pass a read-only
   GATT check.
3. Choose **Register selected**. The badge changes to **Verified** and one
   role-scoped ignored registration is stored.
4. Restart the same server when convenient. The saved bill is loaded without
   waiting for BLE. **Connect** and later invoice/consignment operations open
   an on-demand connection to that address.

Do not change registration while a transfer, confirmation, or recovery is
active. The server rejects that switch. A UUID match proves protocol
compatibility, not cryptographic ownership; the operator's physical selection
is still part of this prototype's trust boundary.

## $5 transfer through the browser

1. On dock B, select **Receive USDT**.
   - Expect a real transport-free invoice receipt and BLE session ID.
   - The server never adds a proxy endpoint.
2. When Bill B shows `$5.00 / INVOICE TAP`, press Bill A once nearby.
3. When Bill A shows `$5.00 / INVOICE DOCK`, select **Send USDT** on Dock A.
   - The server retrieves and parses the invoice, then shows the immutable
     recipient, 5,000,000 base-unit amount, balance, fee, expiry, and hashes.
4. Type the displayed `CONFIRM <plan_id>` phrase exactly and select
   **Broadcast once**.
   - A mismatch cannot call send.
   - A successful send consumes the plan exactly once.
5. When Bill A shows `$5.00 / PROOF TAP`, press Bill B once nearby.
6. When Bill B shows `$5.00 / PROOF DOCK`, select **Receive USDT** on Dock B.
   - The exact received artifact is persisted before wallet import.
7. On each dock, enter `status` until the local transfer reports `settled`.
   - Refresh runs through the wallet already owned by that server; do not open
     a second CLI wallet process.

## Recovery boundaries

- Invoice BLE failure: select **Receive USDT** again; the service reuses the
  retained invoice instead of creating another one.
- Bill inventory `recovery-blocked`: do not press Send or Receive again. Run
  the explicit `chunk-discard` operation for that physical bill, verify
  `artifact=empty:empty`, then select the same dock action once. The live dock
  retains a failed invoice stage and does not create another invoice.
- Confirmation mismatch: correct the phrase. Nothing was broadcast and the
  displayed plan remains pending.
- Send failure or unknown outcome: the plan is consumed and the UI says to
  inspect the wallet. Never repeat that send.
- Broadcast succeeded but consignment staging failed: enter `retry stage` or
  call `POST /api/rgb/retry-stage`. This stages the retained consignment and
  cannot call send.
- Import failed after receipt: select **Receive USDT** again. The service
  reuses the persisted artifact and does not require a second tap.
- Cancel closes and invalidates the web-visible plan without broadcasting.

## JSON endpoints

| Endpoint | Role | Operation |
| --- | --- | --- |
| `GET /api/health` | A/B | Live service readiness |
| `GET /api/device` | A/B | Saved selection and last verification snapshot |
| `GET /api/bill` | A/B | Projected balance, pending plan, receipts, recovery |
| `POST /api/device/scan` | A/B | List strict service-UUID/name matches |
| `POST /api/device/connect` | A/B | Read-only GATT identity/state verification |
| `POST /api/device/register` | A/B | Verify and atomically replace the one saved bill |
| `POST /api/workflow/send` | A | Inventory-check invoice, then prepare send plan |
| `POST /api/workflow/receive` | B | Inventory-check, then stage invoice or import proof |
| `POST /api/rgb/invoice` | B | Create/stage transport-free witness invoice |
| `POST /api/rgb/plan` | A | Retrieve invoice and prepare immutable send plan |
| `POST /api/rgb/confirm` | A | Exact phrase, one send, then consignment staging |
| `POST /api/rgb/retry-stage` | A | Stage retained consignment without sending again |
| `POST /api/rgb/import` | B | Receive/import or retry retained consignment |
| `POST /api/rgb/refresh` | A/B | Refresh settlement through the owned wallet |
| `POST /api/cancel` | A | Discard the web-visible unconfirmed plan |

The web integration and exact confirmation gate were physically accepted on
both boards on 2026-10-15. The $5 browser-driven transfer settled on Mutinynet
as transaction
`1f8953866f24f5b64ec02875aa51507fc6c76777646680eddfb573247cf5d45f`;
both role wallets refreshed to $50 and both physical inventories returned to
empty.
