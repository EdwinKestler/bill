# Isolated Mutinynet RGB adapter

This package is the policy boundary between the dock application and pinned
`rgb-lib==0.3.0b7`. It is implemented, live accepted, and composed into
`web/server.py` through `web/rgb_web.py`. The web layer keeps the adapter's
one-use confirmation and exact-artifact recovery boundaries intact.

## Isolation invariants

- One OS process opens one role and one datadir. It never opens the peer path.
- Bill A and Bill B paths must be distinct and non-nested.
- A non-blocking file lock rejects a second process on the active datadir.
- The loaded rgb-lib wallet must report `SIGNET_CUSTOM` (Mutinynet).
- Only role B creates `witness_receive` intents and imports consignments.
- Only role A creates whole-spendable-balance transfer plans.
- `send` is unreachable until a plan receives a fresh, one-use confirmation.
- A failed/ambiguous send consumes the confirmation and is never retried
  automatically.
- Receive and send both pass `transport_endpoints=[]`.
- The transfer is `donation=true`; rgb-lib broadcasts during the confirmed
  send, so this path has no receiver ACK step.
- The exact `consignment_path` returned by `list_transfers` is hashed and handed
  to the BLE chunk layer. Bill B persists the received bytes in its isolated
  inbox, then calls `provide_out_of_band_consignment` with no media paths.

The initial third-party faucet receive is the sole transport exception: the
operator-only `receive --bootstrap` command includes
`RGB_BOOTSTRAP_PROXY=rpcs://proxy.kaleidoswap.com/json-rpc` because the faucet
refuses invoices it cannot deliver through a proxy. This endpoint is never
passed to the adapter's Bill A to Bill B tap receive or send methods.

## Safe configuration check

This validates role, paths, OOB mode, and the Mutinynet URL. It does not import
rgb-lib, read a mnemonic, open a wallet, or contact a network.

```bash
cd /media/kestl/andor/github/rgbhackathon/ideas/bill
set -a; source .env; set +a
.venv/bin/python -m web.rgb config-check
```

Run it once in the Bill A environment and once in the Bill B environment. The
reported active and peer paths must swap. The two live docks must be separate
processes (normally separate laptops), not two adapters inside the web server.

## Live acceptance gate

Do not run these steps until a human explicitly authorizes wallet/network
operations:

1. Install the pinned native wheel:
   `.venv/bin/pip install -r requirements-rgb.txt`.
2. Provision two custom-signet wallets independently. Each gets its own
   mnemonic, master fingerprint, and datadir.
3. Put each mnemonic in its role-specific ignored file and `chmod 600` it.
   Configure only the variable names in `.env`; never print mnemonic contents.
4. Fund Bill A with Mutinynet BTC for fees and the selected RGB USDT asset.
   Fund Bill B's witness receive requirements as dictated by rgb-lib.
5. Record the exact RGB asset ID and precision out of band. The adapter moves
   the complete spendable integer amount; it does not infer decimal display.
6. Start each dock with its own `BILL_ROLE`. `open_adapter()` acquires the
   datadir lock before `Wallet.load` and `go_online`.
7. First acceptance uses a human-visible plan, explicit confirmation, and a
   captured consignment file. The wallet-to-chunk bridge is implemented by
   `scripts.rgb_tap`; follow [RGB-TAP-LIVE.md](../../docs/RGB-TAP-LIVE.md) and
   verify both wallets reach the expected confirmation/settled states.

The direct invoice bridge intentionally has no wallet-generation command, no
proxy transport endpoint, and no implicit broadcast retry. The separate
bearer-note orchestrator may prepare a confirmation-gated `send_btc` from the
issuing dock wallet to its fresh disposable note. This replaces only the
interactive faucet step; it never adds an RGB transport endpoint or retries an
ambiguous Bitcoin or RGB broadcast.

The operator-only provisioning helper is deliberately separate from the web
server and runs once per process:

```bash
.venv/bin/python scripts/rgb_provision.py --role A
.venv/bin/python scripts/rgb_provision.py --role B
```

It refuses to overwrite any existing wallet, mnemonic, or role environment.
It prints file paths and permission modes, never mnemonic contents.

Use one role environment per process for live inspection and acceptance:

```bash
set -a; source .env.a; set +a
.venv/bin/python -m scripts.rgb_wallet status
.venv/bin/python -m scripts.rgb_wallet receive --bootstrap

set -a; source .env.b; set +a
.venv/bin/python -m scripts.rgb_wallet status
```

The `send` command displays an immutable whole-balance plan and blocks until
the operator types its randomly generated `CONFIRM <plan_id>` phrase. The
`import-consignment` command must run under Bill B's environment and imports
the exact file bytes through the content-addressed OOB inbox.

For the physical flow, use `scripts.rgb_tap`: Bill B creates and stages the
native invoice, Bill A retrieves and validates it before the existing exact
confirmation gate, and Bill B receives/imports the generated consignment. The
CLI records timestamps, paths, sizes, SHA-256 values, and BLE session IDs. It
also emits recovery-only commands if BLE staging or import fails, so a
successful or ambiguous broadcast is never repeated.
