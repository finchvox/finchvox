import json
import tempfile
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from finchvox.metrics import Metrics
from finchvox.ui_routes import register_ui_routes


@pytest.fixture
def temp_data_dir():
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def app_with_temp_dir(temp_data_dir):
    app = FastAPI()
    register_ui_routes(app, temp_data_dir)
    return app


@pytest.fixture
def client(app_with_temp_dir):
    return TestClient(app_with_temp_dir)


def create_session_with_spans(data_dir: Path, session_id: str, spans: list):
    session_dir = data_dir / "sessions" / session_id
    session_dir.mkdir(parents=True, exist_ok=True)

    trace_file = session_dir / f"trace_{session_id}.jsonl"
    with trace_file.open("w") as f:
        for span in spans:
            json.dump(span, f)
            f.write("\n")


CATEGORY_MAP = {
    "stt": "stt",
    "llm": "llm",
    "tts": "tts",
    "turn": "turn",
    "conversation": "root",
}


def make_span(
    name: str, start_nano: int, ttfb_seconds: float | None = None, span_id: str = "abc123"
):
    span = {
        "name": name,
        "span_id_hex": span_id,
        "start_time_unix_nano": str(start_nano),
        "end_time_unix_nano": str(start_nano + 1000000000),
        "attributes": [],
        "_normalized": {
            "platform": "pipecat",
            "display_name": name.upper(),
            "category": CATEGORY_MAP.get(name, "other"),
            "css_class": f"bar-{name}",
            "transcript": None,
            "output_text": None,
            "ttfb_seconds": ttfb_seconds,
        },
    }
    if ttfb_seconds is not None:
        span["attributes"].append(
            {"key": "metrics.ttfb", "value": {"double_value": ttfb_seconds}}
        )
    return span


def make_turn_span(
    start_nano: int, latency_seconds: float | None = None, span_id: str = "turn123"
):
    span = {
        "name": "turn",
        "span_id_hex": span_id,
        "start_time_unix_nano": str(start_nano),
        "end_time_unix_nano": str(start_nano + 1000000000),
        "attributes": [],
    }
    if latency_seconds is not None:
        span["attributes"].append(
            {
                "key": "turn.user_bot_latency_seconds",
                "value": {"double_value": latency_seconds},
            }
        )
    return span


def get_llm_series(spans: list):
    return Metrics(spans).get_ttfb_series()["llm"]


class TestMetricsClass:
    def test_extracts_ttfb_from_spans(self):
        spans = [
            make_span("llm", 1000000000000, ttfb_seconds=1.5, span_id="span1"),
            make_span("llm", 2000000000000, ttfb_seconds=2.0, span_id="span2"),
        ]
        llm_series = get_llm_series(spans)

        assert len(llm_series.data_points) == 2
        assert llm_series.data_points[0].ttfb_ms == 1500.0
        assert llm_series.data_points[1].ttfb_ms == 2000.0

    def test_groups_by_service(self):
        spans = [
            make_span("stt", 1000000000000, ttfb_seconds=0.1, span_id="stt1"),
            make_span("llm", 1100000000000, ttfb_seconds=1.0, span_id="llm1"),
            make_span("tts", 1200000000000, ttfb_seconds=0.05, span_id="tts1"),
        ]

        metrics = Metrics(spans)
        series = metrics.get_ttfb_series()

        assert "stt" in series
        assert "llm" in series
        assert "tts" in series
        assert len(series["stt"].data_points) == 1
        assert len(series["llm"].data_points) == 1
        assert len(series["tts"].data_points) == 1

    def test_ignores_spans_without_ttfb(self):
        spans = [
            make_span("llm", 1000000000000, ttfb_seconds=1.0, span_id="with_ttfb"),
            make_span("llm", 2000000000000, ttfb_seconds=None, span_id="without_ttfb"),
        ]

        metrics = Metrics(spans)
        series = metrics.get_ttfb_series()

        assert len(series["llm"].data_points) == 1
        assert series["llm"].data_points[0].span_id == "with_ttfb"

    def test_ignores_non_service_spans(self):
        spans = [
            make_span("conversation", 1000000000000, ttfb_seconds=1.0, span_id="conv1"),
            make_span("turn", 1100000000000, ttfb_seconds=0.5, span_id="turn1"),
            make_span("llm", 1200000000000, ttfb_seconds=2.0, span_id="llm1"),
        ]

        metrics = Metrics(spans)
        series = metrics.get_ttfb_series()

        assert "conversation" not in series
        assert "turn" not in series
        assert "llm" in series

    def test_computes_relative_time(self):
        spans = [
            make_span("llm", 1000000000000, ttfb_seconds=1.0, span_id="span1"),
            make_span("llm", 1500000000000, ttfb_seconds=2.0, span_id="span2"),
        ]
        llm_series = get_llm_series(spans)

        assert llm_series.data_points[0].relative_time_ms == 0.0
        assert llm_series.data_points[1].relative_time_ms == 500000.0

    def test_sorts_data_points_by_timestamp(self):
        spans = [
            make_span("llm", 3000000000000, ttfb_seconds=3.0, span_id="span3"),
            make_span("llm", 1000000000000, ttfb_seconds=1.0, span_id="span1"),
            make_span("llm", 2000000000000, ttfb_seconds=2.0, span_id="span2"),
        ]

        metrics = Metrics(spans)
        series = metrics.get_ttfb_series()

        assert series["llm"].data_points[0].span_id == "span1"
        assert series["llm"].data_points[1].span_id == "span2"
        assert series["llm"].data_points[2].span_id == "span3"

    def test_computes_statistics(self):
        spans = [
            make_span("llm", 1000000000000, ttfb_seconds=1.0, span_id="span1"),
            make_span("llm", 2000000000000, ttfb_seconds=2.0, span_id="span2"),
            make_span("llm", 3000000000000, ttfb_seconds=3.0, span_id="span3"),
            make_span("llm", 4000000000000, ttfb_seconds=4.0, span_id="span4"),
        ]

        metrics = Metrics(spans)
        series = metrics.get_ttfb_series()
        stats = series["llm"].stats

        assert stats.count == 4
        assert stats.min_ms == 1000.0
        assert stats.max_ms == 4000.0
        assert stats.avg_ms == 2500.0
        assert stats.p50_ms == 3000.0

    def test_to_dict_format(self):
        spans = [
            make_span("llm", 1000000000000, ttfb_seconds=1.0, span_id="span1"),
        ]

        metrics = Metrics(spans)
        result = metrics.to_dict()

        assert "series" in result
        assert "services" in result
        assert "llm" in result["series"]
        assert "llm" in result["services"]
        assert "data_points" in result["series"]["llm"]
        assert "stats" in result["series"]["llm"]

    def test_empty_spans(self):
        metrics = Metrics([])
        result = metrics.to_dict()

        assert result["series"] == {}
        assert result["services"] == []

    def test_session_start_ms_caching(self):
        spans = [
            make_span("llm", 1000000000000, ttfb_seconds=1.0),
        ]

        metrics = Metrics(spans)

        first_call = metrics.session_start_ms
        second_call = metrics.session_start_ms

        assert first_call == second_call == 1000000.0

    def test_extracts_user_bot_latency_from_turn_spans(self):
        spans = [
            make_turn_span(1000000000000, latency_seconds=1.5, span_id="turn1"),
            make_turn_span(2000000000000, latency_seconds=2.0, span_id="turn2"),
        ]
        metrics = Metrics(spans)
        series = metrics.get_user_bot_latency_series()

        assert series is not None
        assert len(series.data_points) == 2
        assert series.data_points[0].latency_ms == 1500.0
        assert series.data_points[1].latency_ms == 2000.0

    def test_ignores_turns_without_latency_attribute(self):
        spans = [
            make_turn_span(1000000000000, latency_seconds=1.0, span_id="with_latency"),
            make_turn_span(
                2000000000000, latency_seconds=None, span_id="without_latency"
            ),
        ]
        metrics = Metrics(spans)
        series = metrics.get_user_bot_latency_series()

        assert len(series.data_points) == 1
        assert series.data_points[0].span_id == "with_latency"

    def test_ignores_non_turn_spans_for_latency(self):
        spans = [
            make_span("llm", 1000000000000, ttfb_seconds=1.0, span_id="llm1"),
            make_span("stt", 1100000000000, ttfb_seconds=0.5, span_id="stt1"),
            make_turn_span(1200000000000, latency_seconds=2.0, span_id="turn1"),
        ]
        metrics = Metrics(spans)
        series = metrics.get_user_bot_latency_series()

        assert len(series.data_points) == 1
        assert series.data_points[0].span_id == "turn1"

    def test_computes_user_bot_latency_relative_time(self):
        spans = [
            make_turn_span(1000000000000, latency_seconds=1.0, span_id="turn1"),
            make_turn_span(1500000000000, latency_seconds=2.0, span_id="turn2"),
        ]
        metrics = Metrics(spans)
        series = metrics.get_user_bot_latency_series()

        assert series.data_points[0].relative_time_ms == 0.0
        assert series.data_points[1].relative_time_ms == 500000.0

    def test_sorts_latency_data_points_by_timestamp(self):
        spans = [
            make_turn_span(3000000000000, latency_seconds=3.0, span_id="turn3"),
            make_turn_span(1000000000000, latency_seconds=1.0, span_id="turn1"),
            make_turn_span(2000000000000, latency_seconds=2.0, span_id="turn2"),
        ]
        metrics = Metrics(spans)
        series = metrics.get_user_bot_latency_series()

        assert series.data_points[0].span_id == "turn1"
        assert series.data_points[1].span_id == "turn2"
        assert series.data_points[2].span_id == "turn3"

    def test_computes_user_bot_latency_statistics(self):
        spans = [
            make_turn_span(1000000000000, latency_seconds=1.0, span_id="turn1"),
            make_turn_span(2000000000000, latency_seconds=2.0, span_id="turn2"),
            make_turn_span(3000000000000, latency_seconds=3.0, span_id="turn3"),
            make_turn_span(4000000000000, latency_seconds=4.0, span_id="turn4"),
        ]
        metrics = Metrics(spans)
        series = metrics.get_user_bot_latency_series()
        stats = series.stats

        assert stats.count == 4
        assert stats.min_ms == 1000.0
        assert stats.max_ms == 4000.0
        assert stats.avg_ms == 2500.0
        assert stats.p50_ms == 3000.0

    def test_to_dict_includes_user_bot_latency(self):
        spans = [
            make_turn_span(1000000000000, latency_seconds=1.0, span_id="turn1"),
        ]
        metrics = Metrics(spans)
        result = metrics.to_dict()

        assert "user_bot_latency" in result
        assert result["user_bot_latency"] is not None
        assert "data_points" in result["user_bot_latency"]
        assert "stats" in result["user_bot_latency"]

    def test_empty_when_no_turns_with_latency(self):
        spans = [
            make_span("llm", 1000000000000, ttfb_seconds=1.0, span_id="llm1"),
            make_turn_span(1100000000000, latency_seconds=None, span_id="turn1"),
        ]
        metrics = Metrics(spans)
        result = metrics.to_dict()

        assert result["user_bot_latency"] is None


class TestMetricsEndpoint:
    def test_returns_metrics_for_valid_session(self, client, temp_data_dir):
        session_id = "metrics_test_123"
        spans = [
            make_span("stt", 1000000000000, ttfb_seconds=0.1, span_id="stt1"),
            make_span("llm", 1100000000000, ttfb_seconds=1.5, span_id="llm1"),
            make_span("tts", 1200000000000, ttfb_seconds=0.05, span_id="tts1"),
        ]
        create_session_with_spans(temp_data_dir, session_id, spans)

        response = client.get(f"/api/sessions/{session_id}/metrics")

        assert response.status_code == 200
        data = response.json()
        assert "series" in data
        assert "services" in data
        assert set(data["services"]) == {"stt", "llm", "tts"}

    def test_returns_empty_for_session_without_ttfb(self, client, temp_data_dir):
        session_id = "no_ttfb_session"
        spans = [
            make_span("llm", 1000000000000, ttfb_seconds=None, span_id="llm1"),
        ]
        create_session_with_spans(temp_data_dir, session_id, spans)

        response = client.get(f"/api/sessions/{session_id}/metrics")

        assert response.status_code == 200
        data = response.json()
        assert data["series"] == {}
        assert data["services"] == []

    def test_returns_404_for_nonexistent_session(self, client):
        response = client.get("/api/sessions/nonexistent_metrics_session/metrics")

        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()

    def test_stats_included_in_response(self, client, temp_data_dir):
        session_id = "stats_test_session"
        spans = [
            make_span("llm", 1000000000000, ttfb_seconds=1.0, span_id="llm1"),
            make_span("llm", 2000000000000, ttfb_seconds=2.0, span_id="llm2"),
        ]
        create_session_with_spans(temp_data_dir, session_id, spans)

        response = client.get(f"/api/sessions/{session_id}/metrics")

        assert response.status_code == 200
        data = response.json()
        llm_stats = data["series"]["llm"]["stats"]
        assert "avg_ms" in llm_stats
        assert "min_ms" in llm_stats
        assert "max_ms" in llm_stats
        assert "p50_ms" in llm_stats
        assert "p95_ms" in llm_stats
        assert "count" in llm_stats
        assert llm_stats["count"] == 2

    def test_returns_user_bot_latency_for_valid_session(self, client, temp_data_dir):
        session_id = "latency_test_123"
        spans = [
            make_turn_span(1000000000000, latency_seconds=1.5, span_id="turn1"),
            make_turn_span(2000000000000, latency_seconds=2.0, span_id="turn2"),
        ]
        create_session_with_spans(temp_data_dir, session_id, spans)

        response = client.get(f"/api/sessions/{session_id}/metrics")

        assert response.status_code == 200
        data = response.json()
        assert "user_bot_latency" in data
        assert data["user_bot_latency"] is not None
        assert len(data["user_bot_latency"]["data_points"]) == 2

    def test_latency_stats_included_in_response(self, client, temp_data_dir):
        session_id = "latency_stats_session"
        spans = [
            make_turn_span(1000000000000, latency_seconds=1.0, span_id="turn1"),
            make_turn_span(2000000000000, latency_seconds=2.0, span_id="turn2"),
        ]
        create_session_with_spans(temp_data_dir, session_id, spans)

        response = client.get(f"/api/sessions/{session_id}/metrics")

        assert response.status_code == 200
        data = response.json()
        latency_stats = data["user_bot_latency"]["stats"]
        assert "avg_ms" in latency_stats
        assert "min_ms" in latency_stats
        assert "max_ms" in latency_stats
        assert "p50_ms" in latency_stats
        assert "p95_ms" in latency_stats
        assert "count" in latency_stats
        assert latency_stats["count"] == 2


def test_livekit_agent_turn_e2e_latency_is_exposed():
    span = {
        "name": "agent_turn",
        "span_id_hex": "agent1",
        "start_time_unix_nano": 1_000_000_000,
        "attributes": [{"key": "lk.e2e_latency", "value": {"double_value": 1.25}}],
        "_normalized": {"category": "turn", "e2e_latency_seconds": 1.25},
    }
    metrics = Metrics([span]).to_dict()
    assert metrics["user_bot_latency"] is not None
    assert metrics["user_bot_latency"]["data_points"][0]["latency_ms"] == 1250


def test_livekit_turn_breakdown_is_exposed():
    span = {
        "name": "user_turn",
        "span_id_hex": "user1",
        "start_time_unix_nano": 1_000_000_000,
        "_normalized": {
            "category": "stt",
            "transcription_delay_seconds": 0.15,
            "end_of_turn_delay_seconds": 0.25,
        },
    }
    metrics = Metrics([span]).to_dict()
    assert metrics["turn_breakdown"]["transcription"]["stats"]["avg_ms"] == 150
    assert metrics["turn_breakdown"]["endpointing"]["stats"]["avg_ms"] == 250
