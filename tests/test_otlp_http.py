"""OpenTelemetry over HTTP, the paths LiveKit uploads to when
LIVEKIT_OBSERVABILITY_URL points at Finchvox."""

import gzip
import json

import pytest
from fastapi.testclient import TestClient
from opentelemetry.proto.collector.logs.v1.logs_service_pb2 import (
    ExportLogsServiceRequest,
    ExportLogsServiceResponse,
)
from opentelemetry.proto.collector.metrics.v1.metrics_service_pb2 import (
    ExportMetricsServiceRequest,
    ExportMetricsServiceResponse,
)
from opentelemetry.proto.collector.trace.v1.trace_service_pb2 import (
    ExportTraceServiceRequest,
    ExportTraceServiceResponse,
)
from opentelemetry.proto.common.v1.common_pb2 import AnyValue, KeyValue
from opentelemetry.proto.logs.v1.logs_pb2 import LogRecord, ResourceLogs, ScopeLogs
from opentelemetry.proto.metrics.v1.metrics_pb2 import ResourceMetrics
from opentelemetry.proto.trace.v1.trace_pb2 import ResourceSpans, ScopeSpans, Span

from finchvox.collector.config import get_session_dir
from finchvox.server import UnifiedServer

TRACE_ID = bytes.fromhex("0123456789abcdef0123456789abcdef")
TOKEN = "Bearer eyJhbGciOiJIUzI1NiJ9.do-not-store-me.signature"
PROTOBUF = {"Content-Type": "application/x-protobuf"}


@pytest.fixture
def server(tmp_path):
    return TestClient(UnifiedServer(data_dir=tmp_path).app), tmp_path


def span_request(name="agent_session") -> bytes:
    span = Span(
        trace_id=TRACE_ID,
        span_id=bytes.fromhex("1111111111111111"),
        name=name,
        start_time_unix_nano=1_000_000_000,
        end_time_unix_nano=2_000_000_000,
        attributes=[KeyValue(key="job_id", value=AnyValue(string_value="AJ_1"))],
    )
    request = ExportTraceServiceRequest(
        resource_spans=[ResourceSpans(scope_spans=[ScopeSpans(spans=[span])])]
    )
    return request.SerializeToString()


def log_request(trace_id=TRACE_ID) -> bytes:
    record = LogRecord(
        time_unix_nano=1_500_000_000,
        body=AnyValue(string_value="agent said hi"),
        trace_id=trace_id,
        span_id=bytes.fromhex("1111111111111111"),
    )
    request = ExportLogsServiceRequest(
        resource_logs=[ResourceLogs(scope_logs=[ScopeLogs(log_records=[record])])]
    )
    return request.SerializeToString()


def post(client, path, body, *, gzipped=True, headers=None):
    headers = {**PROTOBUF, **(headers or {})}
    if gzipped:
        body = gzip.compress(body)
        headers["Content-Encoding"] = "gzip"
    return client.post(path, content=body, headers=headers)


class TestTraces:
    def test_gzipped_spans_are_stored_like_grpc_spans(self, server):
        client, data_dir = server

        response = post(client, "/observability/traces/otlp/v0", span_request())

        assert response.status_code == 200
        assert response.headers["content-type"] == "application/x-protobuf"
        ExportTraceServiceResponse.FromString(response.content)
        trace_file = get_session_dir(data_dir, TRACE_ID.hex()) / f"trace_{TRACE_ID.hex()}.jsonl"
        stored = json.loads(trace_file.read_text().splitlines()[0])
        assert stored["name"] == "agent_session"
        assert stored["span_id_hex"] == "1111111111111111"

    def test_uncompressed_spans_are_accepted(self, server):
        client, data_dir = server

        response = post(client, "/observability/traces/otlp/v0", span_request(), gzipped=False)

        assert response.status_code == 200
        assert (get_session_dir(data_dir, TRACE_ID.hex()) / f"trace_{TRACE_ID.hex()}.jsonl").exists()


class TestLogs:
    def test_logs_are_stored_with_their_trace(self, server):
        client, data_dir = server

        response = post(client, "/observability/logs/otlp/v0", log_request())

        assert response.status_code == 200
        ExportLogsServiceResponse.FromString(response.content)
        log_file = get_session_dir(data_dir, TRACE_ID.hex()) / f"logs_{TRACE_ID.hex()}.jsonl"
        assert json.loads(log_file.read_text())["body"]["string_value"] == "agent said hi"


class TestMetrics:
    def test_metrics_are_acknowledged_but_not_stored(self, server):
        client, data_dir = server
        body = ExportMetricsServiceRequest(resource_metrics=[ResourceMetrics()]).SerializeToString()

        response = post(client, "/observability/metrics/otlp/v0", body)

        assert response.status_code == 200
        ExportMetricsServiceResponse.FromString(response.content)
        assert not (data_dir / "sessions").exists() or not any((data_dir / "sessions").iterdir())


class TestBadInput:
    def test_a_body_that_is_not_protobuf_is_rejected(self, server):
        client, _ = server

        response = post(client, "/observability/traces/otlp/v0", b"\xff\xfe not protobuf")

        assert response.status_code == 400

    def test_a_broken_gzip_body_is_rejected(self, server):
        client, _ = server

        response = client.post(
            "/observability/traces/otlp/v0",
            content=b"not gzip at all",
            headers={**PROTOBUF, "Content-Encoding": "gzip"},
        )

        assert response.status_code == 400

    def test_an_unknown_compression_is_rejected(self, server):
        client, _ = server

        response = client.post(
            "/observability/traces/otlp/v0",
            content=span_request(),
            headers={**PROTOBUF, "Content-Encoding": "br"},
        )

        assert response.status_code == 415

    def test_a_body_that_unpacks_beyond_the_limit_is_refused(self, server, monkeypatch):
        from finchvox.collector import otlp_http

        monkeypatch.setattr(otlp_http, "MAX_OTLP_BYTES", 1024)
        client, _ = server

        response = post(client, "/observability/traces/otlp/v0", b"\x00" * 10_000)

        assert response.status_code == 413


def test_the_upload_token_is_never_stored(server):
    client, data_dir = server

    post(client, "/observability/traces/otlp/v0", span_request(), headers={"Authorization": TOKEN})
    post(client, "/observability/logs/otlp/v0", log_request(), headers={"Authorization": TOKEN})

    stored = "".join(p.read_text() for p in data_dir.rglob("*") if p.is_file())
    assert stored
    assert "do-not-store-me" not in stored
