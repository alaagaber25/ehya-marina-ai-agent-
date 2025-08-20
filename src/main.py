import asyncio
import base64
import json
import logging
from contextlib import asynccontextmanager
from datetime import datetime

import redis.asyncio as redis
from fastapi import Depends, FastAPI, WebSocket
from fastapi.websockets import WebSocketDisconnect, WebSocketState
from fastapi_limiter import FastAPILimiter
from fastapi_limiter.depends import WebSocketRateLimiter
from pydantic import BaseModel, Field

import config as config
from agents.live_agent import LiveAgent, MessageType
from agents.voomi_agent import Voomi
from prompts import live_prompt
from tools import units_fetcher
from utils.audio_codec import AudioCodec

# Configure logging
logging.getLogger("google_genai.types").setLevel(logging.ERROR)
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_: FastAPI):
    """Application lifespan management - database initialization removed"""
    logger.info("Application starting up...")
    if getattr(config, "ENABLE_RATE_LIMIT", True):
        redis_connection = redis.from_url(
            config.REDIS_URL, encoding="utf-8", decode_responses=True
        )
        await FastAPILimiter.init(redis_connection)
    yield
    logger.info("Application shutting down...")


app = FastAPI(title="Voomi Live WebSocket", lifespan=lifespan)


class ClientData(BaseModel):
    """WebSocket client data model"""

    text: str | None = None
    audio: str | None = None
    audio_stream_end: bool = Field(default=False)


websocket_dependencies = []
if getattr(config, "ENABLE_RATE_LIMIT", True):
    # Google's session limit is 15 minutes, so we only limit the ip to make at most 3 requests in this window
    websocket_dependencies.append(Depends(WebSocketRateLimiter(times=3, minutes=15)))


@app.websocket("/ws", dependencies=websocket_dependencies)
async def websocket_endpoint(ws: WebSocket):
    """
    Main WebSocket endpoint for voice communication.
    Handles real-time voice interaction with the AI agent.
    """
    await ws.accept()

    # Get voice configuration from client
    voice_config_raw = await ws.receive()
    text_data = voice_config_raw.get("text")
    parsed_data = json.loads(text_data)

    dialect = parsed_data.get("data", {}).get("dialect")
    agent_gender = parsed_data.get("data", {}).get("persona")
    agent_name = parsed_data.get("data", {}).get("name")

    voice_name = (
        config.FEMALE_VOICE_NAME if agent_gender == "female" else config.MALE_VOICE_NAME
    )

    # Map dialect to language code
    language_map = {
        "EGYPTIAN": "ar-EG",
        "SAUDI": "ar-SA",
        "ENGLISH": "en-US",
        "FRENCH": "fr-FR",
        "SPANISH": "es-ES",
    }
    languages_skills = ["English", "Egyptian Arabic", "Saudi Arabic"]
    language_code = language_map.get(dialect)

    logger.info(
        f"WebSocket connected - Dialect: {dialect}, Agent Name: {agent_name}, Agent Gender: {agent_gender}, Voice: {voice_name}"
    )

    # Initialize agent and session
    session_id = f"session_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    voomi = Voomi(
        project_id="flamant",
        agent_name=agent_name,
        agent_gender=agent_gender,
        dialect=dialect,
        languages_skills=languages_skills,
    )

    logger.info(f"Created session: {session_id}")

    async def send_json_streaming(type_: str, data):
        """Send JSON message to client with streaming support"""
        try:
            logger.debug(f"Sending {type_} message")

            await ws.send_json(
                {
                    "type": type_,
                    "data": data,
                    "session_id": session_id,
                    "timestamp": datetime.now().isoformat(),
                }
            )
            logger.debug(f"Sent {type_} to client")

        except Exception as e:
            logger.error(f"Failed to send {type_} message: {e}")

    # Message type handlers
    handle_message_type = {
        MessageType.TEXT: lambda data: send_json_streaming("text-delta", data),
        MessageType.INPUT_TRANSCRIPTION: lambda data: send_json_streaming(
            "input_transcription-delta", data
        ),
        MessageType.OUTPUT_TRANSCRIPTION: lambda data: send_json_streaming(
            "output_transcription-delta", data
        ),
        MessageType.AUDIO: lambda data: send_json_streaming(
            "audio-delta", AudioCodec.to_wav(data)
        ),
        MessageType.INTERRUPTION: lambda data: send_json_streaming(
            "interruption", {"interrupted": data}
        ),
        MessageType.TOOL_CALL_RESPONSE: lambda data: send_json_streaming(
            "tool_call_response", data
        ),
    }

    # Initialize Live Agent
    async with LiveAgent(
        config={
            "API_KEY": config.GOOGLE_API_KEY,
            "ENABLE_TRANSCRIPTION": True,
            "MODEL": config.LIVEAPI_MODEL,
            "SYSTEM_PROMPT": live_prompt.get_system_prompt(
                dialect=dialect, language_code=language_code, gender=agent_gender
            ),
            "VOICE_NAME": voice_name,
            "DIALECT": dialect,
            "LANGUAGE_CODE": language_code,
        },
        tools=[voomi],
    ) as live_agent:

        async def receive_messages():
            """Handle incoming WebSocket messages from client"""
            while ws.client_state in [
                WebSocketState.CONNECTED,
                WebSocketState.CONNECTING,
            ]:
                raw_data = await ws.receive_text()
                data = ClientData.model_validate_json(raw_data)

                if data.text:
                    logger.info(f"Received text: {data.text[:50]}...")
                    await live_agent.send_text(data.text)

                if data.audio:
                    logger.info("Received audio chunk")
                    await live_agent.send_audio(base64.b64decode(data.audio))

                if data.audio_stream_end:
                    logger.info("Audio stream ended")
                    await live_agent.send_audio_stream_end()

        async def send_messages():
            """Handle outgoing messages from Live API to client"""
            await ws.send_json(
                {"type": "connected", "data": {"session_id": session_id}}
            )

            while ws.client_state in [
                WebSocketState.CONNECTED,
                WebSocketState.CONNECTING,
            ]:
                async for message in live_agent.receive_message():
                    if handler := handle_message_type.get(message.type):
                        await asyncio.wait_for(handler(message.data), timeout=30.0)

        tasks = [
            asyncio.create_task(receive_messages()),
            asyncio.create_task(send_messages()),
        ]

        try:
            await asyncio.gather(
                *tasks,
            )
        except WebSocketDisconnect:
            pass
        except Exception as e:
            logger.error(f"Error in WebSocket handler: {e}")
        finally:
            if ws.client_state == WebSocketState.CONNECTED:
                await ws.close()
            for task in tasks:
                task.cancel()
            await live_agent._session.close()


@app.get("/invlidate-cache")
def invalidate_cache():
    units_fetcher.fetch_units_from_api.cache_clear()
    return True


if __name__ == "__main__":
    import uvicorn

    units = units_fetcher.fetch_units_from_api("flamant")
    if units:
        logger.info(f"Fetched {len(units)} units from API.")
    else:
        logger.warning("No units found.")

    logger.info("Starting FastAPI server...")
    uvicorn.run(app, host="0.0.0.0", port=8000)
