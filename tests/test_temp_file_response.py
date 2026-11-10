"""A download's temp file must be closed, and so deleted, however the response ends."""

import asyncio
import tempfile

import pytest
from starlette.requests import ClientDisconnect

from finchvox.temp_file_response import CHUNK_SIZE, TempFileResponse

CONTENT = b"x" * (CHUNK_SIZE + 10)


@pytest.fixture
def temp_file():
    file = tempfile.TemporaryFile()  # noqa: SIM115 - the response closes it
    file.write(CONTENT)
    file.seek(0)
    yield file
    file.close()


def _scope(spec_version: str) -> dict:
    return {"type": "http", "asgi": {"spec_version": spec_version}}


async def _wait_forever():
    await asyncio.Event().wait()


def test_full_response_sends_everything_and_closes(temp_file):
    sent = []

    async def send(message):
        sent.append(message)

    asyncio.run(TempFileResponse(temp_file)(_scope("2.4"), _wait_forever, send))

    body = b"".join(m.get("body", b"") for m in sent)
    assert body == CONTENT
    assert temp_file.closed


def test_response_declares_its_size_and_keeps_other_headers(temp_file):
    response = TempFileResponse(temp_file, headers={"X-Example": "kept"})

    assert response.headers["content-length"] == str(len(CONTENT))
    assert response.headers["x-example"] == "kept"


def test_closes_when_sending_fails_mid_download(temp_file):
    """ASGI 2.4 servers report a disconnect by raising from send."""
    sends = []

    async def send(message):
        sends.append(message)
        if len(sends) == 2:
            raise OSError("client went away")

    with pytest.raises(ClientDisconnect):
        asyncio.run(TempFileResponse(temp_file)(_scope("2.4"), _wait_forever, send))

    assert temp_file.closed


def test_closes_when_client_disconnects_mid_download(temp_file):
    """Older ASGI servers report a disconnect through receive instead."""
    first_chunk_sent = asyncio.Event()

    async def send(message):
        if message.get("body"):
            first_chunk_sent.set()
            await _wait_forever()

    async def receive():
        await first_chunk_sent.wait()
        return {"type": "http.disconnect"}

    asyncio.run(TempFileResponse(temp_file)(_scope("2.3"), receive, send))

    assert temp_file.closed
