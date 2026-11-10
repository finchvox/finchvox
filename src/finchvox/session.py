import json
import re
import tempfile
import wave
import zipfile
import zlib
from pathlib import Path
from typing import BinaryIO, Optional

from finchvox.adapters import LiveKitAdapter, PipecatAdapter, detect_platform
from finchvox.audio_utils import find_chunks, find_finalized_audio
from finchvox.collector.config import (
    ALREADY_COMPRESSED_AUDIO,
    DEFAULT_MAX_UPLOAD_BYTES,
    MAX_UNZIPPED_RATIO,
    UNZIPPED_TEXT_DIVISOR,
)

# The session ID becomes a folder name that from_zip replaces, so it must never
# be able to resolve to anything but a single child of the sessions dir.
_SAFE_SESSION_ID = re.compile(r"[A-Za-z0-9_-]+")

# Raised by zipfile for corrupt, encrypted or unsupported archives. Python stops
# reading an entry at its declared size and then fails its CRC check, so an entry
# cannot get past the size limits by understating its size.
_UNREADABLE_ZIP_ERRORS = (
    zipfile.BadZipFile,
    zlib.error,
    EOFError,
    RuntimeError,
    NotImplementedError,
    UnicodeDecodeError,
)

# Raised while reading a session whose files are damaged or hand-edited. A line
# can be valid JSON yet the wrong shape, such as [1, 2] instead of a span, so this
# has to cover more than file errors for one bad session not to break the session
# list. The last two come from merging corrupt WAV chunks. Anything else is a real
# bug and should surface.
MALFORMED_SESSION_ERRORS = (
    OSError,
    ValueError,
    TypeError,
    AttributeError,
    RecursionError,
    wave.Error,
    EOFError,
)


def _read_jsonl_file(file_path: Path) -> list[dict]:
    records = []
    with open(file_path, "r") as f:
        for line in f:
            if line.strip():
                records.append(json.loads(line))
    return records


class Trace:
    def __init__(self, turn_count: int):
        self.turn_count = turn_count

    def to_dict(self) -> dict:
        return {
            "turn_count": self.turn_count,
        }


class Session:
    def __init__(self, session_dir: Path):
        self.session_dir = session_dir
        self.session_id = session_dir.name
        self._span_count: int | None = None
        self._turn_count: int | None = None
        self._log_count: int | None = None
        self._min_start_nano: int | None = None
        self._max_end_nano: int | None = None
        self._service_name: str | None = None
        self._platform: str | None = None
        self._error_count: int = 0
        self.load_error: str | None = None
        self._load_metadata()
        self._load_log_count()

    @property
    def trace_file(self) -> Path:
        return self.session_dir / f"trace_{self.session_id}.jsonl"

    def _extract_service_name(self, span: dict) -> str | None:
        resource = span.get("resource", {})
        for attr in resource.get("attributes", []):
            if attr.get("key") == "service.name":
                return attr.get("value", {}).get("string_value")
        return None

    def _update_min_start(self, current: int | None, span: dict) -> int | None:
        if "start_time_unix_nano" not in span:
            return current
        start_nano = int(span["start_time_unix_nano"])
        if current is None or start_nano < current:
            return start_nano
        return current

    def _update_max_end(self, current: int | None, span: dict) -> int | None:
        if "end_time_unix_nano" not in span:
            return current
        end_nano = int(span["end_time_unix_nano"])
        if current is None or end_nano > current:
            return end_nano
        return current

    def _detect_platform(self, spans: list[dict]) -> str:
        return detect_platform(spans)

    def _get_turn_span_names(self, platform: str) -> list[str]:
        if platform == "livekit":
            return LiveKitAdapter().get_turn_span_names()
        return PipecatAdapter().get_turn_span_names()

    def _load_metadata(self):
        self._error_count = 0
        span_count = 0
        turn_count = 0
        min_start = None
        max_end = None
        service_name = None
        spans = []

        try:
            with open(self.trace_file, "r") as f:
                for line in f:
                    if line.strip():
                        span = json.loads(line)
                        spans.append(span)
                        span_count += 1
                        min_start = self._update_min_start(min_start, span)
                        max_end = self._update_max_end(max_end, span)
                        if service_name is None:
                            service_name = self._extract_service_name(span)

            platform = self._detect_platform(spans)
            turn_span_names = self._get_turn_span_names(platform)
            adapter = LiveKitAdapter() if platform == "livekit" else PipecatAdapter()
            for span in spans:
                if span.get("name") in turn_span_names:
                    turn_count += 1
                if adapter.normalize_span(span).get("_normalized", {}).get("is_error"):
                    self._error_count += 1
            self._platform = platform
        except MALFORMED_SESSION_ERRORS as e:
            self.load_error = str(e) or type(e).__name__
            print(f"Error loading session {self.trace_file}: {e}")

        self._span_count = span_count
        self._turn_count = turn_count
        self._min_start_nano = min_start
        self._max_end_nano = max_end
        self._service_name = service_name

    def _load_log_count(self):
        log_file = self.session_dir / f"logs_{self.session_id}.jsonl"
        if not log_file.exists():
            self._log_count = 0
            return

        try:
            count = 0
            with open(log_file, "r") as f:
                for line in f:
                    if line.strip():
                        count += 1
            self._log_count = count
        except MALFORMED_SESSION_ERRORS as e:
            print(f"Error loading log count for session {self.session_id}: {e}")
            self._log_count = 0

    @property
    def span_count(self) -> int:
        return self._span_count or 0

    @property
    def turn_count(self) -> int:
        return self._turn_count or 0

    @property
    def log_count(self) -> int:
        return self._log_count or 0

    @property
    def start_time(self) -> float | None:
        if self._min_start_nano:
            return self._min_start_nano / 1_000_000_000
        return None

    @property
    def end_time(self) -> float | None:
        if self._max_end_nano:
            return self._max_end_nano / 1_000_000_000
        return None

    @property
    def duration_ms(self) -> float | None:
        if self._min_start_nano and self._max_end_nano:
            return (self._max_end_nano - self._min_start_nano) / 1_000_000
        return None

    @property
    def service_name(self) -> str | None:
        return self._service_name

    @property
    def platform(self) -> str:
        return self._platform or "pipecat"

    @property
    def error_count(self) -> int:
        return self._error_count

    @property
    def trace(self) -> Trace:
        return Trace(turn_count=self.turn_count)

    def get_audio_size_bytes(self) -> int | None:
        audio_file = find_finalized_audio(self.session_dir)
        if audio_file:
            return audio_file.stat().st_size

        sessions_base_dir = self.session_dir.parent
        chunks = find_chunks(sessions_base_dir, self.session_id)
        if not chunks:
            return None
        return sum(chunk_path.stat().st_size for _, chunk_path in chunks)

    def to_dict(self) -> dict:
        audio_bytes = self.get_audio_size_bytes()
        if audio_bytes is None:
            audio_size_mb = None
        elif audio_bytes < 1024 * 1024:
            audio_size_mb = round(audio_bytes / (1024 * 1024), 1)
        else:
            audio_size_mb = audio_bytes // (1024 * 1024)
        return {
            "session_id": self.session_id,
            "service_name": self.service_name,
            "platform": self.platform,
            "error_count": self.error_count,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "duration_ms": self.duration_ms,
            "audio_size_mb": audio_size_mb,
            "trace": self.trace.to_dict(),
            "log_count": self.log_count,
        }

    def to_zip(self) -> BinaryIO:
        """Build the session's zip in a temp file, so its size does not use RAM.

        The operating system removes the temp file when it is closed or when the
        server exits, so the caller must close it when finished.

        Already-compressed audio is stored as-is, since compressing it again takes
        time and saves almost nothing. Dot-prefixed files are work in progress,
        such as an upload or a compression, so they are left out.
        """
        zip_file = tempfile.TemporaryFile()  # noqa: SIM115 - closed by the caller
        try:
            with zipfile.ZipFile(zip_file, "w", zipfile.ZIP_DEFLATED) as zf:
                for file_path in self.session_dir.rglob("*"):
                    relative = file_path.relative_to(self.session_dir)
                    if not file_path.is_file() or any(
                        part.startswith(".") for part in relative.parts
                    ):
                        continue
                    compress_type = (
                        zipfile.ZIP_STORED
                        if file_path.suffix.lower() in ALREADY_COMPRESSED_AUDIO
                        else zipfile.ZIP_DEFLATED
                    )
                    zf.write(
                        file_path,
                        f"{self.session_id}/{relative.as_posix()}",
                        compress_type=compress_type,
                    )
        except BaseException:
            zip_file.close()
            raise

        zip_file.seek(0)
        return zip_file

    @property
    def start_time_nano(self) -> int | None:
        return self._min_start_nano

    @property
    def logs_file(self) -> Path:
        return self.session_dir / f"logs_{self.session_id}.jsonl"

    @property
    def exceptions_file(self) -> Path:
        return self.session_dir / f"exceptions_{self.session_id}.jsonl"

    @property
    def environment_file(self) -> Path:
        return self.session_dir / f"environment_{self.session_id}.json"

    @property
    def has_environment(self) -> bool:
        return self.environment_file.exists()

    def get_spans(self) -> list[dict]:
        if not self.trace_file.exists():
            return []
        return _read_jsonl_file(self.trace_file)

    def get_logs(self) -> list[dict]:
        if not self.logs_file.exists():
            return []
        logs = []
        with open(self.logs_file, "r") as f:
            for line in f:
                if line.strip():
                    try:
                        logs.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue
        return logs

    def get_exceptions(self) -> list[dict]:
        if not self.exceptions_file.exists():
            return []
        return _read_jsonl_file(self.exceptions_file)

    @staticmethod
    def _validate_jsonl_file(zf: zipfile.ZipFile, jsonl_file: str) -> str | None:
        with zf.open(jsonl_file) as f:
            for line_num, line in enumerate(f, 1):
                line = line.decode("utf-8").strip()
                if not line:
                    continue
                try:
                    record = json.loads(line)
                except json.JSONDecodeError:
                    return f"Invalid JSON on line {line_num} of {jsonl_file}"
                if not isinstance(record, dict):
                    return f"Line {line_num} of {jsonl_file} is not a JSON object"
        return None

    @staticmethod
    def validate_zip(zf: zipfile.ZipFile) -> tuple[bool, str | None]:
        jsonl_files = [f for f in zf.namelist() if f.endswith(".jsonl")]
        if not jsonl_files:
            return False, "Zip must contain at least one .jsonl file"

        for jsonl_file in jsonl_files:
            error = Session._validate_jsonl_file(zf, jsonl_file)
            if error:
                return False, error

        return True, None

    @staticmethod
    def extract_id_from_zip(zf: zipfile.ZipFile) -> str | None:
        file_list = zf.namelist()
        if not file_list:
            return None

        first_path = file_list[0]
        parts = first_path.split("/")
        if parts and parts[0]:
            return parts[0]

        return None

    @staticmethod
    def _all_entries_inside_session(zf: zipfile.ZipFile, session_id: str) -> bool:
        for name in zf.namelist():
            parts = name.rstrip("/").split("/")
            if parts[0] != session_id:
                return False
            if any(part in ("", ".", "..") or "\\" in part for part in parts):
                return False
        return True

    @staticmethod
    def _fits_unzipped_limits(zf: zipfile.ZipFile, max_upload_bytes: int) -> bool:
        entries = zf.infolist()
        total_bytes = sum(entry.file_size for entry in entries)
        text_bytes = sum(
            entry.file_size
            for entry in entries
            if Path(entry.filename).suffix.lower() in (".json", ".jsonl")
        )
        return (
            total_bytes <= max_upload_bytes * MAX_UNZIPPED_RATIO
            and text_bytes <= max_upload_bytes // UNZIPPED_TEXT_DIVISOR
        )

    @staticmethod
    def _extract_and_swap(
        zf: zipfile.ZipFile, session_id: str, sessions_base_dir: Path
    ) -> tuple[Optional["Session"], str | None]:
        """Replace a session only once its new copy has extracted and loaded.

        Loading the staged copy runs the same code the UI relies on, so a trace
        that would break the UI is refused here without a second set of rules.

        The staging folder is inside the sessions folder so that moving a session
        in or out of it is a rename on one disk rather than a slow copy. Its dot
        prefix cannot collide with a session ID, and it has no trace file, so the
        session list and the audio scheduler both skip it.
        """
        sessions_base_dir.mkdir(parents=True, exist_ok=True)
        session_dir = sessions_base_dir / session_id

        with tempfile.TemporaryDirectory(
            dir=sessions_base_dir, prefix=".upload-", ignore_cleanup_errors=True
        ) as staging:
            zf.extractall(staging)
            staged_session = Path(staging) / session_id
            previous_session = Path(staging) / ".previous"

            session = Session(staged_session)
            if session.load_error:
                return None, f"Trace has unexpected contents: {session.load_error}"

            had_previous_session = session_dir.exists()
            if had_previous_session:
                session_dir.replace(previous_session)
            try:
                staged_session.replace(session_dir)
            except OSError:
                if had_previous_session:
                    previous_session.replace(session_dir)
                raise

        session.session_dir = session_dir
        return session, None

    @staticmethod
    def from_zip(
        zip_file: BinaryIO,
        sessions_base_dir: Path,
        max_upload_bytes: int = DEFAULT_MAX_UPLOAD_BYTES,
    ) -> tuple[Optional["Session"], str | None]:
        try:
            with zipfile.ZipFile(zip_file, "r") as zf:
                if not Session._fits_unzipped_limits(zf, max_upload_bytes):
                    return None, (
                        "Session is too large once unzipped. Restart Finchvox with "
                        "a higher --max-upload-mb to allow it."
                    )

                is_valid, error_msg = Session.validate_zip(zf)
                if not is_valid:
                    return None, error_msg

                session_id = Session.extract_id_from_zip(zf)
                if not session_id:
                    return None, "Could not determine session ID from zip structure"
                if not _SAFE_SESSION_ID.fullmatch(session_id):
                    return None, "Invalid session ID in zip"
                if not Session._all_entries_inside_session(zf, session_id):
                    return None, "All zip entries must be inside the session folder"
                trace_entry = f"{session_id}/trace_{session_id}.jsonl"
                if trace_entry not in zf.namelist():
                    return None, f"Zip must contain {trace_entry}"

                return Session._extract_and_swap(zf, session_id, sessions_base_dir)
        except _UNREADABLE_ZIP_ERRORS:
            return None, "Invalid zip file"
