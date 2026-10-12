# Palimnex for the bill (parent silo)

This project has **no** Palimnex of its own. Do not run `palimnex init` here.
Do not create `.palimnex.json` or `.palimnex/` under `ideas/bill/`.

The hackathon workspace already has one cache and one ledger:

| | |
| --- | --- |
| Root | `/media/kestl/andor/github/rgbhackathon` |
| Slug | `rgbhackathon` |
| project_id | `c1f0cd81-e63c-45d0-afed-a01b5e9ff764` |
| Config | `.palimnex.json` |
| Skill | `.agents/skills/source-cache/SKILL.md` |
| Notes | `docs/palimnex.md` |
| Setup | `./scripts/palimnex-setup.sh` |

Bill markdown, firmware, dock Python, and GATT JSON are **include_patterns** on
that same project. After you edit them, reindex **from the hackathon root**.

```bash
cd /media/kestl/andor/github/rgbhackathon
export PALIMNEX_ROOT=/media/kestl/andor/github/rgbhackathon
palimnex status
palimnex search "witness_receive out-of-band consignment rgb-lib" --limit 8
palimnex search "RgbBill dock GATT IDENTITY" --limit 8
```

If stale: `palimnex index --incremental` then `palimnex validate --deep`.
Pipeline batch limit: `palimnex redis reset`, `palimnex redis start`, incremental
index. Ledger stays. Never `FLUSHDB` / `FLUSHALL`.

Search, then open the returned file. Cache hits never authorize spends, flashes,
or git writes.

Recall (`palimnex recall`) is historical context on the **same** SQLite ledger.
Use `--kind fact` / `--session` from the hackathon root so bill decisions sit
in the weekend graph with RGB/QVAC notes.

Agent skill in this folder: `.agents/skills/source-cache/SKILL.md` (named
`source-cache` because Palimnex skips a path segment `palimnex`).
