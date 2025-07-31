import asyncio
import base64
import logging
from functools import partial

from fastapi import FastAPI, WebSocket
from fastapi.websockets import WebSocketDisconnect, WebSocketState
from pydantic import BaseModel, Field

from ai.agents.live import LiveAgent, MessageType
from ai.agents.voomi import Voomi
from ai.prompts import live
from utils.audio_codec import AudioCodec
import config as config

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Voomi Live WebSocket")


@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await ws.accept()

    class ClientData(BaseModel):
        text: str | None = None
        audio: str | None = None
        # Remove client-side interruption flag - use server VAD instead
        audio_stream_end: bool = Field(default=False)  # Signal end of audio stream

    async def send_json(type_: str, data):
        """Send JSON message to client"""
        try:
            await ws.send_json({"type": f"{type_}-delta", "data": data})
        except Exception as e:
            logger.error(f"Failed to send {type_} message: {e}")

    # Enhanced message handlers
    handle_message_type = {
        MessageType.TEXT: partial(send_json, "text"),
        MessageType.INPUT_TRANSCRIPTION: partial(send_json, "input_transcription"),
        MessageType.OUTPUT_TRANSCRIPTION: partial(send_json, "output_transcription"),
        MessageType.AUDIO: lambda data: send_json("audio", AudioCodec.to_wav(data)),
        MessageType.INTERRUPTION: lambda data: send_json(
            "interruption", {"interrupted": data}
        ),
        MessageType.TOOL_CALL_CANCELLED: lambda data: send_json(
            "tool_cancelled", {"cancelled_ids": data}
        ),
    }

    try:
        voomi = Voomi()

        # Enhanced configuration with VAD settings
        live_config = {
            "API_KEY": config.GOOGLE_API_KEY,
            "ENABLE_TRANSCRIPTION": True,
            "MODEL": "gemini-2.0-flash-live-001",  # Use the standard live model
            "SYSTEM_PROMPT": live.SYSTEM_PROMPT,
            # VAD configuration for better interruption handling
            # "VAD_START_SENSITIVITY": "medium",  # Adjust based on your needs
            # "VAD_END_SENSITIVITY": "medium",
            # "VAD_SILENCE_DURATION_MS": 300,  # How long to wait for silence before ending speech
            # "VAD_PREFIX_PADDING_MS": 50,  # Padding before speech detection
        }

        async with LiveAgent(config=live_config, tools=[voomi]) as live_agent:

            async def receive_thread():
                """Handle incoming WebSocket messages"""
                try:
                    while ws.client_state in [
                        WebSocketState.CONNECTED,
                        WebSocketState.CONNECTING,
                    ]:
                        raw_data = await ws.receive_text()
                        data = ClientData.model_validate_json(raw_data)

                        # Handle text input
                        if data.text:
                            logger.info(f"Received text: {data.text[:50]}...")
                            await live_agent.send_text(data.text)

                        # Handle audio input
                        if data.audio:
                            logger.debug("Received audio chunk")
                            await live_agent.send_audio(base64.b64decode(data.audio))

                        # Handle audio stream end signal
                        if data.audio_stream_end:
                            logger.info("Audio stream ended")
                            await live_agent.send_audio_stream_end()

                except WebSocketDisconnect:
                    logger.info("WebSocket disconnected in receive_thread")
                except Exception as e:
                    logger.error(f"Error in receive_thread: {e}")

            async def send_thread():
                """Handle outgoing messages from the Live API"""
                try:
                    # Send initial connection confirmation
                    await ws.send_json({"type": "connected", "data": {}})

                    while ws.client_state in [
                        WebSocketState.CONNECTED,
                        WebSocketState.CONNECTING,
                    ]:
                        async for message in live_agent.receive_message():
                            if handler := handle_message_type.get(message.type):
                                await handler(message.data)

                except WebSocketDisconnect:
                    logger.info("WebSocket disconnected in send_thread")
                except Exception as e:
                    logger.error(f"Error in send_thread: {e}")

            # Run both threads concurrently
            await asyncio.gather(
                receive_thread(),
                send_thread(),
                return_exceptions=True,  # Don't fail if one task fails
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

    uvicorn.run(app, host="0.0.0.0", port=8000)
