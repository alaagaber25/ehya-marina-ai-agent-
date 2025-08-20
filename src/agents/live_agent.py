import logging
from collections.abc import AsyncGenerator, Callable
from dataclasses import dataclass
from enum import StrEnum, auto
from typing import Any, Literal, NotRequired, TypedDict
import json

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
    VAD_START_SENSITIVITY: NotRequired[Literal["low"] | Literal["high"]]
    VAD_END_SENSITIVITY: NotRequired[Literal["low"] | Literal["high"]]
    VAD_SILENCE_DURATION_MS: NotRequired[int]
    VAD_PREFIX_PADDING_MS: NotRequired[int]
    DIALECT: NotRequired[str]


class MessageType(StrEnum):
    TEXT = auto()
    AUDIO = auto()
    TOOL_CALL = auto()
    INPUT_TRANSCRIPTION = auto()
    OUTPUT_TRANSCRIPTION = auto()
    INTERRUPTION = auto()
    TOOL_CALL_CANCELLED = auto()
    TOOL_CALL_RESPONSE = auto()


@dataclass
class AgentMessage:
    type: MessageType
    data: Any
    metadata: dict[str, Any] | None = None


class LiveAgent:
    def __init__(self, config: LiveAgentConfig, tools: list[Callable[..., Any]]):
        self.__client = genai.Client(api_key=config.get("API_KEY"))
        self.__dialect = config.get("DIALECT")

        # Build the live config with improved VAD settings
        audio_transcription_config = self.__get_transcroption_config(config)
        realtime_input_config = self.__get_realtime_input_config(config)
        voice_name = config.get("VOICE_NAME")
        if not voice_name:
            logger.warning("VOICE_NAME not specified in config, using default voice.")
            
        self.__live_config = LiveConnectConfig(
            response_modalities=[Modality.AUDIO],
            speech_config=SpeechConfig(
                voice_config=VoiceConfig(
                    prebuilt_voice_config=PrebuiltVoiceConfig(
                        voice_name=voice_name
                    )
                ),
            ),
            tools=tools,
            system_instruction=Content(
                parts=[Part.from_text(text=config.get("SYSTEM_PROMPT"))]
            ),
            input_audio_transcription=audio_transcription_config,
            output_audio_transcription=audio_transcription_config,
            realtime_input_config=realtime_input_config,
        )

        self.__model = config.get("MODEL")
        self.__functions_to_call = {tool.__name__: tool for tool in tools}
        self._interrupted_tool_calls = set()

    @staticmethod
    def __get_transcroption_config(config: LiveAgentConfig):
        if config.get("ENABLE_TRANSCRIPTION"):
            return AudioTranscriptionConfig()
        return None

    @staticmethod
    def __get_realtime_input_config(config: LiveAgentConfig):
        """Configure VAD settings for better interruption handling"""
        vad_config: RealtimeInputConfigOrDict = {}

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
        await self._session.close()
        await self.__session.__aexit__(exc_type, exc_value, traceback)

    async def send_text(self, text: str):
        """Send text message with turn completion"""
        await self._session.send_client_content(
            turns=Content(role="user", parts=[Part(text=text)]),
            turn_complete=True,
        )

    async def send_audio(self, audio: bytes):
        """Send audio using realtime input for better VAD handling"""
        await self._session.send_realtime_input(
            audio=Blob(data=audio, mime_type="audio/pcm")
        )

    async def send_audio_stream_end(self):
        """Signal end of audio stream (important for VAD)"""
        await self._session.send_realtime_input(audio_stream_end=True)

    def _create_error_response(self, error_msg: str, tool_name: str) -> dict:
        """Create standardized error response for tool failures"""
        return {
            "action": "finalize_response",
            "action_input": {
                "action": "answer",
                "action_data": None,
                "responseText": f"I encountered an issue while processing your request. Please try again or contact support if the problem persists."
            }
        }

    async def receive_message(self) -> AsyncGenerator[AgentMessage, None]:
        """Improved message receiving with proper interruption and error handling"""
        
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

            # Handle tool calls with improved error handling
            if message.tool_call and message.tool_call.function_calls:
                function_responses: list[FunctionResponse] = []
                
                for fc in message.tool_call.function_calls:
                    # Skip if this tool call was already cancelled
                    if fc.id in self._interrupted_tool_calls:
                        logger.info(f"Skipping cancelled tool call: {fc.id}")
                        continue

                    if fc.name in self.__functions_to_call:
                        try:
                            # Prepare arguments
                            if fc.args is None:
                                fc.args = {}
                            
                            # Add dialect info if not present
                            if 'dialect' not in fc.args and self.__dialect:
                                fc.args['dialect'] = self.__dialect
                            if 'original_dialect' not in fc.args and self.__dialect:
                                fc.args['original_dialect'] = self.__dialect

                            logger.info(f"Calling tool: {fc.name} with args: {fc.args}")
                            
                            # Execute tool
                            tool_output = self.__functions_to_call[fc.name](**fc.args)
                            
                            # Standardize tool output
                            if isinstance(tool_output, dict):
                                response_payload = tool_output
                            else:
                                response_payload = {"result": tool_output}

                            # Create function response
                            function_response = FunctionResponse(
                                name=fc.name, 
                                response=response_payload, 
                                id=fc.id
                            )

                            # Yield to client
                            yield AgentMessage(
                                type=MessageType.TOOL_CALL_RESPONSE,
                                data=response_payload,
                            )

                            function_responses.append(function_response)
                            logger.info(f"Tool {fc.name} executed successfully")

                        except Exception as e:
                            logger.error(f"Tool call {fc.name} failed: {e}")
                            
                            # Create error response
                            error_response = self._create_error_response(str(e), fc.name)
                            
                            function_response = FunctionResponse(
                                name=fc.name, 
                                response=error_response, 
                                id=fc.id
                            )

                            yield AgentMessage(
                                type=MessageType.TOOL_CALL_RESPONSE,
                                data=error_response,
                            )

                            function_responses.append(function_response)
                    else:
                        logger.warning(f"Unknown tool called: {fc.name}")
                        
                        # Handle unknown tool
                        error_response = self._create_error_response(
                            f"Unknown tool: {fc.name}", fc.name
                        )
                        
                        function_response = FunctionResponse(
                            name=fc.name, 
                            response=error_response, 
                            id=fc.id
                        )
                        
                        function_responses.append(function_response)

                # Send all function responses back to the model
                if function_responses:
                    try:
                        await self._session.send_tool_response(
                            function_responses=function_responses
                        )
                        logger.info(f"Sent {len(function_responses)} tool responses")
                    except Exception as e:
                        logger.error(f"Failed to send tool responses: {e}")

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

import logging
from collections.abc import AsyncGenerator, Callable
from dataclasses import dataclass
from enum import StrEnum, auto
from typing import Any, Literal, NotRequired, TypedDict
import json

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
    VAD_START_SENSITIVITY: NotRequired[Literal["low"] | Literal["high"]]
    VAD_END_SENSITIVITY: NotRequired[Literal["low"] | Literal["high"]]
    VAD_SILENCE_DURATION_MS: NotRequired[int]
    VAD_PREFIX_PADDING_MS: NotRequired[int]
    DIALECT: NotRequired[str]


class MessageType(StrEnum):
    TEXT = auto()
    AUDIO = auto()
    TOOL_CALL = auto()
    INPUT_TRANSCRIPTION = auto()
    OUTPUT_TRANSCRIPTION = auto()
    INTERRUPTION = auto()
    TOOL_CALL_CANCELLED = auto()
    TOOL_CALL_RESPONSE = auto()


@dataclass
class AgentMessage:
    type: MessageType
    data: Any
    metadata: dict[str, Any] | None = None


class LiveAgent:
    def __init__(self, config: LiveAgentConfig, tools: list[Callable[..., Any]]):
        self.__client = genai.Client(api_key=config.get("API_KEY"))
        self.__dialect = config.get("DIALECT")

        # Build the live config with improved VAD settings
        audio_transcription_config = self.__get_transcroption_config(config)
        realtime_input_config = self.__get_realtime_input_config(config)
        voice_name = config.get("VOICE_NAME")
        if not voice_name:
            logger.warning("VOICE_NAME not specified in config, using default voice.")
            
        self.__live_config = LiveConnectConfig(
            response_modalities=[Modality.AUDIO],
            speech_config=SpeechConfig(
                voice_config=VoiceConfig(
                    prebuilt_voice_config=PrebuiltVoiceConfig(
                        voice_name=voice_name
                    )
                ),
            ),
            tools=tools,
            system_instruction=Content(
                parts=[Part.from_text(text=config.get("SYSTEM_PROMPT"))]
            ),
            input_audio_transcription=audio_transcription_config,
            output_audio_transcription=audio_transcription_config,
            realtime_input_config=realtime_input_config,
        )

        self.__model = config.get("MODEL")
        self.__functions_to_call = {tool.__name__: tool for tool in tools}
        self._interrupted_tool_calls = set()

    @staticmethod
    def __get_transcroption_config(config: LiveAgentConfig):
        if config.get("ENABLE_TRANSCRIPTION"):
            return AudioTranscriptionConfig()
        return None

    @staticmethod
    def __get_realtime_input_config(config: LiveAgentConfig):
        """Configure VAD settings for better interruption handling"""
        vad_config: RealtimeInputConfigOrDict = {}

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
        await self._session.close()
        await self.__session.__aexit__(exc_type, exc_value, traceback)

    async def send_text(self, text: str):
        """Send text message with turn completion"""
        await self._session.send_client_content(
            turns=Content(role="user", parts=[Part(text=text)]),
            turn_complete=True,
        )

    async def send_audio(self, audio: bytes):
        """Send audio using realtime input for better VAD handling"""
        await self._session.send_realtime_input(
            audio=Blob(data=audio, mime_type="audio/pcm")
        )

    async def send_audio_stream_end(self):
        """Signal end of audio stream (important for VAD)"""
        await self._session.send_realtime_input(audio_stream_end=True)

    def _create_error_response(self, error_msg: str, tool_name: str) -> dict:
        """Create standardized error response for tool failures"""
        return {
            "action": "finalize_response",
            "action_input": {
                "action": "answer",
                "action_data": None,
                "responseText": f"I encountered an issue while processing your request. Please try again or contact support if the problem persists."
            }
        }

    async def receive_message(self) -> AsyncGenerator[AgentMessage, None]:
        """Improved message receiving with proper interruption and error handling"""
        
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

            # Handle tool calls with improved error handling
            if message.tool_call and message.tool_call.function_calls:
                function_responses: list[FunctionResponse] = []
                
                for fc in message.tool_call.function_calls:
                    # Skip if this tool call was already cancelled
                    if fc.id in self._interrupted_tool_calls:
                        logger.info(f"Skipping cancelled tool call: {fc.id}")
                        continue

                    if fc.name in self.__functions_to_call:
                        try:
                            # Prepare arguments
                            if fc.args is None:
                                fc.args = {}
                            
                            # Add dialect info if not present
                            if 'dialect' not in fc.args and self.__dialect:
                                fc.args['dialect'] = self.__dialect
                            if 'original_dialect' not in fc.args and self.__dialect:
                                fc.args['original_dialect'] = self.__dialect

                            logger.info(f"Calling tool: {fc.name} with args: {fc.args}")
                            
                            # Execute tool
                            tool_output = self.__functions_to_call[fc.name](**fc.args)
                            
                            # Standardize tool output
                            if isinstance(tool_output, dict):
                                response_payload = tool_output
                            else:
                                response_payload = {"result": tool_output}

                            # Create function response
                            function_response = FunctionResponse(
                                name=fc.name, 
                                response=response_payload, 
                                id=fc.id
                            )

                            # Yield to client
                            yield AgentMessage(
                                type=MessageType.TOOL_CALL_RESPONSE,
                                data=response_payload,
                            )

                            function_responses.append(function_response)
                            logger.info(f"Tool {fc.name} executed successfully")

                        except Exception as e:
                            logger.error(f"Tool call {fc.name} failed: {e}")
                            
                            # Create error response
                            error_response = self._create_error_response(str(e), fc.name)
                            
                            function_response = FunctionResponse(
                                name=fc.name, 
                                response=error_response, 
                                id=fc.id
                            )

                            yield AgentMessage(
                                type=MessageType.TOOL_CALL_RESPONSE,
                                data=error_response,
                            )

                            function_responses.append(function_response)
                    else:
                        logger.warning(f"Unknown tool called: {fc.name}")
                        
                        # Handle unknown tool
                        error_response = self._create_error_response(
                            f"Unknown tool: {fc.name}", fc.name
                        )
                        
                        function_response = FunctionResponse(
                            name=fc.name, 
                            response=error_response, 
                            id=fc.id
                        )
                        
                        function_responses.append(function_response)

                # Send all function responses back to the model
                if function_responses:
                    try:
                        await self._session.send_tool_response(
                            function_responses=function_responses
                        )
                        logger.info(f"Sent {len(function_responses)} tool responses")
                    except Exception as e:
                        logger.error(f"Failed to send tool responses: {e}")

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