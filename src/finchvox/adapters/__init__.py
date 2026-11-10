from finchvox.adapters.base import BaseTraceAdapter, SpanTypeConfig
from finchvox.adapters.livekit import LIVEKIT_SPAN_NAMES, LiveKitAdapter
from finchvox.adapters.pipecat import PipecatAdapter


def detect_platform(spans: list[dict]) -> str:
    for span in spans:
        scope = span.get("instrumentation_scope", {})
        scope_name = scope.get("name", "")
        if scope_name == "livekit-agents":
            return "livekit"

        if span.get("name") in LIVEKIT_SPAN_NAMES:
            return "livekit"

        attrs = span.get("attributes", [])
        for attr in attrs:
            key = attr.get("key", "")
            if key.startswith("lk."):
                return "livekit"

    return "pipecat"


def get_adapter(spans: list[dict]) -> BaseTraceAdapter:
    platform = detect_platform(spans)
    if platform == "livekit":
        return LiveKitAdapter()
    return PipecatAdapter()


__all__ = [
    "BaseTraceAdapter",
    "LiveKitAdapter",
    "PipecatAdapter",
    "SpanTypeConfig",
    "detect_platform",
    "get_adapter",
]
