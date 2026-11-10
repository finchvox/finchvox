import asyncio

import aiohttp
import pytest
from opentelemetry import trace as otel_trace
from opentelemetry.trace import NonRecordingSpan, SpanContext, TraceFlags

from finchvox.livekit import current_trace_id, session_report_json


def test_current_trace_id_returns_active_otel_trace():
    trace_id_int = int("0123456789abcdef0123456789abcdef", 16)
    span_context = SpanContext(
        trace_id=trace_id_int,
        span_id=int("0123456789abcdef", 16),
        is_remote=False,
        trace_flags=TraceFlags(TraceFlags.SAMPLED),
        trace_state=otel_trace.DEFAULT_TRACE_STATE,
    )

    with otel_trace.use_span(NonRecordingSpan(span_context), end_on_exit=False):
        assert current_trace_id() == "0123456789abcdef0123456789abcdef"


def test_session_report_json_accepts_dict():
    rendered = session_report_json({"room_name": "local-room", "events": []})

    assert '"room_name": "local-room"' in rendered


def test_session_report_serializer_uses_current_sdk_to_dict_defaults():
    import json

    class Report:
        # SessionReport.to_dict in LiveKit 1.8.9 still includes history/events
        # by default, and converts its Path to a JSON-safe string itself.
        def to_dict(self, *, include_chat_history=True, include_events=True):
            assert include_chat_history is True
            assert include_events is True
            return {
                "sdk_version": "1.8.9",
                "audio_recording_path": "session.ogg",
                "audio_recording_started_at": 1_700_000_000.5,
                "chat_history": {"items": []},
                "events": [],
            }

    report = json.loads(session_report_json(Report()))
    assert report["sdk_version"] == "1.8.9"
    assert report["audio_recording_started_at"] == 1_700_000_000.5
    assert report["chat_history"] == {"items": []}


TRACE_ID = "0123456789abcdef0123456789abcdef"
RECORDING = b"recording bytes " * 1000


def _run_upload_against(statuses, tmp_path, monkeypatch):
    """Serves the given audio statuses in order, then uploads a recording.

    Returns (error or None, bodies the server received, waits requested).
    """
    from aiohttp import web

    import finchvox.livekit as livekit_module

    received = []
    waits = []

    async def wait(seconds):
        waits.append(seconds)

    monkeypatch.setattr(livekit_module, "_wait_before_retry", wait)
    recording = tmp_path / "session.ogg"
    recording.write_bytes(RECORDING)

    async def audio(request):
        form = await request.post()
        received.append(form["audio"].file.read())
        status = statuses[min(len(received), len(statuses)) - 1]
        return web.json_response({"status": status}, status=status)

    async def run():
        app = web.Application(client_max_size=10 * 1024 * 1024)
        app.router.add_post(f"/collector/livekit/{TRACE_ID}/audio", audio)
        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, "127.0.0.1", 0)
        await site.start()
        port = site._server.sockets[0].getsockname()[1]
        try:
            await livekit_module.upload_session_artifacts(
                TRACE_ID, audio_path=recording, endpoint=f"http://127.0.0.1:{port}"
            )
            return None
        except Exception as error:  # noqa: BLE001 - the test inspects whatever was raised
            return error
        finally:
            await runner.cleanup()

    return asyncio.run(run()), received, waits


def test_recording_in_use_is_retried_until_it_succeeds(tmp_path, monkeypatch):
    error, received, waits = _run_upload_against([409, 409, 201], tmp_path, monkeypatch)

    assert error is None
    assert waits == [1.0, 2.0]
    # The file is sent in full on every attempt, not half-consumed by the first.
    assert received == [RECORDING, RECORDING, RECORDING]


def test_recording_still_in_use_after_every_retry_raises_409(tmp_path, monkeypatch):
    error, received, waits = _run_upload_against([409], tmp_path, monkeypatch)

    assert isinstance(error, aiohttp.ClientResponseError)
    assert error.status == 409
    assert waits == [1.0, 2.0, 4.0, 8.0, 16.0]
    assert len(received) == 6


@pytest.mark.parametrize("status", [400, 413, 415, 500])
def test_other_errors_are_not_retried(tmp_path, monkeypatch, status):
    error, received, waits = _run_upload_against([status], tmp_path, monkeypatch)

    assert isinstance(error, aiohttp.ClientResponseError)
    assert error.status == status
    assert waits == []
    assert len(received) == 1


def test_retry_budget_fits_inside_livekits_on_session_end_limit():
    """upload_session_artifacts is meant to run in on_session_end."""
    from livekit.agents.worker import WorkerOptions

    from finchvox.livekit import IN_USE_RETRY_DELAYS

    assert sum(IN_USE_RETRY_DELAYS) < WorkerOptions.session_end_timeout / 4


def test_upload_session_artifacts_requires_report_without_trace_id():
    import asyncio

    from finchvox.livekit import upload_session_artifacts

    async def run():
        try:
            await upload_session_artifacts()
        except ValueError as exc:
            return str(exc)
        raise AssertionError("expected ValueError")

    assert "report is required" in asyncio.run(run())
