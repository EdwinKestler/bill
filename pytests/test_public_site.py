import re
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SITE = PROJECT_ROOT / "site"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_public_site_describes_the_verified_bearer_flow_honestly():
    html = _read(SITE / "index.html")
    javascript = _read(SITE / "app.js")

    assert len(re.findall(r'\bdata-step="\d+"', html)) == 6
    assert 'id="flow-counter">01 / 06' in html
    assert "first-redemption-wins" in html
    assert "trusted vault" in html.lower()
    assert "QVAC" in html
    assert "WDK" in html
    assert "ILI9341 color display" not in html
    assert "b325cbe40c282e661c40ff8555cb6cb0fc9867a32855feb8b17d7756c9a83963" in html
    assert "dfe138b0983f6238103d2e5c57bf0848fdd5b7fd733162299fb4c6e5e9f427bf" in html
    assert "String(steps.length).padStart" in javascript


def test_public_site_lists_every_documentation_diagram():
    html = _read(SITE / "index.html")
    javascript = _read(SITE / "app.js")
    builder = _read(PROJECT_ROOT / "scripts" / "build_site.py")

    for number, name in (
        ("01", "system-architecture"),
        ("02", "component-ownership"),
        ("03", "rgb-transfer-sequence"),
        ("04", "bill-state-machine"),
        ("05", "gatt-contract"),
        ("06", "chunk-frame"),
        ("07", "bill-hardware"),
        ("08", "trust-boundaries"),
        ("09", "live-evidence-timeline"),
        ("10", "note-vault-state"),
    ):
        stem = f"{number}-{name}"
        assert f'value="{stem}"' in html
        assert f'"{stem}"' in javascript
        assert f'"{stem}"' in builder
        assert (PROJECT_ROOT / "docs" / "diagrams" / "src" / f"{stem}.mmd").is_file()


def test_canonical_docs_link_to_evidence_runbook_and_threat_model():
    readme = _read(PROJECT_ROOT / "README.md")
    design = _read(PROJECT_ROOT / "docs" / "DESIGN.md")
    protocol = _read(PROJECT_ROOT / "docs" / "PROTOCOL.md")

    for document in (
        "docs/LIVE-EVIDENCE.md",
        "docs/OFFLINE-BEARER-RUNBOOK.md",
        "docs/THREAT-MODEL.md",
    ):
        assert document in readme
    assert "exactly two RGB transitions" in design
    assert "Primary procedure: carry value offline" in protocol
