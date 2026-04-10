import asyncio
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
from loguru import logger
from pipecat.audio.vad.silero import SileroVADAnalyzer
from pipecat.frames.frames import LLMRunFrame
from pipecat.pipeline.runner import PipelineRunner
from pipecat.processors.aggregators.llm_response_universal import (
    LLMUserAggregatorParams,
)
from pipecat.runner.types import RunnerArguments
from pipecat.runner.utils import create_transport
from pipecat.services.llm_service import FunctionCallParams
from pipecat.transports.base_transport import BaseTransport, TransportParams
from pipecat.transports.daily.transport import DailyParams
from pipecat.transports.websocket.fastapi import FastAPIWebsocketParams

import finchvox
import shared

load_dotenv(override=True)

finchvox.init(service_name="pipecat-demo")

SIMULATED_DB_LATENCY = 0.2


async def add_item_to_order(params: FunctionCallParams):
    await asyncio.sleep(SIMULATED_DB_LATENCY)
    await shared.add_item_to_order(params)


async def remove_item_from_order(params: FunctionCallParams):
    await asyncio.sleep(SIMULATED_DB_LATENCY)
    await shared.remove_item_from_order(params)


async def get_order_summary(params: FunctionCallParams):
    await asyncio.sleep(SIMULATED_DB_LATENCY)
    await shared.get_order_summary(params)


async def submit_order(params: FunctionCallParams):
    await asyncio.sleep(SIMULATED_DB_LATENCY)
    await shared.submit_order(params)


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
    services = shared.create_services()
    stt, tts, llm = services

    llm.register_function("add_item_to_order", add_item_to_order)
    llm.register_function("remove_item_from_order", remove_item_from_order)
    llm.register_function("get_order_summary", get_order_summary)
    llm.register_function("submit_order", submit_order)
    shared.register_function_calls_started_handler(llm, tts)

    task = shared.build_pipeline(
        transport,
        services,
        user_params=LLMUserAggregatorParams(vad_analyzer=SileroVADAnalyzer()),
    )

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
