import json
from pathlib import Path

from opentelemetry.proto.common.v1.common_pb2 import InstrumentationScope, KeyValue
from opentelemetry.proto.resource.v1.resource_pb2 import Resource
from opentelemetry.proto.trace.v1.trace_pb2 import ResourceSpans, ScopeSpans, Span

from finchvox.collector.writer import SpanWriter


def create_mock_resource_spans():
    """Create a mock ResourceSpans for testing."""
    resource_spans = ResourceSpans()
    resource = Resource()

    # Add a resource attribute
    attr = KeyValue()
    attr.key = "service.name"
    attr.value.string_value = "test-service"
    resource.attributes.append(attr)

    resource_spans.resource.CopyFrom(resource)
    return resource_spans


def create_mock_scope_spans():
    """Create a mock ScopeSpans for testing."""
    scope_spans = ScopeSpans()
    scope = InstrumentationScope()
    scope.name = "test-instrumentation"
    scope.version = "1.0.0"
    scope_spans.scope.CopyFrom(scope)
    return scope_spans


def test_write_span_creates_file(tmp_path):
    """Test that writing a span creates a JSONL file with correct trace_id filename."""
    writer = SpanWriter(tmp_path)

    # Create mock span with known trace_id
    span = Span()
    span.trace_id = b"\x01\x23\x45\x67\x89\xab\xcd\xef" * 2  # 16 bytes
    span.span_id = b"\xaa\xbb\xcc\xdd\xee\xff\x00\x11"  # 8 bytes
    span.name = "test-span"

    # Create mock resource and scope spans
    resource_spans = create_mock_resource_spans()
    scope_spans = create_mock_scope_spans()

    # Write span
    writer.write_span(span, resource_spans, scope_spans)

    # Verify file created with correct name
    trace_id_hex = span.trace_id.hex()
    trace_file = tmp_path / "sessions" / trace_id_hex / f"trace_{trace_id_hex}.jsonl"
    assert trace_file.exists(), f"Expected file {trace_file} to exist"

    # Verify JSON content
    with trace_file.open() as f:
        data = json.loads(f.readline())
        assert data["trace_id_hex"] == span.trace_id.hex()
        assert data["name"] == "test-span"


def test_write_multiple_spans_same_trace(tmp_path):
    """Test that multiple spans with same trace_id go to same file (appended)."""
    writer = SpanWriter(tmp_path)

    # Create two spans with same trace_id
    trace_id = b"\xaa\xbb\xcc\xdd" * 4  # 16 bytes

    span1 = Span()
    span1.trace_id = trace_id
    span1.span_id = b"\x11\x11\x11\x11\x11\x11\x11\x11"
    span1.name = "span-1"

    span2 = Span()
    span2.trace_id = trace_id
    span2.span_id = b"\x22\x22\x22\x22\x22\x22\x22\x22"
    span2.name = "span-2"

    # Create mock resource and scope spans
    resource_spans = create_mock_resource_spans()
    scope_spans = create_mock_scope_spans()

    # Write both spans
    writer.write_span(span1, resource_spans, scope_spans)
    writer.write_span(span2, resource_spans, scope_spans)

    # Verify both spans are in the same file
    trace_id_hex = trace_id.hex()
    trace_file = tmp_path / "sessions" / trace_id_hex / f"trace_{trace_id_hex}.jsonl"
    assert trace_file.exists()

    with trace_file.open() as f:
        lines = f.readlines()
        assert len(lines) == 2, "Expected 2 spans in the file"

        # Verify each span
        span1_data = json.loads(lines[0])
        assert span1_data["name"] == "span-1"
        assert span1_data["trace_id_hex"] == trace_id.hex()

        span2_data = json.loads(lines[1])
        assert span2_data["name"] == "span-2"
        assert span2_data["trace_id_hex"] == trace_id.hex()


def test_span_json_fields_preserved(tmp_path):
    """Test that all span fields are present in JSON output."""
    writer = SpanWriter(tmp_path)

    # Create span with various fields
    span = Span()
    span.trace_id = b"\xff" * 16
    span.span_id = b"\xee" * 8
    span.parent_span_id = b"\xdd" * 8
    span.name = "test-span-with-fields"
    span.kind = 1  # SPAN_KIND_INTERNAL
    span.start_time_unix_nano = 1640000000000000000
    span.end_time_unix_nano = 1640000001000000000

    # Add an attribute
    attr = KeyValue()
    attr.key = "http.method"
    attr.value.string_value = "GET"
    span.attributes.append(attr)

    # Create mock resource and scope spans
    resource_spans = create_mock_resource_spans()
    scope_spans = create_mock_scope_spans()

    # Write span
    writer.write_span(span, resource_spans, scope_spans)

    # Read and verify JSON
    trace_id_hex = span.trace_id.hex()
    trace_file = tmp_path / "sessions" / trace_id_hex / f"trace_{trace_id_hex}.jsonl"
    with trace_file.open() as f:
        data = json.loads(f.readline())

        # Verify key fields are present
        assert "trace_id_hex" in data
        assert "span_id_hex" in data
        assert "parent_span_id_hex" in data
        assert data["name"] == "test-span-with-fields"
        assert "start_time_unix_nano" in data
        assert "end_time_unix_nano" in data
        assert "attributes" in data
        assert "resource" in data
        assert "instrumentation_scope" in data


def test_trace_id_hex_conversion(tmp_path):
    """Test that bytes trace_id correctly converts to hex string for filename."""
    writer = SpanWriter(tmp_path)

    # Create span with specific trace_id
    trace_id_bytes = b"\x01\x02\x03\x04\x05\x06\x07\x08\x09\x0a\x0b\x0c\x0d\x0e\x0f\x10"
    expected_hex = "0102030405060708090a0b0c0d0e0f10"

    span = Span()
    span.trace_id = trace_id_bytes
    span.span_id = b"\xff" * 8
    span.name = "hex-test-span"

    # Create mock resource and scope spans
    resource_spans = create_mock_resource_spans()
    scope_spans = create_mock_scope_spans()

    # Write span
    writer.write_span(span, resource_spans, scope_spans)

    # Verify filename uses correct hex conversion
    trace_file = tmp_path / "sessions" / expected_hex / f"trace_{expected_hex}.jsonl"
    assert trace_file.exists(), f"Expected file with hex name {expected_hex}"

    # Verify hex value in JSON
    with trace_file.open() as f:
        data = json.loads(f.readline())
        assert data["trace_id_hex"] == expected_hex


def test_write_error_does_not_propagate_to_the_export_batch(tmp_path, monkeypatch):
    """Test that a disk error on one span is logged rather than raised."""
    writer = SpanWriter(tmp_path)

    span = Span()
    span.trace_id = b"\xcd" * 16
    span.span_id = b"\x01" * 8

    def failing_open(self, *args, **kwargs):
        raise OSError("disk full")

    monkeypatch.setattr(Path, "open", failing_open)

    writer.write_span(span, create_mock_resource_spans(), create_mock_scope_spans())


def test_appending_span_does_not_read_existing_trace_file(tmp_path, monkeypatch):
    """Test that write cost does not grow with the size of the trace file."""
    writer = SpanWriter(tmp_path)
    resource_spans = create_mock_resource_spans()
    scope_spans = create_mock_scope_spans()

    span = Span()
    span.trace_id = b"\xab" * 16
    span.span_id = b"\x01" * 8
    span.name = "first-span"
    writer.write_span(span, resource_spans, scope_spans)

    opened_modes = []
    real_open = Path.open

    def recording_open(self, mode="r", *args, **kwargs):
        opened_modes.append(mode)
        return real_open(self, mode, *args, **kwargs)

    monkeypatch.setattr(Path, "open", recording_open)
    span.span_id = b"\x02" * 8
    span.name = "second-span"
    writer.write_span(span, resource_spans, scope_spans)
    monkeypatch.undo()

    assert opened_modes == ["a"]
    trace_id_hex = span.trace_id.hex()
    trace_file = tmp_path / "sessions" / trace_id_hex / f"trace_{trace_id_hex}.jsonl"
    names = [json.loads(line)["name"] for line in trace_file.read_text().splitlines()]
    assert names == ["first-span", "second-span"]
