"""
Audio utilities for FinchVox trace viewer.

This module provides functions for finding and combining audio chunks
from voice conversation traces.
"""

import tempfile
import wave
from pathlib import Path

from loguru import logger

from finchvox.collector.config import FINALIZED_AUDIO_EXTENSIONS


def find_finalized_audio(session_dir: Path) -> Path | None:
    """Return the session's finished recording, the one every reader should use."""
    for extension in FINALIZED_AUDIO_EXTENSIONS:
        candidate = session_dir / f"audio{extension}"
        if candidate.exists():
            return candidate
    return None


def find_chunks(sessions_dir: Path, session_id: str) -> list[tuple[int, Path]]:
    """
    Find all audio chunks for a given session_id.

    Args:
        sessions_dir: Base sessions directory (e.g., ~/.finchvox/sessions)
        session_id: Session ID to search for

    Returns:
        List of (chunk_number, chunk_path) tuples, sorted by chunk number
    """
    chunks = []

    audio_dir = sessions_dir / session_id / "audio"
    if audio_dir.exists():
        for chunk_file in audio_dir.glob("chunk_*.wav"):
            try:
                chunk_num = int(chunk_file.stem.split("_")[1])
                chunks.append((chunk_num, chunk_file))
            except (IndexError, ValueError) as e:
                logger.warning(f"Could not parse chunk number from {chunk_file}: {e}")

    chunks = list(set(chunks))
    chunks.sort(key=lambda x: x[0])
    return chunks


def combine_chunks_to_temp_file(chunks: list[tuple[int, Path]]) -> Path:
    """Combine chunks into a new temp WAV file, which the caller must delete.

    The temp file is removed here if combining fails, for example on a corrupt chunk.
    """
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
        tmp_path = Path(tmp.name)

    try:
        combine_chunks(chunks, tmp_path)
    except BaseException:
        tmp_path.unlink(missing_ok=True)
        raise

    return tmp_path


def combine_chunks(chunks: list[tuple[int, Path]], output_file: Path) -> None:
    """
    Combine audio chunks into a single WAV file.

    Args:
        chunks: List of (chunk_number, chunk_path) tuples
        output_file: Path to write combined WAV file
    """
    if not chunks:
        logger.error("No chunks to combine")
        return

    # Get audio parameters from first chunk
    first_chunk = chunks[0][1]
    with wave.open(str(first_chunk), "rb") as wf:
        sample_rate = wf.getframerate()
        num_channels = wf.getnchannels()
        sample_width = wf.getsampwidth()

    logger.info(
        f"Combining {len(chunks)} chunks: "
        f"{sample_rate}Hz, {num_channels} channels, {sample_width * 8}-bit"
    )

    # Open output file
    with wave.open(str(output_file), "wb") as out_wf:
        out_wf.setnchannels(num_channels)
        out_wf.setsampwidth(sample_width)
        out_wf.setframerate(sample_rate)

        # Append each chunk
        total_frames = 0
        for chunk_num, chunk_path in chunks:
            logger.debug(f"Adding chunk {chunk_num}: {chunk_path.name}")

            with wave.open(str(chunk_path), "rb") as in_wf:
                # Verify parameters match
                if (
                    in_wf.getframerate() != sample_rate
                    or in_wf.getnchannels() != num_channels
                    or in_wf.getsampwidth() != sample_width
                ):
                    logger.warning(
                        f"Chunk {chunk_num} has different audio parameters, skipping"
                    )
                    continue

                # Read and write all frames
                frames = in_wf.readframes(in_wf.getnframes())
                out_wf.writeframes(frames)
                total_frames += in_wf.getnframes()

        duration_seconds = total_frames / sample_rate
        logger.info(
            f"Combined {len(chunks)} chunks into {output_file.name} "
            f"({duration_seconds:.1f} seconds)"
        )
