"""Drives the installed LiveKit SDK's own observability uploaders against a URL.

Run as a separate process by tests/test_livekit_observability_url.py: LiveKit's
setup installs global OpenTelemetry providers, which must not leak into other
tests. It follows a real job's order: spans and logs during the call, the
recording upload at session end, then LiveKit's per-job flush.

Args: observability_url job_id audio_path
"""

import asyncio
import logging
import sys
import time
from pathlib import Path

import aiohttp
from livekit.agents import AgentSession, llm
from livekit.agents.observability import Tagger
from livekit.agents.telemetry import traces
from livekit.agents.voice.report import SessionReport

url, job_id, audio_path = sys.argv[1], sys.argv[2], Path(sys.argv[3])
room_id = "RM_compat"

traces._setup_cloud_tracer(room_id=room_id, job_id=job_id, observability_url=url)

with (
    traces.tracer.start_as_current_span("agent_session"),
    traces.tracer.start_as_current_span("agent_turn"),
):
    logging.getLogger("compat-agent").warning("hello from the agent")


async def end_session() -> None:
    chat = llm.ChatContext()
    chat.add_message(role="user", content="hello")
    chat.add_message(role="assistant", content="hi there")
    session = AgentSession(vad=None)
    session._opts.recording_options = {
        "audio": True,
        "traces": True,
        "logs": True,
        "transcript": True,
    }
    now = time.time()
    report = SessionReport(
        job_id=job_id,
        room_id=room_id,
        room="compat-room",
        options=session._opts,
        events=[],
        chat_history=chat,
        audio_recording_path=audio_path,
        audio_recording_started_at=now - 5,
        duration=5.0,
        started_at=now - 5,
    )
    async with aiohttp.ClientSession() as http:
        await traces._upload_session_report(
            agent_name="compat",
            observability_url=url,
            report=report,
            tagger=Tagger(),
            http_session=http,
        )


asyncio.run(end_session())
traces._shutdown_telemetry(job_id)
print("uploaded")
