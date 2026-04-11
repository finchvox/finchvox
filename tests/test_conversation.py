from finchvox.conversation import Conversation, TurnLatency


def _attr(key, value):
    if isinstance(value, float):
        return {"key": key, "value": {"double_value": value}}
    elif isinstance(value, bool):
        return {"key": key, "value": {"bool_value": value}}
    elif isinstance(value, int):
        return {"key": key, "value": {"int_value": str(value)}}
    return {"key": key, "value": {"string_value": value}}


def _span(name, span_id, start_nano, parent_id=None, attributes=None):
    s = {
        "name": name,
        "span_id_hex": span_id,
        "start_time_unix_nano": str(start_nano),
        "end_time_unix_nano": str(start_nano + 1_000_000_000),
        "attributes": attributes or [],
    }
    if parent_id:
        s["parent_span_id_hex"] = parent_id
    return s


class TestTurnLatencyInConversation:
    def test_assistant_message_includes_latency_from_turn_span(self):
        turn = _span(
            "turn",
            "turn1",
            1000,
            parent_id="conv1",
            attributes=[
                _attr("turn.user_turn_seconds", 0.517),
                _attr("turn.text_aggregation_seconds", 0.0047),
                _attr("turn.user_bot_latency_seconds", 1.782),
                _attr("turn.was_interrupted", False),
            ],
        )
        stt = _span(
            "stt",
            "stt1",
            1000,
            parent_id="turn1",
            attributes=[
                _attr("transcript", "hello"),
                _attr("metrics.ttfb", 0.25),
            ],
        )
        llm = _span(
            "llm",
            "llm1",
            2000,
            parent_id="turn1",
            attributes=[
                _attr("metrics.ttfb", 0.602),
            ],
        )
        tts = _span(
            "tts",
            "tts1",
            3000,
            parent_id="turn1",
            attributes=[
                _attr("text", "hi there"),
                _attr("metrics.ttfb", 0.024),
            ],
        )

        conv = Conversation([turn, stt, llm, tts])
        messages = conv.get_messages()

        assert len(messages) == 2
        user_msg = messages[0]
        assistant_msg = messages[1]

        assert user_msg.role == "user"
        assert user_msg.latency is None

        assert assistant_msg.role == "assistant"
        assert assistant_msg.latency is not None
        assert assistant_msg.latency.user_turn_seconds == 0.517
        assert assistant_msg.latency.stt_ttfb == 0.25
        assert assistant_msg.latency.llm_ttfb == 0.602
        assert assistant_msg.latency.text_aggregation_seconds == 0.0047
        assert assistant_msg.latency.tts_ttfb == 0.024
        assert assistant_msg.latency.user_bot_latency_seconds == 1.782

    def test_latency_dict_omits_none_values(self):
        latency = TurnLatency(llm_ttfb=0.5, tts_ttfb=0.02)
        d = latency.to_dict()
        assert d == {"llm_ttfb": 0.5, "tts_ttfb": 0.02}

    def test_greeting_turn_has_partial_latency(self):
        turn = _span(
            "turn",
            "turn1",
            1000,
            parent_id="conv1",
            attributes=[
                _attr("turn.text_aggregation_seconds", 0.0038),
                _attr("turn.was_interrupted", False),
            ],
        )
        llm = _span(
            "llm",
            "llm1",
            1500,
            parent_id="turn1",
            attributes=[
                _attr("metrics.ttfb", 3.4),
            ],
        )
        tts = _span(
            "tts",
            "tts1",
            2000,
            parent_id="turn1",
            attributes=[
                _attr("text", "Hey there! What can I get started for you today?"),
                _attr("metrics.ttfb", 0.001),
            ],
        )

        conv = Conversation([turn, llm, tts])
        messages = conv.get_messages()

        assert len(messages) == 1
        msg = messages[0]
        assert msg.role == "assistant"
        assert msg.latency is not None
        assert msg.latency.user_turn_seconds is None
        assert msg.latency.user_bot_latency_seconds is None
        assert msg.latency.llm_ttfb == 3.4
        assert msg.latency.text_aggregation_seconds == 0.0038

    def test_no_latency_when_no_turn_span(self):
        tts = _span(
            "tts",
            "tts1",
            1000,
            attributes=[
                _attr("text", "hello"),
            ],
        )

        conv = Conversation([tts])
        messages = conv.get_messages()

        assert len(messages) == 1
        assert messages[0].latency is None

    def test_to_dict_includes_latency(self):
        turn = _span(
            "turn",
            "turn1",
            1000,
            parent_id="conv1",
            attributes=[
                _attr("turn.user_bot_latency_seconds", 1.5),
                _attr("turn.was_interrupted", False),
            ],
        )
        stt = _span(
            "stt",
            "stt1",
            1000,
            parent_id="turn1",
            attributes=[
                _attr("transcript", "hi"),
            ],
        )
        tts = _span(
            "tts",
            "tts1",
            2000,
            parent_id="turn1",
            attributes=[
                _attr("text", "hello"),
            ],
        )

        conv = Conversation([turn, stt, tts])
        dicts = conv.to_dict_list()

        assistant_dict = dicts[1]
        assert "latency" in assistant_dict
        assert assistant_dict["latency"]["user_bot_latency_seconds"] == 1.5

    def test_to_dict_excludes_latency_when_empty(self):
        tts = _span(
            "tts",
            "tts1",
            1000,
            attributes=[
                _attr("text", "hello"),
            ],
        )

        conv = Conversation([tts])
        dicts = conv.to_dict_list()

        assert "latency" not in dicts[0]
