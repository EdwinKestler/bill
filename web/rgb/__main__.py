"""Read-only setup checks for the RGB adapter."""

from __future__ import annotations

import argparse
import json

from .config import RgbSettings


def main() -> None:
    parser = argparse.ArgumentParser(description="fork2checkbook RGB adapter utilities")
    parser.add_argument(
        "command",
        choices=["config-check"],
        help="validate isolation and Mutinynet settings without opening a wallet",
    )
    args = parser.parse_args()
    if args.command == "config-check":
        settings = RgbSettings.from_env(require_credentials=False)
        print(
            json.dumps(
                {
                    "ok": True,
                    "role": settings.role.value,
                    "active_data_dir": str(settings.data_dir),
                    "peer_data_dir": str(settings.peer_data_dir),
                    "oob_inbox": str(settings.inbox_dir),
                    "network": "Mutinynet (custom signet)",
                    "transport_endpoints": [],
                    "wallet_opened": False,
                },
                indent=2,
            )
        )


if __name__ == "__main__":
    main()
