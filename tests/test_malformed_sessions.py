"""One damaged session must not stop the others from being listed."""

import io
import json
import zipfile
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from finchvox.session import Session
from finchvox.ui_routes import register_ui_routes

GOOD_SPAN = {"name": "agent_turn", "start_time_unix_nano": "1000000000"}

SESSION_DATA_ROUTES = ["trace", "raw", "logs", "conversation", "exceptions", "metrics"]

# A nested value deep enough to exhaust Python's recursion limit when decoded.
_DEEP_VALUE = '{"array_value": {"values": [' * 2000 + "{}" + "]}}" * 2000

MALFORMED_TRACE_LINES = [
    pytest.param(b"not json", id="not-json"),
    pytest.param(b"[1, 2]", id="json-list"),
    pytest.param(b"1", id="json-number"),
    pytest.param(b"null", id="json-null"),
    pytest.param(b'"text"', id="json-string"),
    pytest.param(b"\x81\xff", id="undecodable-bytes"),
    pytest.param(b'{"attributes": 5}', id="attributes-not-a-list"),
    pytest.param(b'{"attributes": [5]}', id="attribute-not-a-dict"),
    pytest.param(b'{"name": 5}', id="numeric-name"),
    pytest.param(b'{"name": ["x"]}', id="unhashable-name"),
    pytest.param(b'{"status": 5}', id="status-not-a-dict"),
    pytest.param(b'{"events": 5}', id="events-not-a-list"),
    pytest.param(b'{"start_time_unix_nano": "soon"}', id="bad-start-time"),
    pytest.param(b'{"start_time_unix_nano": null}', id="null-start-time"),
    pytest.param(b'{"resource": 5}', id="resource-not-a-dict"),
    pytest.param(b'{"instrumentation_scope": 5}', id="scope-not-a-dict"),
    pytest.param(
        f'{{"attributes": [{{"key": "k", "value": {_DEEP_VALUE}}}]}}'.encode(),
        id="deeply-nested-value",
    ),
]


@pytest.fixture
def data_dir(tmp_path):
    return tmp_path


@pytest.fixture
def client(data_dir):
    app = FastAPI()
    register_ui_routes(app, data_dir)
    # Fail on the status code rather than re-raising, as a real server would.
    return TestClient(app, raise_server_exceptions=False)


def _write_session(data_dir: Path, session_id: str, trace: bytes) -> Path:
    session_dir = data_dir / "sessions" / session_id
    session_dir.mkdir(parents=True)
    (session_dir / f"trace_{session_id}.jsonl").write_bytes(trace)
    return session_dir


def _good_trace() -> bytes:
    return json.dumps(GOOD_SPAN).encode() + b"\n"


@pytest.mark.parametrize("line", MALFORMED_TRACE_LINES)
def test_session_list_survives_malformed_trace(client, data_dir, line):
    _write_session(data_dir, "good", _good_trace())
    _write_session(data_dir, "damaged", line + b"\n")

    response = client.get("/api/sessions")

    assert response.status_code == 200
    assert "good" in [s["session_id"] for s in response.json()["sessions"]]


@pytest.mark.parametrize("line", MALFORMED_TRACE_LINES)
def test_session_object_survives_malformed_trace(data_dir, line):
    session_dir = _write_session(data_dir, "damaged", line + b"\n")

    session = Session(session_dir)

    assert session.session_id == "damaged"
    assert session.to_dict()["session_id"] == "damaged"


def test_session_list_survives_trace_path_being_a_folder(client, data_dir):
    _write_session(data_dir, "good", _good_trace())
    (data_dir / "sessions" / "damaged" / "trace_damaged.jsonl").mkdir(parents=True)

    response = client.get("/api/sessions")

    assert response.status_code == 200
    assert "good" in [s["session_id"] for s in response.json()["sessions"]]


def test_session_list_survives_undecodable_log_file(client, data_dir):
    session_dir = _write_session(data_dir, "damaged", _good_trace())
    (session_dir / "logs_damaged.jsonl").write_bytes(b"\x81\xff\n")

    response = client.get("/api/sessions")

    assert response.status_code == 200
    listed = {s["session_id"]: s for s in response.json()["sessions"]}
    assert listed["damaged"]["log_count"] == 0


@pytest.mark.parametrize("route", SESSION_DATA_ROUTES)
@pytest.mark.parametrize("line", MALFORMED_TRACE_LINES)
def test_damaged_session_never_gets_a_bare_server_error(client, data_dir, line, route):
    _write_session(data_dir, "damaged", line + b"\n")

    response = client.get(f"/api/sessions/damaged/{route}")

    if response.status_code != 200:
        assert response.status_code == 500
        assert "damaged" in response.json()["detail"]


def test_trace_route_explains_a_wrong_shape_span(client, data_dir):
    _write_session(data_dir, "damaged", b"[1, 2]\n")

    response = client.get("/api/sessions/damaged/trace")

    assert response.status_code == 500
    assert "damaged" in response.json()["detail"]


@pytest.mark.parametrize(
    "log_line",
    [
        pytest.param(b"\x81\xff", id="undecodable-bytes"),
        pytest.param(b'{"time_unix_nano": "soon"}', id="bad-timestamp"),
        pytest.param(b"[1, 2]", id="json-list"),
    ],
)
def test_logs_route_explains_damaged_logs(client, data_dir, log_line):
    session_dir = _write_session(data_dir, "damaged", _good_trace())
    (session_dir / "logs_damaged.jsonl").write_bytes(log_line + b"\n")

    response = client.get("/api/sessions/damaged/logs")

    assert response.status_code == 500
    assert "damaged" in response.json()["detail"]


def test_good_session_routes_still_work(client, data_dir):
    _write_session(data_dir, "good", _good_trace())

    for route in SESSION_DATA_ROUTES:
        assert client.get(f"/api/sessions/good/{route}").status_code == 200


def _upload(client, entries: dict[str, bytes]):
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w") as zf:
        for name, content in entries.items():
            zf.writestr(name, content)
    zip_buffer.seek(0)
    return client.post(
        "/api/sessions/upload",
        files={"file": ("test.zip", zip_buffer, "application/zip")},
    )


@pytest.mark.parametrize("line", MALFORMED_TRACE_LINES)
def test_upload_rejects_malformed_trace_and_keeps_old_session(client, data_dir, line):
    old_trace = _write_session(data_dir, "existing", _good_trace())
    old_trace = old_trace / "trace_existing.jsonl"

    response = _upload(client, {"existing/trace_existing.jsonl": line + b"\n"})

    assert response.status_code == 400
    assert "agent_turn" in old_trace.read_text()
    assert [p.name for p in (data_dir / "sessions").iterdir()] == ["existing"]


def test_upload_rejection_names_the_bad_line(client):
    response = _upload(
        client, {"s1/trace_s1.jsonl": _good_trace() + b"[1, 2]\n"}
    )

    assert response.status_code == 400
    detail = response.json()["detail"]
    assert "Line 2" in detail
    assert "trace_s1.jsonl" in detail


def test_upload_rejects_non_object_line_in_logs(client):
    response = _upload(
        client,
        {
            "s1/trace_s1.jsonl": _good_trace(),
            "s1/logs_s1.jsonl": b'"not an object"\n',
        },
    )

    assert response.status_code == 400
    assert "logs_s1.jsonl" in response.json()["detail"]


def test_upload_without_a_trace_file_is_rejected(client, data_dir):
    response = _upload(client, {"s1/logs_s1.jsonl": b'{"body": "hello"}\n'})

    assert response.status_code == 400
    assert "trace_s1.jsonl" in response.json()["detail"]
    assert not (data_dir / "sessions" / "s1").exists()


def test_upload_error_does_not_reveal_server_paths(client, data_dir):
    response = _upload(client, {"s1/trace_s1.jsonl": b'{"attributes": 5}\n'})

    assert response.status_code == 400
    assert str(data_dir) not in response.json()["detail"]
    assert ".upload-" not in response.json()["detail"]


def test_session_records_why_its_trace_could_not_be_loaded(data_dir):
    good = Session(_write_session(data_dir, "good", _good_trace()))
    damaged = Session(_write_session(data_dir, "damaged", b"[1, 2]\n"))

    assert good.load_error is None
    assert damaged.load_error
