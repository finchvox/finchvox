"""Metrics that only LiveKit Agents 1.8 reports: usage, blocked loops, dispatch."""

import json

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from finchvox.adapters import LiveKitAdapter
from finchvox.livekit_report import report_usage
from finchvox.metrics import Metrics
from finchvox.ui_routes import register_ui_routes

SESSION_ID = "livekitsession"

REPORT_USAGE = [
    {
        "type": "llm_usage",
        "provider": "google",
        "model": "gemma-4-31b-it",
        "input_tokens": 1200,
        "output_tokens": 340,
        "input_cached_tokens": 800,
    },
    {
        "type": "tts_usage",
        "provider": "xai",
        "model": "tts-1",
        "characters_count": 912,
        "audio_duration": 61.5,
    },
    {"type": "stt_usage", "provider": "deepgram", "model": "nova-3", "audio_duration": 75.0},
    {"type": "eot_usage", "provider": "livekit", "model": "turn-detector-v1", "total_requests": 14},
]


def attributes(**values):
    encoded = []
    for key, value in values.items():
        name = key.replace("__", ".")
        if isinstance(value, float):
            encoded.append({"key": name, "value": {"double_value": value}})
        else:
            encoded.append({"key": name, "value": {"string_value": str(value)}})
    return encoded


def normalized_spans(*spans):
    return LiveKitAdapter().normalize_spans(list(spans))


def blocked_span(span_id, start_nano, duration, severity="warn", task=None):
    values = {"lk__blocking__duration": duration, "lk__blocking__severity": severity}
    if task:
        values["lk__blocking__task"] = task
    return {
        "name": "event_loop_blocked",
        "span_id_hex": span_id,
        "start_time_unix_nano": start_nano,
        "attributes": attributes(**values),
    }


class TestReportUsage:
    def test_lists_each_model_with_only_the_amounts_it_used(self):
        rows = report_usage({"usage": REPORT_USAGE})

        assert [row["kind"] for row in rows] == ["llm", "tts", "stt", "turn detector"]
        assert rows[0] == {
            "kind": "llm",
            "provider": "google",
            "model": "gemma-4-31b-it",
            "amounts": {
                "input_tokens": 1200,
                "output_tokens": 340,
                "input_cached_tokens": 800,
            },
        }
        assert rows[1]["amounts"] == {"characters_count": 912, "audio_duration": 61.5}
        assert rows[3]["amounts"] == {"total_requests": 14}

    @pytest.mark.parametrize("usage", [None, "nope", {}, [None, 3]])
    def test_missing_or_malformed_usage_is_empty(self, usage):
        assert report_usage({"usage": usage}) == []
        assert report_usage({}) == []


class TestEventLoopBlocks:
    def test_blocked_loops_are_listed_in_order_with_their_details(self):
        spans = normalized_spans(
            {"name": "agent_session", "span_id_hex": "root", "start_time_unix_nano": 1_000_000_000},
            blocked_span("late", 9_000_000_000, 0.9, "error", "stt_task"),
            blocked_span("early", 4_000_000_000, 0.15),
        )

        blocks = Metrics(spans).get_event_loop_blocks()

        assert [block["span_id"] for block in blocks] == ["early", "late"]
        assert blocks[0]["duration_ms"] == pytest.approx(150)
        assert blocks[0]["relative_time_ms"] == pytest.approx(3000)
        assert blocks[1]["severity"] == "error"
        assert blocks[1]["task"] == "stt_task"

    def test_sessions_without_blocked_loops_report_none(self):
        spans = normalized_spans({"name": "agent_turn", "start_time_unix_nano": 1})
        assert Metrics(spans).get_event_loop_blocks() == []


class TestJobDispatch:
    def test_dispatch_stages_are_reported_in_milliseconds(self):
        spans = normalized_spans(
            {"name": "agent_session", "start_time_unix_nano": 1},
            {
                "name": "job_entrypoint",
                "start_time_unix_nano": 2,
                "attributes": attributes(
                    lk__job__accept_latency=0.01, lk__job__dispatch_latency=0.42
                ),
            },
        )

        assert Metrics(spans).get_job_dispatch() == pytest.approx(
            {"accept": 10, "dispatch": 420}
        )

    def test_no_dispatch_data_is_an_empty_dict(self):
        spans = normalized_spans({"name": "agent_turn", "start_time_unix_nano": 1})
        assert Metrics(spans).get_job_dispatch() == {}


def test_metrics_dict_includes_the_new_sections():
    spans = normalized_spans(blocked_span("b", 5, 0.3))

    result = Metrics(spans, usage=[{"kind": "llm"}]).to_dict()

    assert result["usage"] == [{"kind": "llm"}]
    assert len(result["event_loop_blocks"]) == 1
    assert result["job_dispatch"] == {}


def test_metrics_endpoint_serves_usage_from_the_stored_report(tmp_path):
    session_dir = tmp_path / "sessions" / SESSION_ID
    session_dir.mkdir(parents=True)
    spans = [
        {"name": "agent_session", "span_id_hex": "root", "start_time_unix_nano": "1000000000"},
        blocked_span("b1", "2000000000", 0.4, "error"),
    ]
    (session_dir / f"trace_{SESSION_ID}.jsonl").write_text(
        "".join(json.dumps(span) + "\n" for span in spans)
    )
    (session_dir / "livekit_report.json").write_text(json.dumps({"usage": REPORT_USAGE}))
    app = FastAPI()
    register_ui_routes(app, tmp_path)

    response = TestClient(app).get(f"/api/sessions/{SESSION_ID}/metrics")

    assert response.status_code == 200
    body = response.json()
    assert [row["kind"] for row in body["usage"]] == ["llm", "tts", "stt", "turn detector"]
    assert body["event_loop_blocks"][0]["severity"] == "error"
