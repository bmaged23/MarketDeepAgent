# Project diagrams and actual storefront demo

Serve the documentation from the repository root:

```bash
python docs/generate.py
python -m http.server 8700 --bind 127.0.0.1 --directory docs
```

Open http://127.0.0.1:8700 for the animated architecture, database ERD and demo page.

The architecture explorer has five selectable views: overview, retrieval loop, cart/checkout, private memory and product indexing. Colored arrowheads distinguish requests, responses, authoritative writes and embedding/synchronization. Each view includes a workflow explanation, keyboard-accessible tabs, component inspection, motion controls and a full-size SVG link. `system_diagrams.py` generates the five source-backed architecture assets; `generate.py` also derives the ERD from migrations.

The generated presentation was rejected and removed from public docs. **The actual storefront recording is now available at `assets/storefront-tour.mp4`: 1440×900 H.264, about 5 minutes 52 seconds.** The demo page displays the actual video only after a successful recording creates it.

## Automatically record the actual marketplace

From the project root, with the Python environment installed:

```bash
source .venv/bin/activate
npm --prefix docs install
npm --prefix docs run install-browser
python docs/record_storefront.py
```

Requires Node.js, FFmpeg/ffprobe, the configured Ollama key, working product Qdrant/BGE retrieval and Chromium. Recording dependencies are isolated in `docs/node_modules`, excluded from Git; Python requirements remain the exact runtime snapshot. If Chromium reports missing Linux libraries, install its dependencies with `npm --prefix docs run install-browser -- --with-deps`.

The recorder:

1. Clones only the catalog to temporary SQL and starts a separate real FastAPI backend on port 8601.
2. Opens the existing `UI/frontend` in Chromium, with the application's actual CSS/images/forms.
3. Registers a fictional customer, then signs out and signs back in with readable typing and pauses. Shared memory writes are disabled.
4. Chats with the live agents, researches prices/package sizes/estimated calories, compares alternatives and opens five products: apples, tea, whole wheat bread, Greek yogurt and mixed nuts.
5. Adds all five products through the assistant, changes apples to quantity two, reviews the cart and confirms one synthetic order using the actual form. Does not ask why the order is pending or offer to open an already visible cart.
6. Visits order history, profile and settings.
7. Saves an H.264 MP4 to `docs/assets/storefront-tour.mp4`, trimming long waiting periods without fabricating any replies or UI.

A failed step aborts publication instead of substituting a fake success. Raw WebM/manifest output stays in ignored `docs/assets/raw-recordings/`; the temporary SQL is deleted after the run. The existing catalog, customers, orders and stock are not modified, and no product indexing worker runs against shared Qdrant. The recording reads production product vectors, but customer memory vectors cannot be read or written. No credential or real customer profile is shown.

Use `--headed` to watch the browser on a graphical desktop; default headless mode still records the actual rendered browser. Use `--port 8602` if 8601 is occupied. For manual recording of a test account, use `record.html` and choose the real marketplace tab; its actions operate on that chosen application's database.

## Maintained files

- `index.html`, `architecture.js`, `assets/architecture.svg`: animated system map and inspection controls.
- `erd.html`, `database.md`, `assets/database-erd.svg`: all 20 migration-derived SQL entities and logical Qdrant mappings.
- `generate.py`: diagram regeneration from temporary migrated SQL, without customer data.
- `record_storefront.py`: isolated real server, recorder orchestration and validated FFmpeg conversion.
- `record_storefront.mjs`: actual browser clicks/typing, live chat responses and checkout.
- `package.json`: exact Playwright recording-tool version.
- `demo.html`, `video-player.js`: real MP4 playback, fullscreen and direct playback link.
- `record.html`, `record.js`: native browser manual screen capture.

Static documentation can be published through GitHub Pages using `docs/`. The marketplace backend must still run separately. Animated arrows illustrate architecture, not live telemetry.

## Ubuntu 26.04 browser installation

The pinned Playwright 1.56.0 has no Ubuntu 26.04 browser download entry. Both installer and recorder now select its Ubuntu 24.04 build on Ubuntu 26+ (x64/arm64); this is a compatibility fallback, not official Ubuntu 26.04 support. Existing explicit `PLAYWRIGHT_HOST_PLATFORM_OVERRIDE` is respected.

```bash
npm --prefix docs run install-browser
python docs/record_storefront.py
```

If Chromium reports missing Linux libraries, run `npm --prefix docs run install-browser -- --with-deps`. The recorder now launches/checks Chromium before creating the temporary backend and reports setup failures without an unrelated Python subprocess traceback. Actual browser installation/launch on this host still needs validation; restricted agent execution can verify platform selection but cannot download the browser.

Fullscreen video now expands the player across the browser window even when native fullscreen is blocked. Use Exit fullscreen or Escape to restore it; F11 can hide browser chrome in desktop browsers. Refresh the demo page to load the updated player.

The expanded recording completed successfully with all five products verified in the synthetic order.

## Publish the demo (same GitHub Pages approach as the Fitness project)

Push the updated `main` branch. On GitHub go to **Settings → Pages → Build and deployment → Source: Deploy from a branch**, select **main /docs**, then **Save**. Wait for the **pages build and deployment** job under Actions to complete.

- Customer video: https://bmaged23.github.io/MarketDeepAgent/demo.html
- Architecture explorer: https://bmaged23.github.io/MarketDeepAgent/

The README introduces the project first, then shows a clickable video preview that opens the hosted demo. On the demo page, the left-side Play demo button starts the real MP4; native playback controls and fullscreen remain available. `docs/.nojekyll` makes this a static Pages site. Hosting is ready in the source tree; enable Pages in repository settings before expecting these URLs to work.
