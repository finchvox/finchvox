import logging

import pytest
from opentelemetry import trace
from opentelemetry.context import get_current
from opentelemetry.instrumentation.logging import LoggingInstrumentor
from opentelemetry.instrumentation.logging.handler import LoggingHandler
from opentelemetry.sdk._logs.export import InMemoryLogRecordExporter
from opentelemetry.trace import NonRecordingSpan, SpanContext, TraceFlags

import finchvox


def otel_handlers(root):
    return [
        handler
        for handler in root.handlers
        if isinstance(handler, (LoggingHandler, finchvox.TraceContextLoggingHandler))
    ]


@pytest.fixture
def isolated_log_capture(monkeypatch):
    from opentelemetry.exporter.otlp.proto.grpc import _log_exporter

    root = logging.getLogger()
    monkeypatch.setattr(root, "handlers", [])
    monkeypatch.setattr(root, "level", logging.DEBUG)
    monkeypatch.setattr(finchvox, "_setup_loguru_bridge", lambda: None)
    monkeypatch.setattr(finchvox, "_get_pipecat_context", get_current)
    exporter = InMemoryLogRecordExporter()
    monkeypatch.setattr(_log_exporter, "OTLPLogExporter", lambda **kwargs: exporter)
    instrumentor = LoggingInstrumentor()
    already_instrumented = instrumentor.is_instrumented_by_opentelemetry

    yield root, exporter

    if not already_instrumented and instrumentor.is_instrumented_by_opentelemetry:
        instrumentor.uninstrument()
    for handler in otel_handlers(root):
        otel_handler = getattr(handler, "_otel_handler", handler)
        otel_handler._logger_provider.shutdown()
        handler.close()


@pytest.mark.parametrize("platform", ["livekit", "pipecat"])
def test_explicit_log_handler_preserves_context_and_source(isolated_log_capture, platform):
    root, exporter = isolated_log_capture
    if platform == "livekit":
        provider = finchvox._setup_livekit_log_export("agent", "localhost:4317", True)
    else:
        finchvox._setup_log_capture("agent", "localhost:4317", True)
        provider = otel_handlers(root)[0]._otel_handler._logger_provider
        assert len(otel_handlers(root)) == 1  # No automatic second OTel handler.

    handler = otel_handlers(root)[0]
    handler = getattr(handler, "_otel_handler", handler)
    assert isinstance(handler, LoggingHandler)
    context = SpanContext(
        trace_id=123,
        span_id=456,
        is_remote=False,
        trace_flags=TraceFlags(TraceFlags.SAMPLED),
    )
    record = logging.LogRecord(
        "finchvox.tests", logging.INFO, "agent.py", 42, "hello", (), None,
        func="entrypoint",
    )
    with trace.use_span(NonRecordingSpan(context), end_on_exit=False):
        root.handle(record)
    assert provider.force_flush()

    records = [item.log_record for item in exporter.get_finished_logs()]
    message = next(item for item in records if item.body == "hello")
    assert message.trace_id == 123
    assert message.span_id == 456
    assert message.attributes["code.file.path"] == "agent.py"
    assert message.attributes["code.function.name"] == "entrypoint"
    assert message.attributes["code.line.number"] == 42


def test_livekit_log_setup_does_not_add_duplicate_handlers(isolated_log_capture):
    root, _ = isolated_log_capture
    first = finchvox._setup_livekit_log_export("agent", "localhost:4317", True)
    second = finchvox._setup_livekit_log_export("agent", "localhost:4317", True)

    assert second is first
    assert len(otel_handlers(root)) == 1
