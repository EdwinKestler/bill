# Public project website

Static project presentation for GitHub Pages. The local wallet desk remains in
`web/`; this website explains the project and performs no wallet or BLE operations.

## Preview

From the repository root:

```bash
python3 scripts/build_site.py
python3 -m http.server 8790 --bind 127.0.0.1 --directory .site-build
```

Open <http://127.0.0.1:8790/>. The build copies an explicit list of HTML,
CSS, JavaScript, the favicon, and all eight documentation PNGs. It never copies
the repository root, local environments, wallet datadirs, or model caches.
Relative asset URLs support the GitHub Pages `/bill/` project path.

The site uses optional Google Fonts with system fallbacks. The five-step
explainer and diagram selector work without dependencies; the page remains
readable with JavaScript disabled. Illustrations are conceptual, rather than
photographs of the hardware or live wallet balances.

## Deployment

In GitHub repository Settings → Pages, choose **GitHub Actions** as the source.
The workflow at `.github/workflows/pages.yml` packages `.site-build/` and deploys
on relevant pushes to `main`, or through a manual workflow run. Expected URL:
<https://edwinkestler.github.io/bill/>.

The repository and Pages configuration are public. Deployment uses only the
explicit `.site-build/` allowlist produced by `scripts/build_site.py`; it never
uploads the repository root, local environments, wallet data, or model caches.
The deploy job runs after every successful site build without a separate
repository-variable gate.

Workflow reference:
[GitHub Pages custom workflows](https://docs.github.com/en/pages/getting-started-with-github-pages/using-custom-workflows-with-github-pages).

## Content evidence

- `docs/DESIGN.md` and `docs/PROTOCOL.md`: architecture, hardware, radio behavior.
- `docs/RGB-TAP-LIVE.md`: accepted 20 USDT test transfer on 2026-10-11.
- `docs/WEB-RGB-TEST.md`: accepted browser-driven physical transfer.

Keep the status copy aligned with those records. The browser-driven physical
transfer is accepted. Local QVAC inference is verified; connecting it to the
deterministic, confirmation-gated action flow remains the next integration
gate.
