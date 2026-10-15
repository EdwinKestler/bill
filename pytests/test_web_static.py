import re
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
STATIC = PROJECT_ROOT / "web" / "static"


def _read(name: str) -> str:
    return (STATIC / name).read_text(encoding="utf-8")


def test_dock_javascript_references_existing_dom_ids():
    html = _read("index.html")
    javascript = _read("app.js")
    html_ids = set(re.findall(r'\bid="([^"]+)"', html))
    javascript_ids = set(
        re.findall(r'document\.getElementById\("([^"]+)"\)', javascript)
    )

    assert javascript_ids <= html_ids
    assert {
        "scan-device",
        "connect-device",
        "register-device",
        "send-usdt",
        "receive-usdt",
        "recovery",
        "retry-stage",
        "confirm",
        "confirmation-phrase",
        "confirm-error",
    } <= html_ids


def test_visual_redesign_preserves_human_first_protocol_language():
    html = _read("index.html")
    javascript = _read("app.js")

    assert "Cash bill" in html
    assert "Physical bill" in html
    assert "Send USDT" in html
    assert "Receive USDT" in html
    assert "Confirmation gate" in html
    assert "Confirm Mutinynet broadcast" in html
    assert "Browser mode: direct invoice + consignment transfer" in html
    assert "offline bearer-note lifecycle" in html
    assert "Cash wallet" not in html
    assert "/api/wallet/peek" not in javascript
    assert "/api/contacts" not in javascript


def test_recovery_controls_use_existing_no_resend_endpoints():
    javascript = _read("app.js")
    server = (PROJECT_ROOT / "web" / "server.py").read_text(encoding="utf-8")

    assert '"retry-consignment-stage"' in javascript
    assert '"retry-consignment-import"' in javascript
    assert '"retry-invoice-stage"' in javascript
    assert '"inspect-wallet-before-any-new-plan"' in javascript
    assert '"/api/rgb/retry-stage"' in javascript
    assert '"/api/rgb/retry-stage"' in server
    assert '"/api/rgb/import"' in server
    assert '"/api/rgb/invoice"' in server


def test_styles_include_responsive_cash_note_design():
    css = _read("app.css")

    assert ".note-grid" in css
    assert ".note-seal" in css
    assert ".workflow-step" in css
    assert ".recovery" in css
    assert "@media (max-width: 34rem)" in css
