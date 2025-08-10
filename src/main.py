import asyncio
import base64
import logging
from contextlib import asynccontextmanager
from datetime import datetime

from fastapi import Depends, FastAPI, WebSocket
from fastapi.websockets import WebSocketDisconnect, WebSocketState
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
import asyncio
import json
import config as config
from agents.live_agent import LiveAgent, MessageType
from agents.voomi_agent import Voomi
from prompts import live_prompt
from db import DatabaseService, MessageDirection, create_tables, get_db
from utils.audio_codec import AudioCodec
from utils.message_accumulator import MessageAccumulator
logging.getLogger('google_genai.types').setLevel(logging.ERROR)
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_: FastAPI):
    await create_tables()
    yield
    print("Shutting down...")


app = FastAPI(title="Voomi Live WebSocket", lifespan=lifespan)


class ClientData(BaseModel):
    text: str | None = None
    audio: str | None = None
    audio_stream_end: bool = Field(default=False)

    
@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket, db: AsyncSession = Depends(get_db)):
    await ws.accept()
    voice_config_raw= await ws.receive()
    text_data = voice_config_raw.get("text")
    parsed_data = json.loads(text_data)
    DIALECT = parsed_data.get("data", {}).get("dialect")
    PERSONA = parsed_data.get("data", {}).get("persona")
    logger.info(f"WebSocket connected with dialect: {DIALECT}, persona: {PERSONA}")
    VOICE_NAME = "Zephyr" if PERSONA == "female" else "Orus"
    # Create a new chat session
    chat = await DatabaseService.create_chat(db, "Live Chat Session")
    voomi = Voomi(dialect=DIALECT)
    message_accumulator = MessageAccumulator()

    logger.info(f"Created chat session: {chat.id}")

    async def send_json_streaming(type_: str, data, content_type: MessageType):
        """Send JSON message to client and accumulate for later DB save"""
        try:
            timestamp = datetime.now()
            logger.debug(f"Sending {type_} message")
            # Send message to client immediately (streaming)
            response = {
                "type": type_,
                "data": data,
                "chat_id": str(chat.id),
                "timestamp": timestamp.isoformat(),
            }

            await ws.send_json(response)
            logger.debug(f"Sent {type_} to client")

            # Accumulate message pieces (don't save to DB yet)
            if content_type in [
                MessageType.TEXT,
                MessageType.AUDIO,
                MessageType.OUTPUT_TRANSCRIPTION,
            ]:
                message_accumulator.add_piece(content_type, data)

        except Exception as e:
            logger.error(f"Failed to send {type_} message: {e}")

    async def handle_message_completion():
        """Called when agent finishes sending a complete message"""
        logger.info("Agent finished sending message, saving to database...")
        await message_accumulator.save_accumulated_message(db, chat.id)

    # Fixed message handlers with proper content_type
    handle_message_type = {
        MessageType.TEXT: lambda data: send_json_streaming(
            "text-delta", data, MessageType.TEXT
        ),
        MessageType.INPUT_TRANSCRIPTION: lambda data: send_json_streaming(
            "input_transcription-delta", data, MessageType.INPUT_TRANSCRIPTION
        ),
        MessageType.OUTPUT_TRANSCRIPTION: lambda data: send_json_streaming(
            "output_transcription-delta", data, MessageType.OUTPUT_TRANSCRIPTION
        ),
        MessageType.AUDIO: lambda data: send_json_streaming(
            "audio-delta", AudioCodec.to_wav(data), MessageType.AUDIO
        ),
        MessageType.INTERRUPTION: lambda data: send_json_streaming(
            "interruption", {"interrupted": data}, MessageType.INTERRUPTION
        ),
        MessageType.TOOL_CALL_RESPONSE: lambda data: send_json_streaming(
            "tool_call_response", data, MessageType.TOOL_CALL_RESPONSE
        ),
    }
    # system_prompt = get_system_prompt(DIALECT)
    # logger.info(f"UsingUsing system prompt: {system_prompt}")
    language_map = {"EGYPTIAN": "ar-EG", "SAUDI": "ar-SA", "ENGLISH": "en-US"}
    code= language_map.get(DIALECT)
    try:
        async with LiveAgent(
            config={
                "API_KEY": config.GOOGLE_API_KEY,
                "ENABLE_TRANSCRIPTION": True,
                "MODEL": config.LIVEAPI_MODEL,
                "SYSTEM_PROMPT": live_prompt.get_system_prompt(dialect=DIALECT, language_code=code),
                "VOICE_NAME": VOICE_NAME,
                "DIALECT": DIALECT,
            },
            tools=[voomi],
        ) as live_agent:

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

                            asyncio.create_task(
                                DatabaseService.save_message(
                                    db=db,
                                    chat_id=chat.id,
                                    direction=MessageDirection.INCOMING,
                                    content_type=MessageType.TEXT,
                                    text_content=data.text,
                                )
                            )

                            await live_agent.send_text(data.text)

                        # Handle audio input
                        if data.audio:
                            logger.debug("Received audio chunk")
                            audio_data = base64.b64decode(data.audio)

                            asyncio.create_task(
                                DatabaseService.save_message(
                                    db=db,
                                    chat_id=chat.id,
                                    direction=MessageDirection.INCOMING,
                                    content_type=MessageType.AUDIO,
                                    audio_content=audio_data,
                                    audio_format="audio/pcm",
                                )
                            )

                            await live_agent.send_audio(audio_data)

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
                    # Send initial connection confirmation with chat ID
                    await ws.send_json(
                        {"type": "connected", "data": {"chat_id": str(chat.id)}}
                    )

                    message_timeout = None

                    while ws.client_state in [
                        WebSocketState.CONNECTED,
                        WebSocketState.CONNECTING,
                    ]:
                        try:
                            # Add timeout for receive_message
                            async for message in live_agent.receive_message():
                                if handler := handle_message_type.get(message.type):
                                    try:
                                        await asyncio.wait_for(handler(message.data), timeout=30.0)
                                        
                                        # Reset timeout for message completion detection
                                        if message_timeout:
                                            message_timeout.cancel()

                                        # Set timeout to detect when agent stops sending messages
                                        async def timeout_handler():
                                            try:
                                                await asyncio.sleep(2.0)
                                                await handle_message_completion()
                                            except Exception as e:
                                                logger.error(f"Timeout handler error: {e}")

                                        message_timeout = asyncio.create_task(timeout_handler())
                                        
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
                            except:
                                logger.error("Failed to send ping - connection lost")
                                break
                                
                        except Exception as e:
                            # logger.error(f"Receive message error: {e}")
                            # Attempt to continue operation
                            await asyncio.sleep(1)
                            continue

                except WebSocketDisconnect:
                    logger.info("WebSocket disconnected in send_thread")
                except Exception as e:
                    logger.error(f"Error in send_thread: {e}")
                    # Attempt to close connection properly
                    try:
                        if ws.client_state == WebSocketState.CONNECTED:
                            await ws.close(code=1000, reason="Internal error")
                    except:
                        pass
                finally:
                    # Save any remaining accumulated message
                    try:
                        if message_accumulator.is_collecting:
                            await handle_message_completion()
                    except Exception as e:
                        logger.error(f"Final cleanup error: {e}")

            # Run both threads concurrently
            await asyncio.gather(
                receive_thread(),
                send_thread(),
                return_exceptions=True,
            )

    except WebSocketDisconnect:
        logger.info("WebSocket disconnected")
    except Exception as e:
        logger.error(f"Unexpected error in websocket_endpoint: {e}")
    finally:
        try:
            # Ensure any pending message is saved
            if message_accumulator.is_collecting:
                await handle_message_completion()

            await db.close()
            if ws.client_state == WebSocketState.CONNECTED:
                await ws.close()
        except Exception as e:
            logger.error(f"Error closing resources: {e}")


# Endpoints for retrieving chats & messages
#
# @app.get("/chats")
# async def get_chats(db: AsyncSession = Depends(get_db)):
#     """Get all chat sessions"""
#     from sqlalchemy import select
#
#     from db import Chat
#
#     result = await db.execute(select(Chat).order_by(Chat.created_at.desc()))  # type: ignore
#     chats = result.scalars().all()
#
#     return [
#         {
#             "id": str(chat.id),
#             "title": chat.title,
#             "created_at": chat.created_at.isoformat(),
#             "updated_at": chat.updated_at.isoformat(),
#             "is_active": chat.is_active,
#         }
#         for chat in chats
#     ]
#
#
# @app.get("/chats/{chat_id}/messages")
# async def get_chat_messages(chat_id: str, db: AsyncSession = Depends(get_db)):
#     """Get all messages for a specific chat"""
#     messages = await DatabaseService.get_chat_messages(db, uuid.UUID(chat_id))
#
#     return [
#         {
#             "id": str(msg.id),
#             "direction": msg.direction,
#             "content_type": msg.content_type,
#             "text_content": msg.text_content,
#             "audio_format": msg.audio_format,
#             "has_audio": msg.audio_content is not None,
#             "created_at": msg.created_at.isoformat(), # type: ignore
#             "metadata": msg.metadata,
#         }
#         for msg in messages
#     ]


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
