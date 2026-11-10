from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any


@dataclass
class SpanTypeConfig:
    display_name: str
    category: str
    css_class: str
    sort_order: int = 999
    hidden: bool = False


class BaseTraceAdapter(ABC):
    @abstractmethod
    def get_platform(self) -> str:
        pass

    @abstractmethod
    def get_span_config(self, span_name: str) -> SpanTypeConfig:
        pass

    @abstractmethod
    def get_transcript(self, span: dict) -> str | None:
        pass

    @abstractmethod
    def get_output_text(self, span: dict) -> str | None:
        pass

    @abstractmethod
    def get_ttfb(self, span: dict) -> float | None:
        pass

    @abstractmethod
    def get_turn_span_names(self) -> list[str]:
        pass

    @staticmethod
    def _decode_otel_value(value: dict[str, Any]) -> Any:
        """Decode the JSON representation of an OpenTelemetry AnyValue.

        Finchvox stores protobuf spans as JSON. Checking keys rather than using an
        ``or`` chain is important here because ``False``, ``0`` and ``0.0`` are
        perfectly valid telemetry values.
        """
        for key in ("string_value", "bool_value", "int_value", "double_value", "bytes_value"):
            if key in value:
                return value[key]

        if "array_value" in value:
            values = value.get("array_value", {}).get("values", [])
            return [BaseTraceAdapter._decode_otel_value(item) for item in values]

        if "kvlist_value" in value:
            pairs = value.get("kvlist_value", {}).get("values", [])
            return {
                pair.get("key", ""): BaseTraceAdapter._decode_otel_value(pair.get("value", {}))
                for pair in pairs
            }
        return None

    def _get_attribute(self, span: dict, key: str) -> Any:
        attrs = span.get("attributes", [])
        for attr in attrs:
            if attr.get("key") == key:
                return self._decode_otel_value(attr.get("value", {}))
        return None

    def _first_attribute(self, span: dict, *keys: str) -> Any:
        for key in keys:
            value = self._get_attribute(span, key)
            if value is not None:
                return value
        return None

    def _is_error(self, span: dict) -> bool:
        status = span.get("status") or {}
        code = status.get("code")
        if code in (2, "STATUS_CODE_ERROR", "ERROR"):
            return True
        if self._get_attribute(span, "error.type") is not None:
            return True
        for event in span.get("events", []):
            if event.get("name") == "exception":
                return True
        return False

    def _error_message(self, span: dict) -> str | None:
        status = span.get("status") or {}
        if status.get("message"):
            return str(status["message"])
        value = self._first_attribute(span, "exception.message", "error.message", "error.type")
        if value is not None:
            return str(value)
        for event in span.get("events", []):
            if event.get("name") != "exception":
                continue
            for attr in event.get("attributes", []):
                if attr.get("key") in ("exception.message", "exception.type"):
                    value = self._decode_otel_value(attr.get("value", {}))
                    if value is not None:
                        return str(value)
        return None

    def normalize_span(self, span: dict) -> dict:
        span_name = span.get("name", "")
        config = self.get_span_config(span_name)

        span["_normalized"] = {
            "platform": self.get_platform(),
            "display_name": config.display_name,
            "category": config.category,
            "css_class": config.css_class,
            "sort_order": config.sort_order,
            "hidden": config.hidden,
            "transcript": self.get_transcript(span),
            "output_text": self.get_output_text(span),
            "ttfb_seconds": self.get_ttfb(span),
            "is_error": self._is_error(span),
            "error_message": self._error_message(span),
        }
        return span

    def normalize_spans(self, spans: list[dict]) -> list[dict]:
        return [self.normalize_span(span) for span in spans]
