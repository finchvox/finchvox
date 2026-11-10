"""Match a LiveKit SessionReport to its local trace, and store it there."""

import json
import re
from pathlib import Path

from .config import get_session_dir


def _otel_attributes(span: dict) -> dict[str, object]:
    """Decode the small subset of OTLP JSON attributes needed for correlation."""
    decoded: dict[str, object] = {}
    for attr in span.get("attributes", []) or []:
        key = attr.get("key")
        value = attr.get("value") or {}
        if not key:
            continue
        for value_key in (
            "string_value",
            "int_value",
            "double_value",
            "bool_value",
        ):
            if value_key in value:
                decoded[key] = value[value_key]
                break
    return decoded


def livekit_report_identity(report: dict) -> tuple[str | None, str | None, str | None]:
    """Return (job_id, room_id, room_name) across Python/JS report spellings."""
    job_id = report.get("job_id") or report.get("jobId")
    room_id = report.get("room_id") or report.get("roomId")
    room_name = report.get("room") or report.get("room_name") or report.get("roomName")
    return (
        str(job_id) if job_id else None,
        str(room_id) if room_id else None,
        str(room_name) if room_name else None,
    )


def resolve_livekit_trace_id(data_dir: Path, report: dict) -> str | None:
    """Find the local OTel trace that belongs to a LiveKit SessionReport.

    LiveKit's report does not currently include the OTel trace ID, but its job,
    room SID, and room name are also emitted on LiveKit spans. Matching these
    values lets a normal ``on_session_end`` callback attach the report/audio
    without application code manually carrying a trace ID through the session.
    """
    job_id, room_id, room_name = livekit_report_identity(report)
    if not any((job_id, room_id, room_name)):
        return None

    sessions_dir = data_dir / "sessions"
    if not sessions_dir.exists():
        return None

    best: tuple[int, float, str] | None = None
    for session_dir in sessions_dir.iterdir():
        if not session_dir.is_dir() or not re.match(r"^[a-f0-9]{32}$", session_dir.name):
            continue
        trace_file = session_dir / f"trace_{session_dir.name}.jsonl"
        if not trace_file.exists():
            continue
        score = 0
        try:
            with trace_file.open() as handle:
                for line in handle:
                    if not line.strip():
                        continue
                    try:
                        span = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    attrs = _otel_attributes(span)
                    span_job_id = attrs.get("job_id") or attrs.get("lk.job_id")
                    span_room_id = attrs.get("room_id") or attrs.get("lk.room_sid") or attrs.get("lk.room_id")
                    if job_id and str(span_job_id or "") == job_id:
                        score = max(score, 100)
                    if room_id and str(span_room_id or "") == room_id:
                        score = max(score, 70)
                    span_room_name = attrs.get("lk.pii.room_name") or attrs.get("lk.room_name")
                    if room_name and str(span_room_name or "") == room_name:
                        score = max(score, 40)
                    if score >= 100:
                        break
        except OSError:
            continue

        if score:
            candidate = (score, trace_file.stat().st_mtime, session_dir.name)
            if best is None or candidate > best:
                best = candidate

    return best[2] if best else None


def store_livekit_report(data_dir: Path, trace_id: str, report: dict) -> Path:
    session_dir = get_session_dir(data_dir, trace_id)
    session_dir.mkdir(parents=True, exist_ok=True)
    destination = session_dir / "livekit_report.json"
    destination.write_text(json.dumps(report, indent=2))
    return destination
