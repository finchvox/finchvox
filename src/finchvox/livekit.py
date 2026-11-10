"""Small helpers for local LiveKit session artifacts.

OpenTelemetry is the primary path. These helpers are optional: they let an app
attach LiveKit's locally-generated SessionReport and a finalized audio recording
to the same Finchvox session so the replay UI can be fully synchronized.
"""

from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path
from typing import Any

import aiohttp
from opentelemetry import trace as otel_trace

logger = logging.getLogger(__name__)

# Finchvox answers 409 when the session's current recording is open, for example
# because someone is playing it, so it cannot be replaced yet. Playback usually
# ends soon, so wait and try again, about 31 s in total. upload_session_artifacts
# is meant to run in on_session_end, which LiveKit allows 5 minutes by default.
IN_USE_RETRY_DELAYS = (1.0, 2.0, 4.0, 8.0, 16.0)


async def _wait_before_retry(seconds: float) -> None:
    await asyncio.sleep(seconds)


async def _upload_recording(
    session: aiohttp.ClientSession, url: str, path: Path
) -> None:
    for delay in (*IN_USE_RETRY_DELAYS, None):
        # A fresh form and file handle per attempt, since a sent form is consumed.
        with path.open("rb") as file_handle:
            form = aiohttp.FormData()
            form.add_field(
                "audio",
                file_handle,
                filename=path.name,
                content_type="application/octet-stream",
            )
            async with session.post(url, data=form) as response:
                if response.status != 409 or delay is None:
                    response.raise_for_status()
                    return
        logger.warning(
            "Finchvox recording is in use, for example being played; "
            "retrying the upload in %.0f s",
            delay,
        )
        await _wait_before_retry(delay)


def current_trace_id() -> str | None:
    """Return the active OpenTelemetry trace ID as 32 lowercase hex characters."""
    span_context = otel_trace.get_current_span().get_span_context()
    if not span_context.is_valid:
        return None
    return format(span_context.trace_id, "032x")


def _report_to_dict(report: Any) -> dict[str, Any]:
    if report is None:
        return {}
    if isinstance(report, dict):
        return report
    if hasattr(report, "to_dict"):
        value = report.to_dict()
        if isinstance(value, dict):
            return value
    if hasattr(report, "model_dump"):
        value = report.model_dump(mode="json")
        if isinstance(value, dict):
            return value
    raise TypeError("report must be a dict or expose to_dict()/model_dump()")


async def upload_session_artifacts(
    trace_id: str | None = None,
    *,
    report: Any | None = None,
    audio_path: str | Path | None = None,
    endpoint: str = "http://localhost:3000",
) -> str:
    """Attach a LiveKit SessionReport and/or recording to a Finchvox trace.

    ``trace_id`` is optional when ``report`` is provided. In that common path,
    Finchvox resolves the report to the matching local trace using LiveKit's
    job ID, room SID, or room name. This makes an ``on_session_end`` callback
    enough for a complete local replay without carrying OTel context manually.

    Args:
        trace_id: Optional 32-character OpenTelemetry trace ID used by Finchvox.
        report: A LiveKit ``SessionReport`` (or its dictionary form).
        audio_path: Optional finalized local recording. If omitted and ``report``
            contains ``audio_recording_path``, that path is used automatically.
        endpoint: Finchvox HTTP server origin.

    If the session's current recording is being played, Finchvox cannot replace it
    yet and answers 409. The upload is then retried for about 31 seconds before the
    409 is raised. Other errors are raised immediately.

    Returns:
        The resolved 32-character Finchvox/OpenTelemetry trace ID.
    """
    if trace_id is not None and (
        len(trace_id) != 32 or any(ch not in "0123456789abcdef" for ch in trace_id)
    ):
        raise ValueError("trace_id must be 32 lowercase hexadecimal characters")

    base = endpoint.rstrip("/")
    report_dict = _report_to_dict(report) if report is not None else None
    if trace_id is None and report_dict is None:
        raise ValueError("report is required when trace_id is not provided")
    if audio_path is None and report_dict:
        audio_path = report_dict.get("audio_recording_path") or report_dict.get(
            "audioRecordingPath"
        )

    async with aiohttp.ClientSession() as session:
        if report_dict is not None:
            report_url = (
                f"{base}/collector/livekit/{trace_id}/report"
                if trace_id
                else f"{base}/collector/livekit/report"
            )
            async with session.post(report_url, json=report_dict) as response:
                response.raise_for_status()
                if trace_id is None:
                    payload = await response.json()
                    trace_id = payload.get("trace_id")

        if not trace_id:
            raise RuntimeError("Finchvox did not resolve a trace ID for the session")

        if audio_path:
            path = Path(audio_path).expanduser()
            if path.exists() and path.is_file():
                await _upload_recording(
                    session, f"{base}/collector/livekit/{trace_id}/audio", path
                )

    return trace_id


async def finalize_session(
    ctx: Any,
    *,
    audio_path: str | Path | None = None,
    endpoint: str | None = None,
) -> str | None:
    """Send a finished LiveKit job's report and recording to Finchvox.

    Use this inside your own ``on_session_end``. If you have none, pass
    ``on_session_end`` below to ``@server.rtc_session`` instead.

    It builds the session report, flushes traces so Finchvox can match the report
    to them, and uploads the report and recording. It also schedules one more
    flush for the spans LiveKit ends after ``on_session_end``. Errors are logged,
    never raised, so Finchvox cannot break the job's shutdown.

    Args:
        ctx: The LiveKit ``JobContext``.
        audio_path: A recording to upload instead of the one in the report.
        endpoint: Finchvox HTTP origin. Defaults to the host ``init_livekit()`` was
            given, on port 3000.

    Returns:
        The Finchvox trace ID, or None if anything failed.
    """
    import finchvox

    async def flush_late_spans() -> None:
        finchvox.flush_livekit()

    try:
        ctx.add_shutdown_callback(flush_late_spans)
        report = ctx.make_session_report()
        finchvox.flush_livekit()
        return await upload_session_artifacts(
            report=report,
            audio_path=audio_path,
            endpoint=endpoint or finchvox._livekit_upload_endpoint,
        )
    except Exception:
        # Runs during the job's shutdown, so observability must never break it.
        logger.exception("Could not send the session to Finchvox")
        return None


async def on_session_end(ctx: Any) -> None:
    """Ready-made LiveKit callback: ``@server.rtc_session(on_session_end=...)``.

    Together with ``finchvox.init_livekit()`` this is the whole Finchvox setup. See
    ``finalize_session`` for what it does and how to use it from your own callback.
    """
    await finalize_session(ctx)


def session_report_json(report: Any) -> str:
    """Serialize a LiveKit SessionReport in a predictable, readable form."""
    return json.dumps(_report_to_dict(report), indent=2, ensure_ascii=False)
