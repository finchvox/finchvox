"""The two-line LiveKit hookup: init_livekit() plus on_session_end."""

import asyncio
import sys
from types import ModuleType
from unittest.mock import Mock

import pytest

import finchvox
import finchvox.livekit as livekit_helpers

TRACE_ID = "0123456789abcdef0123456789abcdef"


class FakeJobContext:
    """The parts of livekit.agents.JobContext that on_session_end uses."""

    def __init__(self, report=None, report_error=None):
        self._report = report if report is not None else {"job_id": "AJ_1"}
        self._report_error = report_error
        self.shutdown_callbacks = []

    def make_session_report(self):
        if self._report_error:
            raise self._report_error
        return self._report

    def add_shutdown_callback(self, callback):
        self.shutdown_callbacks.append(callback)


@pytest.fixture(autouse=True)
def fresh_state(monkeypatch):
    monkeypatch.setattr(finchvox, "_livekit_tracer_provider", None)
    monkeypatch.setattr(finchvox, "_livekit_upload_endpoint", "http://localhost:3000")


@pytest.fixture
def initialized(monkeypatch):
    """Runs init_livekit with LiveKit and the exporters replaced by mocks."""
    from opentelemetry.exporter.otlp.proto.grpc import trace_exporter
    from opentelemetry.sdk import trace as sdk_trace
    from opentelemetry.sdk.trace import export

    telemetry = ModuleType("livekit.agents.telemetry")
    telemetry.set_tracer_provider = Mock()
    monkeypatch.setitem(sys.modules, "livekit.agents.telemetry", telemetry)
    provider = Mock()
    provider.force_flush.return_value = True
    monkeypatch.setattr(sdk_trace, "TracerProvider", Mock(return_value=provider))
    monkeypatch.setattr(trace_exporter, "OTLPSpanExporter", Mock())
    monkeypatch.setattr(export, "BatchSpanProcessor", Mock())
    monkeypatch.setattr(finchvox, "capture_environment", Mock())

    def init(**kwargs):
        finchvox.init_livekit(capture_logs=False, **kwargs)
        return provider

    return init


@pytest.fixture
def uploads(monkeypatch):
    """Records upload_session_artifacts calls and the order of flushes and uploads."""
    calls = []

    async def fake_upload(trace_id=None, *, report=None, audio_path=None, endpoint=None):
        calls.append(("upload", {"report": report, "audio_path": audio_path, "endpoint": endpoint}))
        return TRACE_ID

    real_flush = finchvox.flush_livekit

    def recording_flush(*args, **kwargs):
        calls.append(("flush", None))
        return real_flush(*args, **kwargs)

    monkeypatch.setattr(livekit_helpers, "upload_session_artifacts", fake_upload)
    monkeypatch.setattr(finchvox, "flush_livekit", recording_flush)
    return calls


class TestProviderMemory:
    def test_flush_without_arguments_flushes_the_initialized_provider(self, initialized):
        provider = initialized()

        assert finchvox.flush_livekit() is True
        provider.force_flush.assert_called_once()

    def test_flush_with_an_explicit_provider_still_works(self, initialized):
        initialized()
        other = Mock()
        other.force_flush.return_value = True

        assert finchvox.flush_livekit(other) is True
        other.force_flush.assert_called_once()

    def test_flush_before_init_has_nothing_to_do(self):
        assert finchvox.flush_livekit() is True


class TestOnSessionEnd:
    def test_reports_flushes_then_uploads(self, initialized, uploads):
        initialized()
        ctx = FakeJobContext(report={"job_id": "AJ_7"})

        asyncio.run(livekit_helpers.on_session_end(ctx))

        assert [step for step, _ in uploads] == ["flush", "upload"]
        assert uploads[1][1]["report"] == {"job_id": "AJ_7"}

    def test_uploads_to_the_same_host_init_livekit_was_given(self, initialized, uploads):
        initialized(endpoint="http://host.docker.internal:4317")

        asyncio.run(livekit_helpers.on_session_end(FakeJobContext()))

        assert uploads[-1][1]["endpoint"] == "http://host.docker.internal:3000"

    def test_registers_a_flush_for_spans_that_end_after_it(self, initialized, uploads):
        provider = initialized()
        ctx = FakeJobContext()

        asyncio.run(livekit_helpers.on_session_end(ctx))
        provider.force_flush.reset_mock()
        assert len(ctx.shutdown_callbacks) == 1
        asyncio.run(ctx.shutdown_callbacks[0]())

        provider.force_flush.assert_called_once()

    @pytest.mark.parametrize(
        "error",
        [
            RuntimeError("Cannot prepare report, no AgentSession was found"),
            RuntimeError("the RecorderIO is still recording"),
        ],
    )
    def test_report_errors_never_reach_the_agent(self, initialized, uploads, error, caplog):
        initialized()

        asyncio.run(livekit_helpers.on_session_end(FakeJobContext(report_error=error)))

        assert [step for step, _ in uploads] == []
        assert "Finchvox" in caplog.text

    def test_upload_errors_never_reach_the_agent(self, initialized, monkeypatch, caplog):
        initialized()

        async def failing_upload(*args, **kwargs):
            raise OSError("Finchvox is not running")

        monkeypatch.setattr(livekit_helpers, "upload_session_artifacts", failing_upload)

        asyncio.run(livekit_helpers.on_session_end(FakeJobContext()))

        assert "Finchvox is not running" in caplog.text

    @pytest.mark.parametrize(
        ("grpc_endpoint", "expected"),
        [
            ("http://localhost:4317", "http://localhost:3000"),
            ("http://127.0.0.1:4391", "http://127.0.0.1:3000"),
            ("finchvox:4317", "http://finchvox:3000"),
            ("http://[::1]:4317", "http://[::1]:3000"),
        ],
    )
    def test_upload_address_is_port_3000_on_the_same_host(
        self, initialized, uploads, grpc_endpoint, expected
    ):
        initialized(endpoint=grpc_endpoint)

        asyncio.run(livekit_helpers.on_session_end(FakeJobContext()))

        assert uploads[-1][1]["endpoint"] == expected

    def test_explicit_http_endpoint_wins(self, initialized, uploads):
        initialized(
            endpoint="http://127.0.0.1:4391", http_endpoint="http://127.0.0.1:3991"
        )

        asyncio.run(livekit_helpers.on_session_end(FakeJobContext()))

        assert uploads[-1][1]["endpoint"] == "http://127.0.0.1:3991"

    def test_works_even_without_init_livekit(self, uploads):
        asyncio.run(livekit_helpers.on_session_end(FakeJobContext()))

        assert uploads[-1][1]["endpoint"] == "http://localhost:3000"


class TestFinalizeSession:
    """For agents that already have their own on_session_end."""

    def test_returns_the_trace_id(self, initialized, uploads):
        initialized()

        trace_id = asyncio.run(livekit_helpers.finalize_session(FakeJobContext()))

        assert trace_id == TRACE_ID

    def test_returns_none_instead_of_raising(self, initialized, uploads):
        initialized()
        ctx = FakeJobContext(report_error=RuntimeError("no AgentSession"))

        assert asyncio.run(livekit_helpers.finalize_session(ctx)) is None

    def test_accepts_its_own_recording_and_endpoint(self, initialized, uploads):
        initialized()

        asyncio.run(
            livekit_helpers.finalize_session(
                FakeJobContext(), audio_path="call.ogg", endpoint="http://other:3000"
            )
        )

        assert uploads[-1][1]["audio_path"] == "call.ogg"
        assert uploads[-1][1]["endpoint"] == "http://other:3000"


def test_livekit_accepts_on_session_end_as_its_callback():
    """The real AgentServer takes the helper exactly as the docs show."""
    agents = pytest.importorskip("livekit.agents")
    server = agents.AgentServer()

    @server.rtc_session(on_session_end=livekit_helpers.on_session_end)
    async def entrypoint(ctx):
        pass

    assert server._session_end_fnc is livekit_helpers.on_session_end
