"""The no-code hookup against the installed LiveKit SDK.

LiveKit does not document LIVEKIT_OBSERVABILITY_URL, so this test runs the SDK's
own uploaders (its OTLP exporters and session-recording upload) against a real
Finchvox server. If an SDK upgrade changes the paths or the format, this fails
instead of Finchvox silently receiving nothing.
"""

import json
import os
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest
import uvicorn

pytest.importorskip("livekit.agents")

from finchvox.server import UnifiedServer

UPLOADER = Path(__file__).with_name("livekit_cloud_uploader.py")
JOB_ID = "AJ_compat"
AUDIO = b"OggS" + bytes(range(256)) * 16


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


@pytest.fixture
def finchvox_url(tmp_path):
    port = _free_port()
    server = uvicorn.Server(
        uvicorn.Config(
            UnifiedServer(data_dir=tmp_path / "data").app,
            host="127.0.0.1",
            port=port,
            log_level="warning",
        )
    )
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.monotonic() + 10
    while not server.started and time.monotonic() < deadline:
        time.sleep(0.05)
    assert server.started
    yield f"http://127.0.0.1:{port}", tmp_path / "data"
    server.should_exit = True
    thread.join(timeout=10)


def test_the_sdks_own_uploads_become_a_complete_session(finchvox_url, tmp_path):
    url, data_dir = finchvox_url
    audio_path = tmp_path / "audio.ogg"
    audio_path.write_bytes(AUDIO)

    result = subprocess.run(
        [sys.executable, str(UPLOADER), url, JOB_ID, str(audio_path)],
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
        env={
            **os.environ,
            "LIVEKIT_API_KEY": "compat-key",
            "LIVEKIT_API_SECRET": "compat-secret-compat-secret-compat-secret",
        },
    )
    assert result.returncode == 0, result.stderr
    assert "uploaded" in result.stdout

    sessions = [p for p in (data_dir / "sessions").iterdir() if p.is_dir()]
    assert len(sessions) == 1
    session = sessions[0]
    trace_id = session.name

    span_names = {
        json.loads(line)["name"]
        for line in (session / f"trace_{trace_id}.jsonl").read_text().splitlines()
    }
    assert {"agent_session", "agent_turn"} <= span_names

    logs = (session / f"logs_{trace_id}.jsonl").read_text()
    assert "hello from the agent" in logs

    report = json.loads((session / "livekit_report.json").read_text())
    assert report["job_id"] == JOB_ID
    contents = [item.get("content") for item in report["chat_history"]["items"]]
    assert ["hello"] in contents and ["hi there"] in contents

    assert (session / "audio.ogg").read_bytes() == AUDIO
    assert "compat-secret" not in "".join(
        p.read_text(errors="ignore") for p in session.iterdir() if p.is_file()
    )
