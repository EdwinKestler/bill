# Optional Rust sidecar

Weekend dock is **Python** (`web/server.py` + `dock/` Bleak + rgb-lib-python).

Use this folder only if Python wheels for rgb-lib 0.3.0-beta.7 are missing on
the laptop and we must call the Rust crate over a local socket. Do not start a
second wallet process against the same datadir.

Not in the first demo path. No `Cargo.toml` until a human asks.
