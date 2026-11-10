"""Docker setup for the Finchvox server.

The configuration checks always run. The smoke test builds and runs the real
container, which takes minutes, so it only runs when FINCHVOX_DOCKER_TESTS=1 and
Docker is available:

    FINCHVOX_DOCKER_TESTS=1 uv run --extra dev pytest tests/test_docker.py
"""

import io
import json
import os
import shutil
import socket
import subprocess
import time
import urllib.request
import uuid
import zipfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
yaml = pytest.importorskip("yaml")


def _compose() -> dict:
    return yaml.safe_load((ROOT / "compose.yaml").read_text())


class TestConfiguration:
    def test_published_ports_stay_on_this_machine(self):
        """Finchvox has no login, so its ports must not reach the network."""
        ports = _compose()["services"]["finchvox"]["ports"]

        assert len(ports) == 2
        assert all(port.startswith("127.0.0.1:") for port in ports)

    def test_server_accepts_traffic_from_outside_the_container(self):
        command = _compose()["services"]["finchvox"]["command"]

        assert command[command.index("--host") + 1] == "0.0.0.0"
        assert command[command.index("--data-dir") + 1] == "/data"

    def test_sessions_live_in_a_named_volume(self):
        compose = _compose()

        assert "finchvox-data:/data" in compose["services"]["finchvox"]["volumes"]
        assert "finchvox-data" in compose["volumes"]

    def test_image_runs_as_a_non_root_user_without_uv(self):
        dockerfile = (ROOT / "Dockerfile").read_text()
        final_stage = dockerfile.rsplit("\nFROM ", 1)[1]

        command = next(
            line for line in final_stage.splitlines() if line.startswith("CMD ")
        )

        assert "USER finchvox" in final_stage
        assert "chown finchvox:finchvox /data" in final_stage
        # Started directly, so `docker stop` reaches the server's shutdown handler.
        assert command.startswith('CMD ["finchvox", "start"')

    def test_both_installs_leave_out_uvicorns_optional_packages(self):
        dockerfile = (ROOT / "Dockerfile").read_text()
        skipped = dockerfile.split('ARG SKIP_PACKAGES="', 1)[1].split('"', 1)[0]
        installs = [line for line in dockerfile.splitlines() if "uv sync" in line]

        for package in ("uvloop", "httptools", "websockets", "watchfiles"):
            assert f"--no-install-package {package}" in skipped
        assert len(installs) == 2
        assert all("${SKIP_PACKAGES}" in line for line in installs)

    def test_finchvox_is_rebuilt_from_the_copied_source(self):
        # uv's build cache is keyed on pyproject.toml, so without this a rebuild
        # reuses the previous Finchvox wheel and serves stale code and UI files.
        dockerfile = (ROOT / "Dockerfile").read_text()
        project_install = [line for line in dockerfile.splitlines() if "uv sync" in line][-1]

        assert "--reinstall-package finchvox" in project_install

    def test_build_context_leaves_out_unrelated_folders(self):
        ignored = (ROOT / ".dockerignore").read_text().split()

        for entry in ("worker/", "docs/", "**/.env", "**/.venv/"):
            assert entry in ignored


def _docker_ready() -> bool:
    if os.environ.get("FINCHVOX_DOCKER_TESTS") != "1" or not shutil.which("docker"):
        return False
    result = subprocess.run(["docker", "info"], capture_output=True, check=False)
    return result.returncode == 0


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


@pytest.mark.skipif(
    not _docker_ready(), reason="set FINCHVOX_DOCKER_TESTS=1 with Docker running"
)
class TestContainerSmoke:
    TRACE_ID = "abcdef0123456789abcdef0123456789"

    @pytest.fixture
    def stack(self):
        project = f"finchvox-test-{uuid.uuid4().hex[:8]}"
        http_port, grpc_port = _free_port(), _free_port()
        env = {
            **os.environ,
            "FINCHVOX_HTTP_PORT": str(http_port),
            "FINCHVOX_GRPC_PORT": str(grpc_port),
        }
        base = ["docker", "compose", "-p", project, "-f", str(ROOT / "compose.yaml")]

        def compose(*args, check=True, timeout=600):
            return subprocess.run(
                [*base, *args], cwd=ROOT, env=env, capture_output=True, text=True,
                check=check, timeout=timeout,
            )

        compose("up", "-d", "--build")
        try:
            yield compose, f"http://127.0.0.1:{http_port}", grpc_port
        finally:
            compose("down", "-v", check=False)

    @staticmethod
    def _wait_until_healthy(compose, timeout=90):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            container = compose("ps", "-q", "finchvox").stdout.strip()
            state = subprocess.run(
                ["docker", "inspect", "-f", "{{.State.Health.Status}}", container],
                capture_output=True, text=True, check=False,
            ).stdout.strip()
            if state == "healthy":
                return
            time.sleep(1)
        pytest.fail(f"container did not become healthy; logs:\n{compose('logs').stdout}")

    def _send_span(self, grpc_port):
        from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import (
            OTLPSpanExporter,
        )
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import SimpleSpanProcessor

        provider = TracerProvider()
        provider.add_span_processor(
            SimpleSpanProcessor(
                OTLPSpanExporter(endpoint=f"http://127.0.0.1:{grpc_port}", insecure=True)
            )
        )
        with provider.get_tracer("docker-smoke").start_as_current_span("agent_session") as span:
            trace_id = format(span.get_span_context().trace_id, "032x")
        provider.shutdown()
        return trace_id

    @staticmethod
    def _sessions(base_url):
        with urllib.request.urlopen(f"{base_url}/api/sessions", timeout=10) as response:
            return {s["session_id"] for s in json.load(response)["sessions"]}

    @staticmethod
    def _upload_recording(base_url, trace_id, data: bytes) -> int:
        boundary = "finchvoxsmoke"
        body = (
            f"--{boundary}\r\nContent-Disposition: form-data; name=\"audio\"; "
            f"filename=\"call.ogg\"\r\nContent-Type: audio/ogg\r\n\r\n"
        ).encode() + data + f"\r\n--{boundary}--\r\n".encode()
        request = urllib.request.Request(
            f"{base_url}/collector/livekit/{trace_id}/audio",
            data=body,
            headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
        )
        with urllib.request.urlopen(request, timeout=30) as response:
            return response.status

    def test_container_end_to_end(self, stack):
        compose, base_url, grpc_port = stack
        self._wait_until_healthy(compose)

        # The UI and its assets are served from the installed package.
        for path in ("/", "/js/session_detail.js"):
            with urllib.request.urlopen(f"{base_url}{path}", timeout=10) as response:
                assert response.status == 200
        # ...and they are this checkout's files, not a cached earlier build.
        with urllib.request.urlopen(f"{base_url}/css/app.css", timeout=10) as response:
            assert response.read() == (ROOT / "ui" / "css" / "app.css").read_bytes()

        # A span sent from this machine becomes a session.
        trace_id = self._send_span(grpc_port)
        deadline = time.monotonic() + 15
        while trace_id not in self._sessions(base_url) and time.monotonic() < deadline:
            time.sleep(0.5)
        assert trace_id in self._sessions(base_url)

        # A recording uploads, and the session downloads with it.
        recording = os.urandom(50_000)
        assert self._upload_recording(base_url, trace_id, recording) == 201
        with urllib.request.urlopen(
            f"{base_url}/api/sessions/{trace_id}/download", timeout=30
        ) as response:
            downloaded = response.read()
        with zipfile.ZipFile(io.BytesIO(downloaded)) as zf:
            assert zf.read(f"{trace_id}/audio.ogg") == recording

        # The server runs as a non-root user.
        user_id = compose("exec", "-T", "finchvox", "id", "-u").stdout.strip()
        assert user_id != "0"

        # Uvicorn's optional packages are really absent from the image.
        missing = compose(
            "exec", "-T", "finchvox", "python", "-c",
            "import importlib.util as u; print(all(u.find_spec(p) is None "
            "for p in ('uvloop', 'httptools', 'websockets', 'watchfiles')))",
        ).stdout.strip()
        assert missing == "True"

        # It shuts down cleanly well within Docker's 10 s grace period.
        started = time.monotonic()
        compose("stop", "finchvox")
        assert time.monotonic() - started < 9
        container = compose("ps", "-a", "-q", "finchvox").stdout.strip()
        exit_code = subprocess.run(
            ["docker", "inspect", "-f", "{{.State.ExitCode}}", container],
            capture_output=True, text=True, check=True,
        ).stdout.strip()
        assert exit_code == "0"

        # Sessions survive a restart.
        compose("start", "finchvox")
        self._wait_until_healthy(compose)
        assert trace_id in self._sessions(base_url)
