"""Helpers for turning a local LiveKit ``SessionReport`` into replay UI data.

LiveKit's OpenTelemetry spans are the source of truth for the trace waterfall,
but a SessionReport carries richer conversation items and per-message metrics.
This module keeps that data local and presents it in the same timestamp domain as
OTel (Unix nanoseconds) so the waveform, transcript, traces, and logs can share a
single playhead.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any


def load_livekit_report(session_dir: Path) -> dict[str, Any] | None:
    """Load a stored LiveKit SessionReport, returning ``None`` when unavailable."""
    report_path = session_dir / "livekit_report.json"
    if not report_path.exists():
        return None
    try:
        report = json.loads(report_path.read_text())
    except (OSError, json.JSONDecodeError):
        return None
    return report if isinstance(report, dict) else None


def timestamp_to_unix_nano(value: Any) -> int:
    """Convert LiveKit report timestamps to Unix nanoseconds.

    Current LiveKit chat items use epoch seconds as a float. The defensive
    handling below also accepts milliseconds, microseconds, nanoseconds, and ISO
    timestamps so imported reports from older/newer SDKs remain usable.
    """
    if value is None or isinstance(value, bool):
        return 0

    if isinstance(value, str):
        text = value.strip()
        if not text:
            return 0
        try:
            value = float(text)
        except ValueError:
            try:
                parsed = datetime.fromisoformat(text)
            except ValueError:
                return 0
            return int(parsed.timestamp() * 1_000_000_000)

    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return 0

    magnitude = abs(numeric)
    if magnitude >= 1e17:  # nanoseconds
        return int(numeric)
    if magnitude >= 1e14:  # microseconds
        return int(numeric * 1_000)
    if magnitude >= 1e11:  # milliseconds
        return int(numeric * 1_000_000)
    return int(numeric * 1_000_000_000)  # seconds


def _text_content(content: Any) -> str:
    if isinstance(content, str):
        return content.strip()
    if not isinstance(content, list):
        return ""

    parts: list[str] = []
    for item in content:
        if isinstance(item, str) and item.strip():
            parts.append(item.strip())
        elif isinstance(item, dict):
            text = item.get("text")
            if isinstance(text, str) and text.strip():
                parts.append(text.strip())
    return "\n".join(parts)


def _chat_items(report: dict[str, Any]) -> list[dict[str, Any]]:
    history = report.get("chat_history")
    if isinstance(history, dict):
        items = history.get("items", [])
    elif isinstance(history, list):
        items = history
    else:
        items = []
    return [item for item in items if isinstance(item, dict)]


def _pair_span_ids(
    report_messages: list[dict[str, Any]], trace_messages: list[dict[str, Any]]
) -> None:
    """Pair report messages with OTel-derived messages by role and order.

    A SessionReport has the best transcript/timing data, while the span-derived
    messages know which waterfall spans should open in the inspector. Pairing
    them preserves both without relying on fragile text equality.
    """
    queues: dict[str, list[dict[str, Any]]] = {"user": [], "assistant": []}
    for message in trace_messages:
        role = message.get("role")
        if role in queues:
            queues[role].append(message)

    indices = {"user": 0, "assistant": 0}
    for message in report_messages:
        role = message.get("role")
        if role not in queues:
            continue
        index = indices[role]
        if index >= len(queues[role]):
            continue
        trace_message = queues[role][index]
        indices[role] += 1
        message["span_ids"] = list(trace_message.get("span_ids") or [])


def report_messages(
    report: dict[str, Any], trace_messages: list[dict[str, Any]] | None = None
) -> list[dict[str, Any]]:
    """Return user/assistant messages suitable for the synchronized transcript."""
    messages: list[dict[str, Any]] = []
    for item in _chat_items(report):
        if item.get("type") != "message":
            continue
        role = item.get("role")
        if role not in ("user", "assistant"):
            continue
        content = _text_content(item.get("content"))
        if not content:
            continue
        messages.append(
            {
                "id": item.get("id"),
                "role": role,
                "content": content,
                "timestamp": timestamp_to_unix_nano(item.get("created_at")),
                "was_interrupted": bool(item.get("interrupted")),
                "transcript_confidence": item.get("transcript_confidence"),
                "metrics": item.get("metrics") if isinstance(item.get("metrics"), dict) else {},
                "span_ids": [],
                "source": "livekit_session_report",
            }
        )

    messages.sort(key=lambda message: int(message.get("timestamp") or 0))
    if trace_messages:
        _pair_span_ids(messages, trace_messages)
    return messages


def _report_span(
    *,
    event_id: str,
    name: str,
    timestamp: int,
    display_name: str,
    category: str,
    event_kind: str,
    attributes: dict[str, Any],
    is_error: bool = False,
    error_message: str | None = None,
    primary_text: str | None = None,
) -> dict[str, Any]:
    normalized = {
        "platform": "livekit",
        "display_name": display_name,
        "category": category,
        "event_kind": event_kind,
        "css_class": f"bar-{category}",
        "is_error": is_error,
        "error_message": error_message,
        "report_only": True,
    }
    if primary_text:
        if category == "tool":
            normalized["tool_output"] = primary_text
        else:
            normalized["output_text"] = primary_text
    if category == "tool":
        normalized.update(
            {
                "tool_name": attributes.get("tool.name"),
                "tool_call_id": attributes.get("tool.call_id"),
                "tool_arguments": attributes.get("tool.arguments"),
                "tool_output": attributes.get("tool.output") or primary_text,
            }
        )
    if category == "handoff":
        normalized.update(
            {
                "previous_agent_label": attributes.get("handoff.old_agent_id"),
                "agent_label": attributes.get("handoff.new_agent_id"),
            }
        )

    otel_attributes = []
    for key, value in attributes.items():
        if value is None:
            continue
        if isinstance(value, bool):
            encoded = {"bool_value": value}
        elif isinstance(value, int):
            encoded = {"int_value": value}
        elif isinstance(value, float):
            encoded = {"double_value": value}
        elif isinstance(value, (dict, list)):
            encoded = {"string_value": json.dumps(value, ensure_ascii=False)}
        else:
            encoded = {"string_value": str(value)}
        otel_attributes.append({"key": key, "value": encoded})

    end = timestamp + 1 if timestamp else 1
    return {
        "name": name,
        "span_id_hex": f"report-{event_id}",
        "parent_span_id_hex": "",
        "start_time_unix_nano": timestamp,
        "end_time_unix_nano": end,
        "attributes": otel_attributes,
        "events": [],
        "_normalized": normalized,
    }


def report_events(report: dict[str, Any]) -> list[dict[str, Any]]:
    """Return tool, handoff, and config events from ``chat_history``.

    Tool call/output items are combined into one replay event. This gives the
    transcript the same high-level rows users expect from Agent Insights even if
    OpenTelemetry PII/content attributes were disabled.
    """
    items = _chat_items(report)
    outputs = {
        item.get("call_id"): item
        for item in items
        if item.get("type") == "function_call_output" and item.get("call_id")
    }
    events: list[dict[str, Any]] = []

    for index, item in enumerate(items):
        item_type = item.get("type")
        timestamp = timestamp_to_unix_nano(item.get("created_at"))
        event_id = str(item.get("id") or item.get("call_id") or f"{item_type}-{index}")

        if item_type == "function_call":
            output = outputs.get(item.get("call_id"), {})
            is_error = bool(output.get("is_error"))
            output_text = output.get("output")
            attrs = {
                "tool.name": item.get("name"),
                "tool.call_id": item.get("call_id"),
                "tool.arguments": item.get("arguments"),
                "tool.output": output_text,
                "tool.is_error": is_error,
                "tool.group_id": item.get("group_id"),
            }
            title = f"Tool call: {item.get('name') or 'tool'}"
            span = _report_span(
                event_id=event_id,
                name="function_tool",
                timestamp=timestamp,
                display_name=item.get("name") or "TOOL",
                category="tool",
                event_kind="tool",
                attributes=attrs,
                is_error=is_error,
                error_message=str(output_text) if is_error and output_text is not None else None,
                primary_text=str(output_text) if output_text is not None else None,
            )
            events.append(
                {
                    "id": event_id,
                    "kind": "error" if is_error else "tool",
                    "timestamp": timestamp,
                    "title": title,
                    "subtitle": str(item.get("call_id") or ""),
                    "span": span,
                    "source": "livekit_session_report",
                }
            )
            continue

        if item_type == "agent_handoff":
            old_agent = item.get("old_agent_id")
            new_agent = item.get("new_agent_id")
            attrs = {
                "handoff.old_agent_id": old_agent,
                "handoff.new_agent_id": new_agent,
            }
            span = _report_span(
                event_id=event_id,
                name="update_agent",
                timestamp=timestamp,
                display_name="AGENT_HANDOFF",
                category="handoff",
                event_kind="handoff",
                attributes=attrs,
            )
            events.append(
                {
                    "id": event_id,
                    "kind": "handoff",
                    "timestamp": timestamp,
                    "title": "Agent handoff",
                    "subtitle": " → ".join(str(v) for v in (old_agent, new_agent) if v),
                    "span": span,
                    "source": "livekit_session_report",
                }
            )
            continue

        if item_type == "agent_config_update":
            attrs = {
                "agent.instructions": item.get("instructions"),
                "agent.tools_added": item.get("tools_added"),
                "agent.tools_removed": item.get("tools_removed"),
            }
            span = _report_span(
                event_id=event_id,
                name="agent_config_update",
                timestamp=timestamp,
                display_name="AGENT_CONFIG_UPDATE",
                category="handoff",
                event_kind="config",
                attributes=attrs,
                primary_text=item.get("instructions"),
            )
            events.append(
                {
                    "id": event_id,
                    "kind": "config",
                    "timestamp": timestamp,
                    "title": "Agent configuration updated",
                    "subtitle": "instructions / tools changed",
                    "span": span,
                    "source": "livekit_session_report",
                }
            )

    events.sort(key=lambda event: int(event.get("timestamp") or 0))
    return events


_USAGE_KINDS = {
    "llm_usage": "llm",
    "tts_usage": "tts",
    "stt_usage": "stt",
    "interruption_usage": "interruption",
    "eot_usage": "turn detector",
}


def report_usage(report: dict[str, Any]) -> list[dict[str, Any]]:
    """Return what each model was used for in the session (tokens, characters, seconds).

    LiveKit's report lists one entry per model and provider, with unused fields left
    out. Prices change often, so Finchvox shows the amounts rather than a cost.
    """
    usage = report.get("usage")
    if not isinstance(usage, list):
        return []

    rows = []
    for item in usage:
        if not isinstance(item, dict):
            continue
        amounts = {
            key: value
            for key, value in item.items()
            if key not in ("type", "provider", "model")
            and isinstance(value, int | float)
            and not isinstance(value, bool)
            and value
        }
        rows.append(
            {
                "kind": _USAGE_KINDS.get(item.get("type"), str(item.get("type") or "")),
                "provider": item.get("provider") or "",
                "model": item.get("model") or "",
                "amounts": amounts,
            }
        )
    return rows


def report_metric_messages(report: dict[str, Any]) -> list[dict[str, Any]]:
    """Return only report messages that carry LiveKit per-message metrics."""
    return [message for message in report_messages(report) if message.get("metrics")]
