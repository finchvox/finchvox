import os
import subprocess
import time
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from finchvox.audio_compressor import (
    AudioCompressor,
    check_ffmpeg_available,
    compress_to_opus,
    ffmpeg_available,
)
from finchvox.scheduler import find_sessions_to_compress
from finchvox.session import Session
from finchvox.ui_routes import register_ui_routes


@pytest.fixture
def session_with_chunks(temp_data_dir, create_wav_file):
    session_id = "abc123def456789012345678901234"
    sessions_dir = temp_data_dir / "sessions"
    session_dir = sessions_dir / session_id
    audio_dir = session_dir / "audio"
    audio_dir.mkdir(parents=True)

    for i in range(3):
        chunk_path = audio_dir / f"chunk_{i:04d}.wav"
        create_wav_file(chunk_path, duration_seconds=0.5)
        metadata_path = audio_dir / f"chunk_{i:04d}.json"
        metadata_path.write_text("{}")

    return session_id


class TestFfmpegAvailable:
    def test_returns_true_when_ffmpeg_installed(self):
        result = ffmpeg_available()
        assert isinstance(result, bool)

    def test_check_caches_result(self):
        import finchvox.audio_compressor as ac

        ac._FFMPEG_AVAILABLE = None
        result1 = check_ffmpeg_available()
        result2 = check_ffmpeg_available()
        assert result1 == result2


class TestAudioCompressor:
    @pytest.mark.parametrize("create_audio_dir", [False, True])
    def test_compress_with_no_chunks(self, temp_data_dir, create_audio_dir):
        session_id = "abc123def456789012345678901234"
        sessions_dir = temp_data_dir / "sessions"
        session_dir = sessions_dir / session_id
        audio_dir = session_dir / "audio"
        if create_audio_dir:
            audio_dir.mkdir(parents=True)
        else:
            session_dir.mkdir(parents=True)

        compressor = AudioCompressor(temp_data_dir)
        result = compressor.compress(session_id)

        assert result is True
        if create_audio_dir:
            assert not audio_dir.exists()

    def test_compress_keeps_chunks_without_ffmpeg(
        self, temp_data_dir, session_with_chunks
    ):
        with patch(
            "finchvox.audio_compressor.check_ffmpeg_available", return_value=False
        ):
            compressor = AudioCompressor(temp_data_dir)
            result = compressor.compress(session_with_chunks)

        assert result is False

        sessions_dir = temp_data_dir / "sessions"
        session_dir = sessions_dir / session_with_chunks
        assert (session_dir / "audio").exists()
        assert not (session_dir / "audio.opus").exists()

    def test_compress_creates_opus_and_removes_chunks_with_ffmpeg(
        self, temp_data_dir, session_with_chunks
    ):
        if not ffmpeg_available():
            pytest.skip("ffmpeg not available")

        import finchvox.audio_compressor as ac

        ac._FFMPEG_AVAILABLE = None

        compressor = AudioCompressor(temp_data_dir)
        result = compressor.compress(session_with_chunks)

        assert result is True

        sessions_dir = temp_data_dir / "sessions"
        session_dir = sessions_dir / session_with_chunks
        assert (session_dir / "audio.opus").exists()
        assert not (session_dir / "audio").exists()


class TestPartialAudioIsNeverPublished:
    """audio.opus must mean a finished recording, even while ffmpeg is writing."""

    @pytest.fixture(autouse=True)
    def ffmpeg_is_available(self):
        with patch(
            "finchvox.audio_compressor.check_ffmpeg_available", return_value=True
        ):
            yield

    @pytest.fixture
    def session_dir(self, temp_data_dir, session_with_chunks):
        session_dir = temp_data_dir / "sessions" / session_with_chunks
        (session_dir / f"trace_{session_with_chunks}.jsonl").write_text(
            '{"name": "agent_turn"}\n'
        )
        return session_dir

    @pytest.fixture
    def client(self, temp_data_dir):
        app = FastAPI()
        register_ui_routes(app, temp_data_dir)
        return TestClient(app)

    @staticmethod
    def _fake_ffmpeg(during_write=None, returncode=0):
        """Stands in for ffmpeg: writes partial output, then runs a check mid-write."""

        def run(command, **kwargs):
            output = Path(command[-1])
            output.write_bytes(b"partial")
            if during_write:
                during_write()
            if returncode:
                raise subprocess.CalledProcessError(returncode, command, stderr=b"bad")
            output.write_bytes(b"complete")

        return run

    def test_audio_opus_only_appears_once_complete(
        self, temp_data_dir, session_with_chunks, session_dir
    ):
        seen_during_write = []
        run = self._fake_ffmpeg(
            lambda: seen_during_write.append((session_dir / "audio.opus").exists())
        )

        with patch("finchvox.audio_compressor.subprocess.run", run):
            result = AudioCompressor(temp_data_dir).compress(session_with_chunks)

        assert result is True
        assert seen_during_write == [False]
        assert (session_dir / "audio.opus").read_bytes() == b"complete"
        assert not list(session_dir.glob("*.partial*"))

    def test_playback_uses_chunks_until_compression_finishes(
        self, temp_data_dir, session_with_chunks, session_dir, client
    ):
        audio_url = f"/api/sessions/{session_with_chunks}/audio"
        during_write = {}

        def check_routes():
            during_write["audio"] = client.get(audio_url)
            during_write["status"] = client.get(f"{audio_url}/status")

        with patch(
            "finchvox.audio_compressor.subprocess.run", self._fake_ffmpeg(check_routes)
        ):
            AudioCompressor(temp_data_dir).compress(session_with_chunks)

        assert during_write["audio"].status_code == 200
        assert during_write["audio"].headers["content-type"] == "audio/wav"
        assert during_write["status"].json()["finalized"] is False

        finished = client.get(audio_url)
        assert finished.headers["content-type"] == "audio/opus"
        assert finished.content == b"complete"
        assert client.get(f"{audio_url}/status").json()["finalized"] is True

    def test_session_size_ignores_a_partial_file(
        self, temp_data_dir, session_with_chunks, session_dir
    ):
        sizes = {}
        chunks_size = Session(session_dir).get_audio_size_bytes()

        def check_size():
            sizes["during"] = Session(session_dir).get_audio_size_bytes()

        with patch(
            "finchvox.audio_compressor.subprocess.run", self._fake_ffmpeg(check_size)
        ):
            AudioCompressor(temp_data_dir).compress(session_with_chunks)

        assert sizes["during"] == chunks_size

    def test_failed_ffmpeg_keeps_chunks_and_leaves_no_partial_file(
        self, temp_data_dir, session_with_chunks, session_dir
    ):
        with patch(
            "finchvox.audio_compressor.subprocess.run",
            self._fake_ffmpeg(returncode=1),
        ):
            result = AudioCompressor(temp_data_dir).compress(session_with_chunks)

        assert result is False
        assert not (session_dir / "audio.opus").exists()
        assert not (session_dir / ".audio_merged.wav").exists()
        assert not list(session_dir.glob("*.partial*"))
        assert list((session_dir / "audio").glob("chunk_*.wav"))

    @pytest.mark.parametrize(
        "contents",
        [pytest.param(b"not a wav", id="not-a-wav"), pytest.param(b"", id="empty")],
    )
    def test_corrupt_chunk_keeps_chunks_and_leaves_no_merged_file(
        self, temp_data_dir, session_with_chunks, session_dir, contents
    ):
        (session_dir / "audio" / "chunk_0001.wav").write_bytes(contents)

        result = AudioCompressor(temp_data_dir).compress(session_with_chunks)

        assert result is False
        assert not (session_dir / "audio.opus").exists()
        assert not (session_dir / ".audio_merged.wav").exists()
        assert (session_dir / "audio" / "chunk_0000.wav").exists()

    def test_unexpected_ffmpeg_error_leaves_no_partial_file(
        self, temp_data_dir, session_with_chunks, session_dir
    ):
        def run(command, **kwargs):
            Path(command[-1]).write_bytes(b"partial")
            raise OSError("ffmpeg went away")

        with (
            patch("finchvox.audio_compressor.subprocess.run", run),
            pytest.raises(OSError, match="ffmpeg went away"),
        ):
            AudioCompressor(temp_data_dir).compress(session_with_chunks)

        assert not (session_dir / "audio.opus").exists()
        assert not list(session_dir.glob("*.partial*"))

    def test_partial_file_left_by_a_crash_does_not_block_compression(
        self, temp_data_dir, session_with_chunks, session_dir
    ):
        (session_dir / ".audio.partial.opus").write_bytes(b"left by a crash")
        sessions_dir = temp_data_dir / "sessions"
        old = time.time() - 300
        for chunk in (session_dir / "audio").iterdir():
            os.utime(chunk, (old, old))

        assert session_with_chunks in find_sessions_to_compress(sessions_dir)

        with patch(
            "finchvox.audio_compressor.subprocess.run", self._fake_ffmpeg()
        ):
            result = AudioCompressor(temp_data_dir).compress(session_with_chunks)

        assert result is True
        assert (session_dir / "audio.opus").read_bytes() == b"complete"
        assert not list(session_dir.glob("*.partial*"))


class TestCompressToOpus:
    def test_real_ffmpeg_output_is_published_without_a_partial_file(
        self, temp_sessions_dir, create_wav_file
    ):
        if not ffmpeg_available():
            pytest.skip("ffmpeg not available")

        input_wav = temp_sessions_dir / "input.wav"
        output_opus = temp_sessions_dir / "audio.opus"
        create_wav_file(input_wav, duration_seconds=1.0)

        assert compress_to_opus(input_wav, output_opus) is True
        assert output_opus.read_bytes()[:4] == b"OggS"
        assert not list(temp_sessions_dir.glob("*.partial*"))

    def test_compress_to_opus_creates_file(self, temp_sessions_dir, create_wav_file):
        if not ffmpeg_available():
            pytest.skip("ffmpeg not available")

        input_wav = temp_sessions_dir / "input.wav"
        output_opus = temp_sessions_dir / "output.opus"
        create_wav_file(input_wav, duration_seconds=1.0)

        result = compress_to_opus(input_wav, output_opus)

        assert result is True
        assert output_opus.exists()
        assert output_opus.stat().st_size > 0
        assert output_opus.stat().st_size < input_wav.stat().st_size
