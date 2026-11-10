"""Send temp files as HTTP responses, and clean them up however the response ends."""

import os
from collections.abc import Iterator, Mapping
from pathlib import Path
from typing import BinaryIO

from fastapi.responses import FileResponse, StreamingResponse
from loguru import logger
from starlette.types import Receive, Scope, Send

CHUNK_SIZE = 1024 * 1024


class TempPathResponse(FileResponse):
    """Send a named temp file, then delete it however the response ends.

    Built on FileResponse to keep Range requests, which audio seeking relies on. A
    background task would not be reliable: Starlette skips it when a client
    disconnects on servers using ASGI 2.4 or newer.
    """

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        try:
            await super().__call__(scope, receive, send)
        finally:
            try:
                Path(self.path).unlink(missing_ok=True)
            except OSError:
                logger.exception(f"Could not delete temp file {self.path}")


class TempFileResponse(StreamingResponse):
    """Send a temp file, then close it however the response ends.

    Closing is what deletes the file. It is done here rather than in the generator
    or a background task because neither runs reliably when a client disconnects:
    Starlette abandons the generator without closing it, which leaves the temp file
    on disk until garbage collection happens to run.
    """

    def __init__(
        self,
        file: BinaryIO,
        headers: Mapping[str, str] | None = None,
        media_type: str | None = None,
    ) -> None:
        self.file = file
        size = os.fstat(file.fileno()).st_size
        super().__init__(
            self._chunks(),
            headers={"Content-Length": str(size), **(headers or {})},
            media_type=media_type,
        )

    def _chunks(self) -> Iterator[bytes]:
        while chunk := self.file.read(CHUNK_SIZE):
            yield chunk

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        try:
            await super().__call__(scope, receive, send)
        finally:
            self.file.close()
