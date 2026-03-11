import json
import tempfile
from pathlib import Path

from fastapi import FastAPI, HTTPException, BackgroundTasks, File, UploadFile
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from loguru import logger

from finchvox.audio_utils import find_chunks, combine_chunks
from finchvox.conversation import Conversation
from finchvox.metrics import Metrics
from finchvox.session import Session
from finchvox.session_repository import SessionRepository
from finchvox.collector.config import (
    get_sessions_base_dir,
    get_session_dir,
    get_session_audio_dir,
    get_default_data_dir,
)
from finchvox import telemetry


UI_DIR = Path(__file__).parent / "ui"
if not UI_DIR.exists():
    PROJECT_ROOT = Path(__file__).parent.parent.parent
    UI_DIR = PROJECT_ROOT / "ui"


def _get_finalized_audio_file(data_dir: Path, session_id: str) -> Path | None:
    session_dir = get_session_dir(data_dir, session_id)
    opus_file = session_dir / "audio.opus"
    wav_file = session_dir / "audio.wav"

    if opus_file.exists():
        return opus_file
    if wav_file.exists():
        return wav_file
    return None


def _get_combined_audio_file(
    data_dir: Path, session_id: str, background_tasks: BackgroundTasks
) -> tuple[Path, str, bool]:
    finalized = _get_finalized_audio_file(data_dir, session_id)
    if finalized:
        media_type = "audio/opus" if finalized.suffix == ".opus" else "audio/wav"
        return finalized, media_type, False

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

    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
        tmp_path = Path(tmp.name)

    combine_chunks(chunks, tmp_path)
    background_tasks.add_task(tmp_path.unlink)

    return tmp_path, "audio/wav", True


async def _handle_list_sessions(sessions_base_dir: Path, page: int = 1) -> JSONResponse:
    repository = SessionRepository(sessions_base_dir)
    result = repository.list_paginated(page)
    return JSONResponse(result.to_dict())


def _get_session(data_dir: Path, session_id: str) -> Session:
    session_dir = get_session_dir(data_dir, session_id)
    if not session_dir.exists():
        raise HTTPException(status_code=404, detail=f"Session {session_id} not found")
    trace_file = session_dir / f"trace_{session_id}.jsonl"
    if not trace_file.exists():
        raise HTTPException(status_code=404, detail=f"Session {session_id} not found")
    return Session(session_dir)


def _get_session_spans(data_dir: Path, session_id: str) -> list[dict]:
    session = _get_session(data_dir, session_id)
    try:
        return session.get_spans()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error reading trace: {str(e)}")


async def _handle_get_session_trace(data_dir: Path, session_id: str) -> JSONResponse:
    spans = _get_session_spans(data_dir, session_id)
    last_span_time = None
    for span in spans:
        if "end_time_unix_nano" in span:
            last_span_time = span["end_time_unix_nano"]
    return JSONResponse({"spans": spans, "last_span_time": last_span_time})


def _get_session_logs_raw(data_dir: Path, session_id: str) -> list[dict]:
    session = _get_session(data_dir, session_id)
    return session.get_logs()


async def _handle_get_session_raw(data_dir: Path, session_id: str) -> JSONResponse:
    session = _get_session(data_dir, session_id)
    spans = session.get_spans()
    logs = session.get_logs()

    content = {"traces": spans, "logs": logs}

    if session.has_environment:
        content["environment"] = json.loads(session.environment_file.read_text())

    return JSONResponse(
        content=content,
        media_type="application/json",
        headers={"Content-Type": "application/json; charset=utf-8"},
    )


async def _handle_get_session_logs(
    data_dir: Path, session_id: str, limit: int
) -> JSONResponse:
    session = _get_session(data_dir, session_id)

    try:
        logs = session.get_logs()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error reading logs: {str(e)}")

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


async def _handle_get_session_conversation(
    data_dir: Path, session_id: str
) -> JSONResponse:
    spans = _get_session_spans(data_dir, session_id)
    conversation = Conversation(spans)
    return JSONResponse({"messages": conversation.to_dict_list()})


async def _handle_get_session_audio(
    data_dir: Path,
    session_id: str,
    background_tasks: BackgroundTasks,
    as_download: bool = False,
) -> FileResponse:
    audio_path, media_type, is_temp = _get_combined_audio_file(
        data_dir, session_id, background_tasks
    )
    disposition = "attachment" if as_download else "inline"
    extension = audio_path.suffix

    return FileResponse(
        str(audio_path),
        media_type=media_type,
        headers={
            "Content-Disposition": f"{disposition}; filename=session_{session_id}{extension}"
        },
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
        last_modified = max(Path(c).stat().st_mtime for c in chunks)

    return JSONResponse(
        {
            "finalized": False,
            "chunk_count": len(chunks),
            "last_modified": last_modified,
        }
    )


async def _handle_upload_session(
    sessions_base_dir: Path, file: UploadFile
) -> JSONResponse:
    zip_bytes = await file.read()

    session, error_msg = Session.from_zip(zip_bytes, sessions_base_dir)
    if error_msg:
        raise HTTPException(status_code=400, detail=error_msg)

    return JSONResponse({"success": True, "session_id": session.session_id})


async def _handle_get_session_exceptions(
    data_dir: Path, session_id: str
) -> JSONResponse:
    session = _get_session(data_dir, session_id)
    return JSONResponse({"exceptions": session.get_exceptions()})


async def _handle_get_session_metrics(data_dir: Path, session_id: str) -> JSONResponse:
    spans = _get_session_spans(data_dir, session_id)
    metrics = Metrics(spans)
    return JSONResponse(metrics.to_dict())


async def _handle_download_session(
    data_dir: Path, session_id: str
) -> StreamingResponse:
    session = _get_session(data_dir, session_id)
    zip_buffer = session.to_zip()
    return StreamingResponse(
        zip_buffer,
        media_type="application/zip",
        headers={
            "Content-Disposition": f"attachment; filename=finchvox_session_{session_id}.zip"
        },
    )


async def _handle_get_session_environment(
    data_dir: Path, session_id: str
) -> JSONResponse:
    session_dir = get_session_dir(data_dir, session_id)
    env_file = session_dir / f"environment_{session_id}.json"

    if not env_file.exists():
        raise HTTPException(status_code=404, detail="Environment data not found")

    return JSONResponse(json.loads(env_file.read_text()))


def register_ui_routes(app: FastAPI, data_dir: Path = None):
    if data_dir is None:
        data_dir = get_default_data_dir()

    sessions_base_dir = get_sessions_base_dir(data_dir)

    app.mount("/css", StaticFiles(directory=str(UI_DIR / "css")), name="css")
    app.mount("/js", StaticFiles(directory=str(UI_DIR / "js")), name="js")
    app.mount("/lib", StaticFiles(directory=str(UI_DIR / "lib")), name="lib")
    app.mount("/images", StaticFiles(directory=str(UI_DIR / "images")), name="images")

    @app.get("/favicon.ico")
    async def favicon():
        return FileResponse(str(UI_DIR / "images" / "favicon.ico"))

    @app.get("/")
    async def index():
        return FileResponse(str(UI_DIR / "sessions_list.html"))

    @app.get("/sessions/{session_id}")
    async def session_detail_page(session_id: str):
        telemetry.send_event("session_view")
        return FileResponse(str(UI_DIR / "session_detail.html"))

    @app.get("/api/sessions")
    async def list_sessions(page: int = 1) -> JSONResponse:
        return await _handle_list_sessions(sessions_base_dir, page)

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
    async def get_session_audio(session_id: str, background_tasks: BackgroundTasks):
        return await _handle_get_session_audio(data_dir, session_id, background_tasks)

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
    async def upload_session(file: UploadFile = File(...)):
        return await _handle_upload_session(sessions_base_dir, file)

    @app.get("/api/sessions/{session_id}/environment")
    async def get_session_environment(session_id: str):
        return await _handle_get_session_environment(data_dir, session_id)
