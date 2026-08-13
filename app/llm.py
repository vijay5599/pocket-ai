import os
import logging
import json
import requests
import google.generativeai as genai
import google.api_core.exceptions
from app.config import (
    GEMINI_API_KEY, 
    GEMINI_MODEL_NAME,
    LLM_PROVIDER,
    LLM_API_KEY,
    LLM_BASE_URL,
    LLM_MODEL
)
from app.memory import get_recent_history, resolve_project_path, get_db_connection

logger = logging.getLogger(__name__)

# Upgraded TOOLS_GUIDE to teach the LLM how to utilize run_command dynamically
TOOLS_GUIDE = (
    "- open_vscode: Opens Visual Studio Code on the MacBook.\n"
    "- open_chrome: Opens Google Chrome on the MacBook.\n"
    "- open_terminal: Opens the Terminal application on the MacBook.\n"
    "- open_finder: Opens Finder at the home directory on the MacBook.\n"
    "- open_folder: Opens a specific folder path in Finder on the MacBook. Arguments: {'path': 'string'}\n"
    "- take_screenshot: Takes a screenshot of the MacBook screen (default save to Desktop).\n"
    "- list_downloads: Lists the files inside the Downloads directory on the MacBook.\n"
    "- lock_screen: Locks the MacBook screen immediately.\n"
    "- shutdown: Shuts down the MacBook.\n"
    "- restart: Restarts the MacBook.\n"
    "- run_command: Runs a general terminal shell command or script on the MacBook. Arguments: {'command': 'string'}. "
    "Use this for complex, custom, or multi-step requests not covered by other tools, such as sending emails, "
    "taking and saving screenshots to specific folders, moving/copying files, running custom python code, "
    "or executing AppleScript automations via `osascript -e '...'`.\n"
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
        if "desktop" in cleaned or "folder" in cleaned or "directory" in cleaned:
            # Fallback to run_command for custom location
            return {"tool": "run_command", "arguments": {"command": "screencapture -x ~/Desktop/screenshot_custom.png"}}
        return {"tool": "take_screenshot", "arguments": {}}
    elif "downloads" in cleaned:
        if "list" in cleaned:
            return {"tool": "list_downloads", "arguments": {}}
        else:
            return {"tool": "open_folder", "arguments": {"path": "~/Downloads"}}
    elif "lock" in cleaned:
        return {"tool": "lock_screen", "arguments": {}}
    elif "open folder" in cleaned or "open project" in cleaned:
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

def query_gemini_brain(user_prompt: str) -> dict:
    """
    Queries Google Gemini API with system instructions and chat history.
    """
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
        "For complex, custom, or multi-step requests (e.g. sending an email, taking a screenshot and saving "
        "it in a specific directory, moving files, etc.), you can write a shell command or AppleScript and call "
        "the run_command tool. Be creative and utilize standard macOS CLI utilities (like `screencapture`, `osascript`, `open`, etc.). "
        "Keep replies short and concise."
    )
    
    try:
        model = genai.GenerativeModel(
            model_name=GEMINI_MODEL_NAME,
            system_instruction=system_instruction
        )
        
        prompt_with_context = ""
        if history:
            prompt_with_context += "Recent history:\n"
            for msg in history:
                prompt_with_context += f"{msg['role']}: {msg['content']}\n"
            prompt_with_context += "\n"
        prompt_with_context += f"User: {user_prompt}"
        
        logger.info(f"Querying Gemini ({GEMINI_MODEL_NAME}) with prompt: '{user_prompt}'")
        response = model.generate_content(
            prompt_with_context,
            generation_config={"response_mime_type": "application/json"}
        )
        
        res_data = json.loads(response.text.strip())
        logger.info(f"Gemini parsed response: {res_data}")
        return res_data
    except google.api_core.exceptions.ResourceExhausted:
        logger.warning("Gemini API quota exhausted! Falling back to offline rule-based parser.")
        return run_offline_parser(user_prompt)
    except Exception as e:
        logger.exception(f"Error querying Gemini API: {e}")
        return run_offline_parser(user_prompt)

def query_openai_compatible_brain(user_prompt: str) -> dict:
    """
    Queries an OpenAI-compatible endpoint (OpenAI, Ollama, Groq, DeepSeek).
    """
    provider = LLM_PROVIDER.lower().strip()
    
    base_url = LLM_BASE_URL
    api_key = LLM_API_KEY
    model = LLM_MODEL
    
    if provider == "ollama":
        if not base_url or base_url == "https://api.openai.com/v1":
            base_url = "http://127.0.0.1:11434/v1"
        if not model or model == "gpt-4o-mini":
            model = "llama3"
        api_key = "ollama"
    elif provider == "groq":
        if not base_url or base_url == "https://api.openai.com/v1":
            base_url = "https://api.groq.com/openai/v1"
        if not model or model == "gpt-4o-mini":
            model = "llama3-8b-8192"
    elif provider == "deepseek":
        if not base_url or base_url == "https://api.openai.com/v1":
            base_url = "https://api.deepseek.com/v1"
        if not model or model == "gpt-4o-mini":
            model = "deepseek-chat"
            
    history = get_recent_history(10)
    projects_context = get_known_projects()
    
    system_instruction = (
        "You are PocketDev AI, a personal AI brain running on an Android phone that controls a MacBook worker. "
        "Your task is to understand the user's command and decide if it can be fulfilled by executing a tool "
        "on the Mac, or if you should respond conversationally.\n"
        "You MUST respond with a JSON object ONLY, in one of the following formats:\n"
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
        "For complex, custom, or multi-step requests (e.g. sending an email, taking a screenshot and saving "
        "it in a specific directory, moving files, etc.), you can write a shell command or AppleScript and call "
        "the run_command tool. Be creative and utilize standard macOS CLI utilities (like `screencapture`, `osascript`, `open`, etc.). "
        "Keep replies short and concise."
    )
    
    messages = [{"role": "system", "content": system_instruction}]
    for msg in history:
        role_map = {"user": "user", "assistant": "assistant"}
        messages.append({"role": role_map.get(msg["role"], "user"), "content": msg["content"]})
    messages.append({"role": "user", "content": user_prompt})
    
    headers = {
        "Content-Type": "application/json"
    }
    if api_key and api_key != "ollama":
        headers["Authorization"] = f"Bearer {api_key}"
        
    payload = {
        "model": model,
        "messages": messages,
        "response_format": {"type": "json_object"}
    }
    
    try:
        logger.info(f"Querying {provider} model '{model}' at {base_url}...")
        res = requests.post(f"{base_url}/chat/completions", json=payload, headers=headers, timeout=20)
        res.raise_for_status()
        
        content = res.json()["choices"][0]["message"]["content"]
        res_data = json.loads(content.strip())
        logger.info(f"{provider} parsed response: {res_data}")
        return res_data
    except Exception as e:
        logger.exception(f"Error querying {provider} API: {e}")
        return run_offline_parser(user_prompt)

def query_brain(user_prompt: str) -> dict:
    """
    Main router function to query the selected LLM provider.
    """
    provider = LLM_PROVIDER.lower().strip()
    
    if provider == "gemini":
        res_data = query_gemini_brain(user_prompt)
    else:
        res_data = query_openai_compatible_brain(user_prompt)
        
    if "tool" in res_data and "arguments" in res_data:
        args = res_data["arguments"]
        if "path" in args:
            resolved = resolve_project_path(args["path"])
            if resolved:
                args["path"] = resolved
                
    return res_data

def transcribe_audio_via_api(audio_filepath: str) -> str:
    """
    Transcribes audio using OpenAI or Groq transcription API.
    """
    provider = LLM_PROVIDER.lower().strip()
    api_key = LLM_API_KEY
    base_url = LLM_BASE_URL
    model = "whisper-1"
    
    if provider == "groq":
        base_url = "https://api.groq.com/openai/v1"
        model = "whisper-large-v3"
    elif provider != "openai":
        base_url = "https://api.openai.com/v1"
        
    if not api_key:
        logger.error("No API key available for cloud audio transcription.")
        return ""
        
    url = f"{base_url}/audio/transcriptions"
    headers = {
        "Authorization": f"Bearer {api_key}"
    }
    
    with open(audio_filepath, "rb") as f:
        content_type = "audio/wav"
        if audio_filepath.endswith(".m4a"):
            content_type = "audio/mp4"
        elif audio_filepath.endswith(".amr"):
            content_type = "audio/amr"
            
        files = {
            "file": (os.path.basename(audio_filepath), f, content_type)
        }
        data = {
            "model": model
        }
        try:
            logger.info(f"Uploading audio to {provider} Whisper at {url}...")
            res = requests.post(url, headers=headers, files=files, data=data, timeout=30)
            res.raise_for_status()
            text = res.json().get("text", "").strip()
            logger.info(f"{provider} Whisper result: '{text}'")
            return text
        except Exception as e:
            logger.error(f"Whisper API transcription failed: {e}")
            return ""

def query_brain_with_audio(audio_filepath: str) -> dict:
    """
    Main router function for voice command processing.
    """
    provider = LLM_PROVIDER.lower().strip()
    
    if provider == "gemini":
        if not os.path.exists(audio_filepath):
            logger.error(f"Audio file not found: {audio_filepath}")
            return {"reply": "Sorry, I could not capture your voice input."}

        if not GEMINI_API_KEY:
            logger.error("GEMINI_API_KEY is not set.")
            return {"reply": "I heard your voice command, but I need a Gemini API Key to understand it."}

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
            "  \"transcription\": \"exact transcribed spoken command from the user\",\n"
            "  \"tool\": \"tool_name\",\n"
            "  \"arguments\": {\"param_name\": \"value\"}\n"
            "}\n"
            "If replying conversationally:\n"
            "{\n"
            "  \"transcription\": \"exact transcribed spoken command from the user\",\n"
            "  \"reply\": \"conversational response text\"\n"
            "}\n\n"
            "Available tools:\n"
            f"{TOOLS_GUIDE}\n"
            "Here is the context of saved project folders on the Mac:\n"
            f"{projects_context}\n\n"
            "For complex, custom, or multi-step requests (e.g. sending an email, taking a screenshot and saving "
            "it in a specific directory, moving files, etc.), you can write a shell command or AppleScript and call "
            "the run_command tool. Be creative and utilize standard macOS CLI utilities (like `screencapture`, `osascript`, `open`, etc.). "
            "Keep replies short and concise."
        )

        try:
            model = genai.GenerativeModel(
                model_name=GEMINI_MODEL_NAME,
                system_instruction=system_instruction
            )

            logger.info(f"Reading audio file bytes from {audio_filepath}...")
            with open(audio_filepath, "rb") as f:
                audio_bytes = f.read()

            mime_type = "audio/wav"
            if audio_filepath.endswith(".m4a"):
                mime_type = "audio/mp4"
            elif audio_filepath.endswith(".amr"):
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
            return res_data

        except google.api_core.exceptions.ResourceExhausted:
            logger.warning("Gemini API daily/minute quota exhausted! Audio commands require Gemini, cannot process offline.")
            return {"reply": "Sorry, Gemini API quota is currently exhausted. Please use Text commands (Option 3) which now support offline fallback execution."}
        except Exception as e:
            logger.exception(f"Error querying Gemini API with audio: {e}")
            return {"reply": f"Sorry, I failed to process your voice command: {str(e)}"}
            
    else:
        logger.info(f"Transcribing audio file first via Whisper API for {provider}...")
        transcription = transcribe_audio_via_api(audio_filepath)
        
        if not transcription:
            return {"reply": "Sorry, I was unable to transcribe your voice command using the Whisper API."}
            
        logger.info(f"Whisper transcribed audio to: '{transcription}'. Submitting to {provider} brain...")
        res_data = query_brain(transcription)
        res_data["transcription"] = transcription
        return res_data
