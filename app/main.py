import argparse
import uvicorn
import logging
import sys
import os
from app.config import HOST, PORT
# Wait, we need to declare HOST and PORT in config.py if they are not there, or configure them manually.
# Let's import config and add defaults.
from app.api import app, execute_pipeline, execute_pipeline_with_audio
from app.speech import record_audio, record_audio_with_keypress

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

def run_interactive_loop():
    print("=" * 60)
    print("           POCKETDEV AI - INTERACTIVE CLIENT LOOP            ")
    print("=" * 60)
    print("Options:")
    print("  [1] Voice Command (continuous recording - 5 seconds)")
    print("  [2] Voice Command (press Enter to start/stop)")
    print("  [3] Text Command")
    print("  [q] Quit")
    print("-" * 60)
    
    # Check if Gemini key is set
    from app.config import GEMINI_API_KEY
    if not GEMINI_API_KEY:
        print("\nWARNING: GEMINI_API_KEY environment variable is not set!")
        print("Please export GEMINI_API_KEY='your_key_here' or create a .env file.\n")
        
    while True:
        try:
            choice = input("\nSelect option (1, 2, 3 or q): ").strip()
            if choice == "q":
                print("Exiting pocket brain loop. Goodbye!")
                break
            elif choice == "1":
                audio_file = "voice_prompt.wav"
                print("\nRecording for 5 seconds... Speak now!")
                recorded_path = record_audio(audio_file, duration=5)
                execute_pipeline_with_audio(recorded_path)
            elif choice == "2":
                audio_file = "voice_prompt.wav"
                print("")
                recorded_path = record_audio_with_keypress(audio_file)
                execute_pipeline_with_audio(recorded_path)
            elif choice == "3":
                cmd = input("\nEnter text command: ").strip()
                if cmd:
                    execute_pipeline(cmd)
            else:
                print("Invalid option. Choose 1, 2, 3, or q.")
        except KeyboardInterrupt:
            print("\nExiting...")
            break
        except Exception as e:
            logger.exception(f"An error occurred in interactive loop: {e}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="PocketDev AI Phone Brain")
    parser.add_argument("--cli", action="store_true", help="Run in interactive CLI mode instead of FastAPI server")
    parser.add_argument("--port", type=int, default=8002, help="Port to run FastAPI on (default: 8002)")
    
    args = parser.parse_args()
    
    if args.cli:
        run_interactive_loop()
    else:
        logger.info(f"Starting PocketDev AI Brain API on port {args.port}...")
        uvicorn.run(app, host="0.0.0.0", port=args.port)
