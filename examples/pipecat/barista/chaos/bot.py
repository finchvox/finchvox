import os
import random
import sys
from typing import AsyncGenerator

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
from loguru import logger
from pipecat.audio.vad.silero import SileroVADAnalyzer
from pipecat.frames.frames import Frame, LLMRunFrame
from pipecat.pipeline.runner import PipelineRunner
from pipecat.runner.types import RunnerArguments
from pipecat.runner.utils import create_transport
from pipecat.services.cartesia.tts import CartesiaTTSService
from pipecat.services.deepgram.stt import DeepgramSTTService
from pipecat.services.llm_service import FunctionCallParams
from pipecat.services.openai.llm import OpenAILLMService
from pipecat.transports.base_transport import BaseTransport, TransportParams
from pipecat.transports.daily.transport import DailyParams
from pipecat.transports.websocket.fastapi import FastAPIWebsocketParams

import finchvox
import shared

load_dotenv(override=True)

finchvox.init(service_name="pipecat-chaos-demo")


def should_fail(rate_env_var: str) -> bool:
    rate = float(os.getenv(rate_env_var, "0"))
    if rate > 0 and random.random() < rate:
        logger.warning(f"[CHAOS] Injecting failure ({rate_env_var}={rate})")
        return True
    return False


def with_chaos(handler):
    async def wrapped(params: FunctionCallParams):
        if should_fail("TOOL_FAIL_RATE"):
            await params.result_callback(
                {"error": "Simulated tool failure", "success": False}
            )
            return
        await handler(params)

    return wrapped


class ChaosOpenAILLMService(OpenAILLMService):
    async def get_chat_completions(self, params):
        if should_fail("LLM_FAIL_RATE"):
            raise Exception("Simulated LLM failure")
        return await super().get_chat_completions(params)


class ChaosDeepgramSTTService(DeepgramSTTService):
    async def run_stt(self, audio: bytes) -> AsyncGenerator[Frame, None]:
        if should_fail("STT_FAIL_RATE"):
            raise Exception("Simulated STT failure")
        async for frame in super().run_stt(audio):
            yield frame


class ChaosCartesiaTTSService(CartesiaTTSService):
    async def run_tts(self, text: str) -> AsyncGenerator[Frame, None]:
        if should_fail("TTS_FAIL_RATE"):
            raise Exception("Simulated TTS failure")
        async for frame in super().run_tts(text):
            yield frame


transport_params = {
    "daily": lambda: DailyParams(
        audio_in_enabled=True,
        audio_out_enabled=True,
        vad_analyzer=SileroVADAnalyzer(),
    ),
    "twilio": lambda: FastAPIWebsocketParams(
        audio_in_enabled=True,
        audio_out_enabled=True,
        vad_analyzer=SileroVADAnalyzer(),
    ),
    "webrtc": lambda: TransportParams(
        audio_in_enabled=True,
        audio_out_enabled=True,
        vad_analyzer=SileroVADAnalyzer(),
    ),
}


async def run_bot(transport: BaseTransport):
    services = shared.create_services(
        stt_cls=ChaosDeepgramSTTService,
        tts_cls=ChaosCartesiaTTSService,
        llm_cls=ChaosOpenAILLMService,
    )
    stt, tts, llm = services

    llm.register_function("add_item_to_order", with_chaos(shared.add_item_to_order))
    llm.register_function(
        "remove_item_from_order", with_chaos(shared.remove_item_from_order)
    )
    llm.register_function("get_order_summary", with_chaos(shared.get_order_summary))
    llm.register_function("submit_order", with_chaos(shared.submit_order))
    shared.register_function_calls_started_handler(llm, tts)

    task = shared.build_pipeline(transport, services)

    @transport.event_handler("on_client_connected")
    async def on_client_connected(transport, client):
        logger.info("Client connected")
        await task.queue_frames([LLMRunFrame()])

    @transport.event_handler("on_client_disconnected")
    async def on_client_disconnected(transport, client):
        logger.info("Client disconnected")
        await task.cancel()

    runner = PipelineRunner(handle_sigint=False)
    await runner.run(task)


async def bot(runner_args: RunnerArguments):
    transport = await create_transport(runner_args, transport_params)
    await run_bot(transport)


if __name__ == "__main__":
    from pipecat.runner.run import main

    main()
