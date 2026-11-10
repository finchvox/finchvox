import asyncio
import json
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from finchvox.collector import audio_handler as audio_handler_module
from finchvox.collector import collector_routes
from finchvox.collector.audio_handler import AudioHandler
from finchvox.collector.collector_routes import register_collector_routes
from finchvox.collector.config import get_session_dir


@pytest.fixture
def livekit_collector(tmp_path: Path):
    app = FastAPI()
    audio_handler = AudioHandler(tmp_path)
    register_collector_routes(app, audio_handler)
    return TestClient(app), tmp_path


def test_livekit_report_is_saved_with_session(livekit_collector):
    client, data_dir = livekit_collector
    trace_id = "0123456789abcdef0123456789abcdef"
    report = {"room_name": "local-room", "events": [{"type": "handoff"}]}

    response = client.post(f"/collector/livekit/{trace_id}/report", json=report)

    assert response.status_code == 201
    report_file = get_session_dir(data_dir, trace_id) / "livekit_report.json"
    assert json.loads(report_file.read_text()) == report


def test_livekit_audio_accepts_supported_finalized_recording(livekit_collector):
    client, data_dir = livekit_collector
    trace_id = "abcdef0123456789abcdef0123456789"
    audio = b"webm" + (b"\x00" * 128)

    response = client.post(
        f"/collector/livekit/{trace_id}/audio",
        files={"audio": ("session.webm", audio, "audio/webm")},
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["format"] == "webm"
    assert payload["size_bytes"] == len(audio)
    assert (get_session_dir(data_dir, trace_id) / "audio.webm").read_bytes() == audio


def test_livekit_collector_rejects_bad_trace_id(livekit_collector):
    client, _ = livekit_collector

    report_response = client.post("/collector/livekit/not-a-trace/report", json={})
    audio_response = client.post(
        "/collector/livekit/not-a-trace/audio",
        files={"audio": ("session.wav", b"audio", "audio/wav")},
    )

    assert report_response.status_code == 400
    assert audio_response.status_code == 400


def test_livekit_collector_rejects_unsupported_audio(livekit_collector):
    client, _ = livekit_collector
    trace_id = "0123456789abcdef0123456789abcdef"

    response = client.post(
        f"/collector/livekit/{trace_id}/audio",
        files={"audio": ("session.exe", b"nope", "application/octet-stream")},
    )

    assert response.status_code == 415


def test_livekit_audio_enforces_final_recording_limit_and_cleans_partial_file(
    livekit_collector, monkeypatch
):
    from finchvox.collector import collector_routes

    client, data_dir = livekit_collector
    trace_id = "fedcba9876543210fedcba9876543210"
    monkeypatch.setattr(collector_routes, "MAX_FINAL_AUDIO_FILE_SIZE", 4)

    response = client.post(
        f"/collector/livekit/{trace_id}/audio",
        files={"audio": ("session.webm", b"12345", "audio/webm")},
    )

    assert response.status_code == 413
    assert not (get_session_dir(data_dir, trace_id) / "audio.webm").exists()


class TestAudioBodyLimits:
    """Oversized audio must be refused while arriving, before it reaches temp storage."""

    TRACE_ID = "fedcba9876543210fedcba9876543210"
    METADATA = json.dumps(
        {
            "chunk_number": 0,
            "timestamp": "2026-01-01T00:00:00",
            "sample_rate": 16000,
            "num_channels": 1,
        }
    )

    @pytest.fixture
    def limited_collector(self, tmp_path: Path, monkeypatch):
        # Limits are read when the routes are registered, so patch them first.
        monkeypatch.setattr(collector_routes, "MAX_AUDIO_FILE_SIZE", 10)
        monkeypatch.setattr(collector_routes, "MAX_FINAL_AUDIO_FILE_SIZE", 10)
        monkeypatch.setattr(collector_routes, "UPLOAD_BODY_MARGIN_BYTES", 1024)
        app = FastAPI()
        register_collector_routes(app, AudioHandler(tmp_path))
        return TestClient(app), tmp_path

    def _final_url(self):
        return f"/collector/livekit/{self.TRACE_ID}/audio"

    def _chunk_url(self):
        return f"/collector/audio/{self.TRACE_ID}/chunk"

    def test_oversized_final_recording_is_refused_on_arrival(self, limited_collector):
        client, data_dir = limited_collector

        response = client.post(
            self._final_url(),
            files={"audio": ("session.webm", b"x" * 5000, "audio/webm")},
        )

        assert response.status_code == 413
        # This wording comes from the body limit, not the route's later file check.
        assert response.text == "Content Too Large"
        assert not (get_session_dir(data_dir, self.TRACE_ID) / "audio.webm").exists()

    def test_oversized_chunk_is_refused_on_arrival(self, limited_collector):
        client, data_dir = limited_collector

        response = client.post(
            self._chunk_url(),
            files={"audio": ("chunk.wav", b"x" * 5000, "audio/wav")},
            data={"metadata": self.METADATA},
        )

        assert response.status_code == 413
        assert response.text == "Content Too Large"
        assert not (get_session_dir(data_dir, self.TRACE_ID) / "audio").exists()

    @pytest.mark.parametrize("url_name", ["_final_url", "_chunk_url"])
    def test_oversized_upload_without_content_length_is_refused(
        self, limited_collector, url_name
    ):
        client, _ = limited_collector
        boundary = "finchvoxtestboundary"
        body = (
            f"--{boundary}\r\n"
            'Content-Disposition: form-data; name="audio"; filename="a.wav"\r\n'
            "Content-Type: audio/wav\r\n\r\n"
        ).encode() + b"x" * 5000 + f"\r\n--{boundary}--\r\n".encode()

        def body_chunks():
            yield body

        response = client.post(
            getattr(self, url_name)(),
            content=body_chunks(),
            headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
        )

        assert response.status_code == 413

    def test_file_just_over_its_limit_still_gets_the_precise_error(
        self, limited_collector
    ):
        client, _ = limited_collector

        response = client.post(
            self._final_url(),
            files={"audio": ("session.webm", b"x" * 11, "audio/webm")},
        )

        assert response.status_code == 413
        assert "exceeds" in response.json()["detail"]

    def test_file_exactly_at_its_limit_is_accepted(self, limited_collector):
        client, _ = limited_collector

        final = client.post(
            self._final_url(),
            files={"audio": ("session.webm", b"x" * 10, "audio/webm")},
        )
        chunk = client.post(
            self._chunk_url(),
            files={"audio": ("chunk.wav", b"x" * 10, "audio/wav")},
            data={"metadata": self.METADATA},
        )

        assert final.status_code == 201
        assert chunk.status_code == 201

    def test_body_limit_does_not_affect_other_collector_routes(
        self, limited_collector
    ):
        client, _ = limited_collector

        response = client.post(
            f"/collector/livekit/{self.TRACE_ID}/report",
            json={"note": "x" * 5000},
        )

        assert response.status_code == 201


class _FakeUpload:
    """An upload that hands over its data in small pieces, yielding in between."""

    def __init__(self, data: bytes, piece: int = 4):
        self._data = data
        self._piece = piece
        self._position = 0

    async def read(self, size: int = -1) -> bytes:
        await asyncio.sleep(0)
        chunk = self._data[self._position : self._position + self._piece]
        self._position += len(chunk)
        return chunk


class TestRecordingReplacement:
    """A recording is replaced only once its new copy is complete."""

    TRACE_ID = "0123456789abcdef0123456789abcdef"

    @pytest.fixture
    def collector(self, tmp_path: Path, monkeypatch):
        monkeypatch.setattr(collector_routes, "MAX_FINAL_AUDIO_FILE_SIZE", 10)
        app = FastAPI()
        register_collector_routes(app, AudioHandler(tmp_path))
        return TestClient(app), get_session_dir(tmp_path, self.TRACE_ID)

    def _upload(self, client, filename: str, data: bytes):
        return client.post(
            f"/collector/livekit/{self.TRACE_ID}/audio",
            files={"audio": (filename, data, "application/octet-stream")},
        )

    def test_upload_replaces_the_previous_recording(self, collector):
        client, session_dir = collector

        assert self._upload(client, "a.ogg", b"first").status_code == 201
        assert self._upload(client, "b.ogg", b"second").status_code == 201

        assert (session_dir / "audio.ogg").read_bytes() == b"second"
        assert sorted(p.name for p in session_dir.iterdir()) == ["audio.ogg"]

    def test_failed_upload_keeps_the_previous_recording(self, collector):
        client, session_dir = collector
        self._upload(client, "a.ogg", b"original")

        response = self._upload(client, "b.ogg", b"x" * 11)

        assert response.status_code == 413
        assert (session_dir / "audio.ogg").read_bytes() == b"original"
        assert sorted(p.name for p in session_dir.iterdir()) == ["audio.ogg"]

    def test_new_format_replaces_a_recording_in_another_format(self, collector):
        client, session_dir = collector
        self._upload(client, "a.webm", b"webm")

        response = self._upload(client, "b.ogg", b"ogg")

        assert response.status_code == 201
        assert sorted(p.name for p in session_dir.iterdir()) == ["audio.ogg"]

    def test_recording_in_use_gets_a_clear_409_and_is_kept(
        self, collector, monkeypatch
    ):
        client, session_dir = collector
        self._upload(client, "a.ogg", b"original")

        def busy_replace(source, destination):
            raise PermissionError("in use")

        monkeypatch.setattr(audio_handler_module.os, "replace", busy_replace)
        response = self._upload(client, "b.ogg", b"new")

        assert response.status_code == 409
        assert "retry" in response.json()["detail"].lower()
        assert (session_dir / "audio.ogg").read_bytes() == b"original"
        assert sorted(p.name for p in session_dir.iterdir()) == ["audio.ogg"]

    def test_other_format_in_use_gets_a_409_and_nothing_changes(
        self, collector, monkeypatch
    ):
        """Leaving the old file would let it keep winning playback over the upload."""
        client, session_dir = collector
        self._upload(client, "a.webm", b"webm")
        real_unlink = Path.unlink

        def busy_unlink(self, *args, **kwargs):
            if self.name == "audio.webm":
                raise PermissionError("in use")
            return real_unlink(self, *args, **kwargs)

        monkeypatch.setattr(Path, "unlink", busy_unlink)
        response = self._upload(client, "b.ogg", b"ogg")

        assert response.status_code == 409
        assert sorted(p.name for p in session_dir.iterdir()) == ["audio.webm"]
        assert (session_dir / "audio.webm").read_bytes() == b"webm"

    def test_concurrent_uploads_leave_one_complete_recording(self, tmp_path):
        handler = AudioHandler(tmp_path)
        first, second = b"A" * 40, b"B" * 40

        async def both():
            await asyncio.gather(
                handler.save_final_recording(
                    self.TRACE_ID, _FakeUpload(first), ".ogg", 1000
                ),
                handler.save_final_recording(
                    self.TRACE_ID, _FakeUpload(second), ".ogg", 1000
                ),
            )

        asyncio.run(both())

        session_dir = get_session_dir(tmp_path, self.TRACE_ID)
        assert sorted(p.name for p in session_dir.iterdir()) == ["audio.ogg"]
        assert (session_dir / "audio.ogg").read_bytes() in (first, second)


_JSON_TRACE_ID = "fedcba9876543210fedcba9876543210"
JSON_ROUTES = [
    pytest.param(f"/collector/livekit/{_JSON_TRACE_ID}/report", id="report"),
    pytest.param("/collector/livekit/report", id="report-auto"),
    pytest.param(f"/collector/environment/{_JSON_TRACE_ID}", id="environment"),
]


class TestJsonBodyLimits:
    """JSON routes read the whole body into memory, so its size must be limited."""

    TRACE_ID = _JSON_TRACE_ID

    @pytest.fixture
    def limited_client(self, tmp_path: Path, monkeypatch):
        # Limits are read when the routes are registered, so patch them first.
        monkeypatch.setattr(collector_routes, "MAX_JSON_BODY_BYTES", 1024)
        app = FastAPI()
        register_collector_routes(app, AudioHandler(tmp_path))
        return TestClient(app)

    @pytest.mark.parametrize("url", JSON_ROUTES)
    def test_oversized_body_is_refused(self, limited_client, url):
        response = limited_client.post(url, json={"note": "x" * 5000})

        assert response.status_code == 413

    @pytest.mark.parametrize("url", JSON_ROUTES)
    def test_oversized_body_without_content_length_is_refused(
        self, limited_client, url
    ):
        def body_chunks():
            yield json.dumps({"note": "x" * 5000}).encode()

        response = limited_client.post(
            url,
            content=body_chunks(),
            headers={"Content-Type": "application/json"},
        )

        assert response.status_code == 413

    @pytest.mark.parametrize("url", JSON_ROUTES)
    def test_invalid_json_within_the_limit_is_still_a_400(self, limited_client, url):
        for body in (b"not json", b"\x81\xff"):
            response = limited_client.post(url, content=body)

            assert response.status_code == 400
            assert response.json()["detail"] == "Invalid JSON"

    def test_deeply_nested_json_is_a_400(self, tmp_path):
        app = FastAPI()
        register_collector_routes(app, AudioHandler(tmp_path))

        response = TestClient(app).post(
            f"/collector/environment/{self.TRACE_ID}",
            content=b"[" * 200_000,
        )

        assert response.status_code == 400

    def test_body_within_the_limit_is_stored(self, limited_client, tmp_path):
        response = limited_client.post(
            f"/collector/livekit/{self.TRACE_ID}/report", json={"note": "small"}
        )

        assert response.status_code == 201
        report = get_session_dir(tmp_path, self.TRACE_ID) / "livekit_report.json"
        assert json.loads(report.read_text()) == {"note": "small"}


def _write_trace_with_livekit_identity(data_dir: Path, trace_id: str, **identity):
    session_dir = get_session_dir(data_dir, trace_id)
    session_dir.mkdir(parents=True, exist_ok=True)
    attrs = []
    for key, value in identity.items():
        attrs.append({"key": key, "value": {"string_value": value}})
    span = {
        "trace_id_hex": trace_id,
        "span_id_hex": "0123456789abcdef",
        "name": "agent_turn",
        "start_time_unix_nano": "1",
        "end_time_unix_nano": "2",
        "attributes": attrs,
    }
    (session_dir / f"trace_{trace_id}.jsonl").write_text(json.dumps(span) + "\n")


def test_livekit_report_can_resolve_trace_from_job_id(livekit_collector):
    client, data_dir = livekit_collector
    trace_id = "11111111111111111111111111111111"
    _write_trace_with_livekit_identity(
        data_dir,
        trace_id,
        **{"lk.job_id": "AJ_local_123", "lk.room_sid": "RM_local_123"},
    )
    report = {
        "job_id": "AJ_local_123",
        "room_id": "RM_local_123",
        "room": "local-room",
        "events": [],
    }

    response = client.post("/collector/livekit/report", json=report)

    assert response.status_code == 201
    assert response.json()["trace_id"] == trace_id
    report_file = get_session_dir(data_dir, trace_id) / "livekit_report.json"
    assert json.loads(report_file.read_text()) == report


def test_livekit_report_can_resolve_trace_from_current_bare_context_ids(livekit_collector):
    client, data_dir = livekit_collector
    trace_id = "33333333333333333333333333333333"
    _write_trace_with_livekit_identity(
        data_dir,
        trace_id,
        job_id="AJ_current_123",
        room_id="RM_current_123",
    )

    response = client.post(
        "/collector/livekit/report",
        json={
            "job_id": "AJ_current_123",
            "room_id": "RM_current_123",
            "room": "current-room",
            "events": [],
        },
    )

    assert response.status_code == 201
    assert response.json()["trace_id"] == trace_id


def test_livekit_report_auto_resolve_falls_back_to_room_name(livekit_collector):
    client, data_dir = livekit_collector
    trace_id = "22222222222222222222222222222222"
    _write_trace_with_livekit_identity(
        data_dir,
        trace_id,
        **{"lk.pii.room_name": "room-by-name"},
    )

    response = client.post(
        "/collector/livekit/report",
        json={"room": "room-by-name", "events": []},
    )

    assert response.status_code == 201
    assert response.json()["trace_id"] == trace_id


def test_livekit_report_auto_resolve_returns_actionable_404(livekit_collector):
    client, _ = livekit_collector

    response = client.post(
        "/collector/livekit/report",
        json={"job_id": "AJ_missing", "room_id": "RM_missing"},
    )

    assert response.status_code == 404
    assert "Flush traces first" in response.json()["detail"]
