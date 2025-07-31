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

# # Google Cloud Project and Location
# GOOGLE_CLOUD_PROJECT = os.getenv('GOOGLE_CLOUD_PROJECT', 'voom-n8n-automation')
# GOOGLE_CLOUD_LOCATION = os.getenv('GOOGLE_CLOUD_REGION', 'us-central1')
#
# if not GOOGLE_CLOUD_PROJECT:
#     raise ValueError("ERROR: GOOGLE_CLOUD_PROJECT not found in .env file")
# if not GOOGLE_CLOUD_LOCATION:
#     raise ValueError("ERROR: GOOGLE_CLOUD_LOCATION not found in .env file")

# --- Text-to-Speech Dialect Configuration ---
# Define the style prompts
SAUDI_STYLE_PROMPT = "Please respond as a Saudi real estate sales agent, speaking in a friendly and professional Saudi dialect."
EGYPTIAN_STYLE_PROMPT = "Please respond as an Egyptian real estate sales agent, speaking in a friendly and professional Egyptian dialect."

# Define the voice names for each dialect (find suitable voices in Google's documentation)
# 'Sharifa' and 'Sadaltager' are just examples.
SAUDI_VOICE_NAME = "Sadaltager"
EGYPTIAN_VOICE_NAME = "Sadaltager"

