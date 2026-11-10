"""
Unified FinchVox server combining collector and UI functionality.

This module provides a single server that handles both data collection
(audio, logs, exceptions, OTLP traces) and the web UI for viewing traces.
"""

import asyncio
import signal
from concurrent import futures
from pathlib import Path

import grpc
import uvicorn
from fastapi import FastAPI
from loguru import logger
from opentelemetry.proto.collector.logs.v1.logs_service_pb2_grpc import (
    add_LogsServiceServicer_to_server,
)
from opentelemetry.proto.collector.trace.v1.trace_service_pb2_grpc import (
    add_TraceServiceServicer_to_server,
)

from finchvox import telemetry
from finchvox.collector.audio_handler import AudioHandler
from finchvox.collector.collector_routes import register_collector_routes
from finchvox.collector.config import (
    DEFAULT_MAX_UPLOAD_BYTES,
    GRPC_PORT,
    MAX_WORKERS,
    get_default_data_dir,
)
from finchvox.collector.livekit_recording import LiveKitRecordingReceiver
from finchvox.collector.log_service import LogCollectorServicer
from finchvox.collector.log_writer import LogWriter
from finchvox.collector.observability_routes import register_observability_routes
from finchvox.collector.otlp_http import OtlpHttpReceiver
from finchvox.collector.service import TraceCollectorServicer
from finchvox.collector.writer import SpanWriter
from finchvox.server_info import ServerInfo
from finchvox.ui_routes import register_ui_routes


class UnifiedServer:
    """
    Unified server managing both gRPC (OTLP traces) and HTTP (collector + UI).

    This server provides:
    - gRPC endpoint for OpenTelemetry trace collection (default port 4317)
    - HTTP endpoints for audio/logs/exceptions collection (under /collector prefix)
    - Web UI and REST API for viewing traces (at root /)
    """

    def __init__(
        self,
        port: int = 3000,
        grpc_port: int = GRPC_PORT,
        host: str = "127.0.0.1",
        data_dir: Path | None = None,
        max_upload_bytes: int = DEFAULT_MAX_UPLOAD_BYTES,
    ):
        """
        Initialize the unified server.

        Args:
            port: HTTP server port (default: 3000)
            grpc_port: gRPC server port (default: 4317)
            host: Host to bind to (default: "127.0.0.1")
            data_dir: Base data directory (default: ~/.finchvox)
            max_upload_bytes: Largest session zip the UI upload accepts
        """
        self.port = port
        self.grpc_port = grpc_port
        self.host = host
        self.data_dir = data_dir if data_dir else get_default_data_dir()
        self.max_upload_bytes = max_upload_bytes

        # Initialize shared writer instances
        self.span_writer = SpanWriter(self.data_dir)
        self.log_writer = LogWriter(self.data_dir)
        self.audio_handler = AudioHandler(self.data_dir)

        # Server instances
        self.grpc_server = None
        self.http_server = None
        self.shutdown_event = asyncio.Event()
        self._is_shutting_down = False

        # Create unified FastAPI app
        self.app = self._create_app()

    def _create_app(self) -> FastAPI:
        """
        Create unified FastAPI application with both collector and UI routes.

        Returns:
            Configured FastAPI application
        """
        app = FastAPI(
            title="FinchVox Unified Server",
            description="Combined collector and UI server for voice AI observability",
            version="0.1.0",
        )

        # Register UI routes first (includes static file mounts)
        server_info = ServerInfo.describe(
            data_dir=self.data_dir,
            max_upload_bytes=self.max_upload_bytes,
            host=self.host,
            http_port=self.port,
            grpc_port=self.grpc_port,
        )
        register_ui_routes(app, self.data_dir, self.max_upload_bytes, server_info)

        # Register collector routes with /collector prefix
        register_collector_routes(app, self.audio_handler, prefix="/collector")

        # LiveKit's own uploads, for agents pointed here with LIVEKIT_OBSERVABILITY_URL
        register_observability_routes(
            app,
            OtlpHttpReceiver(self.span_writer, self.log_writer),
            LiveKitRecordingReceiver(self.audio_handler),
        )

        return app

    async def start_grpc(self):
        """Start the gRPC server for OTLP trace collection."""
        # Create gRPC server with thread pool
        self.grpc_server = grpc.server(
            futures.ThreadPoolExecutor(max_workers=MAX_WORKERS)
        )

        # Register trace service
        trace_servicer = TraceCollectorServicer(self.span_writer)
        add_TraceServiceServicer_to_server(trace_servicer, self.grpc_server)

        # Register logs service
        log_servicer = LogCollectorServicer(self.log_writer)
        add_LogsServiceServicer_to_server(log_servicer, self.grpc_server)

        # Bind gRPC to the same interface as the HTTP UI. Keeping the default
        # on loopback matters because traces, transcripts, tool payloads, and
        # audio can contain sensitive data. Use --host 0.0.0.0 explicitly when
        # Finchvox must be reachable from another container or machine.
        grpc_host = self.host
        if ":" in grpc_host and not grpc_host.startswith("["):
            grpc_host = f"[{grpc_host}]"
        bind_address = f"{grpc_host}:{self.grpc_port}"
        bound_port = self.grpc_server.add_insecure_port(bind_address)
        if bound_port == 0:
            raise RuntimeError(f"Failed to bind OTLP gRPC server to {bind_address}")

        # Start serving
        self.grpc_server.start()

    async def start_http(self):
        """Start the HTTP server using uvicorn."""
        # Configure uvicorn server
        config = uvicorn.Config(
            self.app,
            host=self.host,
            port=self.port,
            log_level="info",
            access_log=True,
        )
        self.http_server = uvicorn.Server(config)

        # Run server until shutdown event
        await self.http_server.serve()

    async def start(self):
        """Start both gRPC and HTTP servers concurrently."""
        telemetry.send_event("server_start", dedupe=True)

        await self.start_grpc()

        from finchvox.scheduler import start_scheduler

        start_scheduler(self.data_dir)

        await self.start_http()

    async def stop(self, grace_period: int = 5):
        """
        Gracefully stop both servers.

        Args:
            grace_period: Seconds to wait for in-flight requests to complete
        """
        # Prevent multiple shutdown attempts
        if self._is_shutting_down:
            return

        self._is_shutting_down = True
        logger.info(f"Shutting down servers (grace period: {grace_period}s)")

        # Stop HTTP server
        if self.http_server:
            logger.info("Stopping HTTP server...")
            self.http_server.should_exit = True
            await asyncio.sleep(0.1)  # Give it time to process shutdown

        # Stop gRPC server
        if self.grpc_server:
            logger.info("Stopping gRPC server...")
            self.grpc_server.stop(grace_period)

        logger.info("All servers stopped")

    def run(self):
        """
        Blocking entry point for running the unified server.

        Sets up signal handlers and runs the event loop until shutdown.
        Uses ``loop.add_signal_handler`` on Unix and falls back to
        ``signal.signal`` on Windows where the former is unavailable.
        """

        async def run_with_signals():
            loop = asyncio.get_running_loop()

            def handle_shutdown(signum):
                if not self._is_shutting_down:
                    logger.info(f"Received signal {signum}")
                    # Remove signal handlers to prevent duplicate calls
                    for sig in (signal.SIGINT, signal.SIGTERM):
                        try:
                            loop.remove_signal_handler(sig)
                        except (NotImplementedError, RuntimeError):
                            pass
                    # Create shutdown task
                    asyncio.create_task(self.stop())

            # Register signal handlers (Unix fast path).
            try:
                for sig in (signal.SIGINT, signal.SIGTERM):
                    loop.add_signal_handler(sig, lambda s=sig: handle_shutdown(s))
            except NotImplementedError:
                # Windows: ProactorEventLoop has no add_signal_handler.
                # Fall back to stdlib handlers scheduled thread-safely.
                logger.debug(
                    "loop.add_signal_handler unavailable; using signal.signal fallback"
                )

                def _stdlib_handler(signum, frame):
                    try:
                        loop.call_soon_threadsafe(handle_shutdown, signum)
                    except RuntimeError:
                        pass

                for sig in (signal.SIGINT, signal.SIGTERM):
                    try:
                        signal.signal(sig, _stdlib_handler)
                    except (ValueError, OSError, RuntimeError) as exc:
                        logger.debug(f"Could not install handler for {sig}: {exc}")

            try:
                await self.start()
            except (KeyboardInterrupt, asyncio.CancelledError):
                await self.stop()

        asyncio.run(run_with_signals())
