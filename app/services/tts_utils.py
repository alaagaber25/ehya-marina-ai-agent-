# tts_utils.py

import os
import wave
import contextlib
import pygame
from google import genai
import uuid
from datetime import datetime
import base64

# --- Initialization ---
client = genai.Client(api_key="AIzaSyA8y3ZmWrPObZyXW9_R8Y0WoGrbThDlBYY")

MODEL_ID = "gemini-2.5-flash-preview-tts"
VOICE_NAME = "Sadaltager"

AUDIO_OUTPUT_DIR = "app/services/audio_outputs"
os.makedirs(AUDIO_OUTPUT_DIR, exist_ok=True)

# --- Audio Utilities ---

@contextlib.contextmanager
def wave_file(filename, channels=1, rate=24000, sample_width=2):
    """Context manager to create a proper WAV file."""
    with wave.open(filename, "wb") as wf:
        wf.setnchannels(channels)
        wf.setsampwidth(sample_width)
        wf.setframerate(rate)
        yield wf

def save_audio_blob(blob_data) -> str:
    """Save the binary blob as a permanent .wav file and return the file path."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    unique_id = uuid.uuid4().hex[:6]
    filename = f"tts_{timestamp}_{unique_id}.wav"
    file_path = os.path.join(AUDIO_OUTPUT_DIR, filename)

    decoded_data = base64.b64decode(blob_data)
    with wave_file(file_path) as wav:
        wav.writeframes(decoded_data)

    print(f"[INFO] Audio saved to {file_path}")
    return file_path

def play_wav_file(file_path: str):
    """Play a WAV file using pygame."""
    pygame.mixer.init()
    pygame.mixer.music.load(file_path)
    pygame.mixer.music.play()
    while pygame.mixer.music.get_busy():
        pygame.time.Clock().tick(10)

# --- Main Speak Function ---

def speak(text: str):
    """Convert input text to speech, save it, and play it."""
    try:
        response = client.models.generate_content(
            model=MODEL_ID,
            contents=text,
            config={
                "response_modalities": ['Audio'],
                "speech_config": {
                    "voice_config": {
                        "prebuilt_voice_config": {
                            "voice_name": VOICE_NAME
                        }
                    }
                }
            },
        )

        audio_blob = response.candidates[0].content.parts[0].inline_data.data
        wav_path = save_audio_blob(audio_blob)
        play_wav_file(wav_path)

    except Exception as e:
        print(f"[ERROR] Failed to generate or play audio: {e}")


# --- Example Usage ---
if __name__ == "__main__":
    speak("Hello, this is a test.")