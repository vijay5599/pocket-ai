import os
import subprocess
import shutil
import logging
import time
from app.config import AUDIO_SAMPLE_RATE

logger = logging.getLogger(__name__)

def record_audio_mac(filepath: str, duration: int = 5):
    """
    Records audio using sounddevice library (for macOS/desktop).
    """
    import sounddevice as sd
    import numpy as np
    from scipy.io import wavfile
    
    logger.info(f"Recording audio for {duration} seconds... Speak now!")
    recording = sd.rec(
        int(duration * AUDIO_SAMPLE_RATE), 
        samplerate=AUDIO_SAMPLE_RATE, 
        channels=1, 
        dtype='int16'
    )
    sd.wait()
    wavfile.write(filepath, AUDIO_SAMPLE_RATE, recording)
    logger.info("Recording finished and saved.")

def record_audio_termux(filepath: str, duration: int = 5):
    """
    Records audio using Termux API CLI commands.
    """
    logger.info("Recording audio using Termux:API...")
    if os.path.exists(filepath):
        try:
            os.remove(filepath)
        except Exception as e:
            logger.warning(f"Could not remove existing file: {e}")

    subprocess.run(["termux-microphone-record", "-q"], capture_output=True)
    # Default Termux encoder is amr_nb (writes AMR audio)
    subprocess.run(["termux-microphone-record", "-f", filepath, "-l", str(duration)], check=True)
    logger.info(f"Recording for {duration} seconds...")
    time.sleep(duration)
    subprocess.run(["termux-microphone-record", "-q"], check=True)
    logger.info("Recording finished.")

def record_audio_with_keypress(filepath: str) -> str:
    """
    Records audio until the user presses enter. Returns the recorded filepath.
    """
    is_termux = shutil.which("termux-microphone-record") is not None
    
    if is_termux:
        # Termux records as AMR, change extension to .amr
        amr_path = filepath.replace(".wav", ".amr")
        logger.info("Termux detected. Press Enter to START recording...")
        input()
        if os.path.exists(amr_path):
            try:
                os.remove(amr_path)
            except Exception as e:
                logger.warning(f"Could not remove existing file: {e}")
        subprocess.run(["termux-microphone-record", "-q"], capture_output=True)
        subprocess.run(["termux-microphone-record", "-f", amr_path, "-l", "0"], check=True)
        logger.info("Recording... Press Enter to STOP recording.")
        input()
        subprocess.run(["termux-microphone-record", "-q"], check=True)
        logger.info("Recording stopped.")
        return amr_path
    else:
        import sounddevice as sd
        import numpy as np
        from scipy.io import wavfile
        
        logger.info("Press Enter to START recording (max 30s)...")
        input()
        logger.info("Recording... Press Enter to STOP recording.")
        recording = []
        
        def callback(indata, frames, time, status):
            if status:
                logger.warning(status)
            recording.append(indata.copy())
            
        stream = sd.InputStream(samplerate=AUDIO_SAMPLE_RATE, channels=1, dtype='int16', callback=callback)
        with stream:
            input()
            
        if len(recording) > 0:
            audio_data = np.concatenate(recording, axis=0)
            wavfile.write(filepath, AUDIO_SAMPLE_RATE, audio_data)
            logger.info("Recording saved.")
        else:
            logger.error("No audio recorded.")
        return filepath

def record_audio(filepath: str = "input.wav", duration: int = 5) -> str:
    """
    Helper function to record audio and return the filepath.
    """
    is_termux = shutil.which("termux-microphone-record") is not None
    if is_termux:
        # Save as .amr for Termux
        amr_path = filepath.replace(".wav", ".amr")
        record_audio_termux(amr_path, duration)
        return amr_path
    else:
        record_audio_mac(filepath, duration)
        return filepath
