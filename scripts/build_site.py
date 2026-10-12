"""Package only the public project website and its documentation diagrams."""

from pathlib import Path
from shutil import copy2

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / ".site-build"
FILES = (
    "index.html",
    "styles.css",
    "app.js",
    "assets/favicon.svg",
)
DIAGRAMS = (
    "01-system-architecture",
    "02-component-ownership",
    "03-rgb-transfer-sequence",
    "04-bill-state-machine",
    "05-gatt-contract",
    "06-chunk-frame",
    "07-bill-hardware",
    "08-trust-boundaries",
)


def build() -> None:
    """Copy an explicit public asset list without opening wallets or env files."""
    expected = {Path(name) for name in FILES}
    expected.update(Path(f"assets/diagrams/{name}.png") for name in DIAGRAMS)
    expected.add(Path(".nojekyll"))
    if OUTPUT.is_symlink():
        raise SystemExit("Refusing a symlinked site output directory")
    if OUTPUT.exists():
        for path in OUTPUT.rglob("*"):
            if path.is_symlink() or (path.is_file() and path.relative_to(OUTPUT) not in expected):
                raise SystemExit(f"Unexpected site output entry: {path.relative_to(OUTPUT)}")
    for name in FILES:
        target = OUTPUT / name
        target.parent.mkdir(parents=True, exist_ok=True)
        copy2(ROOT / "site" / name, target)
    for name in DIAGRAMS:
        target = OUTPUT / "assets" / "diagrams" / f"{name}.png"
        target.parent.mkdir(parents=True, exist_ok=True)
        copy2(ROOT / "docs" / "diagrams" / f"{name}.png", target)
    (OUTPUT / ".nojekyll").touch()
    print(f"Built {len(expected)} public files in {OUTPUT}")


if __name__ == "__main__":
    build()
