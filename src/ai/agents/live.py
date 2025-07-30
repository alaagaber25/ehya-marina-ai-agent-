from dataclasses import dataclass
from enum import Enum, auto
from typing import Any, Callable, TypedDict

from google import genai
from google.genai.types import (
    AudioTranscriptionConfig,
    Content,
    LiveConnectConfig,
    Modality,
    Part,
    FunctionResponse,
    Blob,
)


class LiveAgentConfig(TypedDict):
    API_KEY: str
    MODEL: str
    SYSTEM_PROMPT: str
    ENABLE_TRANSCRIPTION: bool


class MessageType(Enum):
    TEXT = auto()
    AUDIO = auto()
    TOOL_CALL = auto()
    INPUT_TRANSCRIPTION = auto()
    OUTPUT_TRANSCRIPTION = auto()


@dataclass
class AgentMessage:
    type: MessageType
    data: Any


class LiveAgent:
    def __init__(self, config: LiveAgentConfig, tools: list[Callable[..., Any]]):
        self.__client = genai.Client(api_key=config.get("API_KEY"))

        audio_transcription_config = self.__get_transcroption_config(config)
        self.__live_config = LiveConnectConfig(
            response_modalities=[Modality.AUDIO],
            tools=tools,
            system_instruction=Content(
                parts=[Part.from_text(text=config.get("SYSTEM_PROMPT"))]
            ),
            input_audio_transcription=audio_transcription_config,
            output_audio_transcription=audio_transcription_config,
        )

        self.__model = config.get("MODEL")
        self.__functions_to_call = {tool.__name__: tool for tool in tools}

    @staticmethod
    def __get_transcroption_config(
        config: LiveAgentConfig,
    ) -> AudioTranscriptionConfig | None:
        if config.get("ENABLE_TRANSCRIPTION"):
            return AudioTranscriptionConfig()
        return None

    async def __aenter__(self):
        self.__session = self.__client.aio.live.connect(
            model=self.__model, config=self.__live_config
        )
        self._session = await self.__session.__aenter__()
        return self

    async def __aexit__(self, exc_type, exc_value, traceback):
        await self.__session.__aexit__(exc_type, exc_value, traceback)

    async def send_text(self, text: str):
        await self._session.send_client_content(
            turns=Content(role="user", parts=[Part(text=text)])
        )

    async def send_audio(self, audio: bytes):
        await self._session.send_client_content(
            turns=Content(
                role="user",
                parts=[
                    Part(
                        inline_data=Blob(data=audio, mime_type="audio/wav"),
                    )
                ],
            )
        )

    async def receive_message(self):
        async for message in self._session.receive():
            if message.server_content and message.server_content.input_transcription:
                yield AgentMessage(
                    type=MessageType.INPUT_TRANSCRIPTION,
                    data=message.server_content.input_transcription.text,
                )

            if message.server_content and message.server_content.output_transcription:
                yield AgentMessage(
                    type=MessageType.OUTPUT_TRANSCRIPTION,
                    data=message.server_content.output_transcription.text,
                )

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

            if message.text:
                yield AgentMessage(type=MessageType.TEXT, data=message.text)

            if message.tool_call and message.tool_call.function_calls:
                function_responses = []
                for fc in message.tool_call.function_calls:
                    if fc.name in self.__functions_to_call:
                        if fc.args is None:
                            fc.args = {}
                        response = self.__functions_to_call[fc.name](**fc.args)
                        function_response = FunctionResponse(
                            name=fc.name, response=response, id=fc.id
                        )
                        function_responses.append(function_response)

                if function_responses:
                    await self._session.send_tool_response(
                        function_responses=function_responses
                    )
