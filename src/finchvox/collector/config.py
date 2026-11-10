from pathlib import Path

GRPC_PORT = 4317
HTTP_PORT = 3000
MAX_WORKERS = 10

LOG_LEVEL = "INFO"

MAX_AUDIO_FILE_SIZE = 10 * 1024 * 1024
MAX_FINAL_AUDIO_FILE_SIZE = 512 * 1024 * 1024
ALLOWED_AUDIO_FORMATS = {".wav", ".mp3", ".ogg", ".flac"}
ALLOWED_FINAL_AUDIO_FORMATS = {
    ".wav",
    ".mp3",
    ".ogg",
    ".flac",
    ".opus",
    ".webm",
    ".m4a",
}

BYTES_PER_MB = 1024 * 1024

# An audio upload's request body also holds form boundaries and metadata (which
# Starlette caps at 1 MB per field), so its limit allows this much beyond the file.
UPLOAD_BODY_MARGIN_BYTES = 2 * BYTES_PER_MB

# Largest SessionReport or environment body. These are read fully into memory, and
# a report holds conversation text and events, not audio, so this is generous.
MAX_JSON_BODY_BYTES = 64 * BYTES_PER_MB

# Largest OpenTelemetry-over-HTTP batch, after unzipping. It is read into memory to
# decode; exporters send batches of at most a few hundred records.
MAX_OTLP_BYTES = 64 * BYTES_PER_MB

# A LiveKit recording upload can arrive before the session's spans, which LiveKit
# uploads in batches every few seconds. Wait this long for them before refusing.
RECORDING_TRACE_WAIT_SECONDS = 20.0
RECORDING_TRACE_POLL_SECONDS = 0.5

# Largest session zip accepted by the UI upload. Change it at startup with
# `finchvox start --max-upload-mb N`; the two limits below scale with it.
DEFAULT_MAX_UPLOAD_MB = 1024
DEFAULT_MAX_UPLOAD_BYTES = DEFAULT_MAX_UPLOAD_MB * BYTES_PER_MB

# A small zip can expand enormously, so unzipped sizes are limited as well.
# Total unzipped size is capped to protect the disk. JSON and JSONL get a much
# lower cap because Session parses them into memory, whereas audio stays on disk.
MAX_UNZIPPED_RATIO = 10
UNZIPPED_TEXT_DIVISOR = 4

# A session keeps one finished recording, saved as audio<extension>. When more than
# one exists, for example a compressed audio.opus beside an upload, this order
# decides which one playback, the session size and the audio status all use.
FINALIZED_AUDIO_EXTENSIONS = (".opus", ".wav", ".mp3", ".ogg", ".flac", ".webm", ".m4a")

# Formats whose audio is already compressed, so zipping them again only costs time.
ALREADY_COMPRESSED_AUDIO = {".opus", ".ogg", ".mp3", ".webm", ".m4a", ".flac"}

MAX_LOG_BATCH_SIZE = 100
LOG_FLUSH_INTERVAL = 5.0


def get_default_data_dir() -> Path:
    return Path.home() / ".finchvox"


def get_sessions_base_dir(data_dir: Path) -> Path:
    return data_dir / "sessions"


def get_session_dir(data_dir: Path, session_id: str) -> Path:
    return get_sessions_base_dir(data_dir) / session_id


def get_session_audio_dir(data_dir: Path, session_id: str) -> Path:
    return get_session_dir(data_dir, session_id) / "audio"


def get_session_exceptions_dir(data_dir: Path, session_id: str) -> Path:
    return get_session_dir(data_dir, session_id) / "exceptions"
