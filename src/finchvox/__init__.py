from __future__ import annotations

import logging
import os
from importlib.metadata import version
from pathlib import Path
from urllib.parse import urlsplit

from loguru import logger
from opentelemetry import trace as otel_trace
from opentelemetry.sdk.trace import TracerProvider

from finchvox.environment import EnvironmentSpanProcessor, capture_environment

_initialized = False
_allowed_log_modules: set[str] = {"pipecat.", "finchvox.", "__main__"}
_app_root: Path | None = None

# Remembered by init_livekit() so that flush_livekit() and
# finchvox.livekit.on_session_end need no arguments.
_livekit_tracer_provider: TracerProvider | None = None
_livekit_upload_endpoint = "http://localhost:3000"


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
    global _initialized, _app_root

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
        env_processor = EnvironmentSpanProcessor(
            endpoint=_collector_http_endpoint(endpoint)
        )
        provider.add_span_processor(env_processor)

    if capture_logs:
        _setup_log_capture(service_name, endpoint, insecure)

    _initialized = True
    logger.info(
        f"Finchvox v{version('finchvox')} initialized with service_name='{service_name}', endpoint='{endpoint}', capture_logs={capture_logs}"
    )


def _collector_http_endpoint(grpc_endpoint: str) -> str:
    """Finchvox's HTTP address on the same host as its OTLP/gRPC collector.

    Finchvox serves HTTP on port 3000 by default, whatever port the collector
    uses, so this keeps the host and scheme and sets the port to 3000. Servers
    started on another HTTP port need an explicit ``http_endpoint``.
    """
    url = grpc_endpoint if "://" in grpc_endpoint else f"http://{grpc_endpoint}"
    parsed = urlsplit(url)
    host = parsed.hostname or "localhost"
    if ":" in host:
        host = f"[{host}]"
    return f"{parsed.scheme}://{host}:3000"


def _is_allowed_source(module: str, pathname: str | None) -> bool:
    """Check if a log source should be captured.

    A source is allowed if:
    1. The module name matches an allowed prefix (pipecat., finchvox., __main__), OR
    2. The file path is within the app_root directory (excluding site-packages, .venv)
    """
    for prefix in _allowed_log_modules:
        if prefix == "__main__":
            if module == "__main__":
                return True
        elif module.startswith(prefix):
            return True

    if pathname and _app_root:
        try:
            path = Path(pathname).resolve()
            if path.is_relative_to(_app_root):
                path_str = str(path)
                if "site-packages" not in path_str and "/.venv/" not in path_str:
                    return True
        except (ValueError, OSError):
            pass

    return False


class TraceContextLoggingHandler(logging.Handler):
    """LoggingHandler that only emits logs with active Pipecat trace context.

    This handler wraps OpenTelemetry's LoggingHandler and only forwards logs
    when there is a valid active OpenTelemetry span from the pipeline.

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


def _build_otel_log_handler(service_name: str, endpoint: str, insecure: bool):
    """Create a stdlib logging handler plus its provider, exporting to Finchvox over OTLP."""
    from opentelemetry.exporter.otlp.proto.grpc._log_exporter import OTLPLogExporter
    from opentelemetry.instrumentation.logging.handler import LoggingHandler
    from opentelemetry.sdk._logs import LoggerProvider
    from opentelemetry.sdk._logs.export import BatchLogRecordProcessor
    from opentelemetry.sdk.resources import SERVICE_NAME, Resource

    logger_provider = LoggerProvider(resource=Resource.create({SERVICE_NAME: service_name}))
    log_exporter = OTLPLogExporter(endpoint=endpoint, insecure=insecure)
    logger_provider.add_log_record_processor(BatchLogRecordProcessor(log_exporter))

    handler = LoggingHandler(
        level=logging.NOTSET,
        logger_provider=logger_provider,
        log_code_attributes=True,
    )
    return handler, logger_provider


def _setup_log_capture(service_name: str, endpoint: str, insecure: bool) -> None:
    """Set up OpenTelemetry log capture and export."""
    from opentelemetry.instrumentation.logging import LoggingInstrumentor

    otel_handler, _ = _build_otel_log_handler(service_name, endpoint, insecure)
    wrapper_handler = TraceContextLoggingHandler(otel_handler)
    logging.getLogger().addHandler(wrapper_handler)
    logging.getLogger().setLevel(logging.DEBUG)

    LoggingInstrumentor().instrument(
        set_logging_format=True, enable_log_auto_instrumentation=False
    )

    _setup_loguru_bridge()

    logger.debug("OpenTelemetry log capture initialized")


def _get_pipecat_context():
    """Return active OpenTelemetry context without a global pipeline singleton."""
    if otel_trace.get_current_span().get_span_context().is_valid:
        from opentelemetry.context import get_current

        return get_current()

    return None


def _setup_loguru_bridge() -> None:
    """Bridge loguru logs to stdlib logging so they get captured by OTel.

    Uses logger.configure(patcher=...) instead of logger.add(sink) because
    patchers survive logger.remove() calls. This is important because Pipecat's
    runner calls logger.remove() to reconfigure logging.

    This bridge preserves active OpenTelemetry context while forwarding logs,
    ensuring logs during active turns are associated with the correct trace.
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


def _setup_livekit_log_export(
    service_name: str, endpoint: str, insecure: bool
):
    """Export stdlib/LiveKit logs to the same local OTLP collector.

    OpenTelemetry's LoggingHandler reads the *current* span context at emit
    time, so logs produced while LiveKit spans are active arrive at Finchvox
    with matching trace/span IDs and can be synchronized with the replay UI.
    """
    root_logger = logging.getLogger()
    for handler in root_logger.handlers:
        if getattr(handler, "_finchvox_livekit_handler", False):
            return getattr(handler, "_finchvox_logger_provider", None)

    handler, logger_provider = _build_otel_log_handler(service_name, endpoint, insecure)
    handler._finchvox_livekit_handler = True
    handler._finchvox_logger_provider = logger_provider
    root_logger.addHandler(handler)
    return logger_provider


def init_livekit(
    service_name: str = "livekit-agent",
    endpoint: str = "http://localhost:4317",
    insecure: bool = True,
    metadata: dict[str, str] | None = None,
    *,
    capture_logs: bool = True,
    allow_pii: bool = True,
    http_endpoint: str | None = None,
) -> TracerProvider:
    """Initialize local-first LiveKit Agents observability.

    Traces are sent directly to Finchvox over OTLP/gRPC. When ``capture_logs``
    is enabled, stdlib logs are exported to the same collector and keep their
    active LiveKit trace/span context.

    ``allow_pii=True`` is intentionally the default for the local replay UX so
    transcripts, tool arguments/results and response text can be displayed.
    Set it to ``False`` to strip span content. This does not redact separately
    exported logs, uploaded session reports, or recordings. Requires the
    supported LiveKit Agents baseline (1.8.9+) with ``allow_pii`` support.

    The provider and endpoint are remembered, so ``flush_livekit()`` and
    ``finchvox.livekit.on_session_end`` work without being passed them.

    ``http_endpoint`` is Finchvox's HTTP address, used for session reports,
    recordings and the Environment tab. It defaults to port 3000 on the host in
    ``endpoint``; set it when Finchvox serves HTTP on another port.
    """
    global _livekit_tracer_provider, _livekit_upload_endpoint

    from livekit.agents.telemetry import set_tracer_provider
    from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
    from opentelemetry.sdk.resources import SERVICE_NAME, Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor

    if observability_url := os.environ.get("LIVEKIT_OBSERVABILITY_URL"):
        logger.warning(
            f"LIVEKIT_OBSERVABILITY_URL is set ({observability_url}), so LiveKit also "
            "uploads this agent's traces and logs there. If it points at Finchvox, use "
            "either init_livekit() or LIVEKIT_OBSERVABILITY_URL, not both: with both, "
            "every span reaches Finchvox twice."
        )

    resource = Resource.create({SERVICE_NAME: service_name})
    tracer_provider = TracerProvider(resource=resource)
    upload_endpoint = http_endpoint or _collector_http_endpoint(endpoint)

    exporter = OTLPSpanExporter(endpoint=endpoint, insecure=insecure)
    tracer_provider.add_span_processor(BatchSpanProcessor(exporter))

    # Feeds the Environment tab: OS, Python and installed package versions.
    capture_environment()
    tracer_provider.add_span_processor(EnvironmentSpanProcessor(endpoint=upload_endpoint))

    set_tracer_provider(
        tracer_provider, metadata=metadata, allow_pii=allow_pii
    )

    logger_provider = None
    if capture_logs:
        logger_provider = _setup_livekit_log_export(
            service_name=service_name, endpoint=endpoint, insecure=insecure
        )
        # Keep a reference so callers can flush/shutdown both signal providers.
        tracer_provider._finchvox_logger_provider = logger_provider

    _livekit_tracer_provider = tracer_provider
    _livekit_upload_endpoint = upload_endpoint

    logger.info(
        f"Finchvox v{version('finchvox')} LiveKit initialized with "
        f"service_name='{service_name}', endpoint='{endpoint}', "
        f"capture_logs={capture_logs}, allow_pii={allow_pii}"
    )

    return tracer_provider


def flush_livekit(
    tracer_provider: TracerProvider | None = None, timeout_millis: int = 30000
) -> bool:
    """Flush LiveKit traces and Finchvox OTLP logs before process shutdown.

    Without an argument, flushes the provider ``init_livekit()`` created. Returns
    True when everything was sent, including when there is nothing to flush.
    """
    tracer_provider = tracer_provider or _livekit_tracer_provider
    if tracer_provider is None:
        return True
    trace_ok = tracer_provider.force_flush(timeout_millis=timeout_millis)
    log_provider = getattr(tracer_provider, "_finchvox_logger_provider", None)
    log_ok = True
    if log_provider is not None:
        log_ok = log_provider.force_flush(timeout_millis=timeout_millis)
    return bool(trace_ok and log_ok)


def __getattr__(name: str):
    # Keep the Pipecat processor lazy so LiveKit-only users do not import the
    # Pipecat runtime merely by importing ``finchvox``.
    if name == "FinchvoxProcessor":
        from finchvox.processor import FinchvoxProcessor

        return FinchvoxProcessor
    raise AttributeError(name)


__all__ = ["FinchvoxProcessor", "flush_livekit", "init", "init_livekit"]
