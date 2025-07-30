import asyncio
import base64

from fastapi import FastAPI, WebSocket
from fastapi.websockets import WebSocketDisconnect, WebSocketState
from pydantic import BaseModel, Field

from ai.agents.live import LiveAgent, MessageType
from ai.agents.voomi import Voomi
from ai.prompts import live
from functools import partial
from utils.audio_codec import AudioCodec
import config as config

app = FastAPI(title="Voomi Live WebSocket")


@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await ws.accept()

    # TODO: move it somewhere
    class ClientData(BaseModel):
        text: str | None = None
        audio: str | None = None
        interrupted: bool = Field(default=False)

    async def send_json(type_, data):
        await ws.send_json({"type": f"{type_}-delta", "data": data})

    # call table
    handle_message_type = {
        MessageType.TEXT: partial(send_json, "text"),
        MessageType.INPUT_TRANSCRIPTION: partial(send_json, "input_transcription"),
        MessageType.OUTPUT_TRANSCRIPTION: partial(send_json, "output_transcription"),
        MessageType.AUDIO: lambda data: ws.send_json(
            {"type": "audio-delta", "data": AudioCodec.to_wav(data)}
        ),
    }

    try:
        voomi = Voomi()
        async with LiveAgent(
            config={
                "API_KEY": config.GOOGLE_API_KEY,
                "ENABLE_TRANSCRIPTION": True,
                "MODEL": "gemini-live-2.5-flash-preview",
                "SYSTEM_PROMPT": live.SYSTEM_PROMPT,
            },
            tools=[voomi],
        ) as live_agent:
            interrupted_event = asyncio.Event()

            async def receive_thread():
                while ws.client_state in [
                    WebSocketState.CONNECTED,
                    WebSocketState.CONNECTING,
                ]:
                    data = ClientData.model_validate_json(await ws.receive_text())
                    if data.interrupted:
                        interrupted_event.set()

                    if data.text:
                        await live_agent.send_text(data.text)

                    if data.audio:
                        await live_agent.send_audio(base64.b64decode(data.audio))

            async def send_thread():
                while ws.client_state in [
                    WebSocketState.CONNECTED,
                    WebSocketState.CONNECTING,
                ]:
                    await ws.send_json({"type": "start"})

                    async for message in live_agent.receive_message():
                        if interrupted_event.is_set():
                            print("Interrupted")
                            continue
                        if handler := handle_message_type.get(message.type):
                            await handler(message.data)

                    interrupted_event.clear()

                    await ws.send_json({"type": "end"})

            await asyncio.gather(receive_thread(), send_thread())

    except WebSocketDisconnect:
        # maybe log? make a summary?
        pass
    finally:
        await ws.close()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
