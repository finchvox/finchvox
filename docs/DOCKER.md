# Running Finchvox in Docker

The repository root has a `Dockerfile` and a `compose.yaml` for the Finchvox server: the UI, HTTP uploads and the OpenTelemetry collector. Your agent keeps running wherever it runs now; only Finchvox moves into a container.

## Start and stop

```bash
docker compose up -d --build
```

Then open <http://localhost:3000>. Other everyday commands:

```bash
docker compose logs -f          # follow the server output
docker compose restart          # restart the server
docker compose down             # stop; sessions are kept
```

`docker compose down -v` also deletes the `finchvox-data` volume, and with it **every recorded session**. Back up first if you need them.

## Connecting an agent

The container publishes the same ports Finchvox uses outside Docker, so an agent running on the same machine needs no changes:

| Port | What it carries | Agent setting |
|---|---|---|
| `localhost:4317` | traces and logs (OTLP/gRPC) | `finchvox.init_livekit(endpoint="http://localhost:4317")` |
| `localhost:3000` | UI, session reports and recordings | none: `finchvox.livekit.on_session_end` uses port 3000 on the same host |
| `localhost:3000` | Everything, for the no-code hookup | `LIVEKIT_OBSERVABILITY_URL=http://localhost:3000` in the agent's `.env`, instead of the two lines ([setup guide, section 12](LIVEKIT_LOCAL_SETUP.md#12-no-code-hookup-with-livekit_observability_url)) |

An agent running in **another** container cannot use `localhost`, because inside a container that means the container itself. With Docker Desktop, use `init_livekit(endpoint="http://host.docker.internal:4317")`; the session upload follows to port 3000 on that host.

## Privacy

Finchvox has no login, and sessions can contain transcripts, tool payloads and audio. `compose.yaml` therefore publishes both ports on `127.0.0.1` only, so other devices on your network cannot reach them. Inside the container the server must listen on `0.0.0.0`, otherwise no traffic gets in; that part is handled by the image. Before exposing Finchvox beyond your machine, put it behind something that adds authentication and TLS.

## Settings

`compose.yaml` reads these variables from your environment or from a `.env` file next to it:

| Variable | Default | Effect |
|---|---|---|
| `FINCHVOX_HTTP_PORT` | `3000` | Port for the UI and HTTP uploads on this machine |
| `FINCHVOX_GRPC_PORT` | `4317` | Port for traces and logs on this machine |
| `FINCHVOX_MAX_UPLOAD_MB` | `1024` | Largest session zip the UI accepts |
| `FINCHVOX_INSTALL_FFMPEG` | `false` | `true` adds ffmpeg; rebuild with `--build` |

If you change the ports, tell the agent too: `init_livekit(endpoint="http://localhost:<grpc port>", http_endpoint="http://localhost:<http port>")`.

These are Compose variables: Compose turns them into ports and command-line flags. Finchvox itself is configured only by flags; see [Later: environment-variable configuration](#later-environment-variable-configuration).

**ffmpeg** is only needed when sessions arrive as many small WAV chunks, which is how the Pipecat integration sends audio. Finchvox then compresses them into one `audio.opus`. LiveKit agents upload one finished recording instead, so they do not need it. The image is about 177 MB without ffmpeg and about 625 MB with it.

## Your data

Sessions are stored in a Docker named volume called `finchvox-data`, mounted at `/data` in the container. It survives restarts, rebuilds and `docker compose down`.

- **Back up** all sessions to a folder on this machine:

  ```bash
  docker compose cp finchvox:/data ./finchvox-backup
  ```

- **Move sessions in** from another Finchvox: download each session as a zip from that Finchvox (the download icon on a session page), then use **Import session** on this one's sessions list.

- **After changing Finchvox's code or UI**, run `docker compose up -d --build` again. The container serves the copy built into the image, not the files in this folder.

- **Temporary files** for downloads, uploads and merged playback audio are written inside the container, under `/tmp`. They are deleted when each request finishes, but while one is in progress it can take up to the size of that session. On Docker Desktop that space comes from Docker's own virtual disk, not directly from `C:` or `D:`.

## Notes for Windows

- **Check that port 3000 is really Finchvox's.** The container publishes its ports on `127.0.0.1`, IPv4 only. If another program, such as a Next.js or React dev server, listens on port 3000 over IPv6, Windows sends `http://localhost:3000` to that program, because `localhost` tries IPv6 first. Only `http://127.0.0.1:3000` reaches Finchvox, and agents uploading to `localhost:3000` fail. Check with `http://localhost:3000/collector/health`: Finchvox answers `{"status":"healthy","service":"finchvox-collector"}`. If something else answers, move Finchvox with `FINCHVOX_HTTP_PORT=3100` in a `.env` file next to `compose.yaml`, and give the agent `http_endpoint="http://localhost:3100"`.

- **Use the named volume, not a Windows folder.** It is possible to mount a folder such as `D:\finchvox-data` at `/data` instead, but Docker Desktop then passes every file operation through its virtual machine to Windows. Finchvox opens the trace file for each span it receives, so a busy session would write noticeably slower. The named volume lives inside Docker's own Linux disk and avoids that.
- **Replacing a recording while it plays.** On Windows without Docker, uploading a new recording while the old one is being played gets a `409`, and `upload_session_artifacts` retries for up to about 31 seconds. Inside the Linux container, replacing a file that is open is allowed, so this situation does not occur: the player keeps the old copy until it finishes and the upload succeeds at once.

## Testing the image

The configuration checks in `tests/test_docker.py` run with the normal test suite. The smoke test builds and runs the real container. It checks health, that the served UI files match this checkout, receives a span over OTLP, uploads and downloads a recording, runs as non-root, stops cleanly and keeps data across a restart. It takes a minute or so, so it only runs when asked:

```bash
FINCHVOX_DOCKER_TESTS=1 uv run --extra dev pytest tests/test_docker.py
```

In PowerShell, set the variable first with `$env:FINCHVOX_DOCKER_TESTS = "1"`.

## Image size

**Decided on 2026-11-07: variant B.** The `Dockerfile` leaves out Uvicorn's extras (below), which brought the image from 201 MB to 177 MB.

The image is built on `python:3.13-slim`, the official Python image on Debian 13 ("trixie"), currently Python 3.13.18. That base is about 118 MB of the image; Finchvox and its Python packages make up the rest. Four variants were built and checked on 2026-11-07. Each started, served the UI and turned a real span into a session:

| Variant | What changes | Size | Ready in |
|---|---|---|---|
| A: before | With Uvicorn's extras | 201 MB | 1.2 s |
| **B: chosen** | Same base, without Uvicorn's extras | 177 MB | 1.2 s |
| C | B, plus no precompiled bytecode | 165 MB | 2.0 s |
| D | B on `python:3.13-alpine` instead of Debian | 105 MB | 1.9–2.2 s |

B was chosen as the safe option: same Debian base, same startup time. C saves little and starts slower. D is much smaller because Alpine Linux is, but it uses a different C library (musl instead of glibc): some Python packages run slower on it, and a future dependency without an Alpine build would fail the image build. D remains an option if image size becomes more important.

### Uvicorn's extras

> **Needs explaining to the developer:** what Uvicorn's extras are, and whether they are good for this project. Variant B, which leaves them out of the image, was chosen before this was walked through; the notes below are the starting point for that explanation.

Uvicorn is the program that runs Finchvox's web server: the UI, the API and HTTP uploads. Finchvox depends on `uvicorn[standard]`, where `[standard]` is an "extra": a named set of optional packages installed on top of plain Uvicorn. According to [Uvicorn's installation docs](https://github.com/encode/uvicorn/blob/master/docs/installation.md), the standard extra adds:

| Package | What Uvicorn uses it for | Used by Finchvox? |
|---|---|---|
| `uvloop` | A faster replacement for Python's built-in event loop, the part that juggles many requests at once | Yes, automatically when installed |
| `httptools` | A faster parser for incoming HTTP requests | Yes, automatically when installed |
| `websockets` | Live two-way browser connections | No: the UI loads everything with plain HTTP requests |
| `watchfiles` | Restarting the server when code changes (`--reload`) | No: a development convenience Finchvox does not enable |
| `python-dotenv` | Reading settings from a `.env` file (`--env-file`) | No: Finchvox starts Uvicorn from its own code |
| `PyYAML` | Reading a YAML logging configuration (`--log-config`) | No, for the same reason |

Without them, Uvicorn falls back to Python's built-in event loop and its own pure-Python HTTP parser (`h11`), which already comes with plain Uvicorn.

Whether they help this project:

- **Only the web side would get slower.** Traces and logs from agents arrive through Finchvox's separate gRPC server, which these packages do not affect. Uvicorn handles the UI, session reports and recording uploads.
- **Finchvox is a local, one-person tool.** The speed-ups matter most for servers handling many requests at once. Measured startup was the same with and without them (1.2 s).
- **Where they could still matter:** large uploads or downloads, and a busy UI if many people ever share one Finchvox. That has not been measured.
- **Leaving them out affects the image only.** The `Dockerfile` skips them with uv's `--no-install-package` (its `SKIP_PACKAGES` build argument), so `pyproject.toml`, `uv.lock` and installs outside Docker keep them. To put them back in the image, build with `--build-arg SKIP_PACKAGES=`.

## Later: environment-variable configuration

**Status: not implemented; recorded for later.**

Finchvox reads its settings only from command-line flags such as `--host`, `--data-dir` and `--max-upload-mb`. Containers are more commonly configured through environment variables, for example `FINCHVOX_HOST=0.0.0.0`, which is the approach recommended by the [Twelve-Factor App](https://12factor.net/config) guidelines. It would help because:

- the same image could be configured by any container platform, such as Kubernetes or a hosting service, without overriding its start command;
- settings could live in one `.env` file and be changed without editing `compose.yaml`;
- secrets, if Finchvox ever gains authentication, are normally passed this way.

A likely design is for each flag to fall back to a `FINCHVOX_` environment variable, with the flag winning when both are set. Today `compose.yaml` works around the gap by passing flags in its `command`, which is enough for a single machine.
