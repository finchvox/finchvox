"""SDK contract tests that also run without the optional media dependencies.

The doubles model the supported Pipecat 1.14 setup/context API.
Real SDK/media integration tests remain in test_processor.py.
"""

import ast
import importlib.util
import sys
from collections.abc import AsyncGenerator
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from opentelemetry import trace
from opentelemetry.trace import NonRecordingSpan, SpanContext, TraceFlags

import finchvox

ROOT = Path(__file__).resolve().parents[1]


def _context(trace_id):
    span = NonRecordingSpan(SpanContext(trace_id, 1, False, TraceFlags(1)))
    return trace.set_span_in_context(span)


def _module(monkeypatch, name, **members):
    module = ModuleType(name)
    module.__dict__.update(members)
    monkeypatch.setitem(sys.modules, name, module)
    return module


@pytest.fixture
def processor_sdk(monkeypatch):
    frames = {name: type(name, (), {}) for name in (
        "CancelFrame", "EndFrame", "Frame", "InputAudioRawFrame",
        "OutputAudioRawFrame", "StartFrame",
    )}
    base = type("FrameProcessor", (), {
        "setup": AsyncMock(), "process_frame": AsyncMock(), "push_frame": AsyncMock(),
    })
    audio = Mock()
    audio.setup = AsyncMock()
    audio.start_recording = AsyncMock()
    audio.process_frame = AsyncMock()
    audio.event_handler.side_effect = lambda name: lambda handler: handler
    _module(monkeypatch, "pipecat.frames.frames", **frames)
    _module(monkeypatch, "pipecat.processors.frame_processor",
            FrameProcessor=base, FrameProcessorSetup=object, FrameDirection=object)
    _module(monkeypatch, "pipecat.processors.audio.audio_buffer_processor",
            AudioBufferProcessor=Mock(return_value=audio))
    # Current Pipecat does not have this module, even if a legacy SDK is installed.
    monkeypatch.setitem(sys.modules,
                        "pipecat.utils.tracing.conversation_context_provider", None)
    spec = importlib.util.spec_from_file_location(
        "voice_processor_under_test", ROOT / "src/finchvox/processor.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(finchvox, "_initialized", True)
    return SimpleNamespace(processor=module.FinchvoxProcessor, frames=frames, audio=audio)


@pytest.mark.asyncio
@pytest.mark.parametrize("enabled", [False, True])
async def test_processor_uses_setup_without_reading_deprecated_start_fields(
    processor_sdk, enabled
):
    processor = processor_sdk.processor()
    await processor.setup(SimpleNamespace(enable_tracing=enabled, tracing_context=None))
    # Deliberately has no enable_tracing field: reading StartFrame would fail.
    await processor._handle_start_frame(processor_sdk.frames["StartFrame"]())
    assert processor._disabled is not enabled
    assert processor_sdk.audio.start_recording.await_count == int(enabled)


@pytest.mark.asyncio
async def test_scoped_context_keeps_concurrent_pipeline_audio_separate(processor_sdk):
    processors = [processor_sdk.processor(), processor_sdk.processor()]
    for trace_id, processor in enumerate(processors, start=1):
        context = SimpleNamespace(get_conversation_context=lambda n=trace_id: _context(n))
        await processor.setup(SimpleNamespace(enable_tracing=True, tracing_context=context))
    assert [p._get_trace_id() for p in processors] == [f"{n:032x}" for n in (1, 2)]


@pytest.mark.asyncio
async def test_empty_scoped_context_does_not_fall_back_to_legacy_singleton(
    processor_sdk, monkeypatch
):
    legacy = Mock(return_value=_context(42))
    _module(monkeypatch, "pipecat.utils.tracing.conversation_context_provider",
            get_current_conversation_context=legacy)
    processor = processor_sdk.processor()
    await processor.setup(SimpleNamespace(
        enable_tracing=True,
        tracing_context=SimpleNamespace(get_conversation_context=lambda: None),
    ))
    assert processor._get_trace_id() == "no_trace"
    legacy.assert_not_called()


@pytest.mark.asyncio
async def test_missing_scoped_context_never_uses_legacy_singleton(processor_sdk, monkeypatch):
    _module(monkeypatch, "pipecat.utils.tracing.conversation_context_provider",
            get_current_conversation_context=lambda: _context(7))
    processor = processor_sdk.processor()
    await processor.setup(SimpleNamespace(enable_tracing=True, tracing_context=None))
    await processor._handle_start_frame(processor_sdk.frames["StartFrame"]())
    assert processor._disabled is False
    assert processor._get_trace_id() == "no_trace"


def _example_node(example, name):
    tree = ast.parse((ROOT / "examples" / example / "bot.py").read_text(encoding="utf-8"))
    return next(node for node in tree.body if getattr(node, "name", None) == name)


@pytest.mark.asyncio
@pytest.mark.parametrize("example", ["pipecat/webrtc", "pipecat/chaos"])
async def test_example_service_vad_and_runner_wiring(example):
    names = [
        "DeepgramSTTService", "CartesiaTTSService", "OpenAILLMService",
        "ChaosDeepgramSTTService", "ChaosCartesiaTTSService", "ChaosOpenAILLMService",
        "FunctionSchema", "ToolsSchema", "LLMContext", "LLMContextAggregatorPair",
        "LLMUserAggregatorParams", "SileroVADAnalyzer", "FinchvoxProcessor",
        "Pipeline", "PipelineParams", "PipelineWorker", "WorkerRunner",
        "add_item_to_order", "remove_item_from_order", "get_order_summary", "submit_order",
        "with_chaos",
    ]
    namespace = {name: Mock() for name in names}
    namespace.update(BaseTransport=object,
                     os=SimpleNamespace(getenv=lambda key: "test-key"))
    runner = namespace["WorkerRunner"].return_value
    runner.add_workers = AsyncMock()
    runner.run = AsyncMock()
    node = _example_node(example, "run_bot")
    exec(compile(ast.Module(body=[node], type_ignores=[]), example, "exec"), namespace)  # noqa: S102 - runs one function from our own example file against mocked SDKs
    await namespace["run_bot"](Mock())

    prefix = "Chaos" if example.endswith("chaos") else ""
    namespace[f"{prefix}CartesiaTTSService"].Settings.assert_called_once_with(
        voice="f786b574-daa5-4673-aa0c-cbe3e8534c02"
    )
    namespace[f"{prefix}OpenAILLMService"].Settings.assert_called_once_with(temperature=0.5)
    namespace["LLMUserAggregatorParams"].assert_called_once_with(
        vad_analyzer=namespace["SileroVADAnalyzer"].return_value
    )
    worker = namespace["PipelineWorker"].return_value
    runner.add_workers.assert_awaited_once_with(worker)
    runner.run.assert_awaited_once_with()


@pytest.mark.asyncio
@pytest.mark.parametrize("fail", [False, True])
async def test_chaos_tts_forwards_required_context_id(fail):
    calls = []

    class Cartesia:
        async def run_tts(self, text, context_id):
            calls.append((text, context_id))
            yield "audio-frame"

    namespace = {"CartesiaTTSService": Cartesia, "should_fail": lambda key: fail,
                 "AsyncGenerator": AsyncGenerator, "Frame": object}
    node = _example_node("pipecat/chaos", "ChaosCartesiaTTSService")
    exec(compile(ast.Module(body=[node], type_ignores=[]), "chaos", "exec"), namespace)  # noqa: S102 - runs one class from our own example file against mocked SDKs
    stream = namespace["ChaosCartesiaTTSService"]().run_tts("hello", "context-123")
    if fail:
        with pytest.raises(Exception, match="Simulated TTS failure"):
            await anext(stream)
        assert calls == []
    else:
        assert [frame async for frame in stream] == ["audio-frame"]
        assert calls == [("hello", "context-123")]


@pytest.mark.parametrize("example", ["pipecat/webrtc", "pipecat/chaos"])
def test_examples_no_longer_put_ignored_vad_option_on_transports(example):
    tree = ast.parse((ROOT / "examples" / example / "bot.py").read_text(encoding="utf-8"))
    params = next(node for node in tree.body if isinstance(node, ast.Assign)
                  and any(isinstance(target, ast.Name) and target.id == "transport_params"
                          for target in node.targets))
    namespace = {name: Mock() for name in (
        "DailyParams", "FastAPIWebsocketParams", "TransportParams"
    )}
    exec(compile(ast.Module(body=[params], type_ignores=[]), example, "exec"), namespace)  # noqa: S102 - runs one assignment from our own example file against mocked SDKs
    for factory in namespace["transport_params"].values():
        factory()
    for name in ("DailyParams", "FastAPIWebsocketParams", "TransportParams"):
        namespace[name].assert_called_once_with(audio_in_enabled=True, audio_out_enabled=True)


def test_livekit_example_uses_documented_replacement_for_retired_sonic():
    tree = ast.parse((ROOT / "examples/livekit/agent.py").read_text(encoding="utf-8"))
    agent_class = next(node for node in tree.body if isinstance(node, ast.ClassDef))

    class Agent:
        def __init__(self, **kwargs):
            self.options = kwargs

    inference = Mock()
    namespace = {"Agent": Agent, "inference": inference}
    exec(compile(ast.Module(body=[agent_class], type_ignores=[]), "livekit", "exec"), namespace)  # noqa: S102 - runs one class from our own example file against mocked SDKs
    namespace["VoiceAgent"]()
    inference.TTS.assert_called_once_with(model="cartesia/sonic-3")
    assert not any(isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                   and node.func.attr == "run_app" for node in ast.walk(tree))
