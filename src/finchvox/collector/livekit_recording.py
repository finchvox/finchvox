"""The session-end upload LiveKit Agents sends to ``LIVEKIT_OBSERVABILITY_URL``.

It is a multipart form with three parts: ``header``, a LiveKit protobuf message
(``MetricsRecordingHeader``) whose ``session_summary`` is the SessionReport as
JSON without its chat history; ``chat_history``, that history as JSON; and
``audio``, the call recording. Together they give Finchvox the same report and
recording that ``finchvox.livekit.on_session_end`` uploads.
"""

import asyncio
import json
import time
from pathlib import Path

from fastapi import UploadFile
from google.protobuf.message import DecodeError
from livekit.protocol.metrics import MetricsRecordingHeader
from loguru import logger
from starlette.concurrency import run_in_threadpool

from .audio_handler import AudioHandler
from .config import (
    ALLOWED_FINAL_AUDIO_FORMATS,
    MAX_FINAL_AUDIO_FILE_SIZE,
    MAX_JSON_BODY_BYTES,
    RECORDING_TRACE_POLL_SECONDS,
    RECORDING_TRACE_WAIT_SECONDS,
)
from .livekit_reports import resolve_livekit_trace_id, store_livekit_report


class RecordingUploadError(ValueError):
    """The upload is not a LiveKit recording upload Finchvox can read."""


class UnsupportedRecordingFormat(ValueError):
    """The recording's file type is not one Finchvox plays."""


class NoMatchingTrace(LookupError):
    """No stored trace carries the report's job or room ID."""


def report_from_upload(header: bytes, chat_history: bytes | None) -> dict:
    """Rebuild the SessionReport from the header and the chat history parts."""
    try:
        message = MetricsRecordingHeader.FromString(header)
    except DecodeError as e:
        raise RecordingUploadError("header is not a LiveKit MetricsRecordingHeader") from e

    report: dict = {}
    if message.session_summary:
        try:
            summary = json.loads(message.session_summary)
        except ValueError as e:
            raise RecordingUploadError("session_summary is not valid JSON") from e
        if isinstance(summary, dict):
            report.update(summary)
    for key, value in (
        ("job_id", message.job_id),
        ("room_id", message.room_id),
        ("room", message.room_name),
    ):
        if value and not report.get(key):
            report[key] = value
    if not any(report.get(key) for key in ("job_id", "room_id", "room")):
        raise RecordingUploadError("header carries no job or room ID")

    if chat_history:
        try:
            history = json.loads(chat_history)
        except ValueError as e:
            raise RecordingUploadError("chat_history is not valid JSON") from e
        if isinstance(history, dict):
            report["chat_history"] = history
    return report


async def _read_limited(upload: UploadFile, limit: int, name: str) -> bytes:
    data = await upload.read(limit + 1)
    if len(data) > limit:
        raise RecordingUploadError(f"{name} is larger than {limit} bytes")
    return data


class LiveKitRecordingReceiver:
    """Attaches LiveKit's session-end upload to the session's trace."""

    def __init__(self, audio_handler: AudioHandler):
        self.audio_handler = audio_handler

    async def receive(
        self,
        header: UploadFile,
        chat_history: UploadFile | None,
        audio: UploadFile | None,
    ) -> str:
        """Store the report and recording; return the trace ID they were attached to."""
        extension = ".ogg"
        if audio is not None:
            extension = Path(audio.filename or "recording.ogg").suffix.lower() or ".ogg"
            if extension not in ALLOWED_FINAL_AUDIO_FORMATS:
                raise UnsupportedRecordingFormat(f"Unsupported recording format: {extension}")

        header_bytes = await _read_limited(header, MAX_JSON_BODY_BYTES, "header")
        chat_bytes = (
            await _read_limited(chat_history, MAX_JSON_BODY_BYTES, "chat_history")
            if chat_history is not None
            else None
        )
        report = report_from_upload(header_bytes, chat_bytes)
        trace_id = await self._wait_for_trace(report)

        data_dir = self.audio_handler.data_dir
        await run_in_threadpool(store_livekit_report, data_dir, trace_id, report)
        if audio is not None:
            await self.audio_handler.save_final_recording(
                trace_id, audio, extension, MAX_FINAL_AUDIO_FILE_SIZE
            )
        logger.info(f"Received LiveKit recording upload for trace {trace_id[:8]}...")
        return trace_id

    async def _wait_for_trace(self, report: dict) -> str:
        # LiveKit sends this upload as the session ends, but uploads spans in
        # batches every few seconds, so the trace may not be stored yet.
        deadline = time.monotonic() + RECORDING_TRACE_WAIT_SECONDS
        data_dir = self.audio_handler.data_dir
        while True:
            trace_id = await run_in_threadpool(resolve_livekit_trace_id, data_dir, report)
            if trace_id:
                return trace_id
            if time.monotonic() >= deadline:
                raise NoMatchingTrace(
                    "No trace with this session's job or room ID arrived within "
                    f"{RECORDING_TRACE_WAIT_SECONDS:g} seconds."
                )
            await asyncio.sleep(RECORDING_TRACE_POLL_SECONDS)
