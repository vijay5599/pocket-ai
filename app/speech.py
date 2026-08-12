import os
import subprocess
import shutil
import logging
import time
from app.config import AUDIO_SAMPLE_RATE, WHISPER_MODEL_SIZE

logger = logging.getLogger(__name__)

# Lazy load whisper model to avoid long import times
_whisper_model = None

def get_whisper_model():
    global _whisper_model
    if _whisper_model is None:
        from faster_whisper import WhisperModel
        logger.info(f"Loading Faster Whisper model: '{WHISPER_MODEL_SIZE}' on CPU...")
        # CPU execution with int8 quantization is fast and works on both macOS and Termux (ARM)
        _whisper_model = WhisperModel(WHISPER_MODEL_SIZE, device="cpu", compute_type="int8")
        logger.info("Faster Whisper model loaded successfully.")
    return _whisper_model

def record_audio_mac(filepath: str, duration: int = 5):
    """
    Records audio using sounddevice library (for macOS/desktop).
    """
    import sounddevice as sd
    import numpy as np
    from scipy.io import wavfile
    
    logger.info(f"Recording audio for {duration} seconds... Speak now!")
    # Record audio
    recording = sd.rec(
        int(duration * AUDIO_SAMPLE_RATE), 
        samplerate=AUDIO_SAMPLE_RATE, 
        channels=1, 
        dtype='int16'
    )
    sd.wait()  # Wait until recording is finished
    
    # Save as WAV file
    wavfile.write(filepath, AUDIO_SAMPLE_RATE, recording)
    logger.info("Recording finished and saved.")

def record_audio_termux(filepath: str, duration: int = 5):
    """
    Records audio using Termux API CLI commands.
    """
    logger.info("Recording audio using Termux:API...")
    
    # Ensure any previous recording is stopped
    subprocess.run(["termux-microphone-record", "-q"], capture_output=True)
    
    # Start recording
    # termux-microphone-record -f filepath -l 0 (limit 0 = infinite, we stop it manual or sleep)
    subprocess.run(["termux-microphone-record", "-f", filepath, "-l", str(duration)], check=True)
    
    logger.info(f"Recording for {duration} seconds...")
    time.sleep(duration)
    
    # Stop recording to flush content
    subprocess.run(["termux-microphone-record", "-q"], check=True)
    logger.info("Recording finished.")

def record_audio_with_keypress(filepath: str):
    """
    Records audio until the user presses enter.
    """
    is_termux = shutil.which("termux-microphone-record") is not None
    
    if is_termux:
        logger.info("Termux detected. Press Enter to START recording...")
        input()
        subprocess.run(["termux-microphone-record", "-q"], capture_output=True)
        subprocess.run(["termux-microphone-record", "-f", filepath, "-l", "0"], check=True)
        logger.info("Recording... Press Enter to STOP recording.")
        input()
        subprocess.run(["termux-microphone-record", "-q"], check=True)
        logger.info("Recording stopped.")
    else:
        # Mac / Local PC
        import sounddevice as sd
        import numpy as np
        from scipy.io import wavfile
        
        logger.info("Press Enter to START recording (max 30s)...")
        input()
        
        # We start a long recording and will stop it on enter
        logger.info("Recording... Press Enter to STOP recording.")
        max_duration = 30
        
        # We record using an array we can slice or simple continuous stream
        recording = []
        
        def callback(indata, frames, time, status):
            if status:
                logger.warning(status)
            recording.append(indata.copy())
            
        stream = sd.InputStream(samplerate=AUDIO_SAMPLE_RATE, channels=1, dtype='int16', callback=callback)
        with stream:
            input()  # Wait for Enter to stop
            
        if len(recording) > 0:
            audio_data = np.concatenate(recording, axis=0)
            wavfile.write(filepath, AUDIO_SAMPLE_RATE, audio_data)
            logger.info("Recording saved.")
        else:
            logger.error("No audio recorded.")

def transcribe_audio(filepath: str) -> str:
    """
    Transcribes a WAV/MP3 file into text using faster-whisper.
    """
    if not os.path.exists(filepath):
        logger.error(f"Audio file not found for transcription: {filepath}")
        return ""
        
    logger.info("Transcribing audio...")
    try:
        model = get_whisper_model()
        segments, info = model.transcribe(filepath, beam_size=5)
        text = " ".join([segment.text for segment in segments]).strip()
        logger.info(f"Transcribed Text: '{text}'")
        return text
    except Exception as e:
        logger.error(f"Transcription failed: {e}")
        return ""

def record_and_transcribe(filepath: str = "input.wav", duration: int = 5) -> str:
    """
    Helper function to record audio and return transcription.
    """
    is_termux = shutil.which("termux-microphone-record") is not None
    
    try:
        if is_termux:
            record_audio_termux(filepath, duration)
        else:
            record_audio_mac(filepath, duration)
            
        return transcribe_audio(filepath)
    except Exception as e:
        logger.error(f"Recording/transcription workflow error: {e}")
        return ""
