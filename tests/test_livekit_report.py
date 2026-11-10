from finchvox.livekit_report import (
    report_events,
    report_messages,
    timestamp_to_unix_nano,
)


def test_timestamp_to_unix_nano_accepts_seconds_and_iso():
    assert timestamp_to_unix_nano(1_700_000_000.5) == 1_700_000_000_500_000_000
    assert timestamp_to_unix_nano("2023-11-14T22:13:20+00:00") == 1_700_000_000_000_000_000


def test_report_messages_preserve_metrics_and_pair_span_ids():
    report = {
        "chat_history": {
            "items": [
                {
                    "id": "user-1",
                    "type": "message",
                    "role": "user",
                    "content": ["Hello"],
                    "created_at": 1_700_000_000.0,
                    "transcript_confidence": 0.97,
                    "metrics": {"transcription_delay": 0.12},
                },
                {
                    "id": "agent-1",
                    "type": "message",
                    "role": "assistant",
                    "content": ["Hi there"],
                    "created_at": 1_700_000_001.0,
                    "interrupted": True,
                    "metrics": {"llm_node_ttft": 0.41, "tts_node_ttfb": 0.08},
                },
            ]
        }
    }
    trace_messages = [
        {"role": "user", "span_ids": ["user-turn"]},
        {"role": "assistant", "span_ids": ["agent-turn", "llm"]},
    ]

    messages = report_messages(report, trace_messages)

    assert messages[0]["content"] == "Hello"
    assert messages[0]["transcript_confidence"] == 0.97
    assert messages[0]["span_ids"] == ["user-turn"]
    assert messages[1]["was_interrupted"] is True
    assert messages[1]["metrics"]["llm_node_ttft"] == 0.41
    assert messages[1]["span_ids"] == ["agent-turn", "llm"]


def test_report_events_combine_tool_output_and_handoff():
    report = {
        "chat_history": {
            "items": [
                {
                    "type": "function_call",
                    "call_id": "call-1",
                    "name": "lookup_order",
                    "arguments": '{"id":"42"}',
                    "created_at": 1_700_000_002.0,
                },
                {
                    "type": "function_call_output",
                    "call_id": "call-1",
                    "name": "lookup_order",
                    "output": "timeout",
                    "is_error": True,
                    "created_at": 1_700_000_002.2,
                },
                {
                    "type": "agent_handoff",
                    "old_agent_id": "greeter",
                    "new_agent_id": "support",
                    "created_at": 1_700_000_003.0,
                },
            ]
        }
    }

    events = report_events(report)

    assert [event["kind"] for event in events] == ["error", "handoff"]
    assert events[0]["title"] == "Tool call: lookup_order"
    assert events[0]["span"]["_normalized"]["tool_output"] == "timeout"
    assert events[0]["span"]["_normalized"]["is_error"] is True
    assert events[1]["subtitle"] == "greeter → support"
