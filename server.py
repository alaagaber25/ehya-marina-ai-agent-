import asyncio
import numpy as np
from google import genai
from google.genai import types
import app.core.config as config
from google.genai.types import LiveConnectConfig, Part, Content
import wave
import base64
import json  # <-- Import the JSON library
from app.services.live_api_bridge import process_text_with_agent

# --- Agent Bridge Function (MODIFIED TO BE ASYNC AND SIMPLIFY RESPONSE) ---
async def call_agent_and_get_response(prompt: str) -> dict:
    """
    Asynchronously calls the LangChain agent and returns a simple dictionary
    containing only the response text for the model to speak.
    """
    print(f"INFO: Handing off to agent thread for prompt: '{prompt}'")
    
    # Run the blocking agent function in a separate thread
    agent_json_string = await asyncio.to_thread(process_text_with_agent, prompt)
    print(f"INFO: Received agent JSON: '{agent_json_string}'")

    try:
        # Parse the JSON string from the agent
        agent_data = json.loads(agent_json_string)
        # Extract only the text that needs to be spoken
        response_text = agent_data.get("responseText", "Error: Could not parse agent response.")
    except (json.JSONDecodeError, TypeError):
        # Handle cases where the agent returns a plain string or invalid JSON
        response_text = agent_json_string

    # ✅ Return a simple dictionary. This is what the model needs.
    return {"text_response": response_text}
GOOGLE_API_KEY = "AIzaSyDghmp3M-3WngG5StlQiF3wmq7pqxYEw9A"

# --- Google GenAI Client Setup ---
client = genai.Client(
    api_key=GOOGLE_API_KEY,
)

model = "gemini-live-2.5-flash-preview"


# --- Tool and LiveAPI Configuration ---
agent_function_declaration = {
    "name": "call_agent_and_get_response",
    "description": "Gets a response from the real estate AI agent for a given user prompt.",
    "parameters": {
        "type": "object",
        "properties": {
            "prompt": {
                "type": "string",
                "description": "The user's query, e.g., 'ابحث عن شقة بغرفة نوم واحدة'"
            }
        },
        "required": ["prompt"]
    }
}
tools = [{"function_declarations": [agent_function_declaration]}]

live_config = LiveConnectConfig(
    response_modalities=["AUDIO"],
    tools=tools,
    system_instruction=Part.from_text(text="You are a specialized real estate agent for a project called Flamant. For ANY user query, including greetings, questions about your identity, or real estate searches, you MUST use the `call_agent_and_get_response` tool to get the answer. Do not answer any questions from your own knowledge."),    input_audio_transcription={},
    output_audio_transcription={},
)

async def main():
    async with client.aio.live.connect(model=model, config=live_config) as session:
        print("Connected to Gemini Live. Type 'exit' to quit.")

        while True:
            prompt = input("\nEnter your prompt (or 'exit' to quit): ")
            if prompt.lower() == 'exit':
                break

            await session.send_client_content(
                turns=Content(
                    role="user",
                    parts=[Part(text=prompt)]
                )
            )

            print("Waiting for response...")
            audio_data = []

            async for message in session.receive():
                #  Correctly structured checks to prevent AttributeError
                if hasattr(message, 'server_content') and message.server_content:
                    if message.server_content.output_transcription:
                        print("Output transcript:", message.server_content.output_transcription.text)
                    
                    if hasattr(message.server_content, 'model_turn') and message.server_content.model_turn:
                        for part in message.server_content.model_turn.parts:
                            if part.inline_data and part.inline_data.data:
                                audio_data.append(np.frombuffer(part.inline_data.data, dtype=np.int16))

                if hasattr(message, 'tool_call') and message.tool_call:
                    print("Processing tool call...")
                    function_responses = []
                    for fc in message.tool_call.function_calls:
                        if fc.name == "call_agent_and_get_response":
                            response_dict = await call_agent_and_get_response(fc.args.get("prompt", ""))
                            function_response = types.FunctionResponse(
                                name=fc.name,
                                response=response_dict,
                                id=fc.id
                            )
                            function_responses.append(function_response)

                    if function_responses:
                        await session.send_tool_response(function_responses=function_responses)
            
            if audio_data:
                print(f"Total audio chunks received: {len(audio_data)}")
                with wave.open(f"app/tts/audio_outputs/output.wav", 'wb') as wav_file:
                    wav_file.setnchannels(1)
                    wav_file.setsampwidth(2)
                    wav_file.setframerate(24000)
                    decoded_data = base64.b64decode(np.concatenate(audio_data))
                    wav_file.writeframes(decoded_data)
                print("Audio saved to output.wav")
            else:
                print("No audio data was received for this turn.")

if __name__ == "__main__":
    asyncio.run(main())