import io
import json
import os
import shutil
import struct
import tempfile
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from finchvox.collector.config import MAX_UNZIPPED_RATIO, UNZIPPED_TEXT_DIVISOR
from finchvox.session import Session
from finchvox.ui_routes import register_ui_routes


@pytest.fixture
def temp_data_dir():
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def app_with_temp_dir(temp_data_dir):
    app = FastAPI()
    register_ui_routes(app, temp_data_dir)
    return app


@pytest.fixture
def client(app_with_temp_dir):
    return TestClient(app_with_temp_dir)


@dataclass
class SessionContent:
    spans: list
    logs: list = field(default_factory=list)
    exceptions: list = field(default_factory=list)
    audio_files: list = field(default_factory=list)


def _write_jsonl(path: Path, records: list):
    with path.open("w") as f:
        for record in records:
            json.dump(record, f)
            f.write("\n")


def create_session_files(data_dir: Path, session_id: str, content: SessionContent):
    session_dir = data_dir / "sessions" / session_id
    session_dir.mkdir(parents=True, exist_ok=True)

    _write_jsonl(session_dir / f"trace_{session_id}.jsonl", content.spans)

    if content.logs:
        _write_jsonl(session_dir / f"logs_{session_id}.jsonl", content.logs)

    if content.exceptions:
        _write_jsonl(session_dir / f"exceptions_{session_id}.jsonl", content.exceptions)

    if content.audio_files:
        audio_dir = session_dir / "audio"
        audio_dir.mkdir(exist_ok=True)
        for audio_filename, audio_content in content.audio_files:
            (audio_dir / audio_filename).write_bytes(audio_content)


def create_valid_zip(session_id: str, spans: list, logs: list | None = None) -> bytes:
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        trace_content = "\n".join(json.dumps(span) for span in spans)
        zf.writestr(f"{session_id}/trace_{session_id}.jsonl", trace_content)

        if logs:
            log_content = "\n".join(json.dumps(log) for log in logs)
            zf.writestr(f"{session_id}/logs_{session_id}.jsonl", log_content)

    zip_buffer.seek(0)
    return zip_buffer.read()


def upload_zip(client, zip_buffer: io.BytesIO):
    zip_buffer.seek(0)
    return client.post(
        "/api/sessions/upload",
        files={"file": ("test.zip", zip_buffer, "application/zip")},
    )


def download_and_get_zip_files(client, session_id: str) -> list[str]:
    response = client.get(f"/api/sessions/{session_id}/download")
    assert response.status_code == 200
    zip_buffer = io.BytesIO(response.content)
    with zipfile.ZipFile(zip_buffer, "r") as zf:
        return zf.namelist()


class TestSessionDownload:
    def test_download_returns_valid_zip_with_trace(self, client, temp_data_dir):
        session_id = "download123"
        spans = [{"name": "test-span", "start_time_unix_nano": 1000000000}]
        create_session_files(temp_data_dir, session_id, SessionContent(spans=spans))

        response = client.get(f"/api/sessions/{session_id}/download")

        assert response.status_code == 200
        assert response.headers["content-type"] == "application/zip"
        assert (
            f"finchvox_session_{session_id}.zip"
            in response.headers["content-disposition"]
        )

        zip_buffer = io.BytesIO(response.content)
        with zipfile.ZipFile(zip_buffer, "r") as zf:
            file_list = zf.namelist()
            assert f"{session_id}/trace_{session_id}.jsonl" in file_list

    def test_download_includes_logs_if_present(self, client, temp_data_dir):
        session_id = "download_logs"
        spans = [{"name": "test-span", "start_time_unix_nano": 1000000000}]
        logs = [
            {"time_unix_nano": 1500000000, "severity_text": "INFO", "body": "Test log"}
        ]
        create_session_files(
            temp_data_dir, session_id, SessionContent(spans=spans, logs=logs)
        )

        file_list = download_and_get_zip_files(client, session_id)

        assert f"{session_id}/trace_{session_id}.jsonl" in file_list
        assert f"{session_id}/logs_{session_id}.jsonl" in file_list

    def test_download_includes_audio_files(self, client, temp_data_dir):
        session_id = "download_audio"
        spans = [{"name": "test-span", "start_time_unix_nano": 1000000000}]
        audio_files = [("chunk_001.wav", b"fake audio data")]
        create_session_files(
            temp_data_dir,
            session_id,
            SessionContent(spans=spans, audio_files=audio_files),
        )

        file_list = download_and_get_zip_files(client, session_id)

        assert f"{session_id}/audio/chunk_001.wav" in file_list

    def test_download_reports_its_size(self, client, temp_data_dir):
        session_id = "download_size"
        create_session_files(
            temp_data_dir, session_id, SessionContent(spans=[{"name": "span"}])
        )

        response = client.get(f"/api/sessions/{session_id}/download")

        assert response.status_code == 200
        assert int(response.headers["content-length"]) == len(response.content)

    def test_zip_is_built_outside_memory(self, temp_data_dir):
        session_id = "on_disk"
        create_session_files(
            temp_data_dir, session_id, SessionContent(spans=[{"name": "span"}])
        )

        zip_file = Session(temp_data_dir / "sessions" / session_id).to_zip()

        try:
            assert not isinstance(zip_file, io.BytesIO)
            # Only a real file on disk has an operating system file descriptor.
            assert os.fstat(zip_file.fileno()).st_size > 0
            with zipfile.ZipFile(zip_file) as zf:
                assert f"{session_id}/trace_{session_id}.jsonl" in zf.namelist()
        finally:
            zip_file.close()

    def test_failed_zip_closes_its_temp_file(self, temp_data_dir, monkeypatch):
        session_id = "fails"
        create_session_files(
            temp_data_dir, session_id, SessionContent(spans=[{"name": "span"}])
        )
        session = Session(temp_data_dir / "sessions" / session_id)
        opened = []
        real_temporary_file = tempfile.TemporaryFile

        def recording_temporary_file(*args, **kwargs):
            opened.append(real_temporary_file(*args, **kwargs))
            return opened[-1]

        def failing_write(self, *args, **kwargs):
            raise OSError("disk full")

        monkeypatch.setattr(tempfile, "TemporaryFile", recording_temporary_file)
        monkeypatch.setattr(zipfile.ZipFile, "write", failing_write)

        with pytest.raises(OSError, match="disk full"):
            session.to_zip()

        assert opened
        assert opened[0].closed

    @pytest.mark.parametrize(
        ("filename", "expected"),
        [
            ("audio.opus", zipfile.ZIP_STORED),
            ("audio.ogg", zipfile.ZIP_STORED),
            ("audio.mp3", zipfile.ZIP_STORED),
            ("audio.webm", zipfile.ZIP_STORED),
            ("audio.m4a", zipfile.ZIP_STORED),
            ("audio.flac", zipfile.ZIP_STORED),
            ("audio.wav", zipfile.ZIP_DEFLATED),
            ("audio/chunk_0000.wav", zipfile.ZIP_DEFLATED),
            ("livekit_report.json", zipfile.ZIP_DEFLATED),
            ("trace_zipped.jsonl", zipfile.ZIP_DEFLATED),
        ],
    )
    def test_already_compressed_audio_is_stored_as_is(
        self, temp_data_dir, filename, expected
    ):
        create_session_files(
            temp_data_dir, "zipped", SessionContent(spans=[{"name": "span"}])
        )
        path = temp_data_dir / "sessions" / "zipped" / filename
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.exists():
            path.write_bytes(b"x" * 100)

        zip_file = Session(temp_data_dir / "sessions" / "zipped").to_zip()
        with zip_file, zipfile.ZipFile(zip_file) as zf:
            info = zf.getinfo(f"zipped/{filename}")

        assert info.compress_type == expected

    def test_zip_leaves_out_temporary_files(self, temp_data_dir):
        create_session_files(
            temp_data_dir, "busy", SessionContent(spans=[{"name": "span"}])
        )
        session_dir = temp_data_dir / "sessions" / "busy"
        (session_dir / "audio.ogg").write_bytes(b"complete")
        (session_dir / ".audio-k2j4.ogg").write_bytes(b"half an upload")
        (session_dir / ".audio.partial.opus").write_bytes(b"half a compression")
        (session_dir / ".audio_merged.wav").write_bytes(b"merge in progress")

        zip_file = Session(session_dir).to_zip()
        with zip_file, zipfile.ZipFile(zip_file) as zf:
            names = sorted(zf.namelist())

        assert names == ["busy/audio.ogg", "busy/trace_busy.jsonl"]

    def test_download_with_stored_audio_can_be_uploaded_again(
        self, client, temp_data_dir
    ):
        create_session_files(
            temp_data_dir, "stored_trip", SessionContent(spans=[{"name": "span"}])
        )
        session_dir = temp_data_dir / "sessions" / "stored_trip"
        audio = os.urandom(50_000)
        (session_dir / "audio.ogg").write_bytes(audio)

        download = client.get("/api/sessions/stored_trip/download")
        shutil.rmtree(session_dir)
        upload = upload_zip(client, io.BytesIO(download.content))

        assert upload.status_code == 200
        assert (session_dir / "audio.ogg").read_bytes() == audio

    def test_download_returns_404_for_nonexistent_session(self, client):
        response = client.get("/api/sessions/nonexistent_session/download")

        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()


class TestSessionUpload:
    def test_valid_zip_upload_extracts_successfully(self, client, temp_data_dir):
        session_id = "uploaded_session"
        spans = [{"name": "test-span", "start_time_unix_nano": 1000000000}]
        zip_content = create_valid_zip(session_id, spans)

        response = client.post(
            "/api/sessions/upload",
            files={"file": ("test.zip", io.BytesIO(zip_content), "application/zip")},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["session_id"] == session_id

        session_dir = temp_data_dir / "sessions" / session_id
        assert session_dir.exists()
        trace_file = session_dir / f"trace_{session_id}.jsonl"
        assert trace_file.exists()

    def test_upload_without_a_file_returns_422(self, client):
        response = client.post("/api/sessions/upload")

        assert response.status_code == 422

    def test_invalid_zip_file_returns_400(self, client):
        invalid_content = b"this is not a zip file"

        response = client.post(
            "/api/sessions/upload",
            files={
                "file": ("test.zip", io.BytesIO(invalid_content), "application/zip")
            },
        )

        assert response.status_code == 400
        assert "invalid zip" in response.json()["detail"].lower()

    def test_zip_missing_jsonl_returns_400(self, client):
        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, "w") as zf:
            zf.writestr("session123/readme.txt", "No JSONL files here")

        response = upload_zip(client, zip_buffer)

        assert response.status_code == 400
        assert "jsonl" in response.json()["detail"].lower()

    def test_jsonl_with_invalid_json_returns_400(self, client):
        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, "w") as zf:
            zf.writestr(
                "session123/trace_session123.jsonl", "not valid json\n{bad json}"
            )

        response = upload_zip(client, zip_buffer)

        assert response.status_code == 400
        assert "invalid json" in response.json()["detail"].lower()

    def test_upload_overwrites_existing_session(self, client, temp_data_dir):
        session_id = "existing_session"
        original_spans = [{"name": "original-span", "version": 1}]
        create_session_files(
            temp_data_dir, session_id, SessionContent(spans=original_spans)
        )

        new_spans = [{"name": "new-span", "version": 2}]
        zip_content = create_valid_zip(session_id, new_spans)

        response = client.post(
            "/api/sessions/upload",
            files={"file": ("test.zip", io.BytesIO(zip_content), "application/zip")},
        )

        assert response.status_code == 200

        trace_file = (
            temp_data_dir / "sessions" / session_id / f"trace_{session_id}.jsonl"
        )
        content = trace_file.read_text()
        assert "new-span" in content
        assert "original-span" not in content


def _zip_with_entries(*names: str) -> io.BytesIO:
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w") as zf:
        for name in names:
            zf.writestr(name, '{"name": "uploaded"}')
    return zip_buffer


class TestSessionUploadPathSafety:
    @pytest.fixture
    def victim_trace(self, temp_data_dir):
        create_session_files(
            temp_data_dir, "victim", SessionContent(spans=[{"name": "original"}])
        )
        return temp_data_dir / "sessions" / "victim" / "trace_victim.jsonl"

    @pytest.mark.parametrize(
        "entry",
        [
            "../evil.jsonl",
            "../../evil.jsonl",
            "./evil.jsonl",
            "..\\evil.jsonl",
            "/evil.jsonl",
            "bad.name/evil.jsonl",
        ],
    )
    def test_unsafe_session_id_is_rejected_without_deleting_data(
        self, client, temp_data_dir, victim_trace, entry
    ):
        unrelated_file = temp_data_dir / "keep.txt"
        unrelated_file.write_text("keep")

        response = upload_zip(client, _zip_with_entries(entry))

        assert response.status_code == 400
        assert unrelated_file.read_text() == "keep"
        assert "original" in victim_trace.read_text()

    @pytest.mark.parametrize(
        "second_entry",
        [
            "victim/trace_victim.jsonl",
            "uploaded/../victim/trace_victim.jsonl",
        ],
    )
    def test_entry_outside_session_folder_is_rejected(
        self, client, temp_data_dir, victim_trace, second_entry
    ):
        zip_buffer = _zip_with_entries("uploaded/trace_uploaded.jsonl", second_entry)

        response = upload_zip(client, zip_buffer)

        assert response.status_code == 400
        assert "original" in victim_trace.read_text()
        assert not (temp_data_dir / "sessions" / "uploaded").exists()

    def test_rejected_upload_keeps_existing_session_with_same_id(
        self, client, temp_data_dir, victim_trace
    ):
        zip_buffer = _zip_with_entries(
            "victim/trace_victim.jsonl", "other/trace_other.jsonl"
        )

        response = upload_zip(client, zip_buffer)

        assert response.status_code == 400
        assert "original" in victim_trace.read_text()

    def test_zip_with_directory_entries_still_uploads(self, client, temp_data_dir):
        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, "w") as zf:
            zf.writestr("my-session_1/", "")
            zf.writestr("my-session_1/audio/", "")
            zf.writestr("my-session_1/trace_my-session_1.jsonl", '{"name": "span"}')
            zf.writestr("my-session_1/audio/chunk_0000.wav", b"audio")

        response = upload_zip(client, zip_buffer)

        assert response.status_code == 200
        assert response.json()["session_id"] == "my-session_1"
        session_dir = temp_data_dir / "sessions" / "my-session_1"
        assert (session_dir / "audio" / "chunk_0000.wav").read_bytes() == b"audio"


def _zip_entries(entries: dict[str, bytes], compression=zipfile.ZIP_DEFLATED) -> bytes:
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w", compression) as zf:
        for name, content in entries.items():
            zf.writestr(name, content)
    return zip_buffer.getvalue()


def _session_entries(session_id: str, **extra: bytes) -> dict[str, bytes]:
    entries = {f"{session_id}/trace_{session_id}.jsonl": b'{"name": "uploaded"}'}
    entries.update({f"{session_id}/{name}": data for name, data in extra.items()})
    return entries


def _post_zip(client, zip_bytes: bytes):
    return upload_zip(client, io.BytesIO(zip_bytes))


class TestFailedUploadKeepsExistingSession:
    @pytest.fixture
    def existing_trace(self, temp_data_dir):
        create_session_files(
            temp_data_dir, "existing", SessionContent(spans=[{"name": "original"}])
        )
        return temp_data_dir / "sessions" / "existing" / "trace_existing.jsonl"

    def test_corrupt_entry_keeps_old_session_and_leaves_no_temp_files(
        self, client, temp_data_dir, existing_trace
    ):
        # Stored uncompressed so the bytes can be flipped, which fails the CRC
        # check only when extraction reaches this non-JSONL entry.
        zip_bytes = _zip_entries(
            _session_entries("existing", **{"audio.wav": b"A" * 1000}),
            compression=zipfile.ZIP_STORED,
        ).replace(b"A" * 1000, b"B" * 1000)

        response = _post_zip(client, zip_bytes)

        assert response.status_code == 400
        assert "original" in existing_trace.read_text()
        sessions_dir = temp_data_dir / "sessions"
        assert [path.name for path in sessions_dir.iterdir()] == ["existing"]

    def test_successful_upload_leaves_no_temp_files(
        self, client, temp_data_dir, existing_trace
    ):
        response = _post_zip(client, _zip_entries(_session_entries("existing")))

        assert response.status_code == 200
        assert "uploaded" in existing_trace.read_text()
        sessions_dir = temp_data_dir / "sessions"
        assert [path.name for path in sessions_dir.iterdir()] == ["existing"]

    def test_failed_swap_restores_old_session(
        self, temp_data_dir, existing_trace, monkeypatch
    ):
        real_replace = Path.replace

        def failing_replace(self, target):
            moving_new_copy_in = (
                self.name == "existing" and self.parent.name != "sessions"
            )
            if moving_new_copy_in:
                raise OSError("target is busy")
            return real_replace(self, target)

        monkeypatch.setattr(Path, "replace", failing_replace)
        zip_file = io.BytesIO(_zip_entries(_session_entries("existing")))

        with pytest.raises(OSError, match="target is busy"):
            Session.from_zip(zip_file, temp_data_dir / "sessions")

        assert "original" in existing_trace.read_text()
        sessions_dir = temp_data_dir / "sessions"
        assert [path.name for path in sessions_dir.iterdir()] == ["existing"]


class TestUploadSizeLimits:
    MAX_UPLOAD_BYTES = 1024 * 1024

    @pytest.fixture
    def limited_client(self, temp_data_dir):
        app = FastAPI()
        register_ui_routes(app, temp_data_dir, max_upload_bytes=self.MAX_UPLOAD_BYTES)
        return TestClient(app)

    @pytest.fixture
    def oversized_zip(self):
        # Random bytes do not compress, so the zip itself is over the limit.
        return _zip_entries(
            _session_entries(
                "too_big", **{"audio.wav": os.urandom(self.MAX_UPLOAD_BYTES + 1)}
            )
        )

    def test_oversized_upload_is_rejected(
        self, limited_client, temp_data_dir, oversized_zip
    ):
        response = _post_zip(limited_client, oversized_zip)

        assert response.status_code == 413
        assert not (temp_data_dir / "sessions" / "too_big").exists()

    def test_oversized_upload_without_content_length_is_rejected(
        self, limited_client, temp_data_dir, oversized_zip
    ):
        boundary = "finchvoxtestboundary"
        body = (
            f"--{boundary}\r\n"
            'Content-Disposition: form-data; name="file"; filename="test.zip"\r\n'
            "Content-Type: application/zip\r\n\r\n"
        ).encode() + oversized_zip + f"\r\n--{boundary}--\r\n".encode()

        def body_chunks():
            yield body

        response = limited_client.post(
            "/api/sessions/upload",
            content=body_chunks(),
            headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
        )

        assert response.status_code == 413
        assert not (temp_data_dir / "sessions" / "too_big").exists()

    def test_highly_compressed_audio_over_unzipped_limit_is_rejected(
        self, limited_client, temp_data_dir
    ):
        unzipped_limit = self.MAX_UPLOAD_BYTES * MAX_UNZIPPED_RATIO
        zip_bytes = _zip_entries(
            _session_entries("bomb", **{"audio.wav": bytes(unzipped_limit + 1)})
        )
        assert len(zip_bytes) < self.MAX_UPLOAD_BYTES

        response = _post_zip(limited_client, zip_bytes)

        assert response.status_code == 400
        assert "--max-upload-mb" in response.json()["detail"]
        assert not (temp_data_dir / "sessions" / "bomb").exists()

    def test_highly_compressed_trace_over_text_limit_is_rejected(
        self, limited_client, temp_data_dir
    ):
        text_limit = self.MAX_UPLOAD_BYTES // UNZIPPED_TEXT_DIVISOR
        spans = b"{}\n" * (text_limit // 3 + 1)
        zip_bytes = _zip_entries({"bomb/trace_bomb.jsonl": spans})
        assert len(zip_bytes) < self.MAX_UPLOAD_BYTES

        response = _post_zip(limited_client, zip_bytes)

        assert response.status_code == 400
        assert "--max-upload-mb" in response.json()["detail"]
        assert not (temp_data_dir / "sessions" / "bomb").exists()

    def test_entry_lying_about_its_size_is_rejected(
        self, limited_client, temp_data_dir
    ):
        unzipped_limit = self.MAX_UPLOAD_BYTES * MAX_UNZIPPED_RATIO
        zip_bytes = bytearray(
            _zip_entries(
                _session_entries("liar", **{"audio.wav": bytes(unzipped_limit + 1)})
            )
        )
        # Bytes 24-27 of the last central directory record hold the size that
        # zipfile reports for audio.wav. Claim it is tiny.
        central_record = zip_bytes.rfind(b"PK\x01\x02")
        struct.pack_into("<I", zip_bytes, central_record + 24, 10)

        response = _post_zip(limited_client, bytes(zip_bytes))

        assert response.status_code == 400
        assert not (temp_data_dir / "sessions" / "liar").exists()

    def test_compressed_session_within_limits_uploads(
        self, limited_client, temp_data_dir
    ):
        zip_bytes = _zip_entries(
            _session_entries(
                "normal", **{"audio.wav": bytes(self.MAX_UPLOAD_BYTES * 2)}
            )
        )

        response = _post_zip(limited_client, zip_bytes)

        assert response.status_code == 200
        audio = temp_data_dir / "sessions" / "normal" / "audio.wav"
        assert audio.stat().st_size == self.MAX_UPLOAD_BYTES * 2

    def test_session_list_reports_limit_for_the_ui(self, limited_client):
        response = limited_client.get("/api/sessions")

        assert response.json()["max_upload_bytes"] == self.MAX_UPLOAD_BYTES


class TestDownloadUploadRoundTrip:
    def test_downloaded_session_can_be_uploaded(self, client, temp_data_dir):
        session_id = "roundtrip_session"
        spans = [
            {
                "name": "test-span",
                "start_time_unix_nano": 1000000000,
                "end_time_unix_nano": 2000000000,
            }
        ]
        logs = [
            {
                "time_unix_nano": 1500000000,
                "severity_text": "INFO",
                "body": "Test message",
            }
        ]
        create_session_files(
            temp_data_dir, session_id, SessionContent(spans=spans, logs=logs)
        )

        download_response = client.get(f"/api/sessions/{session_id}/download")
        assert download_response.status_code == 200

        session_dir = temp_data_dir / "sessions" / session_id
        import shutil

        shutil.rmtree(session_dir)

        upload_response = client.post(
            "/api/sessions/upload",
            files={
                "file": (
                    "test.zip",
                    io.BytesIO(download_response.content),
                    "application/zip",
                )
            },
        )

        assert upload_response.status_code == 200
        assert upload_response.json()["session_id"] == session_id

        assert session_dir.exists()
        trace_file = session_dir / f"trace_{session_id}.jsonl"
        assert trace_file.exists()
        log_file = session_dir / f"logs_{session_id}.jsonl"
        assert log_file.exists()
