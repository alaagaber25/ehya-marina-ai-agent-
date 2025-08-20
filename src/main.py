import asyncio
import base64
import json
import logging
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Dict, Any

import redis.asyncio as redis
from fastapi import Depends, FastAPI, WebSocket
from fastapi.websockets import WebSocketDisconnect, WebSocketState
from fastapi_limiter import FastAPILimiter
from fastapi_limiter.depends import WebSocketRateLimiter
from pydantic import BaseModel, Field

import config as config
from agents.live_agent import LiveAgent, MessageType
<<<<<<< HEAD
from agents.voomi_agent import Voomi
from prompts import live_prompt
from tools import units_fetcher
from utils.audio_codec import AudioCodec
=======
from prompts.live_prompt import custom_agent_prompt
from utils.audio_codec import AudioCodec
from tools import units_fetcher
from tools import get_project_units, save_lead, finalize_response
>>>>>>> Liveapi-agent

# Configure logging
logging.getLogger("google_genai.types").setLevel(logging.ERROR)
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_: FastAPI):
    """Application lifespan management"""
    logger.info("Application starting up...")
    if getattr(config, "ENABLE_RATE_LIMIT", False):
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


<<<<<<< HEAD
websocket_dependencies = []
if getattr(config, "ENABLE_RATE_LIMIT", False):
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
=======
class MessageHandler:
    """Handles message processing with better error recovery"""
    
    def __init__(self, websocket: WebSocket, session_id: str):
        self.websocket = websocket
        self.session_id = session_id
        self.message_queue = asyncio.Queue(maxsize=100)
        self.is_connected = True
    
    async def send_json_streaming(self, type_: str, data: Any) -> bool:
        """Send JSON message to client with improved error handling"""
        try:
            if not self.is_connected or self.websocket.client_state != WebSocketState.CONNECTED:
                return False
                
            timestamp = datetime.now()
            response = {
                "type": type_,
                "data": data,
                "session_id": self.session_id,
                "timestamp": timestamp.isoformat(),
            }

            # Use asyncio.wait_for to prevent hanging
            await asyncio.wait_for(
                self.websocket.send_json(response), 
                timeout=5.0
            )
            return True

        except asyncio.TimeoutError:
            logger.warning(f"Timeout sending {type_} message")
            return False
        except Exception as e:
            logger.error(f"Failed to send {type_} message: {e}")
            self.is_connected = False
            return False
    
    def get_message_handlers(self) -> Dict[MessageType, callable]:
        """Return message type handlers"""
        return {
            MessageType.TEXT: lambda data: self.send_json_streaming("text-delta", data),
            MessageType.INPUT_TRANSCRIPTION: lambda data: self.send_json_streaming("input_transcription-delta", data),
            MessageType.OUTPUT_TRANSCRIPTION: lambda data: self.send_json_streaming("output_transcription-delta", data),
            MessageType.AUDIO: lambda data: self.send_json_streaming("audio-delta", AudioCodec.to_wav(data)),
            MessageType.INTERRUPTION: lambda data: self.send_json_streaming("interruption", {"interrupted": data}),
            MessageType.TOOL_CALL_RESPONSE: lambda data: self.send_json_streaming("tool_call_response", data),
        }


@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    """Main WebSocket endpoint for voice communication"""
    message_handler = None
    
    try:
        await ws.accept()
        
        # Get voice configuration from client
        voice_config_raw = await asyncio.wait_for(ws.receive(), timeout=30.0)
        text_data = voice_config_raw.get("text")
        if not text_data:
            await ws.close(code=1008, reason="Missing configuration")
            return
            
        parsed_data = json.loads(text_data)
        config_data = parsed_data.get("data", {})
        
        dialect = config_data.get("dialect")
        agent_gender = config_data.get("persona")
        agent_name = config_data.get("name")

        if not all([dialect, agent_gender, agent_name]):
            await ws.close(code=1008, reason="Incomplete configuration")
            return
>>>>>>> Liveapi-agent

    dialect = parsed_data.get("data", {}).get("dialect")
    agent_gender = parsed_data.get("data", {}).get("persona")
    agent_name = parsed_data.get("data", {}).get("name")

<<<<<<< HEAD
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

=======
        # Map dialect to language code
        language_map = {
            "EGYPTIAN": "ar-EG", 
            "SAUDI": "ar-SA", 
            "ENGLISH": "en-US", 
            "FRENCH": "fr-FR", 
            "SPANISH": "es-ES"
        }
        languages_skills = ["English", "Egyptian Arabic", "Saudi Arabic"]
        language_code = language_map.get(dialect)

        logger.info(f"WebSocket connected - Dialect: {dialect}, Agent: {agent_name}, Gender: {agent_gender}")

        # Initialize session
        session_id = f"session_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        message_handler = MessageHandler(ws, session_id)
        
        # Tools setup
        tools = [get_project_units, save_lead, finalize_response]

        # Initialize Live Agent with improved config
        async with LiveAgent(
            config={
                "API_KEY": config.GOOGLE_API_KEY,
                "ENABLE_TRANSCRIPTION": True,
                "MODEL": config.LIVEAPI_MODEL,
                "SYSTEM_PROMPT": custom_agent_prompt(
                    project_id="flamant",
                    agent_name=agent_name,
                    agent_gender=agent_gender,
                    dialect=dialect,
                    languages_skills=languages_skills
                ),
                "VOICE_NAME": voice_name,
                "DIALECT": dialect,
                "LANGUAGE_CODE": language_code,
                # Improved VAD settings for better interruption handling
                "VAD_START_SENSITIVITY": "high",
                "VAD_END_SENSITIVITY": "low", 
                "VAD_SILENCE_DURATION_MS": 1000,
                "VAD_PREFIX_PADDING_MS": 300,
            },
            tools=tools,
        ) as live_agent:

            async def receive_messages():
                """Handle incoming WebSocket messages from client"""
                try:
                    while message_handler.is_connected and ws.client_state == WebSocketState.CONNECTED:
                        try:
                            # Add timeout to prevent hanging
                            raw_data = await asyncio.wait_for(ws.receive_text(), timeout=60.0)
                            data = ClientData.model_validate_json(raw_data)

                            # Handle text input
                            if data.text:
                                logger.info(f"Received text: {data.text[:50]}...")
                                await live_agent.send_text(data.text)

                            # Handle audio input
                            if data.audio:
                                logger.debug("Received audio chunk")
                                try:
                                    audio_data = base64.b64decode(data.audio)
                                    await live_agent.send_audio(audio_data)
                                except Exception as e:
                                    logger.warning(f"Audio decode error: {e}")

                            # Handle audio stream end
                            if data.audio_stream_end:
                                logger.info("Audio stream ended")
                                await live_agent.send_audio_stream_end()

                        except asyncio.TimeoutError:
                            # Send keepalive ping
                            if not await message_handler.send_json_streaming("ping", {}):
                                break
                                
                except WebSocketDisconnect:
                    logger.info("WebSocket disconnected in receive_messages")
                except Exception as e:
                    logger.error(f"Error in receive_messages: {e}")
                finally:
                    message_handler.is_connected = False

            async def send_messages():
                """Handle outgoing messages from Live API to client"""
                try:
                    # Send initial connection confirmation
                    await message_handler.send_json_streaming("connected", {"session_id": session_id})
                    
                    # Get message handlers
                    handlers = message_handler.get_message_handlers()

                    while message_handler.is_connected and ws.client_state == WebSocketState.CONNECTED:
                        try:
                            # Process messages with timeout
                            async for message in live_agent.receive_message():
                                if not message_handler.is_connected:
                                    break
                                    
                                handler = handlers.get(message.type)
                                if handler:
                                    try:
                                        success = await asyncio.wait_for(
                                            handler(message.data), 
                                            timeout=10.0
                                        )
                                        if not success:
                                            logger.warning(f"Failed to send {message.type} message")
                                            
                                    except asyncio.TimeoutError:
                                        logger.warning(f"Handler timeout for {message.type}")
                                    except Exception as e:
                                        logger.error(f"Handler error for {message.type}: {e}")
                                else:
                                    logger.warning(f"No handler for message type: {message.type}")
                                    
                        except Exception as e:
                            # logger.error(f"Error processing live agent messages: {e}")
                            await asyncio.sleep(1)  # Brief pause before retry
                            
                except Exception as e:
                    logger.error(f"Error in send_messages: {e}")
                finally:
                    message_handler.is_connected = False

            # Run both message handlers concurrently with proper error handling
            try:
                await asyncio.gather(
                    receive_messages(),
                    send_messages(),
                    return_exceptions=True,
                )
            except Exception as e:
                logger.error(f"Error in message handling: {e}")

    except asyncio.TimeoutError:
        logger.warning("WebSocket connection timeout")
        try:
            await ws.close(code=1008, reason="Connection timeout")
        except Exception:
            pass
    except WebSocketDisconnect:
        logger.info("WebSocket disconnected")
    except Exception as e:
        logger.error(f"Unexpected error in websocket_endpoint: {e}")
    finally:
        # Cleanup
        if message_handler:
            message_handler.is_connected = False
>>>>>>> Liveapi-agent
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


@app.get("/invalidate-cache")
def invalidate_cache():
    """Invalidate the units cache"""
    units_fetcher.fetch_units_from_api.cache_clear()
    return {"status": "cache cleared"}


if __name__ == "__main__":
    import uvicorn
<<<<<<< HEAD

=======
    
    # Warm up cache
>>>>>>> Liveapi-agent
    units = units_fetcher.fetch_units_from_api("flamant")
    if units:
        logger.info(f"Fetched {len(units)} units from API.")
    else:
        logger.warning("No units found.")

    logger.info("Starting FastAPI server...")
    uvicorn.run(app, host="0.0.0.0", port=8000)