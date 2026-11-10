"""Write OpenTelemetry export requests, whichever transport (gRPC or HTTP) carried them."""

from .log_writer import LogWriter
from .writer import SpanWriter


def write_trace_request(request, span_writer: SpanWriter) -> list[str]:
    """Store every span in an ``ExportTraceServiceRequest``; return their names."""
    names = []
    for resource_spans in request.resource_spans:
        for scope_spans in resource_spans.scope_spans:
            for span in scope_spans.spans:
                span_writer.write_span(span, resource_spans, scope_spans)
                names.append(span.name)
    return names


def write_logs_request(request, log_writer: LogWriter) -> int:
    """Store every log record in an ``ExportLogsServiceRequest``; return how many."""
    count = 0
    for resource_logs in request.resource_logs:
        for scope_logs in resource_logs.scope_logs:
            for log_record in scope_logs.log_records:
                log_writer.write_log(log_record, resource_logs, scope_logs)
                count += 1
    return count
