# Working on Finchvox

Instructions for AI coding agents (and humans) changing this repository. Finchvox is a local session replay for voice agents: a Python server (FastAPI plus an OTLP/gRPC collector) and a no-build-step web UI in `ui/`. Start with `README.md`; the guides are in `docs/`.

## Focus: LiveKit first, Pipecat kept working

- **LiveKit is what this fork develops.** New features target LiveKit Agents.
- **Pipecat is maintained, not extended.** Keep it working and fix what breaks, but don't add Pipecat-only features. Removing Pipecat to make Finchvox LiveKit-only is the planned next step, a long way off; until then, keep its code easy to delete.
- **Platform logic lives in the adapters**: `src/finchvox/adapters/livekit.py` and `adapters/pipecat.py`. Shared code (`metrics.py`, `conversation.py`, the UI) reads the adapter's common `_normalized` fields; don't add `if platform == ...` branches there.
- **Pipecat-only code stays in its own files**: `processor.py`, `adapters/pipecat.py`, the chunked-audio path (`audio_compressor.py`, `scheduler.py`), `examples/pipecat/`.
- `tests/test_pipecat_session.py` checks a synthetic Pipecat session through the HTTP API on every run, without Pipecat installed. If a shared-code change breaks it, fix the shared code rather than the test.
- Before a release or a merge from upstream, run the real Pipecat SDK tests once: `uv run --extra livekit --extra pipecat --extra dev pytest tests/test_processor.py tests/test_voice_sdk_compat.py tests/test_pipecat_session.py`. In a normal environment `test_processor.py` is skipped, because Pipecat is not installed.

## Setup and checks

- Use `uv`, never `pip`: `uv sync --extra livekit --extra dev`.
- Before calling a change done: `uv run pytest -q` and `uv run ruff check src tests`. After UI changes also run `for f in ui/js/*.js; do node --check "$f"; done`.
- `docs/DEVELOPMENT.md` has the targeted test commands, the Docker smoke test and the browser checklist.

## How to make a change

- **Test first.** Add a failing test that shows the bug or the new behaviour, then make it pass. Every fix and feature gets a test.
- **Check it for real.** Unit tests are not enough for anything a user sees: run the server, use the page or the endpoint, and say what you checked. If Finchvox runs in Docker, rebuild it (`docker compose up -d --build`) first, because the container serves the copy built into the image.
- **Simplify before patching.** If a fix stacks a layer on top of a workaround, prefer removing the workaround. Delete code that nothing calls.
- **Use what the framework gives you** (FastAPI, Starlette, Alpine.js, the LiveKit SDK) before writing your own. Check the official docs or the installed package source; don't guess from names.
- **Stay in scope.** Note problems you find outside the task and report them; don't fix them silently.
- **Report honestly.** Say what was verified, what was not, and any test that failed.
- Commit or push only when asked.

## Code conventions

- Keep `src/finchvox/ui_routes.py` and `collector_routes.py` thin. Put logic in classes such as `src/finchvox/session.py`.
- LiveKit support starts at Agents 1.8.9. Take span and attribute names from the installed SDK, not from older releases or memory. LiveKit-specific rules belong in `src/finchvox/adapters/livekit.py`.
- Code that runs inside the user's agent during a call or its shutdown (span processors, `on_session_end`) must log errors, never raise them: observability must not break the agent.
- Log errors with `logger.exception(...)` (Loguru), not `exc_info=True`.

## UI conventions

- No build step and no CDN. `ui/css/local-utilities.css` is hand-written: a utility class used in HTML must be defined there.
- Theme colours are CSS variables in `ui/css/app.css`; font sizes use `calc(<px> * var(--text-scale))`.
- Icons come from `ui/images/icons.svg` (`<svg class="icon"><use href="/images/icons.svg#play"/></svg>`), not text symbols.
- Check narrow widths (phone and tablet) as well as desktop.
- Text shown with `x-text` must be plain text, never HTML.

## Privacy

Sessions contain transcripts, tool payloads and audio. Never commit real session data: use synthetic sessions for tests, fixtures and screenshots. Finchvox has no login, so keep it bound to `127.0.0.1` and don't add writable settings endpoints without authentication.

## Docs

- Update `CHANGELOG.md` for every user-visible change, and the guide in `docs/` that describes it.
- Keep docs true to the code: when you change behaviour, search the docs for the old behaviour.
- Write plainly: short sections, explain each technical term the first time it appears, and give one concrete example.
