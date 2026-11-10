import statistics
from dataclasses import asdict, dataclass
from typing import Any


@dataclass
class TTFBDataPoint:
    timestamp_ms: float
    relative_time_ms: float
    ttfb_ms: float
    span_id: str

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class TTFBStats:
    avg_ms: float
    min_ms: float
    max_ms: float
    p50_ms: float
    p95_ms: float
    count: int

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class TTFBSeries:
    service: str
    data_points: list[TTFBDataPoint]
    stats: TTFBStats

    def to_dict(self) -> dict:
        return {
            "service": self.service,
            "data_points": [dp.to_dict() for dp in self.data_points],
            "stats": self.stats.to_dict(),
        }


@dataclass
class UserBotLatencyDataPoint:
    timestamp_ms: float
    relative_time_ms: float
    latency_ms: float
    span_id: str

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class UserBotLatencySeries:
    data_points: list[UserBotLatencyDataPoint]
    stats: TTFBStats

    def to_dict(self) -> dict:
        return {
            "data_points": [dp.to_dict() for dp in self.data_points],
            "stats": self.stats.to_dict(),
        }


class Metrics:
    """Compute compact, UI-friendly latency series from normalized spans.

    The API stays backwards compatible with Pipecat while understanding current
    LiveKit Agents attributes (``lk.response.ttft``, ``lk.response.ttfb`` and
    ``lk.e2e_latency``) through the adapter's normalized representation.
    """

    CATEGORIES = ("stt", "llm", "tts")

    def __init__(
        self,
        spans: list[dict],
        report_messages: list[dict] | None = None,
        usage: list[dict] | None = None,
    ):
        self.spans = spans
        self.report_messages = report_messages or []
        self.usage = usage or []
        self._session_start_ms: float | None = None
        self._ttfb_series: dict[str, TTFBSeries] | None = None
        self._user_bot_latency_series: UserBotLatencySeries | None = None

    def _find_min_start_nano(self) -> int | None:
        min_start = None
        for span in self.spans:
            start = span.get("start_time_unix_nano")
            if not start:
                continue
            start_int = int(start)
            if min_start is None or start_int < min_start:
                min_start = start_int
        return min_start

    @property
    def session_start_ms(self) -> float:
        if self._session_start_ms is None:
            min_start = self._find_min_start_nano()
            self._session_start_ms = (min_start or 0) / 1_000_000
        return self._session_start_ms

    @staticmethod
    def _decode_numeric(value: dict[str, Any]) -> float | None:
        for key in ("double_value", "int_value"):
            if key in value:
                try:
                    return float(value[key])
                except (TypeError, ValueError):
                    return None
        return None

    def _get_attribute(self, span: dict, key: str) -> float | None:
        attrs = span.get("attributes", [])
        for attr in attrs:
            if attr.get("key") == key:
                return self._decode_numeric(attr.get("value", {}))
        return None

    def _compute_stats(self, values: list[float]) -> TTFBStats:
        if not values:
            return TTFBStats(avg_ms=0, min_ms=0, max_ms=0, p50_ms=0, p95_ms=0, count=0)

        sorted_vals = sorted(values)
        n = len(sorted_vals)
        p50_idx = int(n * 0.5)
        p95_idx = min(int(n * 0.95), n - 1)

        return TTFBStats(
            avg_ms=statistics.mean(values),
            min_ms=min(values),
            max_ms=max(values),
            p50_ms=sorted_vals[p50_idx],
            p95_ms=sorted_vals[p95_idx],
            count=n,
        )

    def _extract_ttfb_data_point(self, span: dict) -> TTFBDataPoint | None:
        normalized = span.get("_normalized", {})
        ttfb_seconds = normalized.get("ttfb_seconds")
        if ttfb_seconds is None:
            ttfb_seconds = self._get_attribute(span, "metrics.ttfb")
        if ttfb_seconds is None:
            return None

        start_nano = int(span.get("start_time_unix_nano", 0))
        timestamp_ms = start_nano / 1_000_000

        return TTFBDataPoint(
            timestamp_ms=timestamp_ms,
            relative_time_ms=timestamp_ms - self.session_start_ms,
            ttfb_ms=float(ttfb_seconds) * 1000,
            span_id=span.get("span_id_hex", ""),
        )

    @staticmethod
    def _metric_seconds(metrics: dict, *keys: str) -> float | None:
        for key in keys:
            value = metrics.get(key)
            if value is None or isinstance(value, bool):
                continue
            try:
                seconds = float(value)
            except (TypeError, ValueError):
                continue
            # A negative timing is a "not measured" placeholder, such as LiveKit's -1.
            if seconds >= 0:
                return seconds
        return None

    def _report_span_id(self, message: dict) -> str:
        span_ids = message.get("span_ids") or []
        return span_ids[0] if span_ids else ""

    def _report_ttfb_points(self) -> dict[str, list[TTFBDataPoint]]:
        result: dict[str, list[TTFBDataPoint]] = {c: [] for c in self.CATEGORIES}
        metric_keys = {
            "stt": ("transcription_delay",),
            "llm": ("llm_node_ttft", "llm_ttft"),
            "tts": ("tts_node_ttfb", "tts_ttfb"),
        }
        for message in self.report_messages:
            metrics = message.get("metrics") or {}
            timestamp_ms = float(message.get("timestamp") or 0) / 1_000_000
            if not timestamp_ms:
                continue
            for service, keys in metric_keys.items():
                seconds = self._metric_seconds(metrics, *keys)
                if seconds is None:
                    continue
                result[service].append(
                    TTFBDataPoint(
                        timestamp_ms=timestamp_ms,
                        relative_time_ms=timestamp_ms - self.session_start_ms,
                        ttfb_ms=seconds * 1000,
                        span_id=self._report_span_id(message),
                    )
                )
        return result

    def _collect_data_points(self) -> dict[str, list[TTFBDataPoint]]:
        series: dict[str, list[TTFBDataPoint]] = {c: [] for c in self.CATEGORIES}
        for span in self.spans:
            normalized = span.get("_normalized", {})
            category = normalized.get("category")
            # Hidden spans wrap a visible one carrying the same timing, such as
            # LiveKit's llm_node around llm_request; counting both doubles each point.
            if category not in self.CATEGORIES or normalized.get("hidden"):
                continue
            data_point = self._extract_ttfb_data_point(span)
            if data_point:
                series[category].append(data_point)

        report_series = self._report_ttfb_points()
        for service in self.CATEGORIES:
            if not series[service] and report_series[service]:
                series[service] = report_series[service]
        return series

    def _build_series(self, service: str, data_points: list[TTFBDataPoint]) -> TTFBSeries:
        data_points.sort(key=lambda dp: dp.timestamp_ms)
        stats = self._compute_stats([dp.ttfb_ms for dp in data_points])
        return TTFBSeries(service=service, data_points=data_points, stats=stats)

    def get_ttfb_series(self) -> dict[str, TTFBSeries]:
        if self._ttfb_series is not None:
            return self._ttfb_series

        series = self._collect_data_points()
        result = {
            service: self._build_series(service, data_points)
            for service, data_points in series.items()
            if data_points
        }
        self._ttfb_series = result
        return result

    def _extract_user_bot_latency_data_point(self, span: dict) -> UserBotLatencyDataPoint | None:
        # Pipecat legacy metric first, then LiveKit's end-to-end turn latency.
        latency_seconds = self._get_attribute(span, "turn.user_bot_latency_seconds")
        if latency_seconds is None:
            normalized = span.get("_normalized", {})
            latency_seconds = normalized.get("e2e_latency_seconds")
        if latency_seconds is None:
            latency_seconds = self._get_attribute(span, "lk.e2e_latency")
        if latency_seconds is None:
            return None

        start_nano = int(span.get("start_time_unix_nano", 0))
        timestamp_ms = start_nano / 1_000_000
        return UserBotLatencyDataPoint(
            timestamp_ms=timestamp_ms,
            relative_time_ms=timestamp_ms - self.session_start_ms,
            latency_ms=float(latency_seconds) * 1000,
            span_id=span.get("span_id_hex", ""),
        )

    def _report_latency_points(self) -> list[UserBotLatencyDataPoint]:
        points = []
        for message in self.report_messages:
            metrics = message.get("metrics") or {}
            seconds = self._metric_seconds(metrics, "e2e_latency")
            timestamp_ms = float(message.get("timestamp") or 0) / 1_000_000
            if seconds is None or not timestamp_ms:
                continue
            points.append(
                UserBotLatencyDataPoint(
                    timestamp_ms=timestamp_ms,
                    relative_time_ms=timestamp_ms - self.session_start_ms,
                    latency_ms=seconds * 1000,
                    span_id=self._report_span_id(message),
                )
            )
        return points

    def _collect_latency_data_points(self) -> list[UserBotLatencyDataPoint]:
        data_points = []
        for span in self.spans:
            if span.get("name") not in ("turn", "agent_turn"):
                continue
            data_point = self._extract_user_bot_latency_data_point(span)
            if data_point:
                data_points.append(data_point)
        return data_points or self._report_latency_points()

    def get_user_bot_latency_series(self) -> UserBotLatencySeries | None:
        if self._user_bot_latency_series is not None:
            return self._user_bot_latency_series

        data_points = self._collect_latency_data_points()
        if not data_points:
            return None

        data_points.sort(key=lambda dp: dp.timestamp_ms)
        stats = self._compute_stats([dp.latency_ms for dp in data_points])
        self._user_bot_latency_series = UserBotLatencySeries(
            data_points=data_points, stats=stats
        )
        return self._user_bot_latency_series

    def _turn_delay_spans(self, normalized_key: str) -> list[dict]:
        """Spans carrying ``normalized_key``, one per user turn.

        LiveKit puts the transcription and end-of-turn delays on the user turn and
        copies them onto the agent turn that answers it. The user turn is the one
        to count, since it exists even when the agent does not answer; agent turns
        are used only when no user turn has the value.
        """
        carrying = [
            span for span in self.spans
            if span.get("_normalized", {}).get(normalized_key) is not None
        ]
        user_turns = [span for span in carrying if span.get("name") == "user_turn"]
        return user_turns or carrying

    def _livekit_turn_breakdown(self) -> dict[str, dict]:
        mapping = {
            "transcription": "transcription_delay_seconds",
            "endpointing": "end_of_turn_delay_seconds",
            "turn_hook": "on_user_turn_completed_delay_seconds",
            "queue_wait": "queue_wait_seconds",
        }
        result: dict[str, dict] = {}
        for label, normalized_key in mapping.items():
            points = []
            values_ms = []
            for span in self._turn_delay_spans(normalized_key):
                value = span["_normalized"][normalized_key]
                start_nano = int(span.get("start_time_unix_nano", 0))
                timestamp_ms = start_nano / 1_000_000
                value_ms = float(value) * 1000
                values_ms.append(value_ms)
                points.append(
                    {
                        "timestamp_ms": timestamp_ms,
                        "relative_time_ms": timestamp_ms - self.session_start_ms,
                        "latency_ms": value_ms,
                        "span_id": span.get("span_id_hex", ""),
                    }
                )
            if points:
                result[label] = {
                    "data_points": points,
                    "stats": self._compute_stats(values_ms).to_dict(),
                }

        report_mapping = {
            "transcription": "transcription_delay",
            "endpointing": "end_of_turn_delay",
            "turn_hook": "on_user_turn_completed_delay",
            "playback": "playback_latency",
        }
        for label, metric_key in report_mapping.items():
            if label in result:
                continue
            points = []
            values_ms = []
            for message in self.report_messages:
                metrics = message.get("metrics") or {}
                seconds = self._metric_seconds(metrics, metric_key)
                timestamp_ms = float(message.get("timestamp") or 0) / 1_000_000
                if seconds is None or not timestamp_ms:
                    continue
                value_ms = seconds * 1000
                values_ms.append(value_ms)
                points.append(
                    {
                        "timestamp_ms": timestamp_ms,
                        "relative_time_ms": timestamp_ms - self.session_start_ms,
                        "latency_ms": value_ms,
                        "span_id": self._report_span_id(message),
                    }
                )
            if points:
                result[label] = {
                    "data_points": points,
                    "stats": self._compute_stats(values_ms).to_dict(),
                }
        return result

    def get_event_loop_blocks(self) -> list[dict]:
        """Moments the agent's event loop was blocked, a common cause of latency spikes."""
        blocks = []
        for span in self.spans:
            if span.get("name") != "event_loop_blocked":
                continue
            normalized = span.get("_normalized", {})
            duration = normalized.get("blocking_duration_seconds")
            if duration is None:
                continue
            timestamp_ms = int(span.get("start_time_unix_nano", 0)) / 1_000_000
            blocks.append(
                {
                    "timestamp_ms": timestamp_ms,
                    "relative_time_ms": timestamp_ms - self.session_start_ms,
                    "duration_ms": duration * 1000,
                    "severity": normalized.get("blocking_severity"),
                    "task": normalized.get("blocking_task"),
                    "span_id": span.get("span_id_hex", ""),
                }
            )
        return sorted(blocks, key=lambda block: block["timestamp_ms"])

    def get_job_dispatch(self) -> dict[str, float]:
        """How long LiveKit took to hand the job to this agent, in ms per stage."""
        for span in self.spans:
            stages = {
                key.removeprefix("job_").removesuffix("_latency_seconds"): value * 1000
                for key, value in span.get("_normalized", {}).items()
                if key.startswith("job_")
                and key.endswith("_latency_seconds")
                and value is not None
            }
            if stages:
                return stages
        return {}

    def to_dict(self) -> dict:
        series = self.get_ttfb_series()
        user_bot_latency = self.get_user_bot_latency_series()
        return {
            "series": {s: series[s].to_dict() for s in series},
            "services": list(series.keys()),
            "user_bot_latency": user_bot_latency.to_dict() if user_bot_latency else None,
            "turn_breakdown": self._livekit_turn_breakdown(),
            "event_loop_blocks": self.get_event_loop_blocks(),
            "job_dispatch": self.get_job_dispatch(),
            "usage": self.usage,
        }
