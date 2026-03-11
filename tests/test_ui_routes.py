import json
import tempfile
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from finchvox.ui_routes import register_ui_routes


@pytest.fixture
def temp_data_dir():
    """Create a temporary data directory for tests."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def app_with_temp_dir(temp_data_dir):
    """Create a FastAPI app with routes registered to temp directory."""
    app = FastAPI()
    register_ui_routes(app, temp_data_dir)
    return app


@pytest.fixture
def client(app_with_temp_dir):
    """Create a test client for the app."""
    return TestClient(app_with_temp_dir)


def create_session_with_logs(data_dir: Path, session_id: str, spans: list, logs: list):
    """Helper to create session trace and log files for testing."""
    session_dir = data_dir / "sessions" / session_id
    session_dir.mkdir(parents=True, exist_ok=True)

    trace_file = session_dir / f"trace_{session_id}.jsonl"
    with trace_file.open("w") as f:
        for span in spans:
            json.dump(span, f)
            f.write("\n")

    if logs:
        log_file = session_dir / f"logs_{session_id}.jsonl"
        with log_file.open("w") as f:
            for log in logs:
                json.dump(log, f)
                f.write("\n")


class TestListSessionsEndpoint:
    def test_returns_empty_list_with_pagination_metadata_when_no_sessions(
        self, client, temp_data_dir
    ):
        response = client.get("/api/sessions")

        assert response.status_code == 200
        data = response.json()
        assert data["sessions"] == []
        assert data["total_count"] == 0
        assert data["total_pages"] == 1
        assert data["page"] == 1
        assert data["page_size"] == 50
        assert data["has_previous_page"] is False
        assert data["has_next_page"] is False
        assert "data_dir" in data

    def test_returns_sessions_with_all_pagination_fields(self, client, temp_data_dir):
        session_id = "testsession123"
        spans = [
            {
                "name": "test-span",
                "start_time_unix_nano": 1000000000000000000,
                "end_time_unix_nano": 2000000000000000000,
            }
        ]
        create_session_with_logs(temp_data_dir, session_id, spans, logs=[])

        response = client.get("/api/sessions")

        assert response.status_code == 200
        data = response.json()
        assert len(data["sessions"]) == 1
        assert data["sessions"][0]["session_id"] == session_id
        assert data["total_count"] == 1
        assert data["total_pages"] == 1
        assert data["page"] == 1
        assert data["has_previous_page"] is False
        assert data["has_next_page"] is False

    def test_respects_page_query_parameter(self, client, temp_data_dir):
        for i in range(60):
            session_id = f"session{i:03d}"
            spans = [
                {
                    "name": "test-span",
                    "start_time_unix_nano": i * 1000000000000000000,
                    "end_time_unix_nano": i * 1000000000000000000 + 1000000000,
                }
            ]
            create_session_with_logs(temp_data_dir, session_id, spans, logs=[])

        response = client.get("/api/sessions?page=2")

        assert response.status_code == 200
        data = response.json()
        assert len(data["sessions"]) == 10
        assert data["total_count"] == 60
        assert data["total_pages"] == 2
        assert data["page"] == 2
        assert data["has_previous_page"] is True
        assert data["has_next_page"] is False

    def test_invalid_page_defaults_to_valid_range(self, client, temp_data_dir):
        session_id = "testsession123"
        spans = [
            {
                "name": "test-span",
                "start_time_unix_nano": 1000000000000000000,
                "end_time_unix_nano": 2000000000000000000,
            }
        ]
        create_session_with_logs(temp_data_dir, session_id, spans, logs=[])

        response = client.get("/api/sessions?page=0")
        assert response.status_code == 200
        assert response.json()["page"] == 1

        response = client.get("/api/sessions?page=-1")
        assert response.status_code == 200
        assert response.json()["page"] == 1

        response = client.get("/api/sessions?page=999")
        assert response.status_code == 200
        assert response.json()["page"] == 1


class TestGetLogsEndpoint:
    def test_returns_logs_for_valid_session(self, client, temp_data_dir):
        session_id = "abc123def456"
        spans = [
            {
                "name": "test-span",
                "start_time_unix_nano": 1000000000,
                "end_time_unix_nano": 2000000000,
            }
        ]
        logs = [
            {
                "time_unix_nano": 1500000000,
                "severity_text": "INFO",
                "body": "Test message 1",
            },
            {
                "time_unix_nano": 1200000000,
                "severity_text": "DEBUG",
                "body": "Test message 2",
            },
        ]
        create_session_with_logs(temp_data_dir, session_id, spans, logs)

        response = client.get(f"/api/sessions/{session_id}/logs")

        assert response.status_code == 200
        data = response.json()
        assert "logs" in data
        assert len(data["logs"]) == 2
        assert data["total_count"] == 2
        assert data["limit"] == 1000
        assert data["trace_start_time"] == 1000000000

    def test_returns_empty_array_for_session_with_no_logs_file(
        self, client, temp_data_dir
    ):
        session_id = "nologs123"
        spans = [
            {
                "name": "test-span",
                "start_time_unix_nano": 5000000000,
                "end_time_unix_nano": 6000000000,
            }
        ]
        create_session_with_logs(temp_data_dir, session_id, spans, logs=[])

        response = client.get(f"/api/sessions/{session_id}/logs")

        assert response.status_code == 200
        data = response.json()
        assert data["logs"] == []
        assert data["total_count"] == 0
        assert data["trace_start_time"] == 5000000000

    def test_returns_404_for_nonexistent_session(self, client):
        response = client.get("/api/sessions/nonexistent_session_id/logs")

        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()

    def test_respects_limit_parameter(self, client, temp_data_dir):
        session_id = "limittest123"
        spans = [{"name": "span", "start_time_unix_nano": 1000000000}]
        logs = [
            {"time_unix_nano": i * 1000000, "severity_text": "INFO", "body": f"Log {i}"}
            for i in range(10)
        ]
        create_session_with_logs(temp_data_dir, session_id, spans, logs)

        response = client.get(f"/api/sessions/{session_id}/logs?limit=5")

        assert response.status_code == 200
        data = response.json()
        assert len(data["logs"]) == 5
        assert data["total_count"] == 10
        assert data["limit"] == 5

    def test_logs_sorted_by_timestamp_ascending(self, client, temp_data_dir):
        session_id = "sorttest123"
        spans = [{"name": "span", "start_time_unix_nano": 1000000000}]
        logs = [
            {"time_unix_nano": 3000000000, "severity_text": "INFO", "body": "Third"},
            {"time_unix_nano": 1000000000, "severity_text": "INFO", "body": "First"},
            {"time_unix_nano": 2000000000, "severity_text": "INFO", "body": "Second"},
        ]
        create_session_with_logs(temp_data_dir, session_id, spans, logs)

        response = client.get(f"/api/sessions/{session_id}/logs")

        assert response.status_code == 200
        data = response.json()
        assert data["logs"][0]["body"] == "First"
        assert data["logs"][1]["body"] == "Second"
        assert data["logs"][2]["body"] == "Third"

    def test_trace_start_time_is_minimum_span_start(self, client, temp_data_dir):
        session_id = "starttime123"
        spans = [
            {"name": "span1", "start_time_unix_nano": 5000000000},
            {"name": "span2", "start_time_unix_nano": 3000000000},
            {"name": "span3", "start_time_unix_nano": 7000000000},
        ]
        logs = [{"time_unix_nano": 4000000000, "severity_text": "INFO", "body": "Test"}]
        create_session_with_logs(temp_data_dir, session_id, spans, logs)

        response = client.get(f"/api/sessions/{session_id}/logs")

        assert response.status_code == 200
        data = response.json()
        assert data["trace_start_time"] == 3000000000
