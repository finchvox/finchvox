"""A stored Pipecat session, read through the same HTTP API the UI uses.

Finchvox's focus is LiveKit; Pipecat support is kept working but not extended
(see AGENTS.md). This synthetic session protects the Pipecat side of the shared
server and UI code on every test run, without installing Pipecat. The span and
attribute names follow Pipecat 1.14's own tracing code
(pipecat/utils/tracing/turn_trace_observer.py, service_decorators.py and
service_attributes.py): a "conversation" span, "turn" spans, and "stt", "llm"
and "tts" spans from the "pipecat" tracer. No real call data is used.
"""

import json
import wave

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from finchvox.ui_routes import register_ui_routes

SESSION_ID = "0123456789abcdef0123456789abcdef"
T0 = 1_800_000_000_000_000_000  # nanoseconds
SECOND = 1_000_000_000


def attribute(key, value):
    if isinstance(value, bool):
        encoded = {"bool_value": value}
    elif isinstance(value, int):
        encoded = {"int_value": str(value)}
    elif isinstance(value, float):
        encoded = {"double_value": value}
    else:
        encoded = {"string_value": value}
    return {"key": key, "value": encoded}


def pipecat_span(name, span_id, parent_id, start_s, end_s, attributes=(), status=None):
    span = {
        "name": name,
        "trace_id_hex": SESSION_ID,
        "span_id_hex": span_id,
        "parent_span_id_hex": parent_id,
        "start_time_unix_nano": str(T0 + int(start_s * SECOND)),
        "end_time_unix_nano": str(T0 + int(end_s * SECOND)),
        "attributes": [attribute(key, value) for key, value in attributes],
        "instrumentation_scope": {"name": "pipecat"},
        "resource": {"attributes": [attribute("service.name", "barista-bot")]},
    }
    if status:
        span["status"] = status
    return span


SPANS = [
    pipecat_span("conversation", "c0", None, 0, 20,
                 [("conversation.id", "conv-1"), ("conversation.type", "voice")]),
    # Turn 1: the user orders, the agent answers in two spoken sentences.
    pipecat_span("turn", "t1", "c0", 0, 8, [
        ("turn.number", 1), ("turn.type", "conversation"),
        ("turn.user_bot_latency_seconds", 1.2), ("turn.was_interrupted", False),
    ]),
    pipecat_span("stt", "s1", "t1", 1, 2, [
        ("transcript", "I'd like an oat latte."), ("is_final", True), ("metrics.ttfb", 0.25),
    ]),
    pipecat_span("llm", "l1", "t1", 2, 3, [
        ("output", "Sure. One oat latte coming up."), ("metrics.ttfb", 0.6),
    ]),
    pipecat_span("tts", "v1", "t1", 3, 4, [("text", "Sure."), ("metrics.ttfb", 0.3)]),
    pipecat_span("tts", "v2", "t1", 4, 6, [("text", "One oat latte coming up."), ("metrics.ttfb", 0.32)]),
    # Turn 2: the user cuts the agent off, and one TTS request fails.
    pipecat_span("turn", "t2", "c0", 8, 20, [
        ("turn.number", 2), ("turn.type", "conversation"),
        ("turn.user_bot_latency_seconds", 2.4), ("turn.was_interrupted", True),
    ]),
    pipecat_span("stt", "s2", "t2", 9, 10, [
        ("transcript", "Make it large."), ("is_final", True), ("metrics.ttfb", 0.27),
    ]),
    pipecat_span("llm", "l2", "t2", 10, 11, [("output", "A large one."), ("metrics.ttfb", 0.5)]),
    pipecat_span("tts", "v3", "t2", 11, 12, [("text", "A large one."), ("metrics.ttfb", 0.34)],
                 status={"code": "STATUS_CODE_ERROR", "message": "TTS connection reset"}),
]

LOGS = [
    {"time_unix_nano": str(T0 + 1 * SECOND), "severity_text": "INFO",
     "body": {"string_value": "User started speaking"}, "trace_id_hex": SESSION_ID, "span_id_hex": "s1"},
    {"time_unix_nano": str(T0 + 11 * SECOND), "severity_text": "ERROR",
     "body": {"string_value": "TTS connection reset"}, "trace_id_hex": SESSION_ID, "span_id_hex": "v3"},
]


def write_wav_chunk(path, seconds=0.1, rate=16000):
    with wave.open(str(path), "wb") as chunk:
        chunk.setnchannels(1)
        chunk.setsampwidth(2)
        chunk.setframerate(rate)
        chunk.writeframes(b"\x00\x00" * int(rate * seconds))


@pytest.fixture
def client(tmp_path):
    session_dir = tmp_path / "sessions" / SESSION_ID
    (session_dir / "audio").mkdir(parents=True)
    (session_dir / f"trace_{SESSION_ID}.jsonl").write_text(
        "".join(json.dumps(span) + "\n" for span in SPANS)
    )
    (session_dir / f"logs_{SESSION_ID}.jsonl").write_text(
        "".join(json.dumps(log) + "\n" for log in LOGS)
    )
    # Pipecat uploads audio as numbered WAV chunks, not one finished recording.
    write_wav_chunk(session_dir / "audio" / "chunk_0000.wav")
    write_wav_chunk(session_dir / "audio" / "chunk_0001.wav")

    app = FastAPI()
    register_ui_routes(app, tmp_path)
    return TestClient(app)


def test_listed_as_a_pipecat_session(client):
    [session] = client.get("/api/sessions").json()["sessions"]

    assert session["session_id"] == SESSION_ID
    assert session["platform"] == "pipecat"
    assert session["service_name"] == "barista-bot"
    assert session["trace"]["turn_count"] == 2
    assert session["error_count"] == 1
    assert session["log_count"] == 2


def test_trace_is_normalized_by_the_pipecat_adapter(client):
    trace = client.get(f"/api/sessions/{SESSION_ID}/trace").json()
    by_id = {span["span_id_hex"]: span["_normalized"] for span in trace["spans"]}

    assert trace["platform"] == "pipecat"
    assert by_id["c0"]["category"] == "root"
    assert by_id["t1"]["category"] == "turn"
    assert [by_id[s]["category"] for s in ("s1", "l1", "v1")] == ["stt", "llm", "tts"]
    assert by_id["s1"]["transcript"] == "I'd like an oat latte."
    assert by_id["l1"]["ttfb_seconds"] == pytest.approx(0.6)
    assert by_id["v3"]["is_error"] is True
    assert by_id["v3"]["error_message"] == "TTS connection reset"


def test_conversation_shows_each_reply_once(client):
    # Pipecat records a reply twice: the whole text on the "llm" span ("output")
    # and the spoken sentences on the "tts" spans ("text"). The transcript must
    # show what was spoken, once.
    messages = client.get(f"/api/sessions/{SESSION_ID}/conversation").json()["messages"]

    assert [(m["role"], m["content"], m["was_interrupted"]) for m in messages] == [
        ("user", "I'd like an oat latte.", False),
        ("assistant", "Sure. One oat latte coming up.", False),
        ("user", "Make it large.", False),
        ("assistant", "A large one.", True),
    ]


def test_a_text_only_bot_shows_the_llm_reply():
    from finchvox.adapters import PipecatAdapter
    from finchvox.conversation import Conversation

    spans = [span for span in SPANS if span["name"] != "tts"]
    messages = Conversation(PipecatAdapter().normalize_spans(spans)).to_dict_list()

    assert [m["content"] for m in messages if m["role"] == "assistant"] == [
        "Sure. One oat latte coming up.", "A large one.",
    ]


def test_metrics_cover_every_service_and_the_turn_latency(client):
    metrics = client.get(f"/api/sessions/{SESSION_ID}/metrics").json()

    assert sorted(metrics["services"]) == ["llm", "stt", "tts"]
    assert metrics["series"]["tts"]["stats"]["count"] == 3
    assert metrics["series"]["llm"]["stats"]["max_ms"] == pytest.approx(600)
    latencies = [p["latency_ms"] for p in metrics["user_bot_latency"]["data_points"]]
    assert latencies == pytest.approx([1200, 2400])


def test_logs_are_served_in_time_order(client):
    logs = client.get(f"/api/sessions/{SESSION_ID}/logs").json()

    assert logs["total_count"] == 2
    assert [log["severity_text"] for log in logs["logs"]] == ["INFO", "ERROR"]


def test_chunked_audio_is_reported_and_merged_for_playback(client):
    status = client.get(f"/api/sessions/{SESSION_ID}/audio/status").json()
    assert status["finalized"] is False
    assert status["chunk_count"] == 2

    audio = client.get(f"/api/sessions/{SESSION_ID}/audio")
    assert audio.status_code == 200
    assert audio.content[:4] == b"RIFF"
