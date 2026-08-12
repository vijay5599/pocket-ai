import os
import logging
import json
import google.generativeai as genai
import google.api_core.exceptions
from app.config import GEMINI_API_KEY
from app.memory import get_recent_history, resolve_project_path, get_db_connection

logger = logging.getLogger(__name__)

# List of available tools for reference in system instructions
TOOLS_GUIDE = (
    "- open_vscode: Opens Visual Studio Code on the MacBook.\n"
    "- open_chrome: Opens Google Chrome on the MacBook.\n"
    "- open_terminal: Opens the Terminal application on the MacBook.\n"
    "- open_finder: Opens Finder at the home directory on the MacBook.\n"
    "- open_folder: Opens a specific folder path in Finder on the MacBook. Arguments: {'path': 'string'}\n"
    "- take_screenshot: Takes a screenshot of the MacBook screen.\n"
    "- list_downloads: Lists the files inside the Downloads directory on the MacBook.\n"
    "- lock_screen: Locks the MacBook screen immediately.\n"
    "- shutdown: Shuts down the MacBook.\n"
    "- restart: Restarts the MacBook.\n"
    "- run_command: Runs a general terminal shell command on the MacBook. Arguments: {'command': 'string'}\n"
)

def run_offline_parser(user_prompt: str) -> dict:
    """
    Offline fallback parser that translates user prompts to tools using regex/rules.
    """
    cleaned = user_prompt.lower().strip()
    if "vscode" in cleaned or "vs code" in cleaned:
        return {"tool": "open_vscode", "arguments": {}}
    elif "chrome" in cleaned or "google chrome" in cleaned:
        return {"tool": "open_chrome", "arguments": {}}
    elif "terminal" in cleaned:
        return {"tool": "open_terminal", "arguments": {}}
    elif "finder" in cleaned:
        return {"tool": "open_finder", "arguments": {}}
    elif "screenshot" in cleaned:
        return {"tool": "take_screenshot", "arguments": {}}
    elif "downloads" in cleaned:
        if "list" in cleaned:
            return {"tool": "list_downloads", "arguments": {}}
        else:
            return {"tool": "open_folder", "arguments": {"path": "~/Downloads"}}
    elif "lock" in cleaned:
        return {"tool": "lock_screen", "arguments": {}}
    elif "open folder" in cleaned or "open project" in cleaned:
        # Try to extract path
        parts = user_prompt.split("open folder")
        if len(parts) < 2:
            parts = user_prompt.split("open project")
        if len(parts) >= 2:
            extracted_path = parts[1].strip()
            return {"tool": "open_folder", "arguments": {"path": extracted_path}}
        return {"tool": "open_finder", "arguments": {}}
    else:
        return {"reply": f"Offline Brain: I heard you say '{user_prompt}'"}

def get_known_projects() -> str:
    """
    Fetches saved project paths from database to give LLM context on known projects.
    """
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT key, value FROM key_value_store WHERE key LIKE 'project_path_%'")
        rows = cursor.fetchall()
        conn.close()
        
        if not rows:
            return "No known project folders saved yet."
            
        projects_str = "Known projects and their folders:\n"
        for row in rows:
            proj_name = row["key"].replace("project_path_", "")
            projects_str += f"- {proj_name}: {row['value']}\n"
        return projects_str
    except Exception as e:
        logger.error(f"Error getting known projects: {e}")
        return "Could not retrieve known projects."

def query_brain(user_prompt: str) -> dict:
    """
    Queries Gemini with context and returns a tool dictionary or conversational reply.
    """
    if not GEMINI_API_KEY:
        logger.warning("GEMINI_API_KEY is not set. Falling back to rule-based parser for demonstration.")
        return run_offline_parser(user_prompt)

    genai.configure(api_key=GEMINI_API_KEY)
    history = get_recent_history(10)
    projects_context = get_known_projects()
    
    system_instruction = (
        "You are PocketDev AI, a personal AI brain running on an Android phone that controls a MacBook worker. "
        "Your task is to understand the user's command and decide if it can be fulfilled by executing a tool "
        "on the Mac, or if you should respond conversationally.\n\n"
        "You MUST respond with a JSON object in one of the following formats:\n"
        "If executing a tool:\n"
        "{\n"
        "  \"tool\": \"tool_name\",\n"
        "  \"arguments\": {\"param_name\": \"value\"}\n"
        "}\n"
        "If replying conversationally:\n"
        "{\n"
        "  \"reply\": \"conversational response text\"\n"
        "}\n\n"
        "Available tools:\n"
        f"{TOOLS_GUIDE}\n"
        "Here is the context of saved project folders on the Mac:\n"
        f"{projects_context}\n\n"
        "If the user asks to open a specific project, call open_folder with the saved path. "
        "Keep replies short and concise."
    )
    
    try:
        model = genai.GenerativeModel(
            model_name="gemini-2.5-flash",
            system_instruction=system_instruction
        )
        
        prompt_with_context = ""
        if history:
            prompt_with_context += "Recent history:\n"
            for msg in history:
                prompt_with_context += f"{msg['role']}: {msg['content']}\n"
            prompt_with_context += "\n"
        prompt_with_context += f"User: {user_prompt}"
        
        logger.info(f"Querying Gemini (JSON Mode) with prompt: '{user_prompt}'")
        response = model.generate_content(
            prompt_with_context,
            generation_config={"response_mime_type": "application/json"}
        )
        
        res_data = json.loads(response.text.strip())
        logger.info(f"Gemini parsed response: {res_data}")
        
        if "tool" in res_data and "arguments" in res_data:
            args = res_data["arguments"]
            if "path" in args:
                resolved = resolve_project_path(args["path"])
                if resolved:
                    args["path"] = resolved
                    
        return res_data
        
    except google.api_core.exceptions.ResourceExhausted:
        logger.warning("Gemini API daily/minute quota exhausted! Falling back to offline rule-based parser.")
        return run_offline_parser(user_prompt)
    except Exception as e:
        logger.exception(f"Error querying Gemini API: {e}")
        return {"reply": f"Sorry, I ran into an error connecting to the AI: {str(e)}"}

def query_brain_with_audio(audio_filepath: str) -> dict:
    """
    Passes a raw WAV audio file directly to Gemini to analyze the spoken command.
    """
    if not os.path.exists(audio_filepath):
        logger.error(f"Audio file not found: {audio_filepath}")
        return {"reply": "Sorry, I could not capture your voice input."}

    if not GEMINI_API_KEY:
        logger.error("GEMINI_API_KEY is not set. Audio commands require Gemini.")
        return {"reply": "I heard your voice command, but I need a Gemini API Key to understand the audio. Please configure the GEMINI_API_KEY in your env."}

    genai.configure(api_key=GEMINI_API_KEY)
    projects_context = get_known_projects()

    system_instruction = (
        "You are PocketDev AI, a personal AI brain running on an Android phone that controls a MacBook worker. "
        "You will receive a voice recording of the user's command. "
        "Your task is to listen to the audio, understand their intent, and decide if it can be fulfilled by executing a tool "
        "on the Mac, or if you should respond conversationally.\n\n"
        "You MUST respond with a JSON object in one of the following formats:\n"
        "If executing a tool:\n"
        "{\n"
        "  \"tool\": \"tool_name\",\n"
        "  \"arguments\": {\"param_name\": \"value\"}\n"
        "}\n"
        "If replying conversationally:\n"
        "{\n"
        "  \"reply\": \"conversational response text\"\n"
        "}\n\n"
        "Available tools:\n"
        f"{TOOLS_GUIDE}\n"
        "Here is the context of saved project folders on the Mac:\n"
        f"{projects_context}\n\n"
        "If the user asks to open a specific project, call open_folder with the saved path. "
        "Keep replies short and concise."
    )

    try:
        model = genai.GenerativeModel(
            model_name="gemini-2.5-flash",
            system_instruction=system_instruction
        )

        logger.info(f"Reading audio file bytes from {audio_filepath}...")
        with open(audio_filepath, "rb") as f:
            audio_bytes = f.read()

        mime_type = "audio/wav"
        if audio_filepath.endswith(".amr"):
            mime_type = "audio/amr"
        elif audio_filepath.endswith(".aac"):
            mime_type = "audio/aac"
            
        audio_part = {
            "mime_type": mime_type,
            "data": audio_bytes
        }

        response = model.generate_content(
            [
                audio_part,
                "Listen to this audio recording, transcribe the spoken command, and execute it using the appropriate tool or reply."
            ],
            generation_config={"response_mime_type": "application/json"}
        )

        res_data = json.loads(response.text.strip())
        logger.info(f"Gemini Audio parsed response: {res_data}")

        if "tool" in res_data and "arguments" in res_data:
            args = res_data["arguments"]
            if "path" in args:
                resolved = resolve_project_path(args["path"])
                if resolved:
                    args["path"] = resolved
                    
        return res_data

    except google.api_core.exceptions.ResourceExhausted:
        logger.warning("Gemini API daily/minute quota exhausted! Audio commands require Gemini, cannot process offline.")
        return {"reply": "Sorry, Gemini API quota is currently exhausted. Please use Text commands (Option 3) which now support offline fallback execution."}
    except Exception as e:
        logger.exception(f"Error querying Gemini API with audio: {e}")
        return {"reply": f"Sorry, I failed to process your voice command: {str(e)}"}
