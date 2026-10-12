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
Then set the Actions repository variable `PAGES_ENABLED` to `true`.
The workflow at `.github/workflows/pages.yml` packages `.site-build/` and deploys
on relevant pushes to `main`, or through a manual workflow run. Expected URL:
<https://edwinkestler.github.io/bill/>.

The build job always runs; deployment stays skipped until that variable is set.
After enabling Pages and the variable, run the workflow from the Actions tab.

On 2026-10-12, GitHub returned HTTP 422 when activation was attempted:
“Your current plan does not support GitHub Pages for this repository.”
The repository is private. The site is prepared and locally verified; it is
not yet published at the expected URL.

The repository can stay private when the owner's GitHub plan supports Pages for
private repositories. The published website is normally public; this does not
change repository visibility. If Pages is unavailable for the current plan,
enable an eligible plan or explicitly choose to make the repository public.

Workflow reference:
[GitHub Pages custom workflows](https://docs.github.com/en/pages/getting-started-with-github-pages/using-custom-workflows-with-github-pages).

## Content evidence

- `docs/DESIGN.md` and `docs/PROTOCOL.md`: architecture, hardware, radio behavior.
- `docs/RGB-TAP-LIVE.md`: accepted 20 USDT test transfer on 2026-10-11.
- `docs/WEB-RGB-TEST.md`: browser integration and remaining physical acceptance.

Keep the status copy aligned with those records. QVAC voice integration is
planned; the CLI transfer is accepted; the browser flow is implemented but its
first full physical transfer remains a separate gate.
