import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# API Keys
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")

# Mac Agent Endpoint
MAC_AGENT_URL = os.getenv("MAC_AGENT_URL", "http://127.0.0.1:8001")
MAC_AGENT_AUTH_TOKEN = os.getenv("MAC_AGENT_AUTH_TOKEN", "")

# Database Config
DB_PATH = os.getenv("DB_PATH", os.path.expanduser("~/pocketdev_ai.db"))

# Audio Recording & Speech to Text Config
AUDIO_SAMPLE_RATE = int(os.getenv("AUDIO_SAMPLE_RATE", "16000"))
WHISPER_MODEL_SIZE = os.getenv("WHISPER_MODEL_SIZE", "tiny")  # "tiny" is fast and lightweight for mobile/Termux

# Text to Speech Config
TTS_VOICE = os.getenv("TTS_VOICE", "en-US-GuyNeural")  # Microsoft Edge TTS Voice
TTS_OUTPUT_FILE = os.getenv("TTS_OUTPUT_FILE", "response.mp3")

# FastAPI Brain Server Config
HOST = os.getenv("BRAIN_HOST", "0.0.0.0")
PORT = int(os.getenv("BRAIN_PORT", "8002"))

