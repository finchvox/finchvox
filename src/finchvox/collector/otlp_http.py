"""OpenTelemetry over HTTP with protobuf bodies (OTLP/HTTP).

LiveKit Agents uploads its observability data this way when
``LIVEKIT_OBSERVABILITY_URL`` points at Finchvox. Spans and logs are stored exactly
as if they had arrived over gRPC; metrics are acknowledged but not stored yet.
"""

import zlib

from google.protobuf.message import DecodeError
from loguru import logger
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

from .config import MAX_OTLP_BYTES
from .log_writer import LogWriter
from .otlp_requests import write_logs_request, write_trace_request
from .writer import SpanWriter

PROTOBUF_MEDIA_TYPE = "application/x-protobuf"


class OtlpBodyError(ValueError):
    """The body is not valid gzip or not the expected protobuf message."""


class OtlpBodyTooLarge(ValueError):
    """The body unpacks to more than ``MAX_OTLP_BYTES``."""


class UnsupportedEncoding(ValueError):
    """The body uses a ``Content-Encoding`` other than gzip or none."""


def unpack_body(body: bytes, content_encoding: str | None) -> bytes:
    """Return the protobuf bytes, unzipping gzip without exceeding the size limit."""
    encoding = (content_encoding or "identity").strip().lower()
    if encoding == "identity":
        data = body
    elif encoding == "gzip":
        data = _gunzip(body)
    else:
        raise UnsupportedEncoding(f"Unsupported Content-Encoding: {encoding}")
    if len(data) > MAX_OTLP_BYTES:
        raise OtlpBodyTooLarge(f"Body is larger than {MAX_OTLP_BYTES} bytes")
    return data


def _gunzip(body: bytes) -> bytes:
    # Stop one byte past the limit, so a small body that unpacks to gigabytes
    # never reaches memory.
    decompressor = zlib.decompressobj(16 + zlib.MAX_WBITS)
    try:
        data = decompressor.decompress(body, MAX_OTLP_BYTES + 1)
    except zlib.error as e:
        raise OtlpBodyError("Body is not valid gzip") from e
    if len(data) > MAX_OTLP_BYTES or decompressor.unconsumed_tail:
        raise OtlpBodyTooLarge(f"Body unpacks to more than {MAX_OTLP_BYTES} bytes")
    if not decompressor.eof:
        raise OtlpBodyError("gzip body is incomplete")
    return data


def _parse(message_type, data: bytes):
    try:
        return message_type.FromString(data)
    except DecodeError as e:
        raise OtlpBodyError(f"Body is not a valid {message_type.__name__}") from e


class OtlpHttpReceiver:
    """Stores OTLP/HTTP exports with the same writers the gRPC collector uses."""

    def __init__(self, span_writer: SpanWriter, log_writer: LogWriter):
        self.span_writer = span_writer
        self.log_writer = log_writer

    def receive_traces(self, body: bytes, content_encoding: str | None) -> bytes:
        request = _parse(ExportTraceServiceRequest, unpack_body(body, content_encoding))
        names = write_trace_request(request, self.span_writer)
        logger.info(f"Processed {len(names)} spans over HTTP spans={names}")
        return ExportTraceServiceResponse().SerializeToString()

    def receive_logs(self, body: bytes, content_encoding: str | None) -> bytes:
        request = _parse(ExportLogsServiceRequest, unpack_body(body, content_encoding))
        count = write_logs_request(request, self.log_writer)
        logger.info(f"Processed {count} log records over HTTP")
        return ExportLogsServiceResponse().SerializeToString()

    def receive_metrics(self, body: bytes, content_encoding: str | None) -> bytes:
        # Decoded to reject bad input, then dropped: Finchvox does not store metrics yet.
        _parse(ExportMetricsServiceRequest, unpack_body(body, content_encoding))
        return ExportMetricsServiceResponse().SerializeToString()
