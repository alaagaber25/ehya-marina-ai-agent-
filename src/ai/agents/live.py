import logging
from collections.abc import AsyncGenerator, Callable
from dataclasses import dataclass
from enum import StrEnum, auto
from typing import Any, Literal, NotRequired, TypedDict

from google import genai
from google.genai.types import (
    AudioTranscriptionConfig,
    Blob,
    Content,
    EndSensitivity,
    FunctionResponse,
    LiveConnectConfig,
    SpeechConfig,  
    VoiceConfig,    
    PrebuiltVoiceConfig,  
    Modality,
    Part,
    RealtimeInputConfigOrDict,
    StartSensitivity,
)

logger = logging.getLogger(__name__)


class LiveAgentConfig(TypedDict):
    API_KEY: str
    MODEL: str
    SYSTEM_PROMPT: str
    ENABLE_TRANSCRIPTION: bool
    # Add VAD configuration options
    VAD_START_SENSITIVITY: NotRequired[Literal["low"] | Literal["high"]]
    VAD_END_SENSITIVITY: NotRequired[Literal["low"] | Literal["high"]]
    VAD_SILENCE_DURATION_MS: NotRequired[int]
    VAD_PREFIX_PADDING_MS: NotRequired[int]


class MessageType(StrEnum):
    TEXT = auto()
    AUDIO = auto()
    TOOL_CALL = auto()
    INPUT_TRANSCRIPTION = auto()
    OUTPUT_TRANSCRIPTION = auto()
    INTERRUPTION = auto()  # Add interruption message type
    TOOL_CALL_CANCELLED = auto()  # Add tool call cancellation
    TOOL_CALL_RESPONSE = auto()


@dataclass
class AgentMessage:
    type: MessageType
    data: Any
    metadata: dict[str, Any] | None = None


class LiveAgent:
    def __init__(self, config: LiveAgentConfig, tools: list[Callable[..., Any]]):
        self.__client = genai.Client(api_key=config.get("API_KEY"))

        # Build the live config with improved VAD settings
        audio_transcription_config = self.__get_transcroption_config(config)
        realtime_input_config = self.__get_realtime_input_config(config)
        voice_name = config.get("VOICE_NAME")
        if not voice_name:
            logger.warning(
                "VOICE_NAME not specified in config, using default voice."
            )
            voice_name = "Leda"  # Default voice if not specified
        self.__live_config = LiveConnectConfig(
            response_modalities=[Modality.AUDIO],
            speech_config=SpeechConfig(
                voice_config=VoiceConfig(
                    prebuilt_voice_config=PrebuiltVoiceConfig(
                        # You can specify a voice name here if needed
                        voice_name=voice_name
                    )
                )
            ),
            tools=tools,
            system_instruction=Content(
                parts=[Part.from_text(text=config.get("SYSTEM_PROMPT"))]
            ),
            input_audio_transcription=audio_transcription_config,
            output_audio_transcription=audio_transcription_config,
            realtime_input_config=realtime_input_config,  # type: ignore
        )

        self.__model = config.get("MODEL")
        self.__functions_to_call = {tool.__name__: tool for tool in tools}
        self._interrupted_tool_calls = set()  # Track interrupted tool calls

    @staticmethod
    def __get_transcroption_config(
        config: LiveAgentConfig,
    ):
        if config.get("ENABLE_TRANSCRIPTION"):
            return AudioTranscriptionConfig()
        return None

    @staticmethod
    def __get_realtime_input_config(config: LiveAgentConfig):
        """Configure VAD settings for better interruption handling"""
        vad_config: RealtimeInputConfigOrDict = {}

        # Map string values to enum values
        start_sensitivity_map = {
            "low": StartSensitivity.START_SENSITIVITY_LOW,
            "high": StartSensitivity.START_SENSITIVITY_HIGH,
        }

        end_sensitivity_map = {
            "low": EndSensitivity.END_SENSITIVITY_LOW,
            "high": EndSensitivity.END_SENSITIVITY_HIGH,
        }

        automatic_activity_detection = {}

        if start_sens := config.get("VAD_START_SENSITIVITY"):
            if start_sens in start_sensitivity_map:
                automatic_activity_detection["start_of_speech_sensitivity"] = (
                    start_sensitivity_map[start_sens]
                )

        if end_sens := config.get("VAD_END_SENSITIVITY"):
            if end_sens in end_sensitivity_map:
                automatic_activity_detection["end_of_speech_sensitivity"] = (
                    end_sensitivity_map[end_sens]
                )

        if prefix_padding := config.get("VAD_PREFIX_PADDING_MS"):
            automatic_activity_detection["prefix_padding_ms"] = prefix_padding

        if silence_duration := config.get("VAD_SILENCE_DURATION_MS"):
            automatic_activity_detection["silence_duration_ms"] = silence_duration

        if automatic_activity_detection:
            vad_config["automatic_activity_detection"] = automatic_activity_detection

        return vad_config if vad_config else None

    async def __aenter__(self):
        self.__session = self.__client.aio.live.connect(
            model=self.__model, config=self.__live_config
        )
        self._session = await self.__session.__aenter__()
        return self

    async def __aexit__(self, exc_type, exc_value, traceback):
        await self.__session.__aexit__(exc_type, exc_value, traceback)

    async def send_text(self, text: str):
        """Send text message with turn completion"""
        await self._session.send_client_content(
            turns=Content(role="user", parts=[Part(text=text)]),
            turn_complete=True,  # Explicitly mark turn as complete
        )

    async def send_audio(self, audio: bytes):
        """Send audio using realtime input for better VAD handling"""
        await self._session.send_realtime_input(
            audio=Blob(data=audio, mime_type="audio/pcm")
        )

    async def send_audio_stream_end(self):
        """Signal end of audio stream (important for VAD)"""
        await self._session.send_realtime_input(audio_stream_end=True)

    async def receive_message(self) -> AsyncGenerator[AgentMessage, None]:
        """Improved message receiving with proper interruption handling"""
        async for message in self._session.receive():
            # Handle server-side interruptions
            if message.server_content and message.server_content.interrupted:
                logger.info("Server detected interruption")
                yield AgentMessage(
                    type=MessageType.INTERRUPTION,
                    data=True,
                    metadata={"source": "server_vad"},
                )
                continue

            # Handle input transcription
            if message.server_content and message.server_content.input_transcription:
                yield AgentMessage(
                    type=MessageType.INPUT_TRANSCRIPTION,
                    data=message.server_content.input_transcription.text,
                )

            # Handle output transcription
            if message.server_content and message.server_content.output_transcription:
                yield AgentMessage(
                    type=MessageType.OUTPUT_TRANSCRIPTION,
                    data=message.server_content.output_transcription.text,
                )

            # Handle model content (text and audio)
            if (
                message.server_content
                and message.server_content.model_turn
                and message.server_content.model_turn.parts
            ):
                for part in message.server_content.model_turn.parts:
                    if part.text:
                        yield AgentMessage(type=MessageType.TEXT, data=part.text)
                    if part.inline_data and part.inline_data.data:
                        yield AgentMessage(
                            type=MessageType.AUDIO,
                            data=part.inline_data.data,
                        )

            # Handle direct text messages
            if message.text:
                yield AgentMessage(type=MessageType.TEXT, data=message.text)

            # Handle tool calls
            if message.tool_call and message.tool_call.function_calls:
                function_responses: list[FunctionResponse] = []
                for fc in message.tool_call.function_calls:
                    # Skip if this tool call was already cancelled
                    if fc.id in self._interrupted_tool_calls:
                        continue

                    if fc.name in self.__functions_to_call:
                        if fc.args is None:
                            fc.args = {}
                        try:
                            response = self.__functions_to_call[fc.name](**fc.args)
                            function_response = FunctionResponse(
                                name=fc.name, response=response, id=fc.id
                            )
                            yield AgentMessage(
                                type=MessageType.TOOL_CALL_RESPONSE,
                                data=response,
                            )
                            function_responses.append(function_response)
                        except Exception as e:
                            logger.error(f"Tool call {fc.name} failed: {e}")

                if function_responses:
                    await self._session.send_tool_response(
                        function_responses=function_responses
                    )

            # Handle tool call cancellations
            if message.tool_call_cancellation and message.tool_call_cancellation.ids:
                cancelled_ids = list(message.tool_call_cancellation.ids)
                self._interrupted_tool_calls.update(cancelled_ids)
                logger.info(f"Tool calls cancelled: {cancelled_ids}")
                yield AgentMessage(
                    type=MessageType.TOOL_CALL_CANCELLED,
                    data=cancelled_ids,
                    metadata={"reason": "interruption"},
                )
