"""The paths LiveKit Agents uploads to when ``LIVEKIT_OBSERVABILITY_URL`` points at
Finchvox. The request handling lives in ``otlp_http`` and ``livekit_recording``.

The ``Authorization`` header LiveKit sends is never read, logged or stored.
"""

from collections.abc import Callable
from typing import Annotated

from fastapi import FastAPI, File, HTTPException, Request, UploadFile, status
from fastapi.responses import JSONResponse, Response
from starlette.concurrency import run_in_threadpool

from finchvox.body_limit import limit_latest_route_body

from .audio_handler import RecordingInUseError, RecordingTooLargeError
from .config import (
    MAX_FINAL_AUDIO_FILE_SIZE,
    MAX_JSON_BODY_BYTES,
    MAX_OTLP_BYTES,
    UPLOAD_BODY_MARGIN_BYTES,
)
from .livekit_recording import (
    LiveKitRecordingReceiver,
    NoMatchingTrace,
    RecordingUploadError,
    UnsupportedRecordingFormat,
)
from .otlp_http import (
    PROTOBUF_MEDIA_TYPE,
    OtlpBodyError,
    OtlpBodyTooLarge,
    OtlpHttpReceiver,
    UnsupportedEncoding,
)

_OTLP_ERRORS = {
    UnsupportedEncoding: status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
    OtlpBodyTooLarge: status.HTTP_413_CONTENT_TOO_LARGE,
    OtlpBodyError: status.HTTP_400_BAD_REQUEST,
}

_RECORDING_ERRORS = {
    RecordingUploadError: status.HTTP_400_BAD_REQUEST,
    UnsupportedRecordingFormat: status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
    NoMatchingTrace: status.HTTP_404_NOT_FOUND,
    RecordingTooLargeError: status.HTTP_413_CONTENT_TOO_LARGE,
    RecordingInUseError: status.HTTP_409_CONFLICT,
}


def _add_otlp_route(
    app: FastAPI, signal: str, handler: Callable[[bytes, str | None], bytes]
) -> None:
    async def receive(request: Request) -> Response:
        body = await request.body()
        try:
            content = await run_in_threadpool(
                handler, body, request.headers.get("content-encoding")
            )
        except tuple(_OTLP_ERRORS) as e:
            raise HTTPException(status_code=_OTLP_ERRORS[type(e)], detail=str(e)) from e
        return Response(content=content, media_type=PROTOBUF_MEDIA_TYPE)

    app.add_api_route(
        f"/observability/{signal}/otlp/v0",
        receive,
        methods=["POST"],
        name=f"receive_otlp_{signal}",
    )
    limit_latest_route_body(app, MAX_OTLP_BYTES)


def register_observability_routes(
    app: FastAPI, otlp: OtlpHttpReceiver, recordings: LiveKitRecordingReceiver
) -> None:
    _add_otlp_route(app, "traces", otlp.receive_traces)
    _add_otlp_route(app, "logs", otlp.receive_logs)
    _add_otlp_route(app, "metrics", otlp.receive_metrics)

    @app.post("/observability/recordings/v0")
    async def receive_livekit_recording(
        header: Annotated[UploadFile, File()],
        chat_history: Annotated[UploadFile | None, File()] = None,
        audio: Annotated[UploadFile | None, File()] = None,
    ):
        try:
            trace_id = await recordings.receive(header, chat_history, audio)
        except tuple(_RECORDING_ERRORS) as e:
            raise HTTPException(
                status_code=_RECORDING_ERRORS[type(e)], detail=str(e)
            ) from e
        return JSONResponse(
            status_code=status.HTTP_201_CREATED,
            content={"status": "success", "trace_id": trace_id},
        )

    limit_latest_route_body(
        app,
        MAX_FINAL_AUDIO_FILE_SIZE + 2 * MAX_JSON_BODY_BYTES + UPLOAD_BODY_MARGIN_BYTES,
    )
