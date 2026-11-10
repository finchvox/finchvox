# syntax=docker/dockerfile:1
# The Finchvox server: UI, HTTP uploads and the OTLP/gRPC collector.
# Usually started with `docker compose up -d`; see docs/DOCKER.md.

ARG PYTHON_VERSION=3.13

# Stage 1 installs dependencies, then Finchvox itself, into /app/.venv.
FROM python:${PYTHON_VERSION}-slim AS builder
COPY --from=ghcr.io/astral-sh/uv:0.13.5 /uv /bin/uv
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=0
WORKDIR /app

# Uvicorn's optional "standard" packages, left out of the image only. Finchvox
# uses just two (faster event loop and HTTP parsing), and only for the UI and
# uploads; without them Uvicorn uses Python's built-in ones. This saves about
# 24 MB. pyproject.toml and uv.lock still list them. See docs/DOCKER.md.
ARG SKIP_PACKAGES="--no-install-package uvloop --no-install-package httptools \
--no-install-package websockets --no-install-package watchfiles \
--no-install-package pyyaml --no-install-package python-dotenv"

# Dependencies first, so this layer is reused until uv.lock changes. No extras:
# the server does not need the LiveKit or Pipecat SDKs.
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    uv sync --locked --no-install-project --no-dev --no-editable ${SKIP_PACKAGES}

COPY pyproject.toml uv.lock README.md LICENSE ./
COPY src ./src
COPY ui ./ui
# uv reuses a cached build of a local project until pyproject.toml changes, so
# a rebuild would otherwise install the previous src/ and ui/ files.
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev --no-editable --reinstall-package finchvox ${SKIP_PACKAGES}

# Stage 2 runs it, with only the finished environment: no uv, no source tree.
FROM python:${PYTHON_VERSION}-slim

# ffmpeg is only needed to compress Pipecat audio chunks into audio.opus.
# LiveKit uploads finished recordings, so it is left out unless requested.
ARG INSTALL_FFMPEG=false
RUN if [ "$INSTALL_FFMPEG" = "true" ]; then \
        apt-get update \
        && apt-get install -y --no-install-recommends ffmpeg \
        && rm -rf /var/lib/apt/lists/*; \
    fi

# A non-root user that owns /data before any volume is mounted there, so the
# server can write sessions on first start.
ARG UID=10001
RUN useradd --uid "${UID}" --create-home --shell /usr/sbin/nologin finchvox \
    && mkdir -p /data \
    && chown finchvox:finchvox /data

COPY --from=builder --chown=finchvox:finchvox /app/.venv /app/.venv
ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1

USER finchvox
WORKDIR /data
EXPOSE 3000 4317

# The slim image has no curl, so the check uses Python.
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:3000/collector/health', timeout=4)"]

# Started directly, not through `uv run`, so `docker stop` reaches the
# server's own shutdown handler. --host 0.0.0.0 lets traffic in from outside
# the container; compose.yaml keeps the published ports private to the host.
CMD ["finchvox", "start", "--host", "0.0.0.0", "--data-dir", "/data"]
