import base64
from fastapi import FastAPI, WebSocket
from fastapi.websockets import WebSocketDisconnect, WebSocketState
from pydantic import BaseModel, Field
from ai.agents.live import LiveAgent, MessageType
from utils.audio_codec import AudioCodec
from ai.prompts import live
from functools import partial
from app.services.live_api_bridge import process_text_with_agent
import json

app = FastAPI(title="Voomi Live WebSocket")


def call_agent(prompt: str) -> dict:
    """
    calls the LangChain agent and returns a simple dictionary
    containing only the response text for the model to speak.
    """
    print(f"INFO: Handing off to agent thread for prompt: '{prompt}'")
    agent_json_string = process_text_with_agent(prompt)
    try:
        # Parse the JSON string from the agent
        agent_data = json.loads(agent_json_string)
        # Extract only the text that needs to be spoken
        response_text = agent_data.get("responseText", "Error: Could not parse agent response.")
    except (json.JSONDecodeError, TypeError):
        # Handle cases where the agent returns a plain string or invalid JSON
        response_text = agent_json_string
    print(f"INFO: Received agent response: '{response_text}'")
    return {"text_response": response_text}


@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await ws.accept()

    # TODO: move it somewhere
    class ClientData(BaseModel):
        text: str | None = Field(...)
        audio: str | None = Field(...)

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
        async with LiveAgent(
            config={
                "API_KEY": "AIzaSyDghmp3M-3WngG5StlQiF3wmq7pqxYEw9A",
                "ENABLE_TRANSCRIPTION": True,
                "MODEL": "gemini-live-2.5-flash-preview",
                "SYSTEM_PROMPT": live.SYSTEM_PROMPT,
            },
            tools=[call_agent],
        ) as live_agent:
            while ws.client_state in [
                WebSocketState.CONNECTED,
                WebSocketState.CONNECTING,
            ]:
                data = ClientData.model_validate_json(await ws.receive_text())

                if data.text:
                    await live_agent.send_text(data.text)

                if data.audio:
                    await live_agent.send_audio(base64.b64decode(data.audio))

                async for message in live_agent.receive_message():
                    await ws.send_json({"type": "start"})
                    if handler := handle_message_type.get(message.type):
                        await handler(message.data)
                await ws.send_json({"type": "end"})

    except WebSocketDisconnect:
        # maybe log? make a summary?
        pass
    finally:
        await ws.close()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
