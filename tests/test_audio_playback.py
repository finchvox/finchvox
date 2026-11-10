"""Merged playback audio must keep working and must never leave a temp file behind."""

import asyncio
import json
import tempfile
import wave
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from finchvox.session import Session
from finchvox.ui_routes import register_ui_routes

SESSION_ID = "chunky"
AUDIO_URL = f"/api/sessions/{SESSION_ID}/audio"


@pytest.fixture
def temp_root(tmp_path, monkeypatch):
    root = tmp_path / "server-temp"
    root.mkdir()
    monkeypatch.setattr(tempfile, "tempdir", str(root))
    return root


@pytest.fixture
def data_dir(tmp_path):
    return tmp_path / "data"


@pytest.fixture
def app(data_dir, temp_root):
    app = FastAPI()
    register_ui_routes(app, data_dir)
    return app


@pytest.fixture
def client(app):
    return TestClient(app, raise_server_exceptions=False)


def _session_dir(data_dir: Path) -> Path:
    session_dir = data_dir / "sessions" / SESSION_ID
    session_dir.mkdir(parents=True, exist_ok=True)
    (session_dir / f"trace_{SESSION_ID}.jsonl").write_text(
        json.dumps({"name": "agent_turn", "start_time_unix_nano": "1000"}) + "\n"
    )
    return session_dir


def _write_chunks(data_dir: Path, count: int = 2, frames: int = 200_000) -> Path:
    audio_dir = _session_dir(data_dir) / "audio"
    audio_dir.mkdir()
    for number in range(count):
        with wave.open(str(audio_dir / f"chunk_{number:04d}.wav"), "wb") as chunk:
            chunk.setnchannels(1)
            chunk.setsampwidth(2)
            chunk.setframerate(16000)
            chunk.writeframes(bytes(frames * 2))
    return audio_dir


def _asgi_scope(spec_version: str) -> dict:
    return {
        "type": "http",
        "asgi": {"version": "3.0", "spec_version": spec_version},
        "http_version": "1.1",
        "method": "GET",
        "scheme": "http",
        "path": AUDIO_URL,
        "raw_path": AUDIO_URL.encode(),
        "query_string": b"",
        "root_path": "",
        "headers": [(b"host", b"testserver")],
        "client": ("127.0.0.1", 1),
        "server": ("testserver", 80),
    }


def test_merged_audio_plays_and_its_temp_file_is_deleted(client, data_dir, temp_root):
    _write_chunks(data_dir)

    response = client.get(AUDIO_URL)

    assert response.status_code == 200
    assert response.headers["content-type"] == "audio/wav"
    assert f"session_{SESSION_ID}.wav" in response.headers["content-disposition"]
    assert response.content[:4] == b"RIFF"
    assert list(temp_root.iterdir()) == []


def test_merged_audio_still_supports_seeking(client, data_dir, temp_root):
    _write_chunks(data_dir)

    response = client.get(AUDIO_URL, headers={"Range": "bytes=0-1023"})

    assert response.status_code == 206
    assert response.headers["content-range"].startswith("bytes 0-1023/")
    assert len(response.content) == 1024
    assert list(temp_root.iterdir()) == []


def test_finalized_recording_plays_and_is_not_deleted(client, data_dir):
    recording = _session_dir(data_dir) / "audio.webm"
    recording.write_bytes(b"recording")

    first = client.get(AUDIO_URL)
    second = client.get(AUDIO_URL, headers={"Range": "bytes=0-3"})

    assert first.status_code == 200
    assert first.content == b"recording"
    assert first.headers["content-type"] == "audio/webm"
    assert second.status_code == 206
    assert recording.read_bytes() == b"recording"


def test_status_reports_a_session_that_still_has_chunks(client, data_dir):
    audio_dir = _write_chunks(data_dir, count=3)
    newest = max(path.stat().st_mtime for path in audio_dir.iterdir())

    response = client.get(f"{AUDIO_URL}/status")

    assert response.status_code == 200
    assert response.json() == {
        "finalized": False,
        "chunk_count": 3,
        "last_modified": newest,
    }


def test_size_playback_and_status_agree_on_the_recording(client, data_dir):
    session_dir = _session_dir(data_dir)
    (session_dir / "audio.wav").write_bytes(b"w" * 300)
    (session_dir / "audio.opus").write_bytes(b"o" * 100)

    played = client.get(AUDIO_URL)
    status = client.get(f"{AUDIO_URL}/status").json()
    listed = Session(session_dir)

    assert listed.get_audio_size_bytes() == len(played.content)
    assert status["size_bytes"] == len(played.content)
    assert played.headers["content-type"] == f"audio/{status['format']}"


def test_session_without_audio_returns_404(client, data_dir, temp_root):
    _session_dir(data_dir)

    assert client.get(AUDIO_URL).status_code == 404
    assert list(temp_root.iterdir()) == []


@pytest.mark.parametrize(
    "contents",
    [
        pytest.param(b"this is not a wav file", id="not-a-wav"),
        pytest.param(b"", id="empty-file"),
        pytest.param(b"RIFF\x10\x00\x00\x00WAVE", id="truncated-header"),
    ],
)
@pytest.mark.parametrize("bad_chunk", [0, 1], ids=["first-chunk", "later-chunk"])
def test_corrupt_chunk_is_explained_and_leaves_no_temp_file(
    client, data_dir, temp_root, contents, bad_chunk
):
    audio_dir = _write_chunks(data_dir)
    (audio_dir / f"chunk_{bad_chunk:04d}.wav").write_bytes(contents)

    response = client.get(AUDIO_URL)

    assert response.status_code == 500
    assert "damaged" in response.json()["detail"]
    assert list(temp_root.iterdir()) == []


def test_temp_file_is_deleted_when_sending_fails(app, data_dir, temp_root):
    """ASGI 2.4 servers report a disconnect by raising from send.

    Uvicorn currently reports 2.3, where Starlette would still run a background
    task, so this guards against the leak appearing after a server upgrade.
    """
    _write_chunks(data_dir)
    saw_temp_file = []

    async def send(message):
        if message["type"] == "http.response.body":
            saw_temp_file.append(bool(list(temp_root.iterdir())))
            raise OSError("client went away")

    async def receive():
        await asyncio.Event().wait()

    with pytest.raises(Exception):  # noqa: B017 - only the cleanup matters here
        asyncio.run(app(_asgi_scope("2.4"), receive, send))

    assert saw_temp_file == [True]
    assert list(temp_root.iterdir()) == []


def test_temp_file_is_deleted_when_client_disconnects(app, data_dir, temp_root):
    """Older ASGI servers report a disconnect through receive instead."""
    _write_chunks(data_dir)

    async def run():
        first_body_sent = asyncio.Event()

        async def send(message):
            if message["type"] == "http.response.body":
                first_body_sent.set()
                await asyncio.Event().wait()

        async def receive():
            await first_body_sent.wait()
            return {"type": "http.disconnect"}

        await app(_asgi_scope("2.3"), receive, send)

    asyncio.run(run())

    assert list(temp_root.iterdir()) == []
