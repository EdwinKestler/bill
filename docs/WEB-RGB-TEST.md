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

The current bench role files bind A to `30:AE:A4:4C:B1:6A` and B to
`30:AE:A4:07:2D:2E`. Each server opens only its own wallet datadir.

## $5 transfer through the browser

1. On dock B, enter `prepare bill for $5`.
   - Expect a real transport-free invoice receipt and BLE session ID.
   - The server never adds a proxy endpoint.
2. Press the TTGO touch input once and release it.
3. On dock A, enter `bill for $5`.
   - The server retrieves and parses the invoice, then shows the immutable
     recipient, 5,000,000 base-unit amount, balance, fee, expiry, and hashes.
4. Type the displayed `CONFIRM <plan_id>` phrase exactly and select
   **Broadcast once**.
   - A mismatch cannot call send.
   - A successful send consumes the plan exactly once.
5. Wait for `consignment-staged`, then press the WEMOS touch input once.
6. On dock B, enter `import consignment`.
   - The exact received artifact is persisted before wallet import.
7. On each dock, enter `status` until the local transfer reports `settled`.
   - Refresh runs through the wallet already owned by that server; do not open
     a second CLI wallet process.

## Recovery boundaries

- Invoice BLE failure: repeat `prepare bill for $5`; the service reuses the
  retained invoice instead of creating another one.
- Confirmation mismatch: correct the phrase. Nothing was broadcast and the
  displayed plan remains pending.
- Send failure or unknown outcome: the plan is consumed and the UI says to
  inspect the wallet. Never repeat that send.
- Broadcast succeeded but consignment staging failed: enter `retry stage` or
  call `POST /api/rgb/retry-stage`. This stages the retained consignment and
  cannot call send.
- Import failed after receipt: enter `import consignment` again. The service
  reuses the persisted artifact and does not require a second tap.
- Cancel closes and invalidates the web-visible plan without broadcasting.

## JSON endpoints

| Endpoint | Role | Operation |
| --- | --- | --- |
| `GET /api/health` | A/B | Live service readiness |
| `GET /api/bill` | A/B | Projected balance, pending plan, receipts, recovery |
| `POST /api/rgb/invoice` | B | Create/stage transport-free witness invoice |
| `POST /api/rgb/plan` | A | Retrieve invoice and prepare immutable send plan |
| `POST /api/rgb/confirm` | A | Exact phrase, one send, then consignment staging |
| `POST /api/rgb/retry-stage` | A | Stage retained consignment without sending again |
| `POST /api/rgb/import` | B | Receive/import or retry retained consignment |
| `POST /api/rgb/refresh` | A/B | Refresh settlement through the owned wallet |
| `POST /api/cancel` | A | Discard the web-visible unconfirmed plan |

The web integration is implemented and both role servers pass non-mutating
live startup/health/balance checks. The first browser-driven broadcast remains
a separate physical acceptance run; it must retain the exact confirmation
gate above.
