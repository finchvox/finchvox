import logging
from importlib.metadata import version
from pathlib import Path
from typing import TYPE_CHECKING, Optional

from loguru import logger
from opentelemetry import trace as otel_trace
from opentelemetry.sdk.trace import TracerProvider

from finchvox.environment import EnvironmentSpanProcessor, capture_environment

if TYPE_CHECKING:
    from pipecat.utils.tracing.tracing_context import TracingContext

_initialized = False
_allowed_log_modules: set[str] = {"pipecat.", "finchvox.", "__main__"}
_app_root: Path | None = None
_current_tracing_context: Optional["TracingContext"] = None


def set_tracing_context(ctx: "TracingContext") -> None:
    global _current_tracing_context
    _current_tracing_context = ctx


def get_tracing_context() -> Optional["TracingContext"]:
    return _current_tracing_context


def init(
    service_name: str = "pipecat-app",
    endpoint: str = "http://localhost:4317",
    insecure: bool = True,
    capture_logs: bool = True,
    log_modules: list[str] | None = None,
    app_root: str | Path | None = None,
) -> None:
    """Initialize Finchvox tracing and log capture for a Pipecat application.

    Must be called before the Pipecat pipeline starts. Sets up OpenTelemetry
    trace export to the Finchvox server and optionally bridges application
    logs (stdlib logging and loguru) into the trace context.

    Args:
        service_name: Name identifying this application in traces.
        endpoint: gRPC endpoint of the Finchvox server.
        insecure: Use insecure (non-TLS) gRPC connection.
        capture_logs: Bridge application logs into OpenTelemetry traces.
        log_modules: Additional module prefixes whose logs should be captured
            (e.g. ``["myapp."]``). Pipecat and finchvox logs are always captured.
        app_root: Root directory of the application source. Logs from files
            under this path are captured automatically. Defaults to ``cwd()``.
    """
    global _initialized, _allowed_log_modules, _app_root

    if _initialized:
        logger.warning("finchvox.init() already called, skipping")
        return

    if app_root is not None:
        _app_root = Path(app_root).resolve()
    else:
        _app_root = Path.cwd()

    if log_modules:
        for mod in log_modules:
            _allowed_log_modules.add(mod if mod.endswith(".") else f"{mod}.")

    from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
    from pipecat.utils.tracing.setup import setup_tracing

    exporter = OTLPSpanExporter(endpoint=endpoint, insecure=insecure)
    setup_tracing(service_name=service_name, exporter=exporter)

    capture_environment()

    provider = otel_trace.get_tracer_provider()
    if isinstance(provider, TracerProvider):
        http_endpoint = endpoint.replace(":4317", ":3000")
        env_processor = EnvironmentSpanProcessor(endpoint=http_endpoint)
        provider.add_span_processor(env_processor)

    if capture_logs:
        _setup_log_capture(service_name, endpoint, insecure)

    _initialized = True
    logger.info(
        f"Finchvox v{version('finchvox')} initialized with service_name='{service_name}', endpoint='{endpoint}', capture_logs={capture_logs}"
    )


def _matches_allowed_module(module: str) -> bool:
    for prefix in _allowed_log_modules:
        if prefix == "__main__" and module == "__main__":
            return True
        if prefix != "__main__" and module.startswith(prefix):
            return True
    return False


def _is_path_in_app_root(pathname: str) -> bool:
    if not _app_root:
        return False
    try:
        path = Path(pathname).resolve()
        if not path.is_relative_to(_app_root):
            return False
        path_str = str(path)
        return "site-packages" not in path_str and "/.venv/" not in path_str
    except (ValueError, OSError):
        return False


def _is_allowed_source(module: str, pathname: str | None) -> bool:
    if _matches_allowed_module(module):
        return True
    if pathname and _is_path_in_app_root(pathname):
        return True
    return False


class TraceContextLoggingHandler(logging.Handler):
    """LoggingHandler that only emits logs with active Pipecat trace context.

    This handler wraps OpenTelemetry's LoggingHandler and only forwards logs
    when there's an active trace context from Pipecat's TurnContextProvider
    or ConversationContextProvider.

    The key difference from using a Filter is that this handler keeps the
    trace context attached during the entire emit() call, including when
    LoggingHandler._translate() calls get_current() to read the trace context.

    Logs without trace context are silently dropped here but still appear
    in the console via other handlers (loguru's default sink).
    """

    def __init__(self, otel_handler: logging.Handler):
        super().__init__()
        self._otel_handler = otel_handler

    def emit(self, record: logging.LogRecord) -> None:
        module = record.name or ""
        pathname = getattr(record, "pathname", None)
        if not _is_allowed_source(module, pathname):
            return

        ctx = _get_pipecat_context()
        if ctx:
            from opentelemetry.context import attach, detach

            token = attach(ctx)
            try:
                self._otel_handler.emit(record)
            finally:
                detach(token)


def _setup_log_capture(service_name: str, endpoint: str, insecure: bool) -> None:
    """Set up OpenTelemetry log capture and export."""
    from opentelemetry.sdk._logs import LoggerProvider, LoggingHandler
    from opentelemetry.sdk._logs.export import BatchLogRecordProcessor
    from opentelemetry.exporter.otlp.proto.grpc._log_exporter import OTLPLogExporter
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.instrumentation.logging import LoggingInstrumentor

    resource = Resource.create({"service.name": service_name})
    logger_provider = LoggerProvider(resource=resource)

    log_exporter = OTLPLogExporter(endpoint=endpoint, insecure=insecure)
    logger_provider.add_log_record_processor(BatchLogRecordProcessor(log_exporter))

    otel_handler = LoggingHandler(level=logging.NOTSET, logger_provider=logger_provider)
    wrapper_handler = TraceContextLoggingHandler(otel_handler)
    logging.getLogger().addHandler(wrapper_handler)
    logging.getLogger().setLevel(logging.DEBUG)

    LoggingInstrumentor().instrument(set_logging_format=True)

    _setup_loguru_bridge()

    logger.debug("OpenTelemetry log capture initialized")


def _get_legacy_pipecat_context():
    try:
        from pipecat.utils.tracing.turn_context_provider import get_current_turn_context

        ctx = get_current_turn_context()
        if ctx:
            return ctx
        from pipecat.utils.tracing.conversation_context_provider import (
            get_current_conversation_context,
        )

        return get_current_conversation_context()
    except ImportError:
        return None


def _get_pipecat_context():
    """Get current trace context from Pipecat's turn or conversation provider."""
    from finchvox.compat import HAS_NEW_TRACING_API

    if HAS_NEW_TRACING_API:
        ctx = get_tracing_context()
        if ctx:
            return ctx.get_turn_context() or ctx.get_conversation_context()
        return None
    return _get_legacy_pipecat_context()


def _setup_loguru_bridge() -> None:
    """Bridge loguru logs to stdlib logging so they get captured by OTel.

    Uses logger.configure(patcher=...) instead of logger.add(sink) because
    patchers survive logger.remove() calls. This is important because Pipecat's
    runner calls logger.remove() to reconfigure logging.

    This bridge also injects trace context from Pipecat's TurnContextProvider
    into thread-local storage before forwarding logs, ensuring logs during
    active turns are associated with the correct trace.
    """
    from loguru import logger as loguru_logger

    def log_patcher(record):
        level_name = record["level"].name
        stdlib_level = getattr(logging, level_name.upper(), logging.INFO)
        module_name = record["name"] or "loguru"
        pathname = record["file"].path if record.get("file") else None
        lineno = record.get("line", 0)
        func_name = record.get("function", "")

        stdlib_logger = logging.getLogger(module_name)
        log_record = stdlib_logger.makeRecord(
            name=module_name,
            level=stdlib_level,
            fn=pathname or "",
            lno=lineno,
            msg=record["message"],
            args=(),
            exc_info=None,
            func=func_name,
        )

        turn_context = _get_pipecat_context()

        if turn_context:
            from opentelemetry.context import attach, detach

            token = attach(turn_context)
            try:
                stdlib_logger.handle(log_record)
            finally:
                detach(token)
        else:
            stdlib_logger.handle(log_record)

    loguru_logger.configure(patcher=log_patcher)


from finchvox.processor import FinchvoxProcessor  # noqa: E402

__all__ = ["init", "FinchvoxProcessor"]
