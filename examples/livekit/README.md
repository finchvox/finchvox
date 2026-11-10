# LiveKit Agent example with local Finchvox observability

This example shows the minimal integration for exporting **LiveKit Agents** telemetry to a Finchvox server running on your machine.

For the complete explanation—including privacy, LiveKit Cloud vs self-hosted behavior, audio recording, Docker networking, and troubleshooting—see [`../../docs/LIVEKIT_LOCAL_SETUP.md`](../../docs/LIVEKIT_LOCAL_SETUP.md).

## 1. Create the example environment

Use Python 3.12–3.14 and LiveKit Agents 1.8.9+.

From the repository root:

```bash
cd examples/livekit
uv sync
```

The example's `pyproject.toml` installs the repository root as an editable `finchvox[livekit]` dependency, so edits to Finchvox are picked up immediately.

## 2. Configure LiveKit

Create `examples/livekit/.env` with your LiveKit project's credentials (`agent.py` loads it with `python-dotenv`):

```bash
LIVEKIT_URL=wss://<your-project>.livekit.cloud
LIVEKIT_API_KEY=<key>
LIVEKIT_API_SECRET=<secret>
```

The example's speech, language and voice models run on LiveKit Inference, which uses these same credentials, so no other provider keys are needed. LiveKit Inference is part of LiveKit Cloud; on a self-hosted LiveKit server, swap the `inference.*` models for provider plugins and add their keys. The `.env` file is git-ignored; do not commit it.

## 3. Start Finchvox

In terminal 1, from `examples/livekit`:

```bash
uv run finchvox start --data-dir ../../.finchvox-data
```

Open `http://localhost:3000`.

The collector listens for OTLP/gRPC traces and logs on `localhost:4317`.

## 4. Start the agent

In terminal 2, also from `examples/livekit`:

```bash
uv run python -m livekit.agents download-files
uv run python -m livekit.agents start agent.py --dev
```

Join the room with your normal LiveKit client/playground and talk to the agent.

## What the example does

`agent.py` adds two lines to an ordinary LiveKit agent:

1. `finchvox.init_livekit()` before the session starts, which exports OpenTelemetry traces and Python logs to `localhost:4317`; and
2. `on_session_end=on_session_end` on `@server.rtc_session`, which flushes the telemetry and uploads the final `SessionReport` (plus a local recording when the report names one) to Finchvox when the session ends.

The session then appears in the Finchvox UI with synchronized **Transcript**, **Trace**, **Logs**, and **Metrics** views.

## PII/content

The example uses `allow_pii=True` so a local replay can display transcript, model, and tool content. Set it to `False` to strip content from exported spans. This does not redact separately exported logs, uploaded SessionReports, or audio.

Treat `../../.finchvox-data` as sensitive when PII is enabled because it may contain transcript text, tool payloads, logs, and audio.

## Audio and LiveKit recording

OTel does not contain replayable room audio. `on_session_end` automatically attaches `report.audio_recording_path` when LiveKit produced a finalized local recording.

LiveKit's own `record=` option is independent from the custom Finchvox exporter. If the agent is connected to LiveKit Cloud, do not assume `record=True` is local-only. See the full setup guide before choosing recording settings for a privacy-sensitive deployment.

## Docker/container note

Build from the repository root so the image installs this fork, not the public PyPI package:

```bash
docker build -f examples/livekit/Dockerfile -t finchvox-livekit-agent .
```

The image installs the root lockfile's LiveKit extra with `uv` and starts the agent using the current module-based CLI. Pass credentials at runtime rather than copying `.env` into the image. Image builds and model downloads require network access.

If the agent runs in a container and Finchvox runs elsewhere, `localhost:4317` points at the agent container and is usually wrong. Point `init_livekit(endpoint=...)` at the Finchvox container/service name, for example `http://finchvox:4317`; `on_session_end` then uploads to port 3000 on the same host.
