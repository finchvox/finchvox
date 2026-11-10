# syntax=docker/dockerfile:1
# Build with repository-root context:
# docker build -f examples/livekit/Dockerfile -t finchvox-livekit-agent .
ARG PYTHON_VERSION=3.13
FROM python:${PYTHON_VERSION}-slim
COPY --from=ghcr.io/astral-sh/uv:0.13.5 /uv /uvx /usr/local/bin/

ENV PYTHONUNBUFFERED=1 \
    UV_PYTHON_DOWNLOADS=never \
    UV_LINK_MODE=copy \
    PATH="/app/.venv/bin:$PATH"

RUN apt-get update && apt-get install -y --no-install-recommends libgomp1 \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /app

# Explicit copies exclude credentials, local environments, and recordings.
COPY pyproject.toml uv.lock README.md LICENSE ./
COPY src ./src
COPY ui ./ui
RUN uv sync --locked --no-dev --extra livekit --no-editable
COPY examples/livekit/agent.py ./agent.py

ARG UID=10001
RUN useradd --uid "${UID}" --home-dir /app --shell /usr/sbin/nologin appuser \
    && chown -R appuser:appuser /app
USER appuser

RUN python -m livekit.agents download-files
CMD ["python", "-m", "livekit.agents", "start", "agent.py"]
