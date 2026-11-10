import os
import time
from pathlib import Path
from unittest.mock import patch

import pytest

pytest.importorskip("apscheduler")

from finchvox.scheduler import (
    compress_pending_sessions,
    find_sessions_to_compress,
    get_scheduler,
    start_scheduler,
    stop_scheduler,
)


def make_session_with_chunks(
    sessions_dir: Path, session_id: str, create_wav_file, mtime: float | None = None
) -> str:
    audio_dir = sessions_dir / session_id / "audio"
    audio_dir.mkdir(parents=True)
    for i in range(3):
        chunk_path = audio_dir / f"chunk_{i:04d}.wav"
        create_wav_file(chunk_path, duration_seconds=0.5)
        if mtime is not None:
            os.utime(chunk_path, (mtime, mtime))
    return session_id


@pytest.fixture
def session_with_old_chunks(temp_data_dir, create_wav_file):
    sessions_dir = temp_data_dir / "sessions"
    return make_session_with_chunks(
        sessions_dir,
        "abc123def456789012345678901234",
        create_wav_file,
        time.time() - 600,
    )


@pytest.fixture
def session_with_recent_chunks(temp_data_dir, create_wav_file):
    sessions_dir = temp_data_dir / "sessions"
    return make_session_with_chunks(
        sessions_dir, "recent123456789012345678901234", create_wav_file
    )


class TestFindSessionsToCompress:
    def test_finds_session_with_old_chunks(
        self, temp_data_dir, session_with_old_chunks
    ):
        sessions_dir = temp_data_dir / "sessions"
        result = find_sessions_to_compress(
            sessions_dir, min_inactive_minutes=5, max_inactive_minutes=60
        )
        assert session_with_old_chunks in result

    def test_excludes_recently_active_session(
        self, temp_data_dir, session_with_recent_chunks
    ):
        sessions_dir = temp_data_dir / "sessions"
        result = find_sessions_to_compress(
            sessions_dir, min_inactive_minutes=5, max_inactive_minutes=60
        )
        assert session_with_recent_chunks not in result

    def test_excludes_already_compressed_session(
        self, temp_data_dir, session_with_old_chunks
    ):
        sessions_dir = temp_data_dir / "sessions"
        session_dir = sessions_dir / session_with_old_chunks
        (session_dir / "audio.opus").touch()

        result = find_sessions_to_compress(
            sessions_dir, min_inactive_minutes=5, max_inactive_minutes=60
        )
        assert session_with_old_chunks not in result

    def test_excludes_session_without_chunks(self, temp_data_dir):
        sessions_dir = temp_data_dir / "sessions"
        session_id = "empty123456789012345678901234"
        session_dir = sessions_dir / session_id
        audio_dir = session_dir / "audio"
        audio_dir.mkdir(parents=True)

        result = find_sessions_to_compress(
            sessions_dir, min_inactive_minutes=5, max_inactive_minutes=60
        )
        assert session_id not in result

    def test_returns_empty_for_nonexistent_dir(self):
        result = find_sessions_to_compress(Path("/nonexistent/path"))
        assert result == []

    def test_excludes_session_older_than_max_threshold(
        self, temp_data_dir, create_wav_file
    ):
        sessions_dir = temp_data_dir / "sessions"
        session_id = make_session_with_chunks(
            sessions_dir,
            "veryold1234567890123456789012",
            create_wav_file,
            time.time() - 7200,
        )
        result = find_sessions_to_compress(
            sessions_dir, min_inactive_minutes=5, max_inactive_minutes=60
        )
        assert session_id not in result

    def test_excludes_session_not_old_enough(
        self, temp_data_dir, session_with_old_chunks
    ):
        sessions_dir = temp_data_dir / "sessions"
        result = find_sessions_to_compress(
            sessions_dir, min_inactive_minutes=20, max_inactive_minutes=60
        )
        assert session_with_old_chunks not in result


class TestCompressPendingSessions:
    def test_compresses_eligible_sessions(self, temp_data_dir, session_with_old_chunks):
        with patch("finchvox.scheduler.AudioCompressor") as mock_compressor_class:
            mock_compressor = mock_compressor_class.return_value
            mock_compressor.compress.return_value = True

            count = compress_pending_sessions(
                temp_data_dir, min_inactive_minutes=5, max_inactive_minutes=60
            )

            assert count == 1
            mock_compressor.compress.assert_called_once_with(session_with_old_chunks)

    def test_returns_zero_when_no_sessions(self, temp_data_dir):
        count = compress_pending_sessions(
            temp_data_dir, min_inactive_minutes=5, max_inactive_minutes=60
        )
        assert count == 0

    def test_counts_successful_compressions(
        self, temp_data_dir, session_with_old_chunks, create_wav_file
    ):
        sessions_dir = temp_data_dir / "sessions"
        session_id_2 = "second23456789012345678901234"
        session_dir_2 = sessions_dir / session_id_2
        audio_dir_2 = session_dir_2 / "audio"
        audio_dir_2.mkdir(parents=True)

        old_time = time.time() - 600
        chunk_path = audio_dir_2 / "chunk_0000.wav"
        create_wav_file(chunk_path)
        os.utime(chunk_path, (old_time, old_time))

        with patch("finchvox.scheduler.AudioCompressor") as mock_compressor_class:
            mock_compressor = mock_compressor_class.return_value
            mock_compressor.compress.side_effect = [True, False]

            count = compress_pending_sessions(
                temp_data_dir, min_inactive_minutes=5, max_inactive_minutes=60
            )

            assert count == 1
            assert mock_compressor.compress.call_count == 2


class TestSchedulerLifecycle:
    def test_get_scheduler_returns_scheduler(self):
        import finchvox.scheduler as sched_module

        sched_module._scheduler = None
        scheduler = get_scheduler()
        assert scheduler is not None
        sched_module._scheduler = None

    @pytest.mark.asyncio
    async def test_start_and_stop_scheduler(self, temp_data_dir):
        import finchvox.scheduler as sched_module

        sched_module._scheduler = None

        start_scheduler(temp_data_dir, interval_minutes=1, min_inactive_minutes=5)
        scheduler = get_scheduler()
        assert scheduler.running

        stop_scheduler()
        assert sched_module._scheduler is None

    def test_stop_scheduler_when_not_running(self):
        import finchvox.scheduler as sched_module

        sched_module._scheduler = None
        stop_scheduler()
        assert sched_module._scheduler is None

    @pytest.mark.asyncio
    async def test_scheduler_runs_immediately_on_start(self, temp_data_dir):
        import asyncio

        import finchvox.scheduler as sched_module

        sched_module._scheduler = None

        with patch("finchvox.scheduler.compress_pending_sessions") as mock_compress:
            start_scheduler(temp_data_dir, interval_minutes=1, min_inactive_minutes=5)

            await asyncio.sleep(0.1)

            mock_compress.assert_called_once()

            stop_scheduler()
