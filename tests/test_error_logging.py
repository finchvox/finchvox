"""Error paths must log a traceback, and logging must never raise on the error text."""

import asyncio
from pathlib import Path
from unittest.mock import Mock

import pytest
from google.protobuf.json_format import SerializeToJsonError
from loguru import logger
from opentelemetry.proto.collector.logs.v1.logs_service_pb2 import (
    ExportLogsServiceRequest,
)
from opentelemetry.proto.collector.trace.v1.trace_service_pb2 import (
    ExportTraceServiceRequest,
)
from opentelemetry.proto.logs.v1.logs_pb2 import LogRecord, ResourceLogs, ScopeLogs
from opentelemetry.proto.trace.v1.trace_pb2 import ResourceSpans, ScopeSpans, Span

from finchvox import environment as environment_module
from finchvox.collector import log_writer as log_writer_module
from finchvox.collector.audio_handler import AudioHandler
from finchvox.collector.log_service import LogCollectorServicer
from finchvox.collector.log_writer import LogWriter
from finchvox.collector.service import TraceCollectorServicer
from finchvox.collector.writer import SpanWriter
from finchvox.environment import EnvironmentSpanProcessor

# Braces matter: Loguru formats a message when given keyword arguments, so this
# text used to raise KeyError from inside the error handler itself.
ERROR_TEXT = "cannot open {path}"


@pytest.fixture
def error_records():
    records = []
    sink_id = logger.add(lambda message: records.append(message.record), level="ERROR")
    yield records
    logger.remove(sink_id)


def _assert_traceback_logged(records):
    assert records, "expected an error to be logged"
    assert records[-1]["exception"] is not None
    assert ERROR_TEXT in records[-1]["message"]


def test_unconvertible_log_does_not_drop_the_rest_of_its_batch(
    tmp_path, monkeypatch, error_records
):
    def failing_conversion(*args, **kwargs):
        raise SerializeToJsonError(ERROR_TEXT)

    monkeypatch.setattr(log_writer_module, "MessageToDict", failing_conversion)
    log_record = LogRecord()
    log_record.trace_id = b"\xab" * 16

    LogWriter(tmp_path).write_log(log_record, ResourceLogs(), ScopeLogs())

    _assert_traceback_logged(error_records)


def test_environment_upload_error_never_reaches_the_users_agent(monkeypatch):
    """on_end runs inside span.end(), so an error here would hit the user's code."""

    async def unexpected_failure(self, trace_id, env):
        raise KeyError("something nobody predicted")

    monkeypatch.setattr(
        EnvironmentSpanProcessor, "_send_environment", unexpected_failure
    )
    monkeypatch.setattr(
        environment_module, "get_captured_environment", lambda: {"os": "test"}
    )
    span = Mock()
    span.get_span_context.return_value.trace_id = 0x1234

    EnvironmentSpanProcessor("http://localhost:3000").on_end(span)


def _span() -> Span:
    span = Span()
    span.trace_id = b"\xab" * 16
    span.span_id = b"\x01" * 8
    return span


def test_span_writer_logs_traceback(tmp_path, monkeypatch, error_records):
    def failing_open(self, *args, **kwargs):
        raise OSError(ERROR_TEXT)

    monkeypatch.setattr(Path, "open", failing_open)

    SpanWriter(tmp_path).write_span(_span(), ResourceSpans(), ScopeSpans())

    _assert_traceback_logged(error_records)


def test_trace_service_logs_traceback(error_records):
    span_writer = Mock()
    span_writer.write_span.side_effect = RuntimeError(ERROR_TEXT)
    request = ExportTraceServiceRequest()
    request.resource_spans.add().scope_spans.add().spans.add()

    response = TraceCollectorServicer(span_writer).Export(request, Mock())

    assert ERROR_TEXT in response.partial_success.error_message
    _assert_traceback_logged(error_records)


def test_log_service_logs_traceback(error_records):
    log_writer = Mock()
    log_writer.write_log.side_effect = RuntimeError(ERROR_TEXT)
    request = ExportLogsServiceRequest()
    request.resource_logs.add().scope_logs.add().log_records.add()

    LogCollectorServicer(log_writer).Export(request, Mock())

    _assert_traceback_logged(error_records)


def test_log_writer_logs_traceback(tmp_path, monkeypatch, error_records):
    def failing_open(self, *args, **kwargs):
        raise OSError(ERROR_TEXT)

    monkeypatch.setattr(Path, "open", failing_open)
    log_record = LogRecord()
    log_record.trace_id = b"\xab" * 16

    LogWriter(tmp_path).write_log(log_record, ResourceLogs(), ScopeLogs())

    _assert_traceback_logged(error_records)


def test_audio_handler_logs_traceback_on_disk_error(tmp_path, monkeypatch, error_records):
    def failing_mkdir(self, *args, **kwargs):
        raise OSError(ERROR_TEXT)

    monkeypatch.setattr(Path, "mkdir", failing_mkdir)

    result = asyncio.run(
        AudioHandler(tmp_path).save_audio_chunk("a" * 32, 0, b"audio", {})
    )

    assert result is None
    _assert_traceback_logged(error_records)


def test_audio_handler_logs_traceback_on_unexpected_error(
    tmp_path, monkeypatch, error_records
):
    def failing_mkdir(self, *args, **kwargs):
        raise ValueError(ERROR_TEXT)

    monkeypatch.setattr(Path, "mkdir", failing_mkdir)

    result = asyncio.run(
        AudioHandler(tmp_path).save_audio_chunk("a" * 32, 0, b"audio", {})
    )

    assert result is None
    _assert_traceback_logged(error_records)


def test_audio_handler_returns_none_for_unserializable_metadata(tmp_path, error_records):
    result = asyncio.run(
        AudioHandler(tmp_path).save_audio_chunk("a" * 32, 0, b"audio", {"bad": object()})
    )

    assert result is None
    assert error_records
    assert error_records[-1]["exception"] is not None
