from finchvox.conversation import Conversation


def test_livekit_conversation_prefers_turn_spans_and_avoids_child_duplicates():
    spans = [
        {
            "name": "agent_session",
            "span_id_hex": "root",
            "start_time_unix_nano": 1,
            "_normalized": {"category": "root"},
        },
        {
            "name": "user_turn",
            "span_id_hex": "user-turn",
            "parent_span_id_hex": "root",
            "start_time_unix_nano": 10,
            "_normalized": {
                "category": "stt",
                "transcript": "Can you check my order?",
            },
        },
        {
            "name": "user_speaking",
            "span_id_hex": "stt-child",
            "parent_span_id_hex": "user-turn",
            "start_time_unix_nano": 11,
            "_normalized": {
                "category": "stt",
                "transcript": "Can you check my order?",
            },
        },
        {
            "name": "agent_turn",
            "span_id_hex": "agent-turn",
            "parent_span_id_hex": "root",
            "start_time_unix_nano": 20,
            "_normalized": {
                "category": "turn",
                "output_text": "Sure, what is the order number?",
                "interrupted": True,
            },
        },
        {
            "name": "llm_request",
            "span_id_hex": "llm-child",
            "parent_span_id_hex": "agent-turn",
            "start_time_unix_nano": 21,
            "_normalized": {
                "category": "llm",
                "output_text": "Sure, what is the order number?",
            },
        },
        {
            "name": "tts_request",
            "span_id_hex": "tts-child",
            "parent_span_id_hex": "agent-turn",
            "start_time_unix_nano": 22,
            "_normalized": {
                "category": "tts",
                "output_text": "Sure, what is the order number?",
            },
        },
    ]

    messages = Conversation(spans).to_dict_list()

    assert [message["role"] for message in messages] == ["user", "assistant"]
    assert messages[0]["content"] == "Can you check my order?"
    assert messages[1]["content"] == "Sure, what is the order number?"
    assert messages[1]["was_interrupted"] is True
    assert messages[0]["span_ids"] == ["user-turn"]
    assert messages[1]["span_ids"] == ["agent-turn"]


def test_livekit_conversation_falls_back_to_child_text_when_turn_has_no_content():
    spans = [
        {
            "name": "agent_session",
            "span_id_hex": "root",
            "start_time_unix_nano": 1,
            "_normalized": {"category": "root"},
        },
        {
            "name": "user_turn",
            "span_id_hex": "user-turn",
            "parent_span_id_hex": "root",
            "start_time_unix_nano": 10,
            "_normalized": {"category": "stt", "transcript": None},
        },
        {
            "name": "user_speaking",
            "span_id_hex": "stt-child",
            "parent_span_id_hex": "user-turn",
            "start_time_unix_nano": 11,
            "_normalized": {"category": "stt", "transcript": "Hello"},
        },
        {
            "name": "agent_turn",
            "span_id_hex": "agent-turn",
            "parent_span_id_hex": "root",
            "start_time_unix_nano": 20,
            "_normalized": {"category": "turn", "output_text": None},
        },
        {
            "name": "llm_request",
            "span_id_hex": "llm-child",
            "parent_span_id_hex": "agent-turn",
            "start_time_unix_nano": 21,
            "_normalized": {"category": "llm", "output_text": "Hi there"},
        },
    ]

    messages = Conversation(spans).to_dict_list()

    assert [message["content"] for message in messages] == ["Hello", "Hi there"]
    assert messages[0]["span_ids"][0] == "user-turn"
    assert "stt-child" in messages[0]["span_ids"]
    assert messages[1]["span_ids"][0] == "agent-turn"
    assert "llm-child" in messages[1]["span_ids"]
