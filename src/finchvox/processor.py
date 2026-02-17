import asyncio
import io
import json
import wave
from datetime import datetime
from typing import TYPE_CHECKING, Optional

import aiohttp
from loguru import logger
from opentelemetry import trace
from pipecat.frames.frames import (
    CancelFrame,
    EndFrame,
    Frame,
    InputAudioRawFrame,
    OutputAudioRawFrame,
    StartFrame,
)
from pipecat.processors.audio.audio_buffer_processor import AudioBufferProcessor
from pipecat.processors.frame_processor import (
    FrameDirection,
    FrameProcessor,
    FrameProcessorSetup,
)

from finchvox.compat import HAS_NEW_TRACING_API

if TYPE_CHECKING:
    from pipecat.utils.tracing.tracing_context import TracingContext

if not HAS_NEW_TRACING_API:
    from pipecat.utils.tracing.conversation_context_provider import (
        ConversationContextProvider,
    )


def _is_finchvox_initialized() -> bool:
    import finchvox

    return finchvox._initialized


class FinchvoxProcessor(FrameProcessor):
    """Pipecat processor that captures conversation audio and uploads it to Finchvox.

    Place this processor after ``transport.output()`` in your pipeline. It records
    both user and bot audio in stereo WAV chunks and uploads them to the Finchvox
    collector for playback and debugging in the web UI.

    Requires ``finchvox.init()`` to be called before the pipeline starts and
    ``enable_tracing=True`` on the ``PipelineTask``.

    Example::

        import finchvox

        finchvox.init(service_name="my-bot")

        pipeline = Pipeline([
            transport.input(),
            stt,
            llm,
            tts,
            transport.output(),
            finchvox.FinchvoxProcessor(),
        ])
    """

    def __init__(
        self,
        endpoint: str = "http://localhost:3000",
        chunk_duration_seconds: int = 5,
        sample_rate: int = 16000,
    ):
        """Create a new FinchvoxProcessor.

        Args:
            endpoint: URL of the Finchvox HTTP server.
            chunk_duration_seconds: Duration of each audio chunk uploaded.
            sample_rate: Audio sample rate in Hz.
        """
        super().__init__()
        self._endpoint = endpoint
        self._chunk_duration = chunk_duration_seconds
        self._sample_rate = sample_rate

        self._audio_buffer: Optional[AudioBufferProcessor] = None
        self._disabled = False
        self._collector_warning_shown = False
        self._timing_events = []
        self._conversation_start_time: Optional[datetime] = None
        self._chunk_counter = 0
        self._setup_info: Optional[FrameProcessorSetup] = None
        self._input_frame_count = 0
        self._tracing_context: Optional["TracingContext"] = None

    async def setup(self, setup: FrameProcessorSetup):
        await super().setup(setup)
        self._setup_info = setup

    async def process_frame(self, frame: Frame, direction: FrameDirection):
        await super().process_frame(frame, direction)

        if isinstance(frame, StartFrame):
            await self._handle_start_frame(frame)
        elif isinstance(frame, (EndFrame, CancelFrame)):
            await self._handle_end_frame(frame)

        if self._audio_buffer and not self._disabled:
            await self._process_audio_frame(frame, direction)

        await self.push_frame(frame, direction)

    async def _process_audio_frame(self, frame: Frame, direction: FrameDirection):
        if isinstance(
            frame,
            (
                StartFrame,
                InputAudioRawFrame,
                OutputAudioRawFrame,
                EndFrame,
                CancelFrame,
            ),
        ):
            await self._audio_buffer.process_frame(frame, direction)

        if isinstance(frame, InputAudioRawFrame):
            self._input_frame_count += 1
            if self._input_frame_count % 100 == 0:
                user_mb = len(self._audio_buffer._user_audio_buffer) / 1024 / 1024
                bot_mb = len(self._audio_buffer._bot_audio_buffer) / 1024 / 1024
                logger.debug(
                    f"Audio frame #{self._input_frame_count}: "
                    f"user_buffer={user_mb:.2f}MB, "
                    f"bot_buffer={bot_mb:.2f}MB"
                )

    async def _handle_start_frame(self, frame: StartFrame):
        if not _is_finchvox_initialized():
            logger.error(
                "finchvox.init() was not called before pipeline started. "
                "Call finchvox.init(service_name='your-app') early in your application."
            )
            self._disabled = True
            return

        if not frame.enable_tracing:
            logger.error(
                "FinchvoxProcessor requires tracing to be enabled. "
                "Add enable_tracing=True to your PipelineTask."
            )
            self._disabled = True
            return

        if HAS_NEW_TRACING_API:
            self._tracing_context = getattr(frame, "tracing_context", None)
            if self._tracing_context:
                import finchvox

                finchvox.set_tracing_context(self._tracing_context)

        self._audio_buffer = AudioBufferProcessor(
            sample_rate=self._sample_rate,
            num_channels=2,
            buffer_size=320000,
            enable_turn_audio=False,
        )
        self._setup_audio_handler()

        await self._audio_buffer.setup(self._setup_info)

        self._conversation_start_time = datetime.now()
        self._chunk_counter = 0
        self._timing_events = []
        self._input_frame_count = 0

        await self._audio_buffer.start_recording()
        logger.info("FinchvoxProcessor: Started audio recording")

    def _setup_audio_handler(self):
        @self._audio_buffer.event_handler("on_audio_data")
        async def on_audio_data(buffer, audio, sample_rate, num_channels):
            if self._disabled:
                return

            try:
                trace_id = self._get_trace_id()

                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                metadata = {
                    "trace_id": trace_id,
                    "chunk_number": self._chunk_counter,
                    "timestamp": timestamp,
                    "sample_rate": sample_rate,
                    "num_channels": num_channels,
                    "channels": {"0": "user", "1": "bot"},
                    "timing_events": self._timing_events,
                    "conversation_start": (
                        self._conversation_start_time.isoformat()
                        if self._conversation_start_time
                        else None
                    ),
                }

                upload_success = await self._upload_chunk(
                    trace_id=trace_id,
                    chunk_number=self._chunk_counter,
                    audio_data=audio,
                    metadata=metadata,
                )

                if upload_success:
                    logger.info(
                        f"Uploaded audio chunk {self._chunk_counter} for trace {trace_id[:8]}... "
                        f"({len(self._timing_events)} timing events)"
                    )
                else:
                    logger.error(
                        f"Failed to upload chunk {self._chunk_counter} for trace {trace_id[:8]}..."
                    )

                self._chunk_counter += 1

                if len(self._timing_events) > 100:
                    self._timing_events = self._timing_events[-50:]

            except Exception as e:
                logger.error(f"Failed to process audio chunk: {e}", exc_info=True)

    def _extract_trace_id_from_context(self, ctx) -> Optional[str]:
        if not ctx:
            return None
        span = trace.get_current_span(ctx)
        span_context = span.get_span_context()
        if span_context.trace_id == 0:
            return None
        return format(span_context.trace_id, "032x")

    def _get_trace_id(self) -> str:
        try:
            if HAS_NEW_TRACING_API:
                ctx = (
                    self._tracing_context.get_conversation_context()
                    if self._tracing_context
                    else None
                )
            else:
                provider = ConversationContextProvider.get_instance()
                ctx = provider.get_current_conversation_context()
            trace_id = self._extract_trace_id_from_context(ctx)
            if trace_id:
                return trace_id
        except Exception:
            pass
        return "no_trace"

    async def _upload_chunk(
        self,
        trace_id: str,
        chunk_number: int,
        audio_data: bytes,
        metadata: dict,
    ) -> bool:
        try:
            url = f"{self._endpoint}/collector/audio/{trace_id}/chunk"

            wav_buffer = io.BytesIO()
            with wave.open(wav_buffer, "wb") as wav_file:
                wav_file.setnchannels(metadata["num_channels"])
                wav_file.setsampwidth(2)
                wav_file.setframerate(metadata["sample_rate"])
                wav_file.writeframes(audio_data)

            wav_mb = wav_buffer.tell() / 1024 / 1024
            logger.debug(f"Uploading chunk {chunk_number}: {wav_mb:.2f}MB")

            wav_buffer.seek(0)

            async with aiohttp.ClientSession() as session:
                form = aiohttp.FormData()
                form.add_field(
                    "audio",
                    wav_buffer,
                    filename=f"chunk_{chunk_number:04d}.wav",
                    content_type="audio/wav",
                )
                form.add_field(
                    "metadata",
                    json.dumps(metadata),
                    content_type="application/json",
                )

                async with session.post(
                    url,
                    data=form,
                    timeout=aiohttp.ClientTimeout(total=30),
                ) as response:
                    if response.status == 201:
                        return True
                    else:
                        error_text = await response.text()
                        logger.error(
                            f"Failed to upload chunk {chunk_number}: "
                            f"HTTP {response.status}: {error_text}"
                        )
                        return False

        except aiohttp.ClientConnectorError:
            if not self._collector_warning_shown:
                logger.warning(
                    f"Could not reach finchvox collector at {self._endpoint}. "
                    "Is the finchvox server running? (uv run finchvox start)"
                )
                self._collector_warning_shown = True
            return False
        except asyncio.TimeoutError:
            logger.error(f"Timeout uploading chunk {chunk_number} to endpoint")
            return False
        except Exception as e:
            logger.error(
                f"Error uploading chunk {chunk_number} to endpoint: {e}",
                exc_info=True,
            )
            return False

    async def _handle_end_frame(self, frame: Frame):
        if self._disabled or self._audio_buffer is None:
            return

        await self._audio_buffer.stop_recording()
        logger.info(
            f"FinchvoxProcessor: Stopped audio recording. Captured {self._chunk_counter} chunks "
            f"with {len(self._timing_events)} timing events"
        )

    def add_timing_event(self, event_type: str, metadata: dict = None):
        event = {
            "type": event_type,
            "timestamp": datetime.now().isoformat(),
            "relative_time": (
                (datetime.now() - self._conversation_start_time).total_seconds()
                if self._conversation_start_time
                else 0
            ),
            "metadata": metadata or {},
        }
        self._timing_events.append(event)
        logger.debug(f"Timing event: {event_type}")
