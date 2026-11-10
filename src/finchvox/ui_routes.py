import json
from functools import wraps
from pathlib import Path
from typing import Annotated

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse, JSONResponse
from loguru import logger

from finchvox import telemetry
from finchvox.adapters import get_adapter
from finchvox.audio_utils import (
    combine_chunks_to_temp_file,
    find_chunks,
    find_finalized_audio,
)
from finchvox.body_limit import limit_latest_route_body
from finchvox.collector.config import (
    DEFAULT_MAX_UPLOAD_BYTES,
    get_default_data_dir,
    get_session_audio_dir,
    get_session_dir,
    get_sessions_base_dir,
)
from finchvox.conversation import Conversation
from finchvox.livekit_report import (
    load_livekit_report,
    report_events,
    report_messages,
    report_usage,
)
from finchvox.metrics import Metrics
from finchvox.server_info import ServerInfo
from finchvox.session import MALFORMED_SESSION_ERRORS, Session
from finchvox.session_repository import SessionRepository
from finchvox.static_files import RevalidatedStaticFiles, page_response
from finchvox.temp_file_response import TempFileResponse, TempPathResponse

UI_DIR = Path(__file__).parent / "ui"
if not UI_DIR.exists():
    PROJECT_ROOT = Path(__file__).parent.parent.parent
    UI_DIR = PROJECT_ROOT / "ui"


def _explains_damaged_session(handler):
    """Turn errors from reading damaged session files into an explanation.

    The details go to the server log, not the response, because they can contain
    server paths.
    """

    @wraps(handler)
    async def wrapper(*args, **kwargs):
        try:
            return await handler(*args, **kwargs)
        except MALFORMED_SESSION_ERRORS as e:
            logger.exception("Could not read session data")
            raise HTTPException(
                status_code=500,
                detail=(
                    "Could not read this session; its files may be damaged. "
                    "See the server log for details."
                ),
            ) from e

    return wrapper


_FINALIZED_AUDIO_MEDIA_TYPES = {
    ".opus": "audio/opus",
    ".wav": "audio/wav",
    ".mp3": "audio/mpeg",
    ".ogg": "audio/ogg",
    ".flac": "audio/flac",
    ".webm": "audio/webm",
    ".m4a": "audio/mp4",
}


def _get_finalized_audio_file(data_dir: Path, session_id: str) -> Path | None:
    return find_finalized_audio(get_session_dir(data_dir, session_id))


def _find_session_chunks(data_dir: Path, session_id: str) -> list[tuple[int, Path]]:
    audio_dir = get_session_audio_dir(data_dir, session_id)
    if not audio_dir.exists():
        raise HTTPException(
            status_code=404, detail=f"Audio for session {session_id} not found"
        )

    logger.info(f"Finding audio chunks for session {session_id}")
    chunks = find_chunks(get_sessions_base_dir(data_dir), session_id)

    if not chunks:
        raise HTTPException(
            status_code=404, detail=f"No audio chunks found for session {session_id}"
        )

    logger.info(f"Found {len(chunks)} chunks for session {session_id}")
    return chunks


async def _handle_list_sessions(
    sessions_base_dir: Path, max_upload_bytes: int, page: int
) -> JSONResponse:
    # Reads every session's trace file, so keep it off the event loop.
    result = await run_in_threadpool(SessionRepository(sessions_base_dir).list_paginated, page)
    return JSONResponse({**result.to_dict(), "max_upload_bytes": max_upload_bytes})


def _get_session(data_dir: Path, session_id: str) -> Session:
    session_dir = get_session_dir(data_dir, session_id)
    if not session_dir.exists():
        raise HTTPException(status_code=404, detail=f"Session {session_id} not found")
    trace_file = session_dir / f"trace_{session_id}.jsonl"
    if not trace_file.exists():
        raise HTTPException(status_code=404, detail=f"Session {session_id} not found")
    return Session(session_dir)


def _get_session_spans(data_dir: Path, session_id: str) -> list[dict]:
    return _get_session(data_dir, session_id).get_spans()


@_explains_damaged_session
async def _handle_get_session_trace(data_dir: Path, session_id: str) -> JSONResponse:
    spans = _get_session_spans(data_dir, session_id)
    adapter = get_adapter(spans)
    normalized_spans = adapter.normalize_spans(spans)
    last_span_time = None
    for span in normalized_spans:
        if "end_time_unix_nano" in span:
            last_span_time = span["end_time_unix_nano"]
    return JSONResponse(
        {
            "spans": normalized_spans,
            "platform": adapter.get_platform(),
            "last_span_time": last_span_time,
        }
    )


@_explains_damaged_session
async def _handle_get_session_raw(data_dir: Path, session_id: str) -> JSONResponse:
    session = _get_session(data_dir, session_id)
    spans = session.get_spans()
    logs = session.get_logs()

    content = {"traces": spans, "logs": logs}

    report_file = session.session_dir / "livekit_report.json"
    if report_file.exists():
        content["livekit_session_report"] = json.loads(report_file.read_text())

    if session.has_environment:
        content["environment"] = json.loads(session.environment_file.read_text())

    return JSONResponse(
        content=content,
        media_type="application/json",
        headers={"Content-Type": "application/json; charset=utf-8"},
    )


@_explains_damaged_session
async def _handle_get_session_logs(
    data_dir: Path, session_id: str, limit: int
) -> JSONResponse:
    session = _get_session(data_dir, session_id)
    logs = session.get_logs()

    logs.sort(key=lambda log: int(log.get("time_unix_nano", 0)))
    total_count = len(logs)

    return JSONResponse(
        {
            "logs": logs[:limit],
            "total_count": total_count,
            "limit": limit,
            "trace_start_time": session.start_time_nano,
        }
    )


@_explains_damaged_session
async def _handle_get_session_conversation(
    data_dir: Path, session_id: str
) -> JSONResponse:
    session = _get_session(data_dir, session_id)
    spans = session.get_spans()
    adapter = get_adapter(spans)
    normalized_spans = adapter.normalize_spans(spans)
    trace_messages = Conversation(normalized_spans).to_dict_list()

    report = load_livekit_report(session.session_dir)
    if report:
        enriched_messages = report_messages(report, trace_messages)
        if enriched_messages:
            return JSONResponse(
                {
                    "messages": enriched_messages,
                    "events": report_events(report),
                    "source": "livekit_session_report",
                }
            )

    return JSONResponse(
        {"messages": trace_messages, "events": [], "source": "opentelemetry"}
    )


@_explains_damaged_session
async def _handle_get_session_audio(
    data_dir: Path,
    session_id: str,
    as_download: bool = False,
) -> FileResponse:
    disposition = "attachment" if as_download else "inline"

    def headers(extension: str) -> dict[str, str]:
        return {
            "Content-Disposition": f"{disposition}; filename=session_{session_id}{extension}"
        }

    finalized = _get_finalized_audio_file(data_dir, session_id)
    if finalized:
        media_type = _FINALIZED_AUDIO_MEDIA_TYPES.get(
            finalized.suffix, "application/octet-stream"
        )
        return FileResponse(
            str(finalized), media_type=media_type, headers=headers(finalized.suffix)
        )

    chunks = _find_session_chunks(data_dir, session_id)
    merged_audio = await run_in_threadpool(combine_chunks_to_temp_file, chunks)
    return TempPathResponse(
        str(merged_audio), media_type="audio/wav", headers=headers(".wav")
    )


async def _handle_get_session_audio_status(
    data_dir: Path, session_id: str
) -> JSONResponse:
    finalized = _get_finalized_audio_file(data_dir, session_id)
    if finalized:
        return JSONResponse(
            {
                "finalized": True,
                "format": finalized.suffix[1:],
                "size_bytes": finalized.stat().st_size,
                "last_modified": finalized.stat().st_mtime,
            }
        )

    audio_dir = get_session_audio_dir(data_dir, session_id)

    if not audio_dir.exists():
        return JSONResponse(
            {"finalized": False, "chunk_count": 0, "last_modified": None}
        )

    chunks = find_chunks(get_sessions_base_dir(data_dir), session_id)

    last_modified = None
    if chunks:
        last_modified = max(chunk_path.stat().st_mtime for _, chunk_path in chunks)

    return JSONResponse(
        {
            "finalized": False,
            "chunk_count": len(chunks),
            "last_modified": last_modified,
        }
    )


async def _handle_upload_session(
    sessions_base_dir: Path, file: UploadFile, max_upload_bytes: int
) -> JSONResponse:
    session, error_msg = await run_in_threadpool(
        Session.from_zip, file.file, sessions_base_dir, max_upload_bytes
    )
    if error_msg:
        raise HTTPException(status_code=400, detail=error_msg)

    return JSONResponse({"success": True, "session_id": session.session_id})


@_explains_damaged_session
async def _handle_get_session_exceptions(
    data_dir: Path, session_id: str
) -> JSONResponse:
    session = _get_session(data_dir, session_id)
    return JSONResponse({"exceptions": session.get_exceptions()})


@_explains_damaged_session
async def _handle_get_session_metrics(data_dir: Path, session_id: str) -> JSONResponse:
    session = _get_session(data_dir, session_id)
    spans = session.get_spans()
    adapter = get_adapter(spans)
    normalized_spans = adapter.normalize_spans(spans)
    trace_messages = Conversation(normalized_spans).to_dict_list()
    report = load_livekit_report(session.session_dir)
    report_message_list = report_messages(report, trace_messages) if report else []
    usage = report_usage(report) if report else []
    metrics = Metrics(normalized_spans, report_messages=report_message_list, usage=usage)
    return JSONResponse(metrics.to_dict())


async def _handle_download_session(
    data_dir: Path, session_id: str
) -> TempFileResponse:
    session = _get_session(data_dir, session_id)
    zip_file = await run_in_threadpool(session.to_zip)
    return TempFileResponse(
        zip_file,
        media_type="application/zip",
        headers={
            "Content-Disposition": f"attachment; filename=finchvox_session_{session_id}.zip",
        },
    )


@_explains_damaged_session
async def _handle_get_session_environment(
    data_dir: Path, session_id: str
) -> JSONResponse:
    session_dir = get_session_dir(data_dir, session_id)
    env_file = session_dir / f"environment_{session_id}.json"

    if not env_file.exists():
        raise HTTPException(status_code=404, detail="Environment data not found")

    return JSONResponse(json.loads(env_file.read_text()))


def register_ui_routes(
    app: FastAPI,
    data_dir: Path | None = None,
    max_upload_bytes: int = DEFAULT_MAX_UPLOAD_BYTES,
    server_info: ServerInfo | None = None,
):
    if data_dir is None:
        data_dir = get_default_data_dir()
    if server_info is None:
        server_info = ServerInfo.describe(data_dir=data_dir, max_upload_bytes=max_upload_bytes)

    sessions_base_dir = get_sessions_base_dir(data_dir)

    for folder in ("css", "js", "lib", "images"):
        app.mount(f"/{folder}", RevalidatedStaticFiles(directory=str(UI_DIR / folder)), name=folder)

    @app.get("/favicon.ico")
    async def favicon():
        return page_response(UI_DIR / "images" / "favicon.ico")

    @app.get("/")
    async def index():
        return page_response(UI_DIR / "sessions_list.html")

    @app.get("/sessions/{session_id}")
    async def session_detail_page(session_id: str):
        telemetry.send_event("session_view")
        return page_response(UI_DIR / "session_detail.html")

    @app.get("/settings")
    async def settings_page():
        return page_response(UI_DIR / "settings.html")

    # Read-only on purpose; see finchvox.server_info.
    @app.get("/api/settings/server")
    async def get_server_settings() -> JSONResponse:
        return JSONResponse(server_info.to_dict())

    @app.get("/api/sessions")
    async def list_sessions(page: int = 1) -> JSONResponse:
        return await _handle_list_sessions(sessions_base_dir, max_upload_bytes, page)

    @app.get("/api/sessions/{session_id}/trace")
    async def get_session_trace(session_id: str) -> JSONResponse:
        return await _handle_get_session_trace(data_dir, session_id)

    @app.get("/api/sessions/{session_id}/raw")
    async def get_session_raw(session_id: str) -> JSONResponse:
        return await _handle_get_session_raw(data_dir, session_id)

    @app.get("/api/sessions/{session_id}/logs")
    async def get_session_logs(session_id: str, limit: int = 1000) -> JSONResponse:
        return await _handle_get_session_logs(data_dir, session_id, limit)

    @app.get("/api/sessions/{session_id}/conversation")
    async def get_session_conversation(session_id: str) -> JSONResponse:
        return await _handle_get_session_conversation(data_dir, session_id)

    @app.get("/api/sessions/{session_id}/exceptions")
    async def get_session_exceptions(session_id: str) -> JSONResponse:
        return await _handle_get_session_exceptions(data_dir, session_id)

    @app.get("/api/sessions/{session_id}/audio")
    async def get_session_audio(session_id: str):
        return await _handle_get_session_audio(data_dir, session_id)

    @app.get("/api/sessions/{session_id}/audio/status")
    async def get_session_audio_status(session_id: str) -> JSONResponse:
        return await _handle_get_session_audio_status(data_dir, session_id)

    @app.get("/api/sessions/{session_id}/metrics")
    async def get_session_metrics(session_id: str) -> JSONResponse:
        return await _handle_get_session_metrics(data_dir, session_id)

    @app.get("/api/sessions/{session_id}/download")
    async def download_session(session_id: str):
        return await _handle_download_session(data_dir, session_id)

    @app.post("/api/sessions/upload")
    async def upload_session(file: Annotated[UploadFile, File()]):
        return await _handle_upload_session(sessions_base_dir, file, max_upload_bytes)

    limit_latest_route_body(app, max_upload_bytes)

    @app.get("/api/sessions/{session_id}/environment")
    async def get_session_environment(session_id: str):
        return await _handle_get_session_environment(data_dir, session_id)
