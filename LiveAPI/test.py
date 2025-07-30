import asyncio
import numpy as np
from google import genai
from google.genai import types

from google.genai.types import (
    LiveConnectConfig,
    Part,
    Content,
    Modality,
    AudioTranscriptionConfig,
)
import wave
import base64


def call_agent(prompt: str) -> str:
    """Calls the agent service to get a response for a given user prompt.

    This function calls an external conversational AI service.
    It takes a user's prompt, sends it to the service, and retrieves a
    structured response. The response is designed to be used in a larger system,
    indicating a final answer and providing the text to be communicated back
    to the user, along with the appropriate dialect.
    Args:
        prompt (str): The user's input prompt. For example: "ابحث عن شقة بغرفة نوم واحدة في مشروع فلامانت"
    Returns:
        str: A JSON string with the service's response.
             Example: '{ "action": "Final Answer", "action_input": { "responseText": "تمام، لقيت لحضرتك 26 وحدة سكنية...", "dialect": "EGYPTIAN" } }'
    """

    return {
        "action": "Final Answer",
        "action_input": {
            "responseText": "تمام، لقيت لحضرتك 26 وحدة سكنية بنظام غرفة نوم واحدة في مشروع فلامانت. تحب تعرف تفاصيل أكتر عن أي وحدة فيهم، أو عندك أي مواصفات تانية حابب أضيفها للبحث؟",
            "dialect": "EGYPTIAN",
        },
    }


GOOGLE_API_KEY = "AIzaSyDghmp3M-3WngG5StlQiF3wmq7pqxYEw9A"

client = genai.Client(
    api_key=GOOGLE_API_KEY,
)

model = "gemini-live-2.5-flash-preview"

live_config = LiveConnectConfig(
    response_modalities=[Modality.AUDIO],
    tools=[call_agent],
    system_instruction=Content(
        parts=[
            Part.from_text(
                text="You're voomi. You are a helpful assistant that can answer questions in Arabic."
            )
        ]
    ),
    input_audio_transcription=AudioTranscriptionConfig(),
    output_audio_transcription=AudioTranscriptionConfig(),
)


async def main():
    async with client.aio.live.connect(model=model, config=live_config) as session:
        print("Connected to Gemini Live. Type 'exit' to quit.")

        while True:
            prompt = input("\nEnter your prompt (or 'exit' to quit): ")
            if prompt.lower() == "exit":
                break

            # Send user message
            await session.send_client_content(
                turns=Content(role="user", parts=[Part(text=prompt)])
            )

            print("Waiting for response...")
            audio_data = []
            async for message in session.receive():
                if message.server_content:
                    # if message.server_content.output_transcription:
                    #     print(
                    #         "Output transcript:",
                    #         message.server_content.output_transcription.text,
                    #     )
                    if message.server_content.model_turn:
                        if message.server_content.model_turn.parts:
                            for part in message.server_content.model_turn.parts:
                                if part.inline_data:
                                    audio_data.append(
                                        np.frombuffer(
                                            part.inline_data.data, dtype=np.int16
                                        )
                                    )

                # # Handle text responses
                # if message.text:
                #     print(f"Text: {message.text}")

                if message.tool_call:
                    print("Processing tool call...")
                    function_responses = []
                    print(message.tool_call)

                    for fc in message.tool_call.function_calls:
                        if fc.name == "call_agent":
                            response = call_agent(fc.args.get("prompt", ""))
                            function_response = types.FunctionResponse(
                                name=fc.name, response=response, id=fc.id
                            )
                            function_responses.append(function_response)

                    if function_responses:
                        print(function_responses)
                        await session.send_tool_response(
                            function_responses=function_responses
                        )

            # Combine all audio data if multiple chunks were received
            if audio_data:
                print(f"Total audio chunks received: {len(audio_data)}")
                with wave.open("output.wav", "wb") as wav_file:
                    decoded_data = base64.b64decode(np.concatenate(audio_data))
                    wav_file.setnchannels(1)
                    wav_file.setsampwidth(2)
                    wav_file.setframerate(24000)
                    wav_file.writeframes(decoded_data)


if __name__ == "__main__":
    asyncio.run(main())
