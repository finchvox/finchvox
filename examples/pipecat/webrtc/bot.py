#
# Copyright (c) 2024–2025, Daily
#
# SPDX-License-Identifier: BSD 2-Clause License
#

import os

from dotenv import load_dotenv
from loguru import logger
from pipecat.adapters.schemas.function_schema import FunctionSchema
from pipecat.adapters.schemas.tools_schema import ToolsSchema
from pipecat.audio.vad.silero import SileroVADAnalyzer
from pipecat.frames.frames import LLMRunFrame, TTSSpeakFrame
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.runner import PipelineRunner
from pipecat.pipeline.task import PipelineParams, PipelineTask
from pipecat.processors.aggregators.llm_context import LLMContext
from pipecat.processors.aggregators.llm_response_universal import (
    LLMContextAggregatorPair,
    LLMUserAggregatorParams,
)
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
from finchvox import FinchvoxProcessor

load_dotenv(override=True)

finchvox.init(service_name="pipecat-demo")


async def add_item_to_order(params: FunctionCallParams):
    item = params.arguments.get("item", "item")
    size = params.arguments.get("size", "")
    modifications = params.arguments.get("modifications", [])
    description = f"{size} {item}".strip()
    if modifications:
        description += f" with {', '.join(modifications)}"
    await params.result_callback({"success": True, "item": description})


async def remove_item_from_order(params: FunctionCallParams):
    item = params.arguments.get("item", "item")
    await params.result_callback({"success": True, "removed": item})


async def get_order_summary(params: FunctionCallParams):
    await params.result_callback(
        {"items": ["medium oat latte", "blueberry muffin"], "item_count": 2}
    )


async def submit_order(params: FunctionCallParams):
    name = params.arguments.get("customer_name", "friend")
    await params.result_callback({"success": True, "order_number": 47, "name": name})


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


def _build_tools_schema() -> ToolsSchema:
    add_item_schema = FunctionSchema(
        name="add_item_to_order",
        description="Add an item to the customer's order",
        properties={
            "item": {
                "type": "string",
                "description": "The item being ordered (e.g., latte, cappuccino, blueberry muffin)",
            },
            "size": {
                "type": "string",
                "enum": ["small", "medium", "large"],
                "description": "Size of the drink if applicable",
            },
            "modifications": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Modifications like 'oat milk', 'extra shot', 'no foam'",
            },
        },
        required=["item"],
    )

    remove_item_schema = FunctionSchema(
        name="remove_item_from_order",
        description="Remove an item from the customer's order",
        properties={
            "item": {
                "type": "string",
                "description": "The item to remove",
            },
        },
        required=["item"],
    )

    get_order_summary_schema = FunctionSchema(
        name="get_order_summary",
        description="Get a summary of what's currently in the customer's order",
        properties={},
        required=[],
    )

    submit_order_schema = FunctionSchema(
        name="submit_order",
        description="Submit the order for preparation. Call this when the customer is done ordering.",
        properties={
            "customer_name": {
                "type": "string",
                "description": "The customer's name for the order",
            },
        },
        required=["customer_name"],
    )

    return ToolsSchema(
        standard_tools=[
            add_item_schema,
            remove_item_schema,
            get_order_summary_schema,
            submit_order_schema,
        ]
    )


def _build_system_messages() -> list[dict]:
    return [
        {
            "role": "system",
            "content": """You are Sam, a friendly barista at a cozy neighborhood coffee shop. You're warm and welcoming but efficient - you keep conversations moving without being rushed.

Your menu includes:
- Coffee drinks: espresso, lattes, cappuccinos, americanos, mochas, cold brew, drip coffee
- Tea: green, black, chai, herbal (hot or iced)
- Pastries: muffins, croissants, scones, cookies
- Food: bagels, breakfast sandwiches, turkey or veggie sandwiches

Behavior:
- Greet customers warmly and ask what they'd like
- Use the order tools to manage their order - don't just pretend
- Ask clarifying questions when needed (size, hot/iced, milk preference)
- Only suggest options or describe items when the customer asks - no unsolicited upselling
- Keep responses short and natural since this is a voice conversation
- When the customer is done, ask for their name and submit the order

Your output will be converted to audio so don't include special characters. Be conversational and brief.""",
        },
    ]


def _create_services():
    stt = DeepgramSTTService(api_key=os.getenv("DEEPGRAM_API_KEY"))

    tts = CartesiaTTSService(
        api_key=os.getenv("CARTESIA_API_KEY"),
        voice_id="f786b574-daa5-4673-aa0c-cbe3e8534c02",
    )

    llm = OpenAILLMService(
        api_key=os.getenv("OPENAI_API_KEY"),
        params=OpenAILLMService.InputParams(temperature=0.5),
    )

    return stt, tts, llm


def _register_llm_tools(llm, tts):
    llm.register_function("add_item_to_order", add_item_to_order)
    llm.register_function("remove_item_from_order", remove_item_from_order)
    llm.register_function("get_order_summary", get_order_summary)
    llm.register_function("submit_order", submit_order)

    @llm.event_handler("on_function_calls_started")
    async def on_function_calls_started(service, function_calls):
        await tts.queue_frame(TTSSpeakFrame("One sec."))


async def run_bot(transport: BaseTransport):
    stt, tts, llm = _create_services()
    _register_llm_tools(llm, tts)

    tools = _build_tools_schema()
    messages = _build_system_messages()

    context = LLMContext(messages, tools)
    context_aggregator = LLMContextAggregatorPair(
        context,
        user_params=LLMUserAggregatorParams(vad_analyzer=SileroVADAnalyzer()),
    )

    pipeline = Pipeline(
        [
            transport.input(),
            stt,
            context_aggregator.user(),
            llm,
            tts,
            transport.output(),
            FinchvoxProcessor(),
            context_aggregator.assistant(),
        ]
    )

    task = PipelineTask(
        pipeline,
        params=PipelineParams(
            enable_metrics=True,
            enable_usage_metrics=True,
        ),
        enable_tracing=True,
        enable_turn_tracking=True,
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
    """Main bot entry point compatible with Pipecat Cloud."""
    transport = await create_transport(runner_args, transport_params)
    await run_bot(transport)


if __name__ == "__main__":
    from pipecat.runner.run import main

    main()
