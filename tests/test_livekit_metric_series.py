"""Each LiveKit measurement is counted once, and LiveKit's placeholders are not counted.

Found on the first real LiveKit call: LiveKit repeats the same timing on wrapper
spans and on both turn spans, writes -1 when no first token arrived, and writes 0
on a user turn whose timing it could not measure.
"""

import json

import pytest

from finchvox.adapters import LiveKitAdapter
from finchvox.metrics import Metrics


def attributes(**values):
    encoded = []
    for key, value in values.items():
        name = key.replace("__", ".")
        if isinstance(value, float):
            encoded.append({"key": name, "value": {"double_value": value}})
        else:
            encoded.append({"key": name, "value": {"string_value": str(value)}})
    return encoded


def span(name, span_id, start_s, parent=None, **attrs):
    return {
        "name": name,
        "span_id_hex": span_id,
        "parent_span_id_hex": parent,
        "start_time_unix_nano": int(start_s * 1_000_000_000),
        "attributes": attributes(**attrs),
    }


def metrics_for(*spans, report_messages=None):
    normalized = LiveKitAdapter().normalize_spans(list(spans))
    return Metrics(normalized, report_messages=report_messages).to_dict()


def values(series):
    return sorted(round(point["ttfb_ms"]) for point in series["data_points"])


def breakdown_values(result, label):
    return sorted(round(point["latency_ms"]) for point in result["turn_breakdown"][label]["data_points"])


class TestWrapperSpansAreNotCountedTwice:
    def test_llm_time_to_first_token_is_counted_once_per_request(self):
        result = metrics_for(
            span("agent_turn", "turn", 1),
            span("llm_node", "node", 1.1, "turn", lk__response__ttft=0.5),
            span("llm_request", "req", 1.1, "node", lk__response__ttft=0.499),
        )

        assert values(result["series"]["llm"]) == [499]

    def test_tts_time_to_first_byte_is_counted_once_per_request(self):
        result = metrics_for(
            span("agent_turn", "turn", 1),
            span("tts_node", "node", 2, "turn", lk__response__ttfb=0.7),
            span("tts_request", "req", 2, "node", lk__response__ttfb=0.701),
        )

        assert values(result["series"]["tts"]) == [701]


class TestTurnDelaysAreCountedOncePerUserTurn:
    def test_delays_copied_onto_the_agent_turn_are_not_counted_again(self):
        result = metrics_for(
            span("user_turn", "u1", 1, lk__transcription_delay=0.3, lk__end_of_turn_delay=0.4),
            span(
                "agent_turn",
                "a1",
                2,
                lk__transcription_delay=0.3,
                lk__end_of_turn_delay=0.4,
                lk__on_user_turn_completed_delay=0.001,
                lk__speech__queue_wait=0.002,
            ),
        )

        assert breakdown_values(result, "transcription") == [300]
        assert breakdown_values(result, "endpointing") == [400]
        assert breakdown_values(result, "turn_hook") == [1]
        assert breakdown_values(result, "queue_wait") == [2]

    def test_a_user_turn_the_agent_did_not_answer_still_counts(self):
        result = metrics_for(
            span("user_turn", "u1", 1, lk__transcription_delay=0.3, lk__end_of_turn_delay=0.4),
            span("agent_turn", "a1", 2, lk__transcription_delay=0.3, lk__end_of_turn_delay=0.4),
            span("user_turn", "u2", 5, lk__transcription_delay=0.6, lk__end_of_turn_delay=0.62),
        )

        assert breakdown_values(result, "transcription") == [300, 600]
        assert breakdown_values(result, "endpointing") == [400, 620]

    def test_agent_turns_are_used_when_no_user_turn_carries_the_delays(self):
        result = metrics_for(
            span("agent_turn", "a1", 2, lk__transcription_delay=0.3, lk__end_of_turn_delay=0.4),
        )

        assert breakdown_values(result, "transcription") == [300]
        assert breakdown_values(result, "endpointing") == [400]


class TestMissingFirstTokenIsNotATiming:
    @pytest.mark.parametrize(
        "llm_span",
        [
            span("llm_request", "req", 2, lk__response__ttft=-1.0),
            span("llm_request", "req", 2, lk__llm_metrics=json.dumps({"ttft": -1.0})),
            span("realtime_inference", "req", 2, lk__realtime_model_metrics=json.dumps({"ttft": -1})),
        ],
        ids=["response attribute", "llm metrics", "realtime metrics"],
    )
    def test_minus_one_is_left_out(self, llm_span):
        result = metrics_for(
            span("llm_request", "ok", 1, lk__response__ttft=0.4),
            llm_span,
        )

        assert values(result["series"]["llm"]) == [400]

    def test_minus_one_is_shown_as_missing_on_the_span(self):
        normalized = LiveKitAdapter().normalize_spans(
            [span("llm_request", "req", 2, lk__llm_metrics=json.dumps({"ttft": -1.0}))]
        )

        assert normalized[0]["_normalized"]["ttfb_seconds"] is None

    def test_negative_values_in_the_session_report_are_left_out(self):
        messages = [
            {"timestamp": 1_000_000_000, "metrics": {"llm_node_ttft": 0.4}},
            {"timestamp": 2_000_000_000, "metrics": {"llm_node_ttft": -1.0}},
        ]

        result = metrics_for(report_messages=messages)

        assert values(result["series"]["llm"]) == [400]


class TestUnmeasuredUserTurns:
    def test_a_turn_livekit_could_not_measure_adds_no_points(self):
        # LiveKit writes 0 for both delays when it has no timing for the turn,
        # for example the user turn it closes after the call has ended.
        result = metrics_for(
            span("user_turn", "u1", 1, lk__transcription_delay=0.3, lk__end_of_turn_delay=0.4),
            span("user_turn", "u2", 9, lk__transcription_delay=0.0, lk__end_of_turn_delay=0.0),
        )

        assert values(result["series"]["stt"]) == [300]
        assert breakdown_values(result, "transcription") == [300]
        assert breakdown_values(result, "endpointing") == [400]

    def test_the_unmeasured_turn_shows_its_delays_as_missing(self):
        normalized = LiveKitAdapter().normalize_spans(
            [span("user_turn", "u", 9, lk__transcription_delay=0.0, lk__end_of_turn_delay=0.0)]
        )[0]["_normalized"]

        assert normalized["ttfb_seconds"] is None
        assert normalized["transcription_delay_seconds"] is None
        assert normalized["end_of_turn_delay_seconds"] is None

    def test_a_transcript_ready_before_speech_ended_keeps_its_zero_delay(self):
        # LiveKit clamps a transcript that arrived early to 0; the turn was still measured.
        result = metrics_for(
            span("user_turn", "u1", 1, lk__transcription_delay=0.0, lk__end_of_turn_delay=0.25),
        )

        assert values(result["series"]["stt"]) == [0]
        assert breakdown_values(result, "transcription") == [0]
        assert breakdown_values(result, "endpointing") == [250]
