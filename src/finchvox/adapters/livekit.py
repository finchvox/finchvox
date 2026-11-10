import json
from typing import Any

from finchvox.adapters.base import BaseTraceAdapter, SpanTypeConfig

# Span names created by livekit-agents 1.8.x (checked against the 1.8.11 source).
# LiveKit support starts at 1.8.9, so older span and attribute names are not kept.
_LIFECYCLE_SPANS = (
    "job_entrypoint",
    "job_shutdown",
    "shutdown_callback",
    "session_close",
    "session_end_upload",
    "on_session_end",
    "on_enter",
    "on_exit",
    "on_user_turn_completed",
    "start_agent_activity",
    "pause_agent_activity",
    "resume_agent_activity",
    "drain_agent_activity",
    "room_disconnect",
    "rpc_call",
    "rpc_handler",
)

SPAN_CONFIGS = {
    "agent_session": SpanTypeConfig("AGENT_SESSION", "root", "bar-conversation", 1),
    "session_start": SpanTypeConfig("SESSION_START", "root", "bar-conversation", 1),
    "agent_turn": SpanTypeConfig("AGENT_TURN", "turn", "bar-turn", 2),
    "tts_request": SpanTypeConfig("TTS", "tts", "bar-tts", 3),
    "tts_fallback_adapter": SpanTypeConfig("TTS_FALLBACK", "other", "bar-default", 3),
    "tts_stream_adapter": SpanTypeConfig("TTS_STREAM_ADAPTER", "other", "bar-default", 3),
    "agent_speaking": SpanTypeConfig("AGENT_SPEAKING", "tts", "bar-tts", 4),
    "tts_node": SpanTypeConfig("TTS_NODE", "tts", "bar-tts", 4, hidden=True),
    "tts_request_run": SpanTypeConfig("TTS_REQUEST_RUN", "tts", "bar-tts", 6, hidden=True),
    "user_turn": SpanTypeConfig("USER_TURN", "stt", "bar-stt", 7),
    "user_speaking": SpanTypeConfig("USER_SPEAKING", "stt", "bar-stt", 8),
    "eou_wait": SpanTypeConfig("END_OF_UTTERANCE", "stt", "bar-stt", 8),
    "eou_detection": SpanTypeConfig("EOU_DETECTION", "stt", "bar-stt", 8),
    "keyterm_detection": SpanTypeConfig("KEYTERM_DETECTION", "stt", "bar-stt", 8),
    "llm_node": SpanTypeConfig("LLM_NODE", "llm", "bar-llm", 9, hidden=True),
    "realtime_inference": SpanTypeConfig("REALTIME_INFERENCE", "llm", "bar-llm", 9),
    "llm_request": SpanTypeConfig("LLM", "llm", "bar-llm", 10),
    "llm_fallback_adapter": SpanTypeConfig("LLM_FALLBACK", "other", "bar-default", 10),
    "llm_request_run": SpanTypeConfig("LLM_REQUEST_RUN", "llm", "bar-llm", 11, hidden=True),
    "function_tool": SpanTypeConfig("TOOL", "tool", "bar-tool", 12),
    "update_agent": SpanTypeConfig("AGENT_HANDOFF", "handoff", "bar-handoff", 13),
    "amd": SpanTypeConfig("ANSWERING_MACHINE_DETECTION", "other", "bar-default", 14),
    "room_connect": SpanTypeConfig("ROOM_CONNECT", "transport", "bar-transport", 20),
    "wait_for_audio_track": SpanTypeConfig(
        "WAIT_FOR_AUDIO_TRACK", "transport", "bar-transport", 20
    ),
    # Red bar: an event loop blocked for this long is the usual cause of a latency spike.
    "event_loop_blocked": SpanTypeConfig("EVENT_LOOP_BLOCKED", "other", "bar-error", 21),
    **{
        name: SpanTypeConfig(name.upper(), "lifecycle", "bar-default", 30, hidden=True)
        for name in _LIFECYCLE_SPANS
    },
}

# Span names that identify a trace as LiveKit's. Lifecycle names such as ``on_enter``
# are generic enough to appear in other frameworks, so they do not count.
JOB_LATENCY_STAGES = ("accept", "assignment", "launch", "entrypoint", "dispatch")

LIVEKIT_SPAN_NAMES = frozenset(
    name for name, config in SPAN_CONFIGS.items() if config.category != "lifecycle"
)

DEFAULT_CONFIG = SpanTypeConfig("OTHER", "other", "bar-default")


class LiveKitAdapter(BaseTraceAdapter):
    def get_platform(self) -> str:
        return "livekit"

    def get_span_config(self, span_name: str) -> SpanTypeConfig:
        config = SPAN_CONFIGS.get(span_name)
        if config:
            return config
        return SpanTypeConfig(
            display_name=(span_name or "other").upper().replace("-", "_"),
            category="other",
            css_class="bar-default",
        )

    @staticmethod
    def _coerce_text(value: Any) -> str | None:
        if value is None:
            return None
        if isinstance(value, str):
            return value if value.strip() else None
        if isinstance(value, (int, float, bool)):
            return str(value)
        return None

    @staticmethod
    def _extract_text_from_json(value: Any) -> str | None:
        """Best-effort extraction from GenAI messages/chat context JSON."""
        if value is None:
            return None
        if isinstance(value, str):
            try:
                value = json.loads(value)
            except (json.JSONDecodeError, TypeError):
                return value if value.strip() else None

        texts: list[str] = []

        def walk(node: Any) -> None:
            if isinstance(node, dict):
                # Common OTel GenAI and LiveKit chat-message shapes.
                for key in ("text", "content", "message"):
                    candidate = node.get(key)
                    if isinstance(candidate, str) and candidate.strip():
                        texts.append(candidate.strip())
                for key, child in node.items():
                    if key not in ("text", "content", "message"):
                        walk(child)
            elif isinstance(node, list):
                for child in node:
                    walk(child)

        walk(value)
        if not texts:
            return None
        # De-duplicate values caused by nested wrappers while keeping order.
        return "\n".join(dict.fromkeys(texts))

    def get_transcript(self, span: dict) -> str | None:
        value = self._first_attribute(
            span,
            "lk.pii.user_transcript",
            "lk.pii.user_input",
            "lk.pii.amd.transcript",
        )
        text = self._coerce_text(value)
        if text:
            return text

        return self._extract_text_from_json(
            self._first_attribute(span, "gen_ai.input.messages")
        )

    def get_output_text(self, span: dict) -> str | None:
        value = self._first_attribute(span, "lk.pii.response.text", "lk.pii.input_text")
        text = self._coerce_text(value)
        if text:
            return text

        for key in ("gen_ai.output.messages", "lk.pii.chat_ctx"):
            text = self._extract_text_from_json(self._get_attribute(span, key))
            if text:
                return text
        return None

    @staticmethod
    def _as_float(value: Any) -> float | None:
        if value is None or isinstance(value, bool):
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    def _metric_from_json(self, span: dict, attribute: str, *keys: str) -> float | None:
        metrics_json = self._get_attribute(span, attribute)
        if metrics_json is None:
            return None
        try:
            metrics = json.loads(metrics_json) if isinstance(metrics_json, str) else metrics_json
        except (json.JSONDecodeError, TypeError):
            return None
        if not isinstance(metrics, dict):
            return None
        for key in keys:
            value = self._as_float(metrics.get(key))
            if value is not None:
                return value
        return None

    def get_ttfb(self, span: dict) -> float | None:
        value = self._reported_ttfb(span)
        # LiveKit reports -1 when no first token or byte arrived (llm.py, gpt_live.py).
        return value if value is not None and value >= 0 else None

    def _reported_ttfb(self, span: dict) -> float | None:
        span_name = span.get("name", "")
        category = self.get_span_config(span_name).category

        if category == "llm":
            value = self._first_attribute(
                span,
                "lk.response.ttft",
                "gen_ai.response.time_to_first_chunk",
            )
            parsed = self._as_float(value)
            if parsed is not None:
                return parsed
            parsed = self._metric_from_json(span, "lk.llm_metrics", "ttft", "ttfb")
            if parsed is not None:
                return parsed
            parsed = self._metric_from_json(span, "lk.realtime_model_metrics", "ttft", "ttfb")
            if parsed is not None:
                return parsed

        if category == "tts":
            parsed = self._as_float(self._get_attribute(span, "lk.response.ttfb"))
            if parsed is not None:
                return parsed
            parsed = self._metric_from_json(span, "lk.tts_metrics", "ttfb", "ttft")
            if parsed is not None:
                return parsed

        if category == "stt" or span_name in ("user_turn", "user_speaking"):
            return self._as_float(self._get_attribute(span, "lk.transcription_delay"))

        return None

    def _is_error(self, span: dict) -> bool:
        if super()._is_error(span):
            return True
        return self._get_attribute(span, "lk.function_tool.is_error") is True

    def normalize_span(self, span: dict) -> dict:
        span = super().normalize_span(span)
        normalized = span["_normalized"]
        span_name = span.get("name", "")

        normalized.update(
            {
                "event_kind": (
                    "tool"
                    if span_name == "function_tool"
                    else "handoff"
                    if span_name == "update_agent"
                    else "span"
                ),
                "interrupted": bool(self._get_attribute(span, "lk.interrupted")),
                "tool_name": self._first_attribute(
                    span, "gen_ai.tool.name", "lk.function_tool.name"
                ),
                "tool_call_id": self._first_attribute(
                    span, "gen_ai.tool.call.id", "lk.function_tool.id"
                ),
                "tool_arguments": self._first_attribute(
                    span, "gen_ai.tool.call.arguments", "lk.pii.function_tool.arguments"
                ),
                "tool_output": self._first_attribute(
                    span, "gen_ai.tool.call.result", "lk.pii.function_tool.output"
                ),
                "agent_label": self._first_attribute(
                    span, "lk.agent_label", "gen_ai.agent.name"
                ),
                "previous_agent_label": self._get_attribute(span, "lk.previous_agent_label"),
                "generation_id": self._get_attribute(span, "lk.generation_id"),
                "parent_generation_id": self._get_attribute(span, "lk.parent_generation_id"),
                "generation_count": self._get_attribute(span, "lk.generation_count"),
                "speech_id": self._get_attribute(span, "lk.speech_id"),
                "agent_name": self._get_attribute(span, "lk.agent_name"),
                "room_name": self._get_attribute(span, "lk.pii.room_name"),
                "room_sid": self._first_attribute(span, "room_id", "lk.room_sid"),
                "job_id": self._first_attribute(span, "job_id", "lk.job_id"),
                "participant_id": self._get_attribute(span, "lk.participant_id"),
                "participant_identity": self._get_attribute(span, "lk.pii.participant_identity"),
                "participant_kind": self._get_attribute(span, "lk.participant_kind"),
                "cloud_agent_id": self._get_attribute(span, "lk.cloud_agent_id"),
                "deployment_id": self._get_attribute(span, "lk.deployment_id"),
                "provider_request_ids": self._get_attribute(span, "lk.provider_request_ids"),
                "provider": self._get_attribute(span, "gen_ai.provider.name"),
                "request_model": self._get_attribute(span, "gen_ai.request.model"),
                "response_model": self._get_attribute(span, "gen_ai.response.model"),
                "input_tokens": self._get_attribute(span, "gen_ai.usage.input_tokens"),
                "output_tokens": self._get_attribute(span, "gen_ai.usage.output_tokens"),
                "finish_reasons": self._get_attribute(span, "gen_ai.response.finish_reasons"),
                "retry_count": self._get_attribute(span, "lk.retry_count"),
                "transcript_confidence": self._as_float(self._get_attribute(span, "lk.transcript_confidence")),
                "interruption_source": self._get_attribute(span, "lk.interruption.source"),
                "playout_position_seconds": self._as_float(self._get_attribute(span, "lk.playout.position")),
                "eou_probability": self._as_float(self._get_attribute(span, "lk.eou.probability")),
                "eou_endpointing_delay_seconds": self._as_float(self._get_attribute(span, "lk.eou.endpointing_delay")),
                "eou_detection_delay_seconds": self._as_float(self._get_attribute(span, "lk.eou.detection_delay")),
                "eou_outcome": self._get_attribute(span, "lk.eou.outcome"),
                "eou_source": self._get_attribute(span, "lk.eou.source"),
                "fallback_label": self._get_attribute(span, "lk.fallback.label"),
                "fallback_index": self._get_attribute(span, "lk.fallback.index"),
                "fallback_recovery": self._get_attribute(span, "lk.fallback.recovery"),
                "tts_label": self._get_attribute(span, "lk.tts.label"),
                "is_interruption": self._get_attribute(span, "lk.is_interruption"),
                "interruption_probability": self._as_float(
                    self._get_attribute(span, "lk.interruption.probability")
                ),
                "blocking_duration_seconds": self._as_float(
                    self._get_attribute(span, "lk.blocking.duration")
                ),
                "blocking_severity": self._get_attribute(span, "lk.blocking.severity"),
                "blocking_task": self._get_attribute(span, "lk.blocking.task"),
                **{
                    f"job_{name}_latency_seconds": self._as_float(
                        self._get_attribute(span, f"lk.job.{name}_latency")
                    )
                    for name in JOB_LATENCY_STAGES
                },
                "e2e_latency_seconds": self._as_float(self._get_attribute(span, "lk.e2e_latency")),
                "transcription_delay_seconds": self._as_float(self._get_attribute(span, "lk.transcription_delay")),
                "end_of_turn_delay_seconds": self._as_float(self._get_attribute(span, "lk.end_of_turn_delay")),
                "on_user_turn_completed_delay_seconds": self._as_float(
                    self._get_attribute(span, "lk.on_user_turn_completed_delay")
                ),
                "queue_wait_seconds": self._as_float(self._get_attribute(span, "lk.speech.queue_wait")),
            }
        )
        if span_name == "user_turn" and normalized["end_of_turn_delay_seconds"] == 0:
            # LiveKit writes 0 for both delays when it could not time the turn
            # (audio_recognition.py, "or 0"). A measured end-of-turn delay is never
            # exactly 0, while a measured transcription delay can be.
            normalized["transcription_delay_seconds"] = None
            normalized["end_of_turn_delay_seconds"] = None
            normalized["ttfb_seconds"] = None
        normalized["is_error"] = self._is_error(span)
        if normalized["is_error"] and normalized.get("category") == "lifecycle":
            # Lifecycle spans are hidden to keep the timeline readable, but a failing
            # ``on_enter`` or shutdown callback must stay visible.
            normalized["hidden"] = False
        return span

    def get_turn_span_names(self) -> list[str]:
        return ["user_turn", "agent_turn"]
