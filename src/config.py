import os

from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL", "")
if not DATABASE_URL:
    raise ValueError("ERROR: DATABASE_URL not found in .env file")

# --- Google Gemini ---
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY", "")
if not GOOGLE_API_KEY:
    raise ValueError("ERROR: GOOGLE_API_KEY not found in .env file")

GOOGLE_LiveAPI_KEY = os.getenv("GOOGLE_LiveAPI_KEY", "")
if not GOOGLE_LiveAPI_KEY:
    raise ValueError("ERROR: GOOGLE_LiveAPI_KEY not found in .env file")

LIVEAPI_MODEL = os.getenv("LIVEAPI_MODEL")
if not LIVEAPI_MODEL:
    raise ValueError("ERROR: LIVEAPI_MODEL not found in .env file")

# --- Voice Names ---
MALE_VOICE_NAME = os.getenv("MALE_VOICE_NAME", "")
if not MALE_VOICE_NAME:
    raise ValueError("ERROR: MALE_VOICE_NAME not found in .env file")

FEMALE_VOICE_NAME = os.getenv("FEMALE_VOICE_NAME", "")
if not FEMALE_VOICE_NAME:
    raise ValueError("ERROR: FEMALE_VOICE_NAME not found in .env file")
