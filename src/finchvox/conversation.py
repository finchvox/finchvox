from dataclasses import dataclass, asdict


@dataclass
class TurnLatency:
    user_turn_seconds: float | None = None
    stt_ttfb: float | None = None
    llm_ttfb: float | None = None
    function_call_seconds: float | None = None
    text_aggregation_seconds: float | None = None
    tts_ttfb: float | None = None
    user_bot_latency_seconds: float | None = None

    def to_dict(self) -> dict:
        return {k: v for k, v in asdict(self).items() if v is not None}

    def has_data(self) -> bool:
        return any(v is not None for v in asdict(self).values())


@dataclass
class FunctionCall:
    name: str
    start_time_unix_nano: int
    end_time_unix_nano: int
    duration_seconds: float
    attributes: dict

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "start_time_unix_nano": self.start_time_unix_nano,
            "end_time_unix_nano": self.end_time_unix_nano,
            "duration_seconds": self.duration_seconds,
            "attributes": self.attributes,
        }


@dataclass
class Message:
    role: str
    content: str
    timestamp: int
    was_interrupted: bool
    span_ids: list[str]
    chunks: list[dict] | None = None
    latency: TurnLatency | None = None
    turn_events: list[dict] | None = None

    def to_dict(self) -> dict:
        d = asdict(self)
        if self.latency and self.latency.has_data():
            d["latency"] = self.latency.to_dict()
        else:
            d.pop("latency", None)
        if not self.chunks:
            d.pop("chunks", None)
        if not self.turn_events:
            d.pop("turn_events", None)
        return d


@dataclass
class MessageAccumulator:
    role: str | None = None
    texts: list[str] = None
    span_ids: list[str] = None
    timestamp: int = 0
    first_span: dict | None = None
    chunks: list[dict] = None

    def __post_init__(self):
        if self.texts is None:
            self.texts = []
        if self.span_ids is None:
            self.span_ids = []
        if self.chunks is None:
            self.chunks = []

    def has_content(self) -> bool:
        return bool(self.texts and self.role)

    def reset(
        self,
        role: str,
        text: str,
        span: dict,
        heard_status: str | None = None,
        gap_seconds: float | None = None,
    ):
        self.role = role
        self.texts = [text]
        self.span_ids = [span.get("span_id_hex")]
        self.timestamp = span.get("start_time_unix_nano", 0)
        self.first_span = span
        if heard_status:
            chunk = {"text": text, "heard_status": heard_status}
            if gap_seconds is not None and gap_seconds > 0.5:
                chunk["gap_seconds"] = round(gap_seconds, 1)
            self.chunks = [chunk]
        else:
            self.chunks = []

    def append(
        self,
        text: str,
        span: dict,
        heard_status: str | None = None,
        gap_seconds: float | None = None,
    ):
        self.texts.append(text)
        self.span_ids.append(span.get("span_id_hex"))
        if heard_status:
            chunk = {"text": text, "heard_status": heard_status}
            if gap_seconds is not None and gap_seconds > 0.5:
                chunk["gap_seconds"] = round(gap_seconds, 1)
            self.chunks.append(chunk)


@dataclass
class Turn:
    turn_number: int
    messages: list[Message]
    latency: TurnLatency | None = None
    events: list[dict] | None = None
    user_bot_latency_seconds: float | None = None
    function_calls: list[FunctionCall] | None = None

    def to_dict(self) -> dict:
        d = {
            "turn_number": self.turn_number,
            "messages": [m.to_dict() for m in self.messages],
        }
        if self.latency and self.latency.has_data():
            d["latency"] = self.latency.to_dict()
        if self.events:
            d["events"] = self.events
        if self.user_bot_latency_seconds is not None:
            d["user_bot_latency_seconds"] = self.user_bot_latency_seconds
        if self.function_calls:
            d["function_calls"] = [fc.to_dict() for fc in self.function_calls]
        return d


class Conversation:
    def __init__(self, spans: list[dict]):
        self.spans = spans
        self._messages: list[Message] | None = None

    def _get_attribute(self, span: dict, key: str) -> str | bool | None:
        attrs = span.get("attributes", [])
        for attr in attrs:
            if attr.get("key") == key:
                value = attr.get("value", {})
                return (
                    value.get("string_value")
                    or value.get("bool_value")
                    or value.get("int_value")
                    or value.get("double_value")
                )
        return None

    def _get_parent_turn(self, span: dict) -> dict | None:
        parent_id = span.get("parent_span_id_hex")
        if not parent_id:
            return None
        for s in self.spans:
            if s.get("span_id_hex") == parent_id and s.get("name") == "turn":
                return s
        return None

    def _get_span_text(self, span: dict) -> str:
        name = span.get("name")
        if name == "stt":
            return self._get_attribute(span, "transcript") or ""
        elif name == "tts":
            return self._get_attribute(span, "text") or ""
        return ""

    def _get_span_role(self, span: dict) -> str:
        return "user" if span.get("name") == "stt" else "assistant"

    def _get_interruption_status(self, span: dict | None) -> bool:
        if not span:
            return False
        turn = self._get_parent_turn(span)
        if not turn:
            return False
        return bool(self._get_attribute(turn, "turn.was_interrupted"))

    def _get_heard_status(self, span: dict) -> tuple[str | None, float | None]:
        if span.get("name") != "tts":
            return None, None
        turn = self._get_parent_turn(span)
        if not turn:
            return None, None

        interruption_times = []
        bot_started_times = []
        bot_stopped_times = []
        for event in turn.get("events", []):
            t = int(event.get("time_unix_nano", 0))
            if event.get("name") == "interruption":
                interruption_times.append(t)
            elif event.get("name") == "bot_started_speaking":
                bot_started_times.append(t)
            elif event.get("name") == "bot_stopped_speaking":
                bot_stopped_times.append(t)

        if not interruption_times:
            return "heard", None

        tts_start = int(span.get("start_time_unix_nano", 0))

        interruptions_after_tts = [t for t in interruption_times if t > tts_start]
        if not interruptions_after_tts:
            return "heard", None

        first_interruption_after = min(interruptions_after_tts)

        prev_boundaries = [
            t for t in interruption_times + bot_stopped_times if t <= tts_start
        ]
        window_start = max(prev_boundaries) if prev_boundaries else 0

        bot_started_in_window = [
            t
            for t in bot_started_times
            if t > window_start and t < first_interruption_after
        ]
        if bot_started_in_window:
            playback_start = min(bot_started_in_window)
            bot_stopped_before_interruption = [
                t
                for t in bot_stopped_times
                if t > playback_start and t < first_interruption_after
            ]
            if bot_stopped_before_interruption:
                return "heard", None
            heard_duration = (first_interruption_after - playback_start) / 1_000_000_000
            return "partial", heard_duration

        return "not_heard", None

    def _get_children_of(self, parent_span_id: str) -> list[dict]:
        return [s for s in self.spans if s.get("parent_span_id_hex") == parent_span_id]

    def _get_turn_latency(self, span: dict | None) -> TurnLatency | None:
        if not span:
            return None
        turn = self._get_parent_turn(span)
        if not turn:
            return None

        turn_id = turn.get("span_id_hex")
        children = self._get_children_of(turn_id)

        stt_ttfb = None
        llm_ttfb = None
        tts_ttfb = None
        fc_total = 0.0
        fc_count = 0
        for child in children:
            name = child.get("name")
            if name == "function_call":
                start = int(child.get("start_time_unix_nano", 0))
                end = int(child.get("end_time_unix_nano", 0))
                if end > start:
                    fc_total += (end - start) / 1_000_000_000
                    fc_count += 1
                continue
            ttfb = self._get_attribute(child, "metrics.ttfb")
            if ttfb is None:
                continue
            if name == "stt" and stt_ttfb is None:
                stt_ttfb = ttfb
            elif name == "llm" and llm_ttfb is None:
                llm_ttfb = ttfb
            elif name == "tts" and tts_ttfb is None:
                tts_ttfb = ttfb

        latency = TurnLatency(
            user_turn_seconds=self._get_attribute(turn, "turn.user_turn_seconds"),
            stt_ttfb=stt_ttfb,
            llm_ttfb=llm_ttfb,
            function_call_seconds=fc_total if fc_count > 0 else None,
            text_aggregation_seconds=self._get_attribute(
                turn, "turn.text_aggregation_seconds"
            ),
            tts_ttfb=tts_ttfb,
            user_bot_latency_seconds=self._get_attribute(
                turn, "turn.user_bot_latency_seconds"
            ),
        )
        return latency if latency.has_data() else None

    def _create_message_from_accumulator(
        self,
        acc: MessageAccumulator,
        was_interrupted: bool,
        latency: TurnLatency | None = None,
    ) -> Message:
        return Message(
            role=acc.role,
            content=" ".join(acc.texts),
            timestamp=acc.timestamp,
            was_interrupted=was_interrupted and acc.role == "assistant",
            span_ids=acc.span_ids,
            chunks=acc.chunks if acc.chunks else None,
            latency=latency,
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
        latency = (
            self._get_turn_latency(acc.first_span) if acc.role == "assistant" else None
        )
        messages.append(
            self._create_message_from_accumulator(acc, was_interrupted, latency)
        )

    def _get_spoken_texts_for_turn(self, turn: dict) -> list[str]:
        spoken_texts = []
        for event in turn.get("events", []):
            if event.get("name") != "interruption":
                continue
            for attr in event.get("attributes", []):
                if attr.get("key") == "tts.spoken_text":
                    val = attr.get("value", {}).get("string_value")
                    if val:
                        spoken_texts.append(val)
        return spoken_texts

    def _refine_chunk_statuses(self, chunks: list[dict], tts_spans: list[dict]):
        if len(chunks) <= 1:
            return
        for i in range(len(chunks) - 1):
            if chunks[i]["heard_status"] == "partial":
                next_span_start = int(tts_spans[i + 1].get("start_time_unix_nano", 0))
                curr_span_start = int(tts_spans[i].get("start_time_unix_nano", 0))
                if next_span_start > curr_span_start:
                    chunks[i]["heard_status"] = "heard"

    def _get_llm_ground_truth(self) -> list[str]:
        llm_spans = sorted(
            [s for s in self.spans if s.get("name") == "llm"],
            key=lambda s: int(s.get("start_time_unix_nano", 0)),
        )
        if not llm_spans:
            return []

        last_llm = llm_spans[-1]
        input_str = self._get_attribute(last_llm, "input")
        if not input_str:
            return []

        try:
            import json

            messages = json.loads(input_str)
        except (Exception,):
            return []

        return [
            m["content"]
            for m in messages
            if m.get("role") == "assistant" and m.get("content")
        ]

    def _split_chunks_with_ground_truth(
        self, chunks: list[dict], tts_spans: list[dict]
    ):
        if not tts_spans or not chunks:
            return

        has_partial = any(c["heard_status"] in ("partial", "not_heard") for c in chunks)
        if not has_partial:
            return

        if not hasattr(self, "_gt_entries"):
            self._gt_entries = self._get_llm_ground_truth()
            self._gt_used = set()

        full_text = " ".join(c["text"] for c in chunks)

        gt_combined = ""
        gt_indices = []
        for gi, gt in enumerate(self._gt_entries):
            if gi in self._gt_used:
                continue
            candidate = (gt_combined + " " + gt).strip() if gt_combined else gt
            if full_text.startswith(candidate):
                gt_combined = candidate
                gt_indices.append(gi)
            elif candidate.startswith(full_text):
                gt_combined = candidate
                gt_indices.append(gi)
                break
            else:
                break

        if not gt_combined:
            return

        for gi in gt_indices:
            self._gt_used.add(gi)

        accumulated = ""
        i = 0
        while i < len(chunks):
            chunk = chunks[i]
            candidate = (accumulated + " " + chunk["text"]).strip()

            if len(candidate) <= len(gt_combined) and gt_combined.startswith(candidate):
                chunk["heard_status"] = "heard"
                accumulated = candidate
                i += 1
                continue

            remaining = (
                gt_combined[len(accumulated) :].lstrip() if accumulated else gt_combined
            )

            if (
                remaining
                and chunk["text"].startswith(remaining)
                and len(remaining) < len(chunk["text"])
            ):
                muted_part = chunk["text"][len(remaining) :]
                chunks[i] = {"text": remaining, "heard_status": "heard"}
                chunks.insert(i + 1, {"text": muted_part, "heard_status": "not_heard"})
                for j in range(i + 2, len(chunks)):
                    chunks[j]["heard_status"] = "not_heard"
                break
            elif remaining and remaining.startswith(chunk["text"]):
                chunk["heard_status"] = "heard"
                accumulated = candidate
                i += 1
                continue
            else:
                chunk["heard_status"] = "not_heard"
                for j in range(i + 1, len(chunks)):
                    chunks[j]["heard_status"] = "not_heard"
                break

    def _build_messages_from_spans(
        self, spans: list[dict], check_interruption: bool = True
    ) -> list[Message]:
        spans_sorted = sorted(spans, key=lambda s: s.get("start_time_unix_nano", 0))
        messages: list[Message] = []
        acc = MessageAccumulator()
        acc_tts_spans: list[dict] = []
        prev_tts_end: int | None = None

        for span in spans_sorted:
            text = self._get_span_text(span)
            if not text:
                continue

            role = self._get_span_role(span)
            heard_status, _ = self._get_heard_status(span)

            gap_seconds = None
            if span.get("name") == "tts" and prev_tts_end is not None:
                gap_seconds = (
                    int(span.get("start_time_unix_nano", 0)) - prev_tts_end
                ) / 1_000_000_000

            if role == acc.role:
                acc.append(text, span, heard_status, gap_seconds)
                if span.get("name") == "tts":
                    acc_tts_spans.append(span)
                    prev_tts_end = int(span.get("end_time_unix_nano", 0))
                continue

            if acc.chunks and acc_tts_spans:
                self._refine_chunk_statuses(acc.chunks, acc_tts_spans)
                self._split_chunks_with_ground_truth(acc.chunks, acc_tts_spans)
            self._flush_accumulator(acc, messages, check_interruption)
            acc.reset(role, text, span, heard_status, gap_seconds)
            if span.get("name") == "tts":
                acc_tts_spans = [span]
                prev_tts_end = int(span.get("end_time_unix_nano", 0))
            else:
                acc_tts_spans = []
                prev_tts_end = None

        if acc.chunks and acc_tts_spans:
            self._refine_chunk_statuses(acc.chunks, acc_tts_spans)
            self._split_chunks_with_ground_truth(acc.chunks, acc_tts_spans)
        self._flush_accumulator(acc, messages, check_interruption)
        return messages

    def _get_turn_events(self, turn: dict) -> list[dict]:
        events = turn.get("events", [])
        if not events:
            return []
        return [
            {"name": e.get("name"), "time_unix_nano": e.get("time_unix_nano")}
            for e in events
        ]

    def _get_turn_id_for_span(self, span: dict) -> str | None:
        turn = self._get_parent_turn(span)
        return turn.get("span_id_hex") if turn else None

    def _apply_turn_events(self, messages: list[Message]):
        seen_turns = set()
        for msg in reversed(messages):
            if not msg.span_ids:
                continue
            for sid in msg.span_ids:
                span = next(
                    (s for s in self.spans if s.get("span_id_hex") == sid), None
                )
                if not span:
                    continue
                turn = self._get_parent_turn(span)
                if not turn:
                    continue
                turn_id = turn.get("span_id_hex")
                if turn_id in seen_turns:
                    continue
                seen_turns.add(turn_id)
                events = self._get_turn_events(turn)
                if events:
                    msg.turn_events = events
                break

    def get_messages(self) -> list[Message]:
        if self._messages is not None:
            return self._messages

        stt_tts_spans = [s for s in self.spans if s.get("name") in ("stt", "tts")]
        if hasattr(self, "_gt_entries"):
            del self._gt_entries
        if hasattr(self, "_gt_used"):
            del self._gt_used
        self._messages = self._build_messages_from_spans(stt_tts_spans)
        self._apply_turn_events(self._messages)
        return self._messages

    def _get_turn_for_message(self, msg: Message) -> dict | None:
        for sid in msg.span_ids:
            span = next((s for s in self.spans if s.get("span_id_hex") == sid), None)
            if span:
                turn = self._get_parent_turn(span)
                if turn:
                    return turn
        return None

    def _build_turn_latency(self, turn: dict) -> TurnLatency | None:
        turn_id = turn.get("span_id_hex")
        children = self._get_children_of(turn_id)

        stt_ttfb = None
        llm_ttfb = None
        tts_ttfb = None
        fc_total = 0.0
        fc_count = 0
        for child in children:
            name = child.get("name")
            if name == "function_call":
                start = int(child.get("start_time_unix_nano", 0))
                end = int(child.get("end_time_unix_nano", 0))
                if end > start:
                    fc_total += (end - start) / 1_000_000_000
                    fc_count += 1
                continue
            ttfb = self._get_attribute(child, "metrics.ttfb")
            if ttfb is None:
                continue
            if name == "stt" and stt_ttfb is None:
                stt_ttfb = ttfb
            elif name == "llm" and llm_ttfb is None:
                llm_ttfb = ttfb
            elif name == "tts" and tts_ttfb is None:
                tts_ttfb = ttfb

        latency = TurnLatency(
            user_turn_seconds=self._get_attribute(turn, "turn.user_turn_seconds"),
            stt_ttfb=stt_ttfb,
            llm_ttfb=llm_ttfb,
            function_call_seconds=fc_total if fc_count > 0 else None,
            text_aggregation_seconds=self._get_attribute(
                turn, "turn.text_aggregation_seconds"
            ),
            tts_ttfb=tts_ttfb,
            user_bot_latency_seconds=self._get_attribute(
                turn, "turn.user_bot_latency_seconds"
            ),
        )
        return latency if latency.has_data() else None

    def _get_function_calls_for_turn(self, turn: dict) -> list[FunctionCall] | None:
        turn_id = turn.get("span_id_hex")
        children = self._get_children_of(turn_id)
        fc_spans = [c for c in children if c.get("name") == "function_call"]
        if not fc_spans:
            return None

        fc_spans.sort(key=lambda s: int(s.get("start_time_unix_nano", 0)))
        result = []
        for span in fc_spans:
            start = int(span.get("start_time_unix_nano", 0))
            end = int(span.get("end_time_unix_nano", 0))
            attrs = {}
            for attr in span.get("attributes", []):
                key = attr.get("key")
                value = attr.get("value", {})
                attrs[key] = (
                    value.get("string_value")
                    or value.get("bool_value")
                    or value.get("int_value")
                    or value.get("double_value")
                )
            result.append(
                FunctionCall(
                    name=attrs.get("tool.function_name", "unknown"),
                    start_time_unix_nano=start,
                    end_time_unix_nano=end,
                    duration_seconds=(end - start) / 1_000_000_000
                    if end > start
                    else 0,
                    attributes=attrs,
                )
            )
        return result

    def get_turns(self) -> list[Turn]:
        messages = self.get_messages()

        turn_groups: dict[str, list[Message]] = {}
        turn_spans: dict[str, dict] = {}
        no_turn_msgs: list[Message] = []

        for msg in messages:
            turn = self._get_turn_for_message(msg)
            if turn:
                turn_id = turn.get("span_id_hex")
                turn_groups.setdefault(turn_id, []).append(msg)
                turn_spans[turn_id] = turn
            else:
                no_turn_msgs.append(msg)

        turns = []
        for turn_id, turn_messages in turn_groups.items():
            turn = turn_spans[turn_id]
            turn_number = self._get_attribute(turn, "turn.number")
            try:
                turn_number = int(turn_number)
            except (TypeError, ValueError):
                turn_number = 0

            latency = self._build_turn_latency(turn)
            events = self._get_turn_events(turn)
            user_bot = self._get_attribute(turn, "turn.user_bot_latency_seconds")
            function_calls = self._get_function_calls_for_turn(turn)

            turns.append(
                Turn(
                    turn_number=turn_number,
                    messages=turn_messages,
                    latency=latency,
                    events=events or None,
                    user_bot_latency_seconds=user_bot,
                    function_calls=function_calls,
                )
            )

        turns.sort(key=lambda t: t.turn_number)

        if no_turn_msgs:
            turns.insert(0, Turn(turn_number=0, messages=no_turn_msgs))

        return turns

    def to_dict_list(self) -> list[dict]:
        return [m.to_dict() for m in self.get_messages()]

    def to_turns_dict_list(self) -> list[dict]:
        return [t.to_dict() for t in self.get_turns()]
