import json
from pathlib import Path

from google.protobuf.json_format import MessageToDict, SerializeToJsonError
from loguru import logger

from finchvox.collector.config import get_session_dir


class LogWriter:
    """Handles writing log records to JSONL files organized by trace_id."""

    def __init__(self, data_dir: Path):
        self.data_dir = data_dir

    def write_log(self, log_record, resource_logs, scope_logs):
        """Write a single log record to its trace-specific JSONL file."""
        trace_id_bytes = log_record.trace_id
        if not trace_id_bytes or trace_id_bytes == b"\x00" * 16:
            body = (
                log_record.body.string_value
                if log_record.body.string_value
                else str(log_record.body)
            )
            logger.debug(f"Received log without trace_id, discarding: {body[:200]}")
            return

        try:
            trace_id_hex = trace_id_bytes.hex()
            session_dir = get_session_dir(self.data_dir, trace_id_hex)
            session_dir.mkdir(parents=True, exist_ok=True)

            log_dict = self._convert_log_to_dict(log_record, resource_logs, scope_logs)

            log_file = session_dir / f"logs_{trace_id_hex}.jsonl"
            with log_file.open("a") as f:
                json.dump(log_dict, f)
                f.write("\n")

            logger.debug(f"Wrote log to {log_file}")
        except (OSError, SerializeToJsonError, TypeError, ValueError) as e:
            # One unwritable log must not drop the rest of its export batch.
            logger.exception(f"Failed to write log: {e}")

    def _convert_log_to_dict(self, log_record, resource_logs, scope_logs):
        """Convert protobuf log record to dictionary."""
        log_data = MessageToDict(log_record, preserving_proto_field_name=True)

        log_data["trace_id_hex"] = log_record.trace_id.hex()
        if log_record.span_id:
            log_data["span_id_hex"] = log_record.span_id.hex()

        if resource_logs.resource:
            log_data["resource"] = MessageToDict(
                resource_logs.resource, preserving_proto_field_name=True
            )

        if scope_logs.scope:
            log_data["instrumentation_scope"] = MessageToDict(
                scope_logs.scope, preserving_proto_field_name=True
            )

        return log_data
