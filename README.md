# <img src="ui/images/finchvox-logo.png" height=24 /> Finchvox - Voice AI Observability, Elevated.

Meet Finchvox, local session replay purpose-built for Voice AI apps.

Finchvox unifies conversation audio, logs, traces, and metrics in a single UI, highlighting voice-specific problems like interruptions and high user <-> bot latency. Finchvox is currently designed for local, development usage.

Visit [Finchvox.dev](https://finchvox.dev) to signup for our production-ready hosted and self-hosted options.

_👇 Click the image for a short video:_
<a href="https://github.com/user-attachments/assets/f093e764-82ae-41cb-9089-4e2d19c7867f" target="_blank"><img src="./docs/screenshot.png" /></a>

## Table of Contents

- [Prerequisites](#prerequisites)
- [Installation](#installation)
- [Setup](#setup)
- [Configuration](#configuration)
- [Usage](#usage---finchvox-server)
- [Troubleshooting](#troubleshooting)
- [Telemetry](#telemetry)

## Prerequisites

- Python 3.11 or higher
- Pipecat 0.0.68 or higher

## Installation

```bash
# uv
uv add finchvox "pipecat-ai[tracing]"

# Or with pip
pip install finchvox "pipecat-ai[tracing]"
```

## Setup

1. Add the following to the top of your bot (e.g., `bot.py`):

```python
import finchvox
from finchvox import FinchvoxProcessor

finchvox.init(service_name="my-voice-app")
```

2. Add `FinchvoxProcessor` to your pipeline, ensuring it comes after `transport.output()`:

```python
pipeline = Pipeline([
    # SST, LLM, TTS, etc. processors
    transport.output(),
    FinchvoxProcessor(), # Must come after transport.output()
    context_aggregator.assistant(),
])
```

3. Initialize your `PipelineTask` with metrics, tracing and turn tracking enabled:

```python
task = PipelineTask(
    pipeline,
    params=PipelineParams(enable_metrics=True),
    enable_tracing=True,
    enable_turn_tracking=True,
)
```

## Configuration

The `finchvox.init()` function accepts the following optional parameters:

| Parameter      | Default                   | Description                                               |
| -------------- | ------------------------- | --------------------------------------------------------- |
| `endpoint`     | `"http://localhost:4317"` | Finchvox collector endpoint                               |
| `insecure`     | `True`                    | Use insecure gRPC connection (no TLS)                     |
| `capture_logs` | `True`                    | Send logs to collector alongside traces                   |
| `log_modules`  | `None`                    | Additional module prefixes to capture (e.g., `["myapp"]`) |

By default, logs from `pipecat.*`, `finchvox.*`, `__main__`, and any source files in your project directory are captured. Use `log_modules` to include additional third-party modules.

## Usage - Finchvox server

```bash
uv run finchvox start
```

For the list of available options, run:

```bash
uv run finchvox --help
```

## Troubleshooting

### No spans being written

1. Check collector is running: Look for "OTLP collector listening on port 4317" log message
2. Verify client endpoint: Ensure Pipecat is configured to send to `http://localhost:4317`

## Telemetry

FinchVox collects minimal, anonymous usage telemetry to help improve the project. No personal data, IP addresses, or session content is collected.

**What's collected:**

- Event type (`server_start`, `session_ingest`, `session_view`)
- FinchVox version
- Operating system (macOS, Linux, or Windows)
- Timestamp

**Disable telemetry:**

```bash
finchvox start --telemetry false
```

Or set the environment variable:

```bash
export FINCHVOX_TELEMETRY=false
```
