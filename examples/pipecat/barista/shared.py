import os

from pipecat.adapters.schemas.function_schema import FunctionSchema
from pipecat.adapters.schemas.tools_schema import ToolsSchema
from pipecat.frames.frames import TTSSpeakFrame
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.task import PipelineParams, PipelineTask
from pipecat.processors.aggregators.llm_context import LLMContext
from pipecat.processors.aggregators.llm_response_universal import (
    LLMContextAggregatorPair,
)
from pipecat.services.cartesia.tts import CartesiaTTSService
from pipecat.services.deepgram.stt import DeepgramSTTService
from pipecat.services.llm_service import FunctionCallParams
from pipecat.services.openai.llm import OpenAILLMService

from finchvox import FinchvoxProcessor

CARTESIA_VOICE_ID = "f786b574-daa5-4673-aa0c-cbe3e8534c02"

TOOLS_SCHEMA = ToolsSchema(
    standard_tools=[
        FunctionSchema(
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
        ),
        FunctionSchema(
            name="remove_item_from_order",
            description="Remove an item from the customer's order",
            properties={
                "item": {
                    "type": "string",
                    "description": "The item to remove",
                },
            },
            required=["item"],
        ),
        FunctionSchema(
            name="get_order_summary",
            description="Get a summary of what's currently in the customer's order",
            properties={},
            required=[],
        ),
        FunctionSchema(
            name="submit_order",
            description="Submit the order for preparation. Call this when the customer is done ordering.",
            properties={
                "customer_name": {
                    "type": "string",
                    "description": "The customer's name for the order",
                },
            },
            required=["customer_name"],
        ),
    ]
)

SYSTEM_MESSAGES = [
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


def create_services(
    stt_cls=DeepgramSTTService,
    tts_cls=CartesiaTTSService,
    llm_cls=OpenAILLMService,
):
    stt = stt_cls(api_key=os.getenv("DEEPGRAM_API_KEY"))
    tts = tts_cls(
        api_key=os.getenv("CARTESIA_API_KEY"),
        voice_id=CARTESIA_VOICE_ID,
    )
    llm = llm_cls(
        api_key=os.getenv("OPENAI_API_KEY"),
        params=llm_cls.InputParams(temperature=0.5),
    )
    return stt, tts, llm


def register_function_calls_started_handler(llm, tts):
    @llm.event_handler("on_function_calls_started")
    async def on_function_calls_started(service, function_calls):
        await tts.queue_frame(TTSSpeakFrame("One sec."))


def build_context_aggregator(user_params=None):
    context = LLMContext(SYSTEM_MESSAGES, TOOLS_SCHEMA)
    return LLMContextAggregatorPair(context, user_params=user_params)


def build_pipeline(transport, stt, tts, llm, context_aggregator):
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

    return PipelineTask(
        pipeline,
        params=PipelineParams(
            enable_metrics=True,
            enable_usage_metrics=True,
        ),
        enable_tracing=True,
        enable_turn_tracking=True,
    )
