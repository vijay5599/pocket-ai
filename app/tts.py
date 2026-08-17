import asyncio
import os
import subprocess
import shutil
import logging
import edge_tts
from app.config import TTS_VOICE, TTS_OUTPUT_FILE

logger = logging.getLogger(__name__)

def play_audio(filepath: str):
    """
    Plays an audio file using available system player commands.
    """
    if not os.path.exists(filepath):
        logger.error(f"Audio file not found: {filepath}")
        return
        
    logger.info(f"Playing audio: {filepath}")
    
    # List of audio players to try
    # 1. afplay (macOS native)
    # 2. termux-media-player (Termux audio player)
    # 3. play-audio (Termux:API alternative)
    # 4. mpv (cross-platform CLI player)
    # 5. ffplay (ffmpeg tool)
    
    players = [
        ("afplay", [filepath]),
        ("termux-media-player", ["play", filepath]),
        ("play-audio", [filepath]),
        ("mpv", [filepath, "--no-video"]),
        ("ffplay", [filepath, "-nodisp", "-autoexit", "-loglevel", "quiet"]),
    ]
    
    for cmd, args in players:
        if shutil.which(cmd):
            logger.info(f"Found player '{cmd}', spawning in background...")
            try:
                subprocess.Popen([cmd] + args)
                return
            except Exception as e:
                logger.error(f"Player {cmd} failed to launch: {e}")
                continue
                
    logger.warning("No command-line audio player could be found to play back TTS output. Output saved to response.mp3.")

async def _synthesize_speech(text: str, filepath: str):
    communicate = edge_tts.Communicate(text, TTS_VOICE)
    await communicate.save(filepath)

def speak(text: str, filepath: str = TTS_OUTPUT_FILE):
    """
    Synthesizes and speaks text. Blocks until completion.
    """
    logger.info(f"Speaking: {text}")
    try:
        # Run edge-tts to generate mp3
        asyncio.run(_synthesize_speech(text, filepath))
        # Play the generated audio file
        play_audio(filepath)
    except Exception as e:
        logger.error(f"Error in TTS synthesis/playback: {e}")

# Simple test block
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    speak("Hello! I am the PocketDev AI voice system. Testing text to speech.")
