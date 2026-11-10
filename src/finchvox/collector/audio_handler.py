"""
Audio handler for storing conversation audio chunks.

This module provides the AudioHandler class which manages the storage of
audio chunks and their associated metadata, organized by trace ID.
"""

import json
import os
import tempfile
from pathlib import Path
from typing import Protocol

import aiofiles
from loguru import logger

from finchvox.collector.config import (
    FINALIZED_AUDIO_EXTENSIONS,
    get_session_audio_dir,
    get_session_dir,
)


class RecordingTooLargeError(Exception):
    """The uploaded recording is over the size limit."""


class RecordingInUseError(Exception):
    """The current recording is open, for example being played, so it cannot be replaced."""


class _AsyncReadable(Protocol):
    async def read(self, size: int = -1) -> bytes: ...


class AudioHandler:
    """Handles writing audio chunks to organized directory structure."""

    def __init__(self, data_dir: Path):
        """
        Initialize audio handler.

        Args:
            data_dir: Base data directory (e.g., ~/.finchvox)
        """
        self.data_dir = data_dir

    async def save_final_recording(
        self,
        trace_id: str,
        upload: _AsyncReadable,
        extension: str,
        max_bytes: int,
    ) -> int:
        """Save a session's recording, replacing any earlier one only when complete.

        The upload goes to a unique, dot-prefixed temp file in the session folder,
        then is renamed into place in one step. A failure at any point deletes the
        temp file and leaves the previous recording untouched.

        A session keeps one recording, so a recording in another format is removed
        just before the rename. That has to succeed first: if it were left behind,
        for example because it is being played, the shared lookup order could keep
        serving it instead of the new upload.

        Returns:
            The size of the saved recording in bytes.

        Raises:
            RecordingTooLargeError: The upload is over max_bytes.
            RecordingInUseError: The current recording is open and cannot be replaced.
        """
        session_dir = get_session_dir(self.data_dir, trace_id)
        session_dir.mkdir(parents=True, exist_ok=True)
        destination = session_dir / f"audio{extension}"

        temp_file = tempfile.NamedTemporaryFile(  # noqa: SIM115 - closed below, then renamed or deleted
            dir=session_dir, prefix=".audio-", suffix=extension, delete=False
        )
        temp_path = Path(temp_file.name)
        try:
            total = 0
            with temp_file:
                while chunk := await upload.read(1024 * 1024):
                    total += len(chunk)
                    if total > max_bytes:
                        raise RecordingTooLargeError(
                            f"Finalized audio file exceeds {max_bytes} byte limit"
                        )
                    temp_file.write(chunk)
            try:
                self._remove_other_recordings(session_dir, keep=destination)
                os.replace(temp_path, destination)
            except PermissionError as e:
                raise RecordingInUseError(
                    "The current recording is in use, for example being played. "
                    "Retry the upload once it is closed."
                ) from e
        except BaseException:
            temp_path.unlink(missing_ok=True)
            raise

        return total

    @staticmethod
    def _remove_other_recordings(session_dir: Path, keep: Path) -> None:
        for extension in FINALIZED_AUDIO_EXTENSIONS:
            other = session_dir / f"audio{extension}"
            if other != keep:
                other.unlink(missing_ok=True)

    async def save_audio_chunk(
        self,
        trace_id: str,
        chunk_number: int,
        audio_data: bytes,
        metadata: dict,
    ) -> Path | None:
        """
        Save audio chunk with metadata.

        Directory structure:
        data_dir/
          sessions/
            {session_id}/
              audio/
                chunk_0000.wav
                chunk_0000.json
                chunk_0001.wav
                chunk_0001.json

        Args:
            trace_id: OpenTelemetry trace ID (32 hex chars)
            chunk_number: Sequential chunk number
            audio_data: Raw audio file bytes
            metadata: Dictionary containing chunk metadata

        Returns:
            Path to saved audio file, or None if save failed
        """
        try:
            # Validate trace_id format
            if not self._is_valid_trace_id(trace_id):
                logger.error(f"Invalid trace_id format: {trace_id}")
                return None

            # Create trace-specific audio directory
            trace_audio_dir = get_session_audio_dir(self.data_dir, trace_id)
            trace_audio_dir.mkdir(exist_ok=True, parents=True)

            # Generate filenames with zero-padded chunk number
            audio_file = trace_audio_dir / f"chunk_{chunk_number:04d}.wav"
            metadata_file = trace_audio_dir / f"chunk_{chunk_number:04d}.json"

            # Save audio file (async to avoid blocking)
            async with aiofiles.open(audio_file, "wb") as f:
                await f.write(audio_data)

            # Save metadata
            async with aiofiles.open(metadata_file, "w") as f:
                await f.write(json.dumps(metadata, indent=2))

            logger.info(
                f"Saved audio chunk {chunk_number} for trace {trace_id[:8]}... "
                f"({len(audio_data)} bytes)"
            )

            return audio_file

        except OSError as e:
            # Disk full, permission denied, etc.
            logger.exception(
                f"Failed to save audio chunk {chunk_number} for trace {trace_id[:8]}...: {e}"
            )
            return None
        except (TypeError, ValueError) as e:
            # Metadata that cannot be serialized to JSON
            logger.exception(
                f"Unexpected error saving audio chunk {chunk_number} "
                f"for trace {trace_id[:8]}...: {e}"
            )
            return None

    def _is_valid_trace_id(self, trace_id: str) -> bool:
        """
        Validate trace_id format.

        Args:
            trace_id: Trace ID to validate

        Returns:
            True if valid (32 hex chars), False otherwise
        """
        if len(trace_id) != 32:
            return False
        try:
            int(trace_id, 16)  # Validate it's hexadecimal
            return True
        except ValueError:
            return False

    def get_session_audio_dir(self, trace_id: str) -> Path:
        """
        Get directory path for a trace's audio files.

        Args:
            trace_id: OpenTelemetry trace ID

        Returns:
            Path to trace-specific audio directory
        """
        return get_session_audio_dir(self.data_dir, trace_id)

    def list_chunks(self, trace_id: str) -> list[Path]:
        """
        List all audio chunks for a trace.

        Args:
            trace_id: OpenTelemetry trace ID

        Returns:
            Sorted list of audio file paths for the trace
        """
        trace_dir = self.get_session_audio_dir(trace_id)
        if not trace_dir.exists():
            return []
        return sorted(trace_dir.glob("chunk_*.wav"))
