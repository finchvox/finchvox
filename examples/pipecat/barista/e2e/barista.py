import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from loguru import logger
from pipecat.audio.vad.silero import SileroVADAnalyzer
from pipecat.frames.frames import LLMRunFrame
from pipecat.pipeline.runner import PipelineRunner
from pipecat.processors.aggregators.llm_response_universal import (
    LLMUserAggregatorParams,
)
from pipecat.services.llm_service import FunctionCallParams
from pipecat.transports.daily.transport import DailyParams, DailyTransport

import shared

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


async def _handle_submit_order(params: FunctionCallParams, done_event: asyncio.Event):
    await asyncio.sleep(SIMULATED_DB_LATENCY)
    await shared.submit_order(params)
    name = params.arguments.get("customer_name", "friend")
    logger.info(f"Order submitted for {name}")
    done_event.set()


async def run_barista(room_url: str, token: str, done_event: asyncio.Event):
    transport = DailyTransport(
        room_url,
        token,
        "Barista",
        DailyParams(
            audio_in_enabled=True,
            audio_out_enabled=True,
            vad_analyzer=SileroVADAnalyzer(),
        ),
    )

    stt, tts, llm = shared.create_services()

    llm.register_function("add_item_to_order", add_item_to_order)
    llm.register_function("remove_item_from_order", remove_item_from_order)
    llm.register_function("get_order_summary", get_order_summary)
    llm.register_function(
        "submit_order", lambda params: _handle_submit_order(params, done_event)
    )
    shared.register_function_calls_started_handler(llm, tts)

    context_aggregator = shared.build_context_aggregator(
        user_params=LLMUserAggregatorParams(vad_analyzer=SileroVADAnalyzer()),
    )
    task = shared.build_pipeline(transport, stt, tts, llm, context_aggregator)

    @transport.event_handler("on_first_participant_joined")
    async def on_first_participant_joined(transport, participant):
        logger.info("Customer joined, barista greeting")
        await task.queue_frames([LLMRunFrame()])

    @transport.event_handler("on_participant_left")
    async def on_participant_left(transport, participant, reason):
        logger.info("Participant left, stopping barista")
        await task.cancel()

    runner = PipelineRunner(handle_sigint=False)
    await runner.run(task)
