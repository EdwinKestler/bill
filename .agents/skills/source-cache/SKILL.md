---
name: palimnex
description: Use the parent rgbhackathon Palimnex cache and ledger for bill work. Never init a second Palimnex silo under ideas/bill. Triggers: palimnex, source cache, lookup, ledger, recall.
---

# Palimnex (bill uses the hackathon silo)

Root: `/media/kestl/andor/github/rgbhackathon`. Slug `rgbhackathon`.
project_id `c1f0cd81-e63c-45d0-afed-a01b5e9ff764`.

```bash
cd /media/kestl/andor/github/rgbhackathon
export PALIMNEX_ROOT=/media/kestl/andor/github/rgbhackathon
palimnex status
```

If missing or stale: `./scripts/palimnex-setup.sh` or `palimnex index --incremental`
then `palimnex validate --deep`.

Search with implementation words (`witness_receive`, `RgbBill`, `DockGatt`).
Open the returned file. Reindex after editing `ideas/bill/` sources.

Do not `palimnex init` in `ideas/bill/`. Do not create `.palimnex/` here.
Ledger remember/recall from the hackathon root so facts join the weekend graph.

Redis is disposable; SQLite is durable history. Neither authorizes flashes,
spends, or git. Never flush shared Redis. Never commit `.palimnex/` or `*.pmem`.

Details: `ideas/bill/docs/LOOKUP.md`, hackathon `docs/palimnex.md`.
