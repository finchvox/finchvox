import asyncio
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from finchvox import environment


@pytest.fixture
def environment_processor(monkeypatch):
    monkeypatch.setattr(environment, "_captured_environment", {"python": {"version": "test"}})
    monkeypatch.setattr(environment, "_environment_sent_traces", set())
    processor = environment.EnvironmentSpanProcessor("http://localhost:3000")
    monkeypatch.setattr(processor, "_send_environment", AsyncMock())
    return processor


def make_span(trace_id=1):
    return SimpleNamespace(get_span_context=lambda: SimpleNamespace(trace_id=trace_id))


def test_environment_is_sent_without_a_current_event_loop(environment_processor):
    async def finish_loop():
        pass

    # asyncio.run clears the current loop, including on Python < 3.14.
    asyncio.run(finish_loop())

    environment_processor.on_end(make_span())

    environment_processor._send_environment.assert_awaited_once_with(
        "0" * 31 + "1", environment.get_captured_environment()
    )


def test_environment_is_sent_from_a_worker_thread(environment_processor):
    with ThreadPoolExecutor(max_workers=1) as executor:
        executor.submit(environment_processor.on_end, make_span()).result()

    environment_processor._send_environment.assert_awaited_once()


@pytest.mark.asyncio
async def test_environment_uses_running_loop_and_deduplicates(environment_processor):
    span = make_span()

    environment_processor.on_end(span)
    environment_processor.on_end(span)
    await asyncio.sleep(0)

    environment_processor._send_environment.assert_awaited_once_with(
        "0" * 31 + "1", environment.get_captured_environment()
    )


def test_environment_ignores_invalid_trace_ids(environment_processor):
    environment_processor.on_end(make_span(trace_id=0))

    environment_processor._send_environment.assert_not_called()
