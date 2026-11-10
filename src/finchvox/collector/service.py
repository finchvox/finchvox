from loguru import logger
from opentelemetry.proto.collector.trace.v1.trace_service_pb2 import (
    ExportTracePartialSuccess,
    ExportTraceServiceResponse,
)
from opentelemetry.proto.collector.trace.v1.trace_service_pb2_grpc import (
    TraceServiceServicer,
)

from .otlp_requests import write_trace_request
from .writer import SpanWriter


class TraceCollectorServicer(TraceServiceServicer):
    """Implements the OTLP TraceService gRPC interface."""

    def __init__(self, span_writer: SpanWriter):
        self.span_writer = span_writer

    def Export(self, request, context):
        """Handle incoming trace export requests."""
        try:
            span_names = write_trace_request(request, self.span_writer)
            logger.info(f"Successfully processed {len(span_names)} spans={span_names}")
            return ExportTraceServiceResponse(
                partial_success=ExportTracePartialSuccess(
                    rejected_spans=0, error_message=""
                )
            )
        except Exception as e:  # noqa: BLE001 - gRPC Export boundary: a bad batch must not crash the collector or the exporting agent
            logger.exception(f"Error processing spans: {e}")
            # Continue processing - return partial success
            return ExportTraceServiceResponse(
                partial_success=ExportTracePartialSuccess(
                    rejected_spans=0,  # Could track actual failures
                    error_message=str(e),
                )
            )
