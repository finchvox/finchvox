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

    def test_message_has_end_timestamp(self):
        turn = _span(
            "turn",
            "turn1",
            1000,
            parent_id="conv1",
            attributes=[_attr("turn.was_interrupted", False)],
        )
        stt = _span(
            "stt",
            "stt1",
            1000,
            parent_id="turn1",
            attributes=[_attr("transcript", "hello")],
        )
        tts1 = {
            "name": "tts",
            "span_id_hex": "tts1",
            "start_time_unix_nano": "3000",
            "end_time_unix_nano": "5000",
            "parent_span_id_hex": "turn1",
            "attributes": [_attr("text", "hi")],
        }
        tts2 = {
            "name": "tts",
            "span_id_hex": "tts2",
            "start_time_unix_nano": "5000",
            "end_time_unix_nano": "8000",
            "parent_span_id_hex": "turn1",
            "attributes": [_attr("text", "there")],
        }

        conv = Conversation([turn, stt, tts1, tts2])
        messages = conv.get_messages()

        user_msg = messages[0]
        assert user_msg.end_timestamp == 1000 + 1_000_000_000

        assistant_msg = messages[1]
        assert assistant_msg.end_timestamp == 8000

    def test_tts_spans_split_on_large_gap(self):
        turn = _span(
            "turn",
            "turn1",
            1000,
            parent_id="conv1",
            attributes=[_attr("turn.was_interrupted", False)],
        )
        stt = _span(
            "stt",
            "stt1",
            1000,
            parent_id="turn1",
            attributes=[_attr("transcript", "order coffee")],
        )
        tts1 = {
            "name": "tts",
            "span_id_hex": "tts1",
            "start_time_unix_nano": "3000000000",
            "end_time_unix_nano": "3001000000",
            "parent_span_id_hex": "turn1",
            "attributes": [_attr("text", "One sec.")],
        }
        tts2 = {
            "name": "tts",
            "span_id_hex": "tts2",
            "start_time_unix_nano": "5000000000",
            "end_time_unix_nano": "5001000000",
            "parent_span_id_hex": "turn1",
            "attributes": [_attr("text", "Got it.")],
        }

        conv = Conversation([turn, stt, tts1, tts2])
        messages = conv.get_messages()

        assert len(messages) == 3
        assert messages[0].role == "user"
        assert messages[1].role == "assistant"
        assert messages[1].content == "One sec."
        assert messages[2].role == "assistant"
        assert messages[2].content == "Got it."

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


def _fc_span(span_id, start_nano, end_nano, parent_id, attributes=None):
    s = {
        "name": "function_call",
        "span_id_hex": span_id,
        "start_time_unix_nano": str(start_nano),
        "end_time_unix_nano": str(end_nano),
        "attributes": attributes or [],
    }
    if parent_id:
        s["parent_span_id_hex"] = parent_id
    return s


class TestFunctionCallsInTurns:
    def test_turn_includes_function_calls(self):
        turn = _span(
            "turn",
            "turn1",
            1000,
            parent_id="conv1",
            attributes=[_attr("turn.number", 1)],
        )
        stt = _span(
            "stt",
            "stt1",
            1000,
            parent_id="turn1",
            attributes=[_attr("transcript", "check the weather")],
        )
        fc = _fc_span(
            "fc1",
            2000,
            3000,
            parent_id="turn1",
            attributes=[
                _attr("tool.function_name", "get_weather"),
                _attr("tool.call_id", "call_123"),
            ],
        )
        tts = _span(
            "tts",
            "tts1",
            4000,
            parent_id="turn1",
            attributes=[_attr("text", "It's sunny")],
        )

        conv = Conversation([turn, stt, fc, tts])
        turns = conv.to_turns_dict_list()

        assert len(turns) == 1
        assert "function_calls" in turns[0]
        assert len(turns[0]["function_calls"]) == 1
        assert turns[0]["function_calls"][0]["name"] == "get_weather"

    def test_function_call_attributes_extracted(self):
        turn = _span(
            "turn",
            "turn1",
            1000,
            parent_id="conv1",
            attributes=[_attr("turn.number", 1)],
        )
        fc = _fc_span(
            "fc1",
            2000,
            3500,
            parent_id="turn1",
            attributes=[
                _attr("tool.function_name", "get_weather"),
                _attr("tool.call_id", "call_123"),
                _attr("tool.arguments", '{"city": "SF"}'),
                _attr("tool.result", '{"temp": 72}'),
                _attr("tool.result_status", "success"),
            ],
        )
        tts = _span(
            "tts",
            "tts1",
            4000,
            parent_id="turn1",
            attributes=[_attr("text", "It's sunny")],
        )

        conv = Conversation([turn, fc, tts])
        turns = conv.to_turns_dict_list()

        fc_data = turns[0]["function_calls"][0]
        assert fc_data["attributes"]["tool.function_name"] == "get_weather"
        assert fc_data["attributes"]["tool.call_id"] == "call_123"
        assert fc_data["attributes"]["tool.arguments"] == '{"city": "SF"}'
        assert fc_data["attributes"]["tool.result"] == '{"temp": 72}'
        assert fc_data["attributes"]["tool.result_status"] == "success"

    def test_multiple_function_calls_ordered_chronologically(self):
        turn = _span(
            "turn",
            "turn1",
            1000,
            parent_id="conv1",
            attributes=[_attr("turn.number", 1)],
        )
        fc2 = _fc_span(
            "fc2",
            5000,
            6000,
            parent_id="turn1",
            attributes=[_attr("tool.function_name", "second_fn")],
        )
        fc1 = _fc_span(
            "fc1",
            2000,
            3000,
            parent_id="turn1",
            attributes=[_attr("tool.function_name", "first_fn")],
        )
        tts = _span(
            "tts", "tts1", 7000, parent_id="turn1", attributes=[_attr("text", "done")]
        )

        conv = Conversation([turn, fc2, fc1, tts])
        turns = conv.to_turns_dict_list()

        fcs = turns[0]["function_calls"]
        assert len(fcs) == 2
        assert fcs[0]["name"] == "first_fn"
        assert fcs[1]["name"] == "second_fn"

    def test_turn_without_function_calls_has_no_key(self):
        turn = _span(
            "turn",
            "turn1",
            1000,
            parent_id="conv1",
            attributes=[_attr("turn.number", 1)],
        )
        stt = _span(
            "stt",
            "stt1",
            1000,
            parent_id="turn1",
            attributes=[_attr("transcript", "hi")],
        )
        tts = _span(
            "tts", "tts1", 2000, parent_id="turn1", attributes=[_attr("text", "hello")]
        )

        conv = Conversation([turn, stt, tts])
        turns = conv.to_turns_dict_list()

        assert "function_calls" not in turns[0]

    def test_function_call_duration_calculated(self):
        turn = _span(
            "turn",
            "turn1",
            1000,
            parent_id="conv1",
            attributes=[_attr("turn.number", 1)],
        )
        fc = _fc_span(
            "fc1",
            2_000_000_000,
            3_500_000_000,
            parent_id="turn1",
            attributes=[_attr("tool.function_name", "slow_fn")],
        )
        tts = _span(
            "tts", "tts1", 4000, parent_id="turn1", attributes=[_attr("text", "done")]
        )

        conv = Conversation([turn, fc, tts])
        turns = conv.to_turns_dict_list()

        fc_data = turns[0]["function_calls"][0]
        assert fc_data["duration_seconds"] == 1.5
