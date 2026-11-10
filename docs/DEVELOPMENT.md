# Development guide

This fork makes the LiveKit Agents path a first-class local session debugger. Pipecat support is kept working but not extended, and is planned to be removed later; `AGENTS.md` ("Focus") has the rules that keep it cheap until then.

## Environment

Python 3.12–3.14 is supported. Use `uv` to manage the environment.

Install the LiveKit development path:

```bash
uv sync --extra livekit --extra dev
```

Install Pipecat support too when working on the original processor integration:

```bash
uv sync --extra livekit --extra pipecat --extra dev
```

Install pre-commit hooks:

```bash
uv run pre-commit install
```

Run formatting/lint fixes:

```bash
uv run scripts/fix-ruff.sh
```

## Run the local server

```bash
uv run finchvox start --data-dir ./.finchvox-data
```

The default bind address is `127.0.0.1`. For a Docker/network integration test, opt in with `--host 0.0.0.0`.

UI:

```text
http://localhost:3000
```

OTLP/gRPC:

```text
localhost:4317
```

While working on the code, run it with automatic restarts instead. `watchfiles` comes with Uvicorn and restarts the server when a Python file under `src/` changes. UI files under `ui/` are read straight from the folder, so they only need a browser refresh. Other ports keep it out of the way of a Docker Finchvox on 3000/4317:

```bash
uv run watchfiles --filter python "finchvox start --port 3200 --grpc-port 4327 --data-dir .finchvox-data" src
```

## Tests

Run the full suite:

```bash
uv run pytest -q
```

The Pipecat processor tests (`tests/test_processor.py`) skip themselves when the `pipecat` extra is not installed, so this also works on the LiveKit-only setup. The Pipecat side of the server and UI is still checked on every run: `tests/test_pipecat_session.py` reads a synthetic Pipecat session (spans, logs and audio chunks) through the HTTP API, with no Pipecat install needed.

Because the processor tests are normally skipped, run them against the real Pipecat SDK before a release or a merge from upstream. This installs the `pipecat` extra into the environment (a few minutes the first time):

```bash
uv run --extra livekit --extra pipecat --extra dev pytest tests/test_processor.py tests/test_voice_sdk_compat.py tests/test_pipecat_session.py
```

It passed against Pipecat 1.14.0 on 2026-11-10.

Useful targeted tests for LiveKit work:

```bash
uv run pytest -q tests/test_adapters.py tests/test_livekit_*.py \
  tests/test_conversation_livekit.py tests/test_metrics.py tests/test_ui_routes.py
```

Lint:

```bash
uv run ruff check src tests
```

JavaScript syntax check of every UI script:

```bash
for f in ui/js/*.js; do node --check "$f"; done
```

Browser-script tests (Node.js; no npm install required). `uv run pytest` runs these too, through `tests/test_browser_scripts.py`, and skips them when Node.js is not installed:

```bash
node --test scripts/test_core_browser_dependencies.cjs scripts/test_preferences.cjs scripts/test_log_formatter.cjs
uv run pytest -q tests/test_browser_vendoring.py
```

The Node tests load the real vendored Alpine reactivity engine, verify asset hashes,
test player/chart integration through public-contract stubs, and test the saved
display preferences (`ui/js/preferences.js`), the inspector resizing and the log
message formatter (`ui/js/log_message_formatter.js`). Rendering, audio decoding, and browser
interaction still need the manual smoke checks below.

Python compile check:

```bash
uv run python -m compileall -q src tests examples/livekit
```

Docker smoke test, which builds and runs the real container (takes a minute or so; see [`DOCKER.md`](DOCKER.md)):

```bash
FINCHVOX_DOCKER_TESTS=1 uv run --extra dev pytest tests/test_docker.py
```

Lock file check, which confirms `uv.lock` still matches `pyproject.toml`:

```bash
uv lock --check
```

## Manual OTLP smoke test

With Finchvox running, `otel-cli` can send a trace without either voice framework:

```bash
otel-cli span \
  --endpoint localhost:4317 \
  --name agent_session \
  --service livekit-smoke-test
```

For a realistic LiveKit session, use [`examples/livekit/agent.py`](../examples/livekit/agent.py) and follow [`LIVEKIT_LOCAL_SETUP.md`](LIVEKIT_LOCAL_SETUP.md).

The automated tests and smoke checks above use local fixtures and synthetic sessions. They do not exercise a real LiveKit room or the speech, LLM and TTS providers, which need credentials and network access. Before a release, run the example against your own LiveKit deployment as an end-to-end check.

## UI work

The session inspector is intentionally framework-aware rather than a generic OpenTelemetry viewer. The main files are:

```text
ui/sessions_list.html, ui/session_detail.html, ui/settings.html
ui/css/app.css               themes, layout and the responsive breakpoints
ui/css/local-utilities.css   the small set of utility classes the pages use
ui/images/icons.svg          line icons, used as <svg><use href="/images/icons.svg#play"/></svg>
ui/js/session_detail.js      the session page: player, timeline, trace tree, inspector
ui/js/conversation.js, logs_view.js, metrics_view.js, environment_view.js
ui/js/sessions_list.js, preferences.js, settings.js, time-utils.js
```

The important interaction invariant is **one shared session clock**. Audio, transcript rows, trace bars, log rows, error markers, tools, and handoffs should all seek/highlight against the same session-relative time.

The page has no build step, and `local-utilities.css` is hand-written, not generated: a utility class you add to the HTML must also be defined there.

When upgrading `livekit-agents`, run the full suite. `tests/test_livekit_observability_url.py` drives the installed SDK's own uploaders (its OTLP exporters and session-recording upload) against a running Finchvox. LiveKit does not document that upload path, so this test is how a changed format shows up.

When changing LiveKit span normalization, add or update tests in `tests/test_adapters.py` and the `test_livekit_*` files. The adapter follows the span and attribute names of LiveKit Agents 1.8.9 and newer; check new names against the installed SDK source rather than adding names from older releases.

If Finchvox is running in Docker, rebuild it (`docker compose up -d --build`) to see UI or code changes there; the container serves the copy built into the image.

### Themes, text size and preferences

- **Colours** that differ between themes are CSS variables at the top of `ui/css/app.css`. The Insights values are in `:root`, and Classic overrides them in `:root[data-palette="classic"]`. A new themed colour needs a variable with a value in both. Neutral white-on-dark shades are written directly, since every theme is dark.
- **Canvas drawings** cannot use CSS: the waveform and Metrics charts read the variables through `FinchvoxPreferences.cssToken()`, and are redrawn when the theme changes (`applyPreferences` in `session_detail.js`). Chart colours must be `#rrggbb`, because the chart fill adds an alpha suffix.
- **Font sizes** are written as `calc(13px * var(--text-scale))`, so the text-size setting scales them. A plain `px` size will not follow the setting.
- **Preferences** live in the browser (`localStorage`). They are loaded by `ui/js/preferences.js`, which every page includes in `<head>` before its stylesheet, so the theme applies before the page is drawn. The settings page is `ui/settings.html` with `ui/js/settings.js`. Server settings are shown read-only from `GET /api/settings/server` (`src/finchvox/server_info.py`). Do not make them writable without adding authentication, because any website could send that request to a local Finchvox.

### Vendored browser libraries

The UI uses **Alpine.js 3.17.5**, **WaveSurfer.js 8.0.3**, and **Chart.js 4.6.1**.
Assets are served locally from `ui/lib`; there is no frontend build step, runtime
CDN requirement, or htmx dependency.

Exact sources, archive integrity, distribution payload hashes, and license sources
are pinned in `ui/lib/vendor-manifest.json`. Reproduce or verify them with:

```bash
uv run python scripts/vendor_browser_dependencies.py
uv run python scripts/vendor_browser_dependencies.py --check
```

These maintenance commands require network access. `--check` never writes files.
The updater verifies all sources before writing assets and `THIRD_PARTY_LICENSES.txt`,
and preserves upstream payloads byte-for-byte after a provenance banner. To update a
version, review its official release/migration notes, independently verify the new
archive integrity and payload hashes, and update the manifest and any embedded
dependency license sources before regenerating. Embedded dependency versions must
come from the released bundle, not just dependency ranges in npm metadata.

Keep native player/chart objects outside Alpine's proxies. Use the shallow-frozen
holders and `getAudioPlayer()` method; a JavaScript getter returning the player is
re-proxied by Alpine. Destroyed WaveSurfer 8 instances must never be reused. Catch
load/playback rejections and release events/charts during teardown.

### Browser smoke checklist

Use disposable/synthetic sessions rather than modifying real recordings. After a
library upgrade, load fresh assets (disable the browser cache or hard-refresh), then:

- Open the sessions list and toggle the import panel; check initialization happens once.
- Decode a stereo recording; check both channels, play/pause, waveform/keyboard seeks,
  seeking to zero, and transcript/trace/log clock alignment.
- Switch inspector tabs; render STT, LLM, TTS and turn-latency charts, hover points,
  select their spans, and verify audio seeking.
- Destroy/recreate the player and charts; reload audio twice rapidly to exercise
  cancellation. Check no duplicate hover/keyboard listeners or reused destroyed objects.
- Exercise retained-page (`pagehide.persisted`) pause and final teardown separately.
- Open a session without audio: the fallback should appear and the rest of the
  inspector remain usable. Its handled audio 404 is expected, not an uncaught failure.
- Inspect browser errors/console and server logs. Passing stub tests alone does not
  validate actual audio or canvas rendering; test other target browsers separately.

## Test fixtures and screenshots

The README screenshots live under `docs/`:

```text
livekit-insights-sessions.png
livekit-insights-transcript.png
livekit-insights-trace.png
```

They predate the November 2026 UI refresh (larger text, icons, settings, responsive layout), so they no longer match the current look. Retake them from a synthetic session, not a real call: the repository is public, and a real session shows transcripts.
