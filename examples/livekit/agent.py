import finchvox
from dotenv import load_dotenv
from finchvox.livekit import on_session_end
from livekit.agents import Agent, AgentServer, AgentSession, JobContext, inference

load_dotenv()

# Finchvox line 1: send traces and logs to the local Finchvox server.
finchvox.init_livekit(
    service_name="livekit-agent",
    metadata={"agent.version": "1.0.0"},
    allow_pii=True,  # Local replay: transcript/tool/response content is visible.
)


class VoiceAgent(Agent):
    def __init__(self) -> None:
        super().__init__(
            instructions="You are a helpful voice assistant. Keep responses brief and conversational.",
            stt=inference.STT(model="deepgram/nova-3"),
            llm=inference.LLM(model="google/gemma-4-31b-it"),
            tts=inference.TTS(model="cartesia/sonic-3"),
        )

    async def on_enter(self):
        self.session.generate_reply(instructions="Greet the user warmly.")


server = AgentServer()


# Finchvox line 2: when the session ends, send its report and recording too.
@server.rtc_session(on_session_end=on_session_end)
async def entrypoint(ctx: JobContext):
    # AgentSession uses LiveKit's bundled Silero VAD by default.
    session = AgentSession()
    await session.start(agent=VoiceAgent(), room=ctx.room)


# Launch with `python -m livekit.agents start agent.py` or `lk agent dev`.
# The legacy cli.run_app()/`python agent.py dev` interface is deprecated.
