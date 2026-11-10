
from finchvox.adapters.base import BaseTraceAdapter, SpanTypeConfig

SPAN_CONFIGS = {
    "conversation": SpanTypeConfig(
        display_name="CONVERSATION",
        category="root",
        css_class="bar-conversation",
    ),
    "turn": SpanTypeConfig(
        display_name="TURN",
        category="turn",
        css_class="bar-turn",
    ),
    "stt": SpanTypeConfig(
        display_name="STT",
        category="stt",
        css_class="bar-stt",
    ),
    "llm": SpanTypeConfig(
        display_name="LLM",
        category="llm",
        css_class="bar-llm",
    ),
    "tts": SpanTypeConfig(
        display_name="TTS",
        category="tts",
        css_class="bar-tts",
    ),
}

DEFAULT_CONFIG = SpanTypeConfig(
    display_name="OTHER",
    category="other",
    css_class="bar-default",
)


class PipecatAdapter(BaseTraceAdapter):
    def get_platform(self) -> str:
        return "pipecat"

    def get_span_config(self, span_name: str) -> SpanTypeConfig:
        config = SPAN_CONFIGS.get(span_name)
        if config:
            return config
        return SpanTypeConfig(
            display_name=span_name.upper(),
            category="other",
            css_class="bar-default",
        )

    def get_transcript(self, span: dict) -> str | None:
        return self._get_attribute(span, "transcript")

    def get_output_text(self, span: dict) -> str | None:
        text = self._get_attribute(span, "text")
        if text:
            return text
        return self._get_attribute(span, "output")

    def get_ttfb(self, span: dict) -> float | None:
        return self._get_attribute(span, "metrics.ttfb")

    def get_turn_span_names(self) -> list[str]:
        return ["turn"]
