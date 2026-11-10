"""The recording upload LiveKit sends at session end when LIVEKIT_OBSERVABILITY_URL
points at Finchvox: a protobuf header holding the session report, the chat history,
and the audio."""

import json
import threading

import pytest
from fastapi.testclient import TestClient
from livekit.protocol.metrics import MetricsRecordingHeader
from opentelemetry.proto.common.v1.common_pb2 import AnyValue, KeyValue
from opentelemetry.proto.trace.v1.trace_pb2 import ResourceSpans, ScopeSpans, Span

from finchvox.collector import livekit_recording
from finchvox.collector.config import get_session_dir
from finchvox.server import UnifiedServer

TRACE_ID = "0123456789abcdef0123456789abcdef"
JOB_ID = "AJ_recording"
AUDIO = b"OggS" + bytes(range(256)) * 8
CHAT = {
    "items": [
        {"id": "m1", "type": "message", "role": "user", "content": ["hello"], "created_at": 1.5},
        {"id": "m2", "type": "message", "role": "assistant", "content": ["hi"], "created_at": 2.0},
    ]
}


@pytest.fixture
def server(tmp_path, monkeypatch):
    monkeypatch.setattr(livekit_recording, "RECORDING_TRACE_WAIT_SECONDS", 3.0)
    monkeypatch.setattr(livekit_recording, "RECORDING_TRACE_POLL_SECONDS", 0.05)
    unified = UnifiedServer(data_dir=tmp_path)
    return unified, TestClient(unified.app), get_session_dir(tmp_path, TRACE_ID)


def write_span(unified, job_id=JOB_ID):
    span = Span(
        trace_id=bytes.fromhex(TRACE_ID),
        span_id=bytes.fromhex("2222222222222222"),
        name="agent_session",
        start_time_unix_nano=1_000_000_000,
        end_time_unix_nano=9_000_000_000,
        attributes=[KeyValue(key="job_id", value=AnyValue(string_value=job_id))],
    )
    unified.span_writer.write_span(span, ResourceSpans(), ScopeSpans())


def header(job_id=JOB_ID) -> bytes:
    summary = {"job_id": job_id, "room_id": "RM_1", "room": "test-room", "usage": []}
    return MetricsRecordingHeader(
        room_id="RM_1", job_id=job_id, duration=8000, session_summary=json.dumps(summary)
    ).SerializeToString()


def upload(client, *, chat=True, audio=True, header_bytes=None, headers=None):
    files = {"header": ("header.binpb", header_bytes or header(), "application/protobuf")}
    if chat:
        files["chat_history"] = ("chat_history.json", json.dumps(CHAT), "application/json")
    if audio:
        files["audio"] = ("recording.ogg", AUDIO, "audio/ogg")
    return client.post("/observability/recordings/v0", files=files, headers=headers or {})


def test_the_report_and_recording_are_attached_to_the_matching_trace(server):
    unified, client, session_dir = server
    write_span(unified)

    response = upload(client)

    assert response.status_code == 201
    assert response.json()["trace_id"] == TRACE_ID
    report = json.loads((session_dir / "livekit_report.json").read_text())
    assert report["job_id"] == JOB_ID
    assert report["room"] == "test-room"
    assert [item["id"] for item in report["chat_history"]["items"]] == ["m1", "m2"]
    assert (session_dir / "audio.ogg").read_bytes() == AUDIO


def test_without_transcript_or_audio_only_the_report_is_stored(server):
    unified, client, session_dir = server
    write_span(unified)

    response = upload(client, chat=False, audio=False)

    assert response.status_code == 201
    report = json.loads((session_dir / "livekit_report.json").read_text())
    assert "chat_history" not in report
    assert not (session_dir / "audio.ogg").exists()


def test_a_recording_that_arrives_before_its_spans_waits_for_them(server):
    unified, client, session_dir = server
    timer = threading.Timer(0.3, write_span, args=(unified,))
    timer.start()

    response = upload(client)

    timer.join()
    assert response.status_code == 201
    assert (session_dir / "livekit_report.json").exists()


def test_a_recording_with_no_matching_trace_is_refused_after_waiting(server, monkeypatch):
    _, client, _ = server
    monkeypatch.setattr(livekit_recording, "RECORDING_TRACE_WAIT_SECONDS", 0.2)

    response = upload(client)

    assert response.status_code == 404


def test_a_header_that_is_not_livekits_is_rejected(server):
    unified, client, _ = server
    write_span(unified)

    response = upload(client, header_bytes=b"\xff\xff\xff not protobuf")

    assert response.status_code == 400


def test_the_upload_token_is_never_stored(server):
    unified, client, session_dir = server
    write_span(unified)

    upload(client, headers={"Authorization": "Bearer abc.do-not-store-me.xyz"})

    stored = "".join(
        p.read_text(errors="ignore") for p in session_dir.iterdir() if p.is_file()
    )
    assert "do-not-store-me" not in stored
