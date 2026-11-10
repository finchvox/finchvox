# Finchvox tracing for Pipecat

This demo shows the original Pipecat session-recording workflow retained by this fork.

## Setup

### 1. Install Finchvox with Pipecat support

See the main [`README.md`](../../../README.md), then install the optional Pipecat extra:

```bash
uv sync --extra pipecat
```

### 2. Configure the environment

```bash
cp env.example .env
```

Fill in the provider credentials required by the demo. Do not commit the populated `.env` file.

### 3. Install the demo dependencies

From this directory:

```bash
uv sync
```

### 4. Run Finchvox and the demo

Start Finchvox in one terminal:

```bash
finchvox start
```

Run the bot in another:

```bash
uv run bot.py
```

### 5. Inspect the replay

Open `http://localhost:3000` to inspect captured sessions.

For LiveKit Agents, use [`../../livekit/README.md`](../../livekit/README.md) instead.
