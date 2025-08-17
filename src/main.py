import asyncio
import base64
import json
import logging
from contextlib import asynccontextmanager
from datetime import datetime

from fastapi import FastAPI, WebSocket
from fastapi.websockets import WebSocketDisconnect, WebSocketState
from pydantic import BaseModel, Field

import config as config
from agents.live_agent import LiveAgent, MessageType
from agents.voomi_agent import Voomi
from prompts import live_prompt
from utils.audio_codec import AudioCodec
from tools import units_fetcher

# Configure logging
logging.getLogger('google_genai.types').setLevel(logging.ERROR)
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_: FastAPI):
    """Application lifespan management - database initialization removed"""
    logger.info("Application starting up...")
    yield
    logger.info("Application shutting down...")


app = FastAPI(title="Voomi Live WebSocket", lifespan=lifespan)


class ClientData(BaseModel):
    """WebSocket client data model"""
    text: str | None = None
    audio: str | None = None
    audio_stream_end: bool = Field(default=False)

    
@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    """
    Main WebSocket endpoint for voice communication.
    Handles real-time voice interaction with the AI agent.
    """
    await ws.accept()
    
    try:
        # Get voice configuration from client
        voice_config_raw = await ws.receive()
        text_data = voice_config_raw.get("text")
        parsed_data = json.loads(text_data)

        dialect = parsed_data.get("data", {}).get("dialect")
        agent_gender = parsed_data.get("data", {}).get("persona")
        agent_name = parsed_data.get("data", {}).get("name")

        voice_name = config.FEMALE_VOICE_NAME if agent_gender == "female" else config.MALE_VOICE_NAME

        # Map dialect to language code
        language_map = {"EGYPTIAN": "ar-EG", "SAUDI": "ar-SA", "ENGLISH": "en-US", "FRENCH": "fr-FR", "SPANISH": "es-ES"}
        languages_skills = ["English", "Egyptian Arabic", "Saudi Arabic"]
        language_code = language_map.get(dialect)

        logger.info(f"WebSocket connected - Dialect: {dialect}, Agent Name: {agent_name}, Agent Gender: {agent_gender}, Voice: {voice_name}")

        # Initialize agent and session
        session_id = f"session_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        voomi = Voomi(project_id="flamant", agent_name=agent_name, agent_gender=agent_gender, dialect=dialect,languages_skills=languages_skills)

        logger.info(f"Created session: {session_id}")

        async def send_json_streaming(type_: str, data):
            """Send JSON message to client with streaming support"""
            try:
                timestamp = datetime.now()
                logger.debug(f"Sending {type_} message")
                
                response = {
                    "type": type_,
                    "data": data,
                    "session_id": session_id,
                    "timestamp": timestamp.isoformat(),
                }

                await ws.send_json(response)
                logger.debug(f"Sent {type_} to client")

            except Exception as e:
                logger.error(f"Failed to send {type_} message: {e}")

        # Message type handlers
        handle_message_type = {
            MessageType.TEXT: lambda data: send_json_streaming("text-delta", data),
            MessageType.INPUT_TRANSCRIPTION: lambda data: send_json_streaming("input_transcription-delta", data),
            MessageType.OUTPUT_TRANSCRIPTION: lambda data: send_json_streaming("output_transcription-delta", data),
            MessageType.AUDIO: lambda data: send_json_streaming("audio-delta", AudioCodec.to_wav(data)),
            MessageType.INTERRUPTION: lambda data: send_json_streaming("interruption", {"interrupted": data}),
            MessageType.TOOL_CALL_RESPONSE: lambda data: send_json_streaming("tool_call_response", data),
        }

        # Initialize Live Agent
        async with LiveAgent(
            config={
                "API_KEY": config.GOOGLE_API_KEY,
                "ENABLE_TRANSCRIPTION": True,
                "MODEL": config.LIVEAPI_MODEL,
                "SYSTEM_PROMPT": live_prompt.get_system_prompt(
                    dialect=dialect, 
                    language_code=language_code, 
                    gender=agent_gender
                ),
                "VOICE_NAME": voice_name,
                "DIALECT": dialect,
                "LANGUAGE_CODE": language_code,
            },
            tools=[voomi],
        ) as live_agent:

            async def receive_messages():
                """Handle incoming WebSocket messages from client"""
                try:
                    while ws.client_state in [WebSocketState.CONNECTED, WebSocketState.CONNECTING]:
                        raw_data = await ws.receive_text()
                        data = ClientData.model_validate_json(raw_data)

                        # Handle text input
                        if data.text:
                            logger.info(f"Received text: {data.text[:50]}...")
                            await live_agent.send_text(data.text)

                        # Handle audio input
                        if data.audio:
                            logger.debug("Received audio chunk")
                            audio_data = base64.b64decode(data.audio)
                            await live_agent.send_audio(audio_data)

                        # Handle audio stream end
                        if data.audio_stream_end:
                            logger.info("Audio stream ended")
                            await live_agent.send_audio_stream_end()

                except WebSocketDisconnect:
                    logger.info("WebSocket disconnected in receive_messages")
                except Exception as e:
                    logger.error(f"Error in receive_messages: {e}")

            async def send_messages():
                """Handle outgoing messages from Live API to client"""
                try:
                    # Send initial connection confirmation
                    await ws.send_json({
                        "type": "connected", 
                        "data": {"session_id": session_id}
                    })

                    while ws.client_state in [WebSocketState.CONNECTED, WebSocketState.CONNECTING]:
                        try:
                            async for message in live_agent.receive_message():
                                if handler := handle_message_type.get(message.type):
                                    try:
                                        await asyncio.wait_for(handler(message.data), timeout=30.0)
                                    except asyncio.TimeoutError:
                                        logger.warning("Message handler timeout - skipping")
                                        continue
                                    except Exception as e:
                                        logger.error(f"Handler error: {e}")
                                        continue
                                        
                        except asyncio.TimeoutError:
                            logger.warning("Live agent receive timeout")
                            # Send ping to check connection
                            try:
                                await ws.send_json({"type": "ping"})
                            except Exception:
                                logger.error("Failed to send ping - connection lost")
                                break
                                
                        except Exception as e:
                            # logger.error(f"Receive message error: {e}")
                            await asyncio.sleep(1)
                            continue

                except WebSocketDisconnect:
                    logger.info("WebSocket disconnected in send_messages")
                except Exception as e:
                    logger.error(f"Error in send_messages: {e}")
                    try:
                        if ws.client_state == WebSocketState.CONNECTED:
                            await ws.close(code=1000, reason="Internal error")
                    except Exception:
                        pass

            # Run both message handlers concurrently
            await asyncio.gather(
                receive_messages(),
                send_messages(),
                return_exceptions=True,
            )

    except WebSocketDisconnect:
        logger.info("WebSocket disconnected")
    except Exception as e:
        logger.error(f"Unexpected error in websocket_endpoint: {e}")
    finally:
        try:
            if ws.client_state == WebSocketState.CONNECTED:
                await ws.close()
        except Exception as e:
            logger.error(f"Error closing WebSocket: {e}")


if __name__ == "__main__":
    import uvicorn
    units = units_fetcher.fetch_units_from_api("flamant")
    if units:
        logger.info(f"Fetched {len(units)} units from API.")
    else:
        logger.warning("No units found.")

    logger.info("Starting FastAPI server...")
    uvicorn.run(app, host="0.0.0.0", port=8000)