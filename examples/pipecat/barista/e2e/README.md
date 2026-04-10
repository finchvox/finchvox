# E2E Bot Conversation Test

Runs two pipecat bots (barista + customer) in a shared Daily room to exercise the full OTEL-instrumented pipeline. The barista reports traces to finchvox.

## Setup

```bash
cd examples/pipecat/e2e
cp env.example .env
# Fill in API keys
uv sync
```

## Usage

Start the finchvox server, then:

```bash
uv run python run.py
```

The customer bot orders a large oat milk latte and a blueberry muffin. When the barista submits the order, both bots disconnect and the script exits. Open the finchvox UI to inspect traces.

Set `E2E_TIMEOUT` to override the default 120s timeout:

```bash
E2E_TIMEOUT=60 uv run python run.py
```
