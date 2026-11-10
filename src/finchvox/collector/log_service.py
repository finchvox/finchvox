from loguru import logger
from opentelemetry.proto.collector.logs.v1.logs_service_pb2 import (
    ExportLogsPartialSuccess,
    ExportLogsServiceResponse,
)
from opentelemetry.proto.collector.logs.v1.logs_service_pb2_grpc import (
    LogsServiceServicer,
)

from .log_writer import LogWriter
from .otlp_requests import write_logs_request


class LogCollectorServicer(LogsServiceServicer):
    """Implements the OTLP LogsService gRPC interface."""

    def __init__(self, log_writer: LogWriter):
        self.log_writer = log_writer

    def Export(self, request, context):
        """Handle incoming log export requests."""
        try:
            log_count = write_logs_request(request, self.log_writer)
            logger.info(f"Processed {log_count} log records")
            return ExportLogsServiceResponse(
                partial_success=ExportLogsPartialSuccess(
                    rejected_log_records=0, error_message=""
                )
            )
        except Exception as e:  # noqa: BLE001 - gRPC Export boundary: a bad batch must not crash the collector or the exporting agent
            logger.exception(f"Error processing logs: {e}")
            return ExportLogsServiceResponse(
                partial_success=ExportLogsPartialSuccess(
                    rejected_log_records=0, error_message=str(e)
                )
            )
