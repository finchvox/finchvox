import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from loguru import logger
from pipecat.audio.vad.silero import SileroVADAnalyzer
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.runner import PipelineRunner
from pipecat.pipeline.task import PipelineParams, PipelineTask
from pipecat.processors.aggregators.llm_context import LLMContext
from pipecat.processors.aggregators.llm_response_universal import (
    LLMContextAggregatorPair,
    LLMUserAggregatorParams,
)
from pipecat.services.cartesia.tts import CartesiaTTSService
from pipecat.services.deepgram.stt import DeepgramSTTService
from pipecat.services.openai.llm import OpenAILLMService
from pipecat.transports.daily.transport import DailyParams, DailyTransport

SYSTEM_MESSAGES = [
    {
        "role": "system",
        "content": """You are a customer at a coffee shop placing an order. You want exactly:
1. A large oat milk latte with an extra shot
2. A blueberry muffin

Be direct and concise. When the barista asks for your name, say Alex.
Do not ask questions about the menu. Do not change your order.
Keep responses to one or two short sentences.
When the barista confirms your order is submitted, say thanks and goodbye.
Your output will be converted to audio so don't include special characters.""",
    },
]


async def run_customer(room_url: str, token: str):
    transport = DailyTransport(
        room_url,
        token,
        "Customer",
        DailyParams(
            audio_in_enabled=True,
            audio_out_enabled=True,
            vad_analyzer=SileroVADAnalyzer(),
        ),
    )

    stt = DeepgramSTTService(api_key=os.getenv("DEEPGRAM_API_KEY"))
    tts = CartesiaTTSService(
        api_key=os.getenv("CARTESIA_API_KEY"),
        voice_id="a0e99841-438c-4a64-b679-ae501e7d6091",
    )
    llm = OpenAILLMService(
        api_key=os.getenv("OPENAI_API_KEY"),
        params=OpenAILLMService.InputParams(temperature=0.3),
    )

    context = LLMContext(SYSTEM_MESSAGES)
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
            context_aggregator.assistant(),
        ]
    )

    task = PipelineTask(
        pipeline,
        params=PipelineParams(
            enable_metrics=False,
            enable_usage_metrics=False,
        ),
        enable_tracing=False,
    )

    @transport.event_handler("on_participant_left")
    async def on_participant_left(transport, participant, reason):
        logger.info("Barista left, stopping customer")
        await task.cancel()

    runner = PipelineRunner(handle_sigint=False)
    await runner.run(task)
