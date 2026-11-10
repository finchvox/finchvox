from unittest.mock import Mock

from opentelemetry.proto.collector.trace.v1.trace_service_pb2 import (
    ExportTraceServiceRequest,
)
from opentelemetry.proto.common.v1.common_pb2 import InstrumentationScope
from opentelemetry.proto.resource.v1.resource_pb2 import Resource
from opentelemetry.proto.trace.v1.trace_pb2 import ResourceSpans, ScopeSpans, Span

from finchvox.collector.service import TraceCollectorServicer


def create_test_request(num_spans=1):
    """Helper to build a test ExportTraceServiceRequest with spans."""
    request = ExportTraceServiceRequest()

    # Create ResourceSpans
    resource_spans = ResourceSpans()
    resource = Resource()
    resource_spans.resource.CopyFrom(resource)

    # Create ScopeSpans
    scope_spans = ScopeSpans()
    scope = InstrumentationScope()
    scope.name = "test-scope"
    scope_spans.scope.CopyFrom(scope)

    # Add test spans
    for i in range(num_spans):
        span = Span()
        span.trace_id = b"\x01" * 16
        span.span_id = bytes([i] * 8)
        span.name = f"test-span-{i}"
        scope_spans.spans.append(span)

    resource_spans.scope_spans.append(scope_spans)
    request.resource_spans.append(resource_spans)

    return request


def test_export_processes_spans():
    """Test that Export() method processes spans and calls writer."""
    mock_writer = Mock()
    servicer = TraceCollectorServicer(mock_writer)

    # Create request with 3 test spans
    request = create_test_request(num_spans=3)
    context = Mock()

    # Call Export
    response = servicer.Export(request, context)

    # Verify writer was called for each span
    assert mock_writer.write_span.call_count == 3, (
        "Expected writer to be called 3 times"
    )

    # Verify response indicates success
    assert response.partial_success.rejected_spans == 0
    assert response.partial_success.error_message == ""


def test_export_returns_success():
    """Test that Export() returns proper ExportTraceServiceResponse."""
    mock_writer = Mock()
    servicer = TraceCollectorServicer(mock_writer)

    # Create request with 1 span
    request = create_test_request(num_spans=1)
    context = Mock()

    # Call Export
    response = servicer.Export(request, context)

    # Verify response structure
    assert hasattr(response, "partial_success")
    assert response.partial_success.rejected_spans == 0
    assert response.partial_success.error_message == ""


def test_export_handles_errors():
    """Test that Export() logs errors and continues (doesn't crash)."""
    mock_writer = Mock()
    # Make writer raise an exception
    mock_writer.write_span.side_effect = Exception("Test error")

    servicer = TraceCollectorServicer(mock_writer)

    # Create request with 1 span
    request = create_test_request(num_spans=1)
    context = Mock()

    # Call Export - should not raise exception
    response = servicer.Export(request, context)

    # Verify it returns a response (not crash)
    assert response is not None
    assert hasattr(response, "partial_success")

    # Error message should be present
    assert response.partial_success.error_message != ""


def test_export_with_multiple_resource_spans():
    """Test Export with multiple ResourceSpans containing multiple ScopeSpans."""
    mock_writer = Mock()
    servicer = TraceCollectorServicer(mock_writer)

    # Create a more complex request with 2 ResourceSpans
    request = ExportTraceServiceRequest()

    for rs_idx in range(2):
        resource_spans = ResourceSpans()
        resource = Resource()
        resource_spans.resource.CopyFrom(resource)

        # Each ResourceSpans has 2 ScopeSpans
        for ss_idx in range(2):
            scope_spans = ScopeSpans()
            scope = InstrumentationScope()
            scope.name = f"scope-{rs_idx}-{ss_idx}"
            scope_spans.scope.CopyFrom(scope)

            # Each ScopeSpans has 2 spans
            for span_idx in range(2):
                span = Span()
                span.trace_id = b"\x01" * 16
                span.span_id = bytes([rs_idx, ss_idx, span_idx] + [0] * 5)
                span.name = f"span-{rs_idx}-{ss_idx}-{span_idx}"
                scope_spans.spans.append(span)

            resource_spans.scope_spans.append(scope_spans)

        request.resource_spans.append(resource_spans)

    context = Mock()

    # Call Export
    response = servicer.Export(request, context)

    # Verify writer was called for all spans: 2 ResourceSpans * 2 ScopeSpans * 2 Spans = 8
    assert mock_writer.write_span.call_count == 8, "Expected 8 spans to be processed"
    assert response.partial_success.rejected_spans == 0
