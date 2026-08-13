import os
from dotenv import load_dotenv

# Load environment variables from .env file relative to the app structure
app_parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
env_path = os.path.join(app_parent_dir, ".env")
load_dotenv(dotenv_path=env_path)

# API Keys
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL_NAME = os.getenv("GEMINI_MODEL_NAME", "gemini-1.5-flash")

# Multi-Provider LLM Config
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "gemini")  # Options: gemini, openai, ollama, groq, deepseek
LLM_API_KEY = os.getenv("LLM_API_KEY", "")
LLM_BASE_URL = os.getenv("LLM_BASE_URL", "https://api.openai.com/v1")
LLM_MODEL = os.getenv("LLM_MODEL", "gpt-4o-mini")

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

