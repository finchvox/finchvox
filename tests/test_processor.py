import pytest

# Pipecat is an optional Finchvox integration. Skip this module cleanly for
# LiveKit-only development installs instead of failing test collection.
pytest.importorskip("pipecat")

from io import StringIO
from unittest.mock import AsyncMock, Mock

from loguru import logger
from pipecat.frames.frames import EndFrame, StartFrame
from pipecat.processors.frame_processor import FrameDirection

import finchvox
from finchvox import FinchvoxProcessor


@pytest.fixture
def reset_finchvox_state():
    original_state = finchvox._initialized
    yield
    finchvox._initialized = original_state


@pytest.fixture
def mock_setup_info():
    def close_coro_and_return_mock(coro, name=None, context=None):
        coro.close()
        return AsyncMock()

    setup = Mock()
    setup.clock = Mock()
    setup.clock.get_time = Mock(return_value=0)
    setup.task_manager = Mock()
    setup.task_manager.create_task = Mock(side_effect=close_coro_and_return_mock)
    setup.task_manager.cancel_task = AsyncMock()
    setup.observer = None
    setup.enable_tracing = True
    setup.tracing_context = None
    return setup


@pytest.fixture
def capture_logs():
    log_output = StringIO()
    handler_id = logger.add(log_output, format="{message}", level="DEBUG")
    yield log_output
    logger.remove(handler_id)


@pytest.mark.asyncio
async def test_pipeline_continues_when_init_not_called(
    reset_finchvox_state, mock_setup_info, capture_logs
):
    finchvox._initialized = False

    processor = FinchvoxProcessor()
    await processor.setup(mock_setup_info)

    pushed_frames = []

    async def capture_push(frame, direction=FrameDirection.DOWNSTREAM):
        pushed_frames.append((frame, direction))

    processor.push_frame = capture_push

    start_frame = StartFrame()
    await processor.process_frame(start_frame, FrameDirection.DOWNSTREAM)

    assert len(pushed_frames) == 1
    assert pushed_frames[0][0] is start_frame
    assert processor._disabled is True
    assert "finchvox.init() was not called" in capture_logs.getvalue()

    await processor.cleanup()


@pytest.mark.asyncio
async def test_pipeline_continues_when_tracing_disabled(
    reset_finchvox_state, mock_setup_info, capture_logs
):
    finchvox._initialized = True
    mock_setup_info.enable_tracing = False

    processor = FinchvoxProcessor()
    await processor.setup(mock_setup_info)

    pushed_frames = []

    async def capture_push(frame, direction=FrameDirection.DOWNSTREAM):
        pushed_frames.append((frame, direction))

    processor.push_frame = capture_push

    start_frame = StartFrame()
    await processor.process_frame(start_frame, FrameDirection.DOWNSTREAM)

    assert len(pushed_frames) == 1
    assert pushed_frames[0][0] is start_frame
    assert processor._disabled is True
    assert "FinchvoxProcessor requires tracing to be enabled" in capture_logs.getvalue()

    await processor.cleanup()


@pytest.mark.asyncio
async def test_pipeline_continues_when_collector_unreachable(
    reset_finchvox_state, mock_setup_info, capture_logs
):
    finchvox._initialized = True

    processor = FinchvoxProcessor(endpoint="http://localhost:59999")
    await processor.setup(mock_setup_info)

    pushed_frames = []

    async def capture_push(frame, direction=FrameDirection.DOWNSTREAM):
        pushed_frames.append((frame, direction))

    processor.push_frame = capture_push

    start_frame = StartFrame()
    await processor.process_frame(start_frame, FrameDirection.DOWNSTREAM)

    assert len(pushed_frames) == 1
    assert pushed_frames[0][0] is start_frame
    assert processor._disabled is False

    success = await processor._upload_chunk(
        trace_id="test_trace_id",
        chunk_number=0,
        audio_data=b"\x00" * 1000,
        metadata={"sample_rate": 16000, "num_channels": 2},
    )

    assert success is False
    assert "Could not reach finchvox collector" in capture_logs.getvalue()
    assert processor._collector_warning_shown is True

    log_before = capture_logs.getvalue()
    success = await processor._upload_chunk(
        trace_id="test_trace_id",
        chunk_number=1,
        audio_data=b"\x00" * 1000,
        metadata={"sample_rate": 16000, "num_channels": 2},
    )

    assert success is False
    log_after = capture_logs.getvalue()
    new_logs = log_after[len(log_before) :]
    assert "Could not reach finchvox collector" not in new_logs

    await processor.cleanup()


@pytest.mark.asyncio
async def test_end_frame_flows_through_when_disabled(
    reset_finchvox_state, mock_setup_info
):
    finchvox._initialized = False

    processor = FinchvoxProcessor()
    await processor.setup(mock_setup_info)

    pushed_frames = []

    async def capture_push(frame, direction=FrameDirection.DOWNSTREAM):
        pushed_frames.append((frame, direction))

    processor.push_frame = capture_push

    start_frame = StartFrame()
    await processor.process_frame(start_frame, FrameDirection.DOWNSTREAM)

    end_frame = EndFrame()
    await processor.process_frame(end_frame, FrameDirection.DOWNSTREAM)

    assert len(pushed_frames) == 2
    assert pushed_frames[0][0] is start_frame
    assert pushed_frames[1][0] is end_frame

    await processor.cleanup()
