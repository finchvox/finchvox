# LiveKit Agents + Finchvox: local observability setup

This guide connects a **LiveKit Agents (Python)** application to Finchvox so you can inspect sessions locally with a synchronized waveform, transcript, trace waterfall, logs, tool calls, handoffs, errors, and voice latency metrics.

Finchvox is the observability backend in this setup. Your agent exports OpenTelemetry directly to a Finchvox process you control.

> Finchvox is an independent open-source project/fork. It is not affiliated with or endorsed by LiveKit.

## What stays local

With the setup in this guide:

- custom OpenTelemetry traces are exported to your Finchvox collector (`localhost:4317` by default),
- stdlib logs can be exported to the same local collector,
- LiveKit `SessionReport` data can be uploaded to the local Finchvox HTTP server,
- finalized session audio can be attached to the local replay,
- Finchvox stores session files under `~/.finchvox` (or a directory you choose), and
- Finchvox anonymous product telemetry is disabled by default in this fork.

There is one important distinction: **LiveKit media transport and LiveKit Cloud observability are separate from Finchvox**. If your agent connects to LiveKit Cloud, the media still uses LiveKit Cloud. Whether LiveKit's own observability is uploaded depends on your LiveKit session/recording configuration. See [LiveKit Cloud while keeping custom telemetry in Finchvox](#livekit-cloud-while-keeping-custom-telemetry-in-finchvox) below.

## Two ways to connect

| | Two lines of code (sections 3–5) | No code: one environment variable (section 12) |
|---|---|---|
| What you change | Add `init_livekit()` and `on_session_end` to the agent | Set `LIVEKIT_OBSERVABILITY_URL` in the agent's `.env` |
| LiveKit Cloud's dashboard | Keeps receiving its own copy | Receives nothing from the agent |
| Self-hosted LiveKit | Works as is | Also needs `record=True` in `session.start()` |
| How it relies on LiveKit | Documented SDK features | An SDK setting LiveKit does not document; Finchvox tests it against each supported SDK version |

Use one or the other, not both: with both, every span reaches Finchvox twice.

## Prerequisites

- Python 3.12–3.14
- `uv` (recommended) or `pip`
- a working LiveKit Agents Python project
- a LiveKit server (LiveKit Cloud or self-hosted)

Finchvox needs LiveKit Agents 1.8.9 or newer. It reads the `lk.pii.*` and GenAI telemetry attributes those releases write, and does not read the attribute names used before 1.8. The span and attribute names were last checked against 1.8.11.

## 1. Install the fork

In your agent's project, install it from this fork's GitHub repository:

```bash
uv add "finchvox @ git+https://github.com/Abdo-Eid/finchvox.git@livekit-agents"
```

or with pip:

```bash
pip install "finchvox @ git+https://github.com/Abdo-Eid/finchvox.git@livekit-agents"
```

This installs the library your agent imports and the `finchvox` command that runs the server. Always include the Git URL: plain `pip install finchvox` installs the original project from PyPI, which has none of the LiveKit support described here.

If Finchvox is checked out next to your agent, an editable install picks up its changes without reinstalling:

```bash
cd /path/to/your-agent
uv add --editable ../finchvox
```

To run the server without installing it into your agent, use Docker instead (section 8 and [`DOCKER.md`](DOCKER.md)).

## 2. Start Finchvox locally

In a separate terminal:

```bash
uv run finchvox start
```

Open:

```text
http://localhost:3000
```

Default endpoints:

| Purpose | Endpoint |
| --- | --- |
| UI + HTTP API | `http://localhost:3000` |
| OTLP/gRPC traces + logs | `http://localhost:4317` |
| SessionReport auto-correlation | `POST http://localhost:3000/collector/livekit/report` |
| SessionReport for a known trace | `POST http://localhost:3000/collector/livekit/{trace_id}/report` |
| Finished recording | `POST http://localhost:3000/collector/livekit/{trace_id}/audio` |
| No-code hookup (section 12) | `POST http://localhost:3000/observability/{traces,logs,metrics}/otlp/v0` and `/observability/recordings/v0` |

Finchvox binds HTTP and OTLP/gRPC to `127.0.0.1` by default, so it is not exposed to your LAN unless you opt in.

To keep the data with your project instead of in your home directory:

```bash
uv run finchvox start --data-dir ./.finchvox-data
```

## 3. Add Finchvox to your LiveKit agent

Two lines connect an agent to Finchvox. To connect without changing the agent's code, see section 12 instead.

```python
import finchvox
from finchvox.livekit import on_session_end

finchvox.init_livekit(service_name="my-livekit-agent")


@server.rtc_session(on_session_end=on_session_end)
async def entrypoint(ctx: JobContext):
    ...
```

Call `init_livekit()` **before the `AgentSession` starts**. It creates an OpenTelemetry `TracerProvider`, sends spans to the local OTLP/gRPC collector, and registers it with LiveKit via `livekit.agents.telemetry.set_tracer_provider()`. Its other options:

```python
finchvox.init_livekit(
    service_name="my-livekit-agent",
    endpoint="http://localhost:4317",   # the default
    capture_logs=True,                  # the default; see section 10
    allow_pii=True,                     # the default; see below
    metadata={"environment": "local"},
    http_endpoint=None,                 # the default: port 3000 on the same host
)
```

`http_endpoint` is where reports, recordings and environment details go. Set it only when Finchvox's HTTP port is not 3000, for example `http_endpoint="http://localhost:3991"` when the container was started with `FINCHVOX_HTTP_PORT=3991`.

`init_livekit()` also remembers its provider and endpoint, so `flush_livekit()` and `on_session_end` need no arguments.

### About `allow_pii`

For a local Agent-Insights-style replay, `allow_pii=True` is normally what you want. It lets your custom exporter receive the content attributes LiveKit uses for transcripts, model responses, tool inputs/results, and related conversational details.

If you only want timing, model, token, and structural telemetry:

```python
finchvox.init_livekit(
    service_name="my-livekit-agent",
    allow_pii=False,
)
```

With the supported LiveKit Agents 1.8.9+ baseline, this strips span content before it reaches the custom exporter. It does not redact separately exported logs, uploaded SessionReports, or recordings. The Trace and Metrics views still work, but the trace-derived transcript/tool-content experience is intentionally reduced.

## 4. What `on_session_end` does

The LiveKit SDK can generate a `SessionReport` entirely inside your agent process. It contains final conversation history, events, usage/metrics, identifiers, and recording metadata. When the session ends, `finchvox.livekit.on_session_end`:

1. builds that report with `ctx.make_session_report()`;
2. flushes the batched traces and logs, so Finchvox can match the report to the trace that just ended (by LiveKit job ID, room SID, or room name);
3. uploads the report, plus the recording it names, to Finchvox; and
4. schedules one more flush for the spans LiveKit ends after `on_session_end`, such as the room disconnect.

Any error is logged, never raised, so Finchvox cannot break the job's shutdown. That includes Finchvox not running, and `make_session_report()` failing while LiveKit's recorder is still recording. LiveKit runs your `on_session_end` before its own Cloud upload, so LiveKit Cloud still receives its copy.

## 5. If you already have an `on_session_end`

Call `finalize_session` from your own callback. It does the same steps and returns the Finchvox trace ID, or `None` if something failed:

```python
from finchvox.livekit import finalize_session


async def on_session_end(ctx: JobContext) -> None:
    ...  # your own code
    trace_id = await finalize_session(ctx)
```

It also accepts `audio_path=` for a recording of your own and `endpoint=` for the Finchvox HTTP address. By default it uses port 3000 on the host given to `init_livekit()`, so an agent configured with `endpoint="http://host.docker.internal:4317"` uploads to `http://host.docker.internal:3000`.

`upload_session_artifacts()` remains available when you need full control, for example to upload a report you built yourself.

## 6. Complete example

```python
import finchvox
from finchvox.livekit import on_session_end
from livekit.agents import Agent, AgentServer, AgentSession, JobContext, inference

finchvox.init_livekit(service_name="my-livekit-agent")


class Assistant(Agent):
    def __init__(self) -> None:
        super().__init__(
            instructions="You are a concise, helpful voice assistant.",
            stt=inference.STT(model="deepgram/nova-3"),
            llm=inference.LLM(model="google/gemma-4-31b-it"),
            tts=inference.TTS(model="cartesia/sonic-3"),
        )


server = AgentServer()


@server.rtc_session(on_session_end=on_session_end)
async def entrypoint(ctx: JobContext):
    # AgentSession uses LiveKit's bundled Silero VAD by default.
    session = AgentSession()
    await session.start(agent=Assistant(), room=ctx.room)


# Save as agent.py, then launch it locally with:
# uv run python -m livekit.agents start agent.py --dev
```

A runnable version lives in [`examples/livekit/agent.py`](../examples/livekit/agent.py). The `inference.*` models run on LiveKit Inference, which needs a LiveKit Cloud project; your `LIVEKIT_API_KEY` and `LIVEKIT_API_SECRET` are enough, with no separate provider keys. On a self-hosted LiveKit server, use provider plugins instead.

## 7. Audio replay

OpenTelemetry spans do **not** contain replayable audio. Finchvox therefore treats audio as a separate session artifact.

### Fully self-hosted LiveKit

On current LiveKit Agents releases, session recording can create a local OGG file inside the job session directory. The resulting `SessionReport` exposes its path as `audio_recording_path`. If that path is present, `on_session_end` uploads it to Finchvox automatically.

Make recording explicit when you want it:

```python
await session.start(
    agent=Assistant(),
    room=ctx.room,
    record={
        "audio": True,
        "transcript": True,
        "traces": False,
        "logs": False,
    },
)
```

For a self-hosted LiveKit server, LiveKit's Cloud observability endpoint is unavailable, while the SDK can still produce the local report/recording used by Finchvox.

### LiveKit Cloud while keeping custom telemetry in Finchvox

Your custom OpenTelemetry exporter still sends its copy of traces to Finchvox. However, LiveKit's `record` settings control LiveKit Cloud observability too. If your requirement is **no session audio/transcript upload to LiveKit Cloud**, use the LiveKit settings appropriate for that requirement (for example `record=False`) and attach audio to Finchvox from your own local recorder instead:

```python
await finalize_session(ctx, audio_path="./recordings/session.ogg")
```

Do not assume `record=True` is local-only when your agent is connected to LiveKit Cloud.

Supported finalized Finchvox audio formats:

```text
.wav  .mp3  .ogg  .flac  .opus  .webm  .m4a
```

## 8. Running agent and Finchvox in Docker

To run only Finchvox in Docker, use this repository's `compose.yaml` (`docker compose up -d --build`). It publishes the same ports on this machine, so an agent running outside Docker needs no changes. Settings, backups and Windows notes are in [`DOCKER.md`](DOCKER.md).

If the **agent** runs in a container, `localhost` inside it means the agent container itself, not Finchvox.

A Finchvox you run in a container yourself must listen with `--host 0.0.0.0`, because the default loopback bind accepts connections only from inside that container. The repository's image already does this. Do not publish the ports to an untrusted network without adding authentication/TLS or a trusted reverse proxy.

If both containers share a Docker network, point the agent at the Finchvox service name (`finchvox` in this repository's `compose.yaml`). `on_session_end` then sends reports and recordings to `http://finchvox:3000` automatically:

```python
finchvox.init_livekit(endpoint="http://finchvox:4317")
```

If Finchvox runs on the host and your agent runs in Docker Desktop, `host.docker.internal` is commonly available:

```text
http://host.docker.internal:4317
http://host.docker.internal:3000
```

On Linux, use an explicit host-gateway mapping or put both services on the same Docker network.

## 9. What Finchvox recognizes from LiveKit

The local trace adapter understands the spans LiveKit Agents 1.8 creates, including:

```text
agent_session
├── user_turn
│   ├── user_speaking
│   ├── eou_wait / eou_detection
│   └── keyterm_detection
├── agent_turn
│   ├── llm_request (llm_fallback_adapter when a fallback chain is used)
│   ├── function_tool
│   └── tts_request (tts_fallback_adapter / tts_stream_adapter)
├── update_agent          # handoff
├── event_loop_blocked    # the agent's event loop was blocked (red bar)
├── amd                   # answering machine detection
└── room_connect / wait_for_audio_track
```

Lifecycle spans such as `job_entrypoint`, `on_enter`, `session_close` and `rpc_call` are kept in the trace but hidden from the timeline unless they fail.

The **Metrics** tab also shows, when the agent provides them:

- blocked moments of the agent's event loop, with the task that blocked it,
- how long LiveKit took to dispatch the job to the agent,
- per-model usage (tokens, characters, audio seconds) from the uploaded `SessionReport`.

When emitted by the SDK, the UI also surfaces:

- end-to-end response latency,
- transcription delay,
- end-of-turn / endpointing delay,
- LLM time to first token/chunk,
- TTS time to first byte,
- speech/generation IDs,
- interruption state,
- tool arguments/results,
- model/provider names,
- token usage,
- exceptions and error spans,
- job/room/participant identifiers.

## 10. Logs

`capture_logs=True` adds an OpenTelemetry stdlib logging handler. Logs emitted while a LiveKit span is active retain trace/span correlation when the context is available and show up in Finchvox's **Logs** tab.

Use normal structured Python logging:

```python
logger = logging.getLogger("my-agent")
logger.info("calling booking service", extra={"booking_id": booking_id})
```

Disable local OTLP logs while keeping traces:

```python
finchvox.init_livekit(capture_logs=False)
```

## 11. Data directory and cleanup

Default data directory:

```text
~/.finchvox/
```

Project-local directory:

```bash
finchvox start --data-dir ./.finchvox-data
```

Finchvox stores each session under its trace ID. Treat this directory as potentially sensitive when `allow_pii=True`, because it can contain transcripts, tool payloads, logs, and recordings.

## 12. No-code hookup with `LIVEKIT_OBSERVABILITY_URL`

LiveKit Agents normally uploads its own observability data (traces, logs, metrics, the transcript and the recording) to LiveKit Cloud. The SDK reads the upload address from the `LIVEKIT_OBSERVABILITY_URL` environment variable and only falls back to LiveKit Cloud when it is unset. Point it at Finchvox and the same uploads arrive there, with no change to the agent's code:

```bash
# in the agent's .env
LIVEKIT_OBSERVABILITY_URL=http://localhost:3000
```

Only Finchvox's HTTP port is used. Start the agent as usual; the session appears in Finchvox with its trace, logs, transcript and recording.

### What Finchvox receives

| Upload | Path | What Finchvox does with it |
|---|---|---|
| Traces | `/observability/traces/otlp/v0` | Stores them like spans sent over gRPC |
| Logs | `/observability/logs/otlp/v0` | Stores them like logs sent over gRPC |
| Recording | `/observability/recordings/v0` | Reads the session report and chat history it contains, matches them to the trace by job ID, and stores the report and the audio |
| Metrics | `/observability/metrics/otlp/v0` | Accepts them, but does not store them yet |

LiveKit sends the recording as soon as the session ends, while spans are uploaded in batches every few seconds. If the recording arrives first, Finchvox waits up to 20 seconds for the session's spans before answering.

Each upload carries a token that LiveKit signs with your API secret. Finchvox ignores it and never stores it; checking it would mean giving Finchvox your LiveKit API secret. As everywhere else, Finchvox relies on listening only on your own machine.

### When LiveKit uploads

LiveKit only uploads while session recording is on:

- **LiveKit Cloud:** when the agent does not pass `record=` to `session.start()`, your project's recording setting decides.
- **Self-hosted LiveKit:** there is no project setting, so the agent must turn recording on itself:

  ```python
  await session.start(agent=Assistant(), room=ctx.room, record=True)
  ```

`record` also accepts a dict to choose what is sent, for example `record={"audio": False}` for everything but the audio, or `record={"redaction": True}` to have LiveKit redact conversation content before it leaves the agent. `allow_pii` belongs to `init_livekit()` and does not apply here.

### Things to know

- **Use this or the two-line hookup, not both.** With both, LiveKit's uploader also attaches to the tracer `init_livekit()` created, and every span arrives twice. `init_livekit()` logs a warning when `LIVEKIT_OBSERVABILITY_URL` is set.
- **LiveKit Cloud's dashboard receives nothing** from the agent while the variable is set. The call's media still goes through your LiveKit server, and `inference.*` models still run on LiveKit Cloud.
- **LiveKit does not document this setting.** A future SDK release could change it. Finchvox's test suite drives the installed SDK's own uploaders against Finchvox, so run it after upgrading `livekit-agents` (see [`DEVELOPMENT.md`](DEVELOPMENT.md)).
- **In Docker**, an agent container reaches a Finchvox container through its service name, for example `LIVEKIT_OBSERVABILITY_URL=http://finchvox:3000` (section 8).

## 13. Troubleshooting

### Session never appears

Check that:

1. Finchvox is running and `localhost:4317` is reachable from the agent process. On Windows, also open `http://localhost:3000/collector/health`: if something other than Finchvox answers, such as a web dev server on port 3000, move Finchvox to another port and pass `http_endpoint=` ([`DOCKER.md`](DOCKER.md#notes-for-windows)).
2. `finchvox.init_livekit()` runs before `session.start()`.
3. `on_session_end` is passed to `@server.rtc_session`, or your own callback calls `finalize_session`; either flushes at shutdown. If not, call `finchvox.flush_livekit()` before the job exits.
4. Docker/container networking is not pointing `localhost` at the wrong container.
5. The agent's log has no "Could not send the session to Finchvox" error.

### Trace appears but transcript content is missing

Confirm `allow_pii=True`. Current LiveKit SDKs mark conversational content under `lk.pii.*` and GenAI content attributes; `allow_pii=False` intentionally strips those fields before your exporter sees them.

### Trace appears but no audio waveform/playback

Traces do not contain audio. Attach a finalized recording, or enable a LiveKit recording path appropriate for your deployment and then upload the `SessionReport`.

### SessionReport upload returns 404 / cannot resolve trace

`on_session_end` flushes before uploading. If you upload yourself, flush first:

```python
finchvox.flush_livekit()
```

Then retry the report upload. Automatic correlation needs at least one completed span with matching LiveKit job/room identifiers. As a fallback, pass the known 32-character OTel trace ID explicitly.

### Logs are missing

Make sure `capture_logs=True` and your application uses Python `logging`. Some logs emitted outside an active span may not have trace correlation; they can still be exported, but a per-session UI cannot reliably assign an uncorrelated log to a session.

## References

- LiveKit export traces: https://docs.livekit.io/deploy/observability/tracing/
- LiveKit data hooks / SessionReport: https://docs.livekit.io/deploy/observability/data/
- LiveKit Agent Insights: https://docs.livekit.io/deploy/observability/insights/
- LiveKit Agents Python reference: https://docs.livekit.io/reference/python/livekit/agents/
