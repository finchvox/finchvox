from dataclasses import asdict, dataclass


@dataclass
class Message:
    role: str
    content: str
    timestamp: int
    was_interrupted: bool
    span_ids: list[str]

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class MessageAccumulator:
    role: str | None = None
    texts: list[str] = None
    span_ids: list[str] = None
    timestamp: int = 0
    first_span: dict | None = None

    def __post_init__(self):
        if self.texts is None:
            self.texts = []
        if self.span_ids is None:
            self.span_ids = []

    def has_content(self) -> bool:
        return bool(self.texts and self.role)

    def reset(self, role: str, text: str, span: dict):
        self.role = role
        self.texts = [text]
        self.span_ids = [span.get("span_id_hex")]
        self.timestamp = span.get("start_time_unix_nano", 0)
        self.first_span = span

    def append(self, text: str, span: dict):
        self.texts.append(text)
        self.span_ids.append(span.get("span_id_hex"))


class Conversation:
    def __init__(self, spans: list[dict]):
        self.spans = spans
        self._messages: list[Message] | None = None

    def _get_attribute(self, span: dict, key: str) -> str | bool | None:
        attrs = span.get("attributes", [])
        for attr in attrs:
            if attr.get("key") == key:
                value = attr.get("value", {})
                for value_key in ("string_value", "bool_value", "int_value", "double_value"):
                    if value_key in value:
                        return value[value_key]
                return None
        return None

    def _get_parent_turn(self, span: dict) -> dict | None:
        parent_id = span.get("parent_span_id_hex")
        if not parent_id:
            return None
        for s in self.spans:
            if s.get("span_id_hex") == parent_id:
                normalized = s.get("_normalized", {})
                if normalized.get("category") == "turn":
                    return s
        return None

    def _get_span_text(self, span: dict) -> str:
        normalized = span.get("_normalized", {})
        category = normalized.get("category")
        if category == "stt":
            return (
                normalized.get("transcript")
                or self._get_attribute(span, "transcript")
                or ""
            )
        elif category in ("tts", "llm"):
            return (
                normalized.get("output_text") or self._get_attribute(span, "text") or ""
            )
        return ""

    def _get_span_role(self, span: dict) -> str:
        normalized = span.get("_normalized", {})
        category = normalized.get("category")
        return "user" if category == "stt" else "assistant"

    def _get_interruption_status(self, span: dict | None) -> bool:
        if not span:
            return False
        turn = self._get_parent_turn(span)
        if not turn:
            return False
        return bool(
            self._get_attribute(turn, "turn.was_interrupted")
            or self._get_attribute(turn, "lk.interrupted")
            or turn.get("_normalized", {}).get("interrupted")
        )

    def _create_message_from_accumulator(
        self, acc: MessageAccumulator, was_interrupted: bool
    ) -> Message:
        return Message(
            role=acc.role,
            content=" ".join(acc.texts),
            timestamp=acc.timestamp,
            was_interrupted=was_interrupted and acc.role == "assistant",
            span_ids=acc.span_ids,
        )

    def _flush_accumulator(
        self, acc: MessageAccumulator, messages: list[Message], check_interruption: bool
    ):
        if not acc.has_content():
            return
        was_interrupted = (
            self._get_interruption_status(acc.first_span)
            if check_interruption
            else False
        )
        messages.append(self._create_message_from_accumulator(acc, was_interrupted))

    def _build_messages_from_spans(
        self, spans: list[dict], check_interruption: bool = True
    ) -> list[Message]:
        spans_sorted = sorted(spans, key=lambda s: s.get("start_time_unix_nano", 0))
        messages: list[Message] = []
        acc = MessageAccumulator()

        for span in spans_sorted:
            text = self._get_span_text(span)
            if not text:
                continue

            role = self._get_span_role(span)
            if role == acc.role:
                acc.append(text, span)
                continue

            self._flush_accumulator(acc, messages, check_interruption)
            acc.reset(role, text, span)

        self._flush_accumulator(acc, messages, check_interruption)
        return messages

    def _get_descendants(self, parent: dict) -> list[dict]:
        descendants = []
        pending = [parent.get("span_id_hex")]
        while pending:
            parent_id = pending.pop()
            if not parent_id:
                continue
            children = [
                span
                for span in self.spans
                if span.get("parent_span_id_hex") == parent_id
            ]
            descendants.extend(children)
            pending.extend(child.get("span_id_hex") for child in children)
        return descendants

    def _text_for_livekit_turn(self, turn: dict, role: str) -> tuple[str, list[str]]:
        normalized = turn.get("_normalized", {})
        direct_text = (
            normalized.get("transcript")
            if role == "user"
            else normalized.get("output_text")
        )
        if direct_text:
            return direct_text, [turn.get("span_id_hex")]

        descendants = self._get_descendants(turn)
        preferred_categories = ("stt",) if role == "user" else ("tts", "llm")
        for category in preferred_categories:
            matching = [
                span
                for span in descendants
                if span.get("_normalized", {}).get("category") == category
            ]
            texts = [self._get_span_text(span) for span in matching]
            texts = [text for text in texts if text]
            if texts:
                return " ".join(dict.fromkeys(texts)), [
                    turn.get("span_id_hex"),
                    *(span.get("span_id_hex") for span in matching),
                ]
        return "", [turn.get("span_id_hex")]

    def _build_livekit_turn_messages(self) -> list[Message]:
        messages = []
        livekit_turns = [
            span
            for span in self.spans
            if span.get("name") in ("user_turn", "agent_turn")
        ]
        for turn in sorted(
            livekit_turns, key=lambda span: span.get("start_time_unix_nano", 0)
        ):
            role = "user" if turn.get("name") == "user_turn" else "assistant"
            text, span_ids = self._text_for_livekit_turn(turn, role)
            if not text:
                continue
            messages.append(
                Message(
                    role=role,
                    content=text,
                    timestamp=turn.get("start_time_unix_nano", 0),
                    was_interrupted=(
                        role == "assistant"
                        and bool(turn.get("_normalized", {}).get("interrupted"))
                    ),
                    span_ids=[span_id for span_id in span_ids if span_id],
                )
            )
        return messages

    def get_messages(self) -> list[Message]:
        if self._messages is not None:
            return self._messages

        if any(
            span.get("_normalized", {}).get("platform") == "livekit"
            or span.get("name") in ("user_turn", "agent_turn")
            for span in self.spans
        ):
            livekit_messages = self._build_livekit_turn_messages()
            if livekit_messages:
                self._messages = livekit_messages
                return self._messages

        self._messages = self._build_messages_from_spans(self._message_spans())
        return self._messages

    def _message_spans(self) -> list[dict]:
        """Spans whose text makes up the messages, for sessions without turn spans.

        A reply is recorded twice: in full on the LLM span ("output") and as the
        spoken sentences on TTS spans ("text"). Use what was spoken, and fall back
        to the LLM text only when nothing was spoken, as in a text-only bot.
        """
        def category(span: dict) -> str | None:
            return span.get("_normalized", {}).get("category")

        spoken = any(category(s) == "tts" and self._get_span_text(s) for s in self.spans)
        wanted = ("stt", "tts") if spoken else ("stt", "llm")
        return [s for s in self.spans if category(s) in wanted]

    def to_dict_list(self) -> list[dict]:
        return [m.to_dict() for m in self.get_messages()]
