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

def sanitize_messages_for_llm(messages: list) -> list:
    """
    Ensures message roles alternate between user and assistant to prevent API 400 errors.
    Merges consecutive messages of the same role together.
    """
    sanitized = []
    if not messages:
        return sanitized
        
    if messages[0]["role"] == "system":
        sanitized.append(messages[0])
        start_idx = 1
    else:
        start_idx = 0
        
    for i in range(start_idx, len(messages)):
        msg = messages[i]
        if not msg.get("content"):
            continue
            
        if not sanitized or sanitized[-1]["role"] != msg["role"]:
            sanitized.append(msg.copy())
        else:
            sanitized[-1]["content"] += "\n" + msg["content"]
            
    return sanitized

# Upgraded TOOLS_GUIDE with a strict instruction on screencapture flags
TOOLS_GUIDE = (
    "- open_vscode: Opens Visual Studio Code on the MacBook. Arguments: {'path': 'string' (optional path to a file or folder to open)}\n"
    "- open_chrome: Opens Google Chrome on the MacBook. Arguments: {'url': 'string' (optional URL to open, e.g., a pre-filled Gmail compose link)}\n"
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
    "or executing AppleScript automations via `osascript -e '...'`. IMPORTANT: when running a custom screenshot "
    "command, never use the interactive '-i' flag as it pauses execution; always run it instantly and silently \n"
    "- write_file: Writes text content to a file on the MacBook. Arguments: {'path': 'string', 'content': 'string'}\n"
    "- send_email: Composes and sends an email natively via the macOS Mail app. Arguments: {'to_email': 'string', 'subject': 'string', 'body': 'string'}\n"
    "- automate_browser: Automates actions in a headless browser (navigate, click, fill input, screenshot). Arguments: {'url': 'string', 'action': 'string' (optional: 'screenshot' or 'content'), 'click_selector': 'string' (optional CSS click selector), 'fill_selector': 'string' (optional CSS input selector), 'fill_text': 'string' (optional text to type into fill_selector)}\n"
    "- modify_file: Modifies an existing file on the MacBook by finding specific target text and replacing it. Arguments: {'path': 'string', 'target_text': 'string', 'replacement_text': 'string'}\n"
    "- play_media: Searches for a video or song on YouTube or YouTube Music, finds the direct link, and opens it directly in Chrome to play automatically. Arguments: {'query': 'string', 'platform': 'string' (optional: 'youtube' or 'youtube_music')}\n"
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

def query_gemini_brain(user_prompt: str) -> any:
    """
    Queries Google Gemini API with system instructions and chat history.
    Returns parsed JSON object (can be list or dict).
    """
    genai.configure(api_key=GEMINI_API_KEY)
    history = get_recent_history(10)
    projects_context = get_known_projects()
    
    system_instruction = (
        "You are PocketDev AI, a personal AI brain running on an Android phone that controls a MacBook worker. "
        "Your task is to understand the user's command and decide if it can be fulfilled by executing a tool "
        "on the Mac, or if you should respond conversationally.\n\n"
        "You MUST respond with a JSON object (or JSON list of objects for multi-step tasks) in one of the following formats:\n"
        "If executing a single tool:\n"
        "{\n"
        "  \"tool\": \"tool_name\",\n"
        "  \"arguments\": {\"param_name\": \"value\"}\n"
        "}\n"
        "If executing multiple actions sequentially (such as opening VS Code and creating a python file), return a JSON list of tool objects, e.g.:\n"
        "[\n"
        "  {\"tool\": \"open_vscode\", \"arguments\": {}},\n"
        "  {\"tool\": \"write_file\", \"arguments\": {\"path\": \"~/Desktop/script.py\", \"content\": \"print('hello')\"}}\n"
        "]\n"
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
        "IMPORTANT: when using `screencapture` to capture the screen, never use the '-i' (interactive) flag as it pauses execution; "
        "always run it instantly and silently using `screencapture -x [filepath.png]`. "
        "If the user asks to create a file and open it (or work on it in VS Code), you MUST return both steps in a JSON list: "
        "first write the file using `write_file`, and then open it using `open_vscode` (passing the path argument). "
        "If the user asks to write or send an email, you MUST use the `send_email` tool to actually send the email. "
        "Only use `open_chrome` with a Gmail compose URL if the user explicitly wants to manually compose/draft "
        "it in the browser without automatically sending it."
        "If the user asks to play a song, play music, or search for a song (e.g. 'play any new kannada song'), "
        "you MUST call `open_chrome` and pass a YouTube Music search URL: 'https://music.youtube.com/search?q=search_terms'."
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

def get_groq_tools_payload() -> list:
    return [
        {
            "type": "function",
            "function": {
                "name": "open_vscode",
                "description": "Opens Visual Studio Code on the MacBook. Option parameter path can be set to open a file/folder.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string", "description": "optional path to a file or folder to open"}
                    }
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "open_chrome",
                "description": "Opens Google Chrome on the MacBook. Optional URL to open can be specified.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "url": {"type": "string", "description": "optional URL to open"}
                    }
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "open_terminal",
                "description": "Opens the Terminal application on the MacBook.",
                "parameters": {"type": "object", "properties": {}}
            }
        },
        {
            "type": "function",
            "function": {
                "name": "open_finder",
                "description": "Opens Finder at the home directory on the MacBook.",
                "parameters": {"type": "object", "properties": {}}
            }
        },
        {
            "type": "function",
            "function": {
                "name": "open_folder",
                "description": "Opens a specific folder path in Finder on the MacBook.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string", "description": "The folder path to open"}
                    },
                    "required": ["path"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "take_screenshot",
                "description": "Takes a screenshot of the MacBook screen (default save to Desktop).",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string", "description": "Optional save path"}
                    }
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "list_downloads",
                "description": "Lists the files inside the Downloads directory on the MacBook.",
                "parameters": {"type": "object", "properties": {}}
            }
        },
        {
            "type": "function",
            "function": {
                "name": "lock_screen",
                "description": "Locks the MacBook screen immediately.",
                "parameters": {"type": "object", "properties": {}}
            }
        },
        {
            "type": "function",
            "function": {
                "name": "shutdown",
                "description": "Shuts down the MacBook.",
                "parameters": {"type": "object", "properties": {}}
            }
        },
        {
            "type": "function",
            "function": {
                "name": "restart",
                "description": "Restarts the MacBook.",
                "parameters": {"type": "object", "properties": {}}
            }
        },
        {
            "type": "function",
            "function": {
                "name": "run_command",
                "description": "Runs a general terminal shell command or script on the MacBook. Used for custom/complex script runs.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "command": {"type": "string", "description": "The command string to run"},
                        "timeout": {"type": "integer", "description": "Optional timeout in seconds. Default is 60. Set larger (e.g. 180) for long commands like package installations."}
                    },
                    "required": ["command"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "write_file",
                "description": "Writes text content to a file on the MacBook.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string", "description": "File path"},
                        "content": {"type": "string", "description": "Content of the file"}
                    },
                    "required": ["path", "content"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "send_email",
                "description": "Composes and sends an email natively via the macOS Mail app.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "to_email": {"type": "string", "description": "Recipient email"},
                        "subject": {"type": "string", "description": "Email subject"},
                        "body": {"type": "string", "description": "Email body"}
                    },
                    "required": ["to_email"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "automate_browser",
                "description": "Automates actions in a headless browser (navigating, clicking, filling inputs, screenshot).",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "url": {"type": "string", "description": "The URL to navigate to"},
                        "action": {"type": "string", "description": "Optional action: screenshot or content"},
                        "click_selector": {"type": "string", "description": "Optional selector to click"},
                        "fill_selector": {"type": "string", "description": "Optional selector to fill"},
                        "fill_text": {"type": "string", "description": "Optional text to fill"}
                    },
                    "required": ["url"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "modify_file",
                "description": "Modifies an existing file on the MacBook by finding specific target text and replacing it.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string", "description": "File path"},
                        "target_text": {"type": "string", "description": "The exact string to find"},
                        "replacement_text": {"type": "string", "description": "The replacement string"}
                    },
                    "required": ["path", "target_text", "replacement_text"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "play_media",
                "description": "Searches for a video or song on YouTube or YouTube Music, finds the direct link, and opens it directly in Chrome to play automatically.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "The search query (e.g. song or artist)"},
                        "platform": {"type": "string", "description": "Target platform: 'youtube' or 'youtube_music'"}
                    },
                    "required": ["query"]
                }
            }
        }
    ]

def query_openai_compatible_brain(user_prompt: str) -> dict:
    """
    Queries an OpenAI-compatible API (like Groq) using native tool calling.
    Returns parsed JSON object containing either tool execution steps or conversational reply.
    """
    provider = LLM_PROVIDER.lower().strip()
    api_key = LLM_API_KEY
    base_url = LLM_BASE_URL
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
        "Your task is to understand the user's command and decide if it can be fulfilled by executing one of your "
        "available tools on the Mac, or if you should respond conversationally.\n\n"
        "Here is the context of saved project folders on the Mac:\n"
        f"{projects_context}\n\n"
        "If the user asks to play a song, play music, or search for a song, you MUST call the play_media tool, "
        "passing the song/artist query and the target platform ('youtube' or 'youtube_music').\n"
        "Keep replies short and concise."
    )
    
    messages = [{"role": "system", "content": system_instruction}]
    for msg in history:
        role_map = {"user": "user", "assistant": "assistant"}
        messages.append({"role": role_map.get(msg["role"], "user"), "content": msg["content"]})
    messages.append({"role": "user", "content": user_prompt})
    
    # Sanitize roles to ensure alternating order for Groq/OpenAI APIs
    messages = sanitize_messages_for_llm(messages)
    
    headers = {
        "Content-Type": "application/json"
    }
    if api_key and api_key != "ollama":
        headers["Authorization"] = f"Bearer {api_key}"
        
    payload = {
        "model": model,
        "messages": messages,
        "tools": get_groq_tools_payload(),
        "tool_choice": "auto"
    }
    
    try:
        logger.info(f"Querying {provider} model '{model}' using native tools at {base_url}...")
        res = requests.post(f"{base_url}/chat/completions", json=payload, headers=headers, timeout=20)
        res.raise_for_status()
        
        choice_msg = res.json()["choices"][0]["message"]
        
        if "tool_calls" in choice_msg:
            tool_calls = choice_msg["tool_calls"]
            steps = []
            for call in tool_calls:
                func = call["function"]
                try:
                    fn_args = json.loads(func["arguments"])
                except Exception:
                    fn_args = {}
                steps.append({
                    "tool": func["name"],
                    "arguments": fn_args
                })
            
            if len(steps) == 1:
                res_data = steps[0]
            else:
                res_data = {"steps": steps}
        else:
            content = choice_msg.get("content", "").strip()
            try:
                res_data = json.loads(content)
            except Exception:
                res_data = {"reply": content}
                
        logger.info(f"{provider} parsed response: {res_data}")
        return res_data
    except Exception as e:
        if 'res' in locals() and hasattr(res, 'text'):
            logger.error(f"Groq/OpenAI API Error Response Body: {res.text}")
        logger.exception(f"Error querying {provider} API: {e}")
        return run_offline_parser(user_prompt)

def query_brain(user_prompt: str) -> dict:
    """
    Main router function to query the selected LLM provider with self-correcting routing.
    Standardizes output to always return a dictionary containing either a single tool call,
    a conversational reply, or a list of steps: {'steps': [...]}
    """
    provider = LLM_PROVIDER.lower().strip()
    
    if provider == "gemini":
        res_data = query_gemini_brain(user_prompt)
    else:
        res_data = query_openai_compatible_brain(user_prompt)
        
    # Helper to clean up individual tool call steps
    def process_tool_call(call: dict) -> dict:
        supported_static_tools = {
            "open_vscode", "open_chrome", "open_terminal", "open_finder",
            "open_folder", "take_screenshot", "list_downloads", "lock_screen",
            "shutdown", "restart", "run_command", "write_file", "send_email",
            "automate_browser", "modify_file", "play_media"
        }
        if "tool" in call:
            tool_name = call["tool"]
            if "args" in call and "arguments" not in call:
                call["arguments"] = call["args"]
            args = call.get("arguments", {})
            
            # Self-correct unrecognized tool names to run_command if they look like commands
            if tool_name not in supported_static_tools:
                if "command" in args:
                    logger.warning(f"Self-corrected tool name hallucination '{tool_name}' -> 'run_command'")
                    call["tool"] = "run_command"
                else:
                    logger.warning(f"Unsupported tool '{tool_name}' returned. Resetting via offline fallback.")
                    return run_offline_parser(user_prompt)
                    
            if "arguments" in call:
                args = call["arguments"]
                if "path" in args:
                    resolved = resolve_project_path(args["path"])
                    if resolved:
                        args["path"] = resolved
        return call

    if isinstance(res_data, list):
        processed_steps = []
        for step in res_data:
            if isinstance(step, dict):
                processed_steps.append(process_tool_call(step))
        # Deduplicate consecutive identical steps
        deduplicated_steps = []
        for step in processed_steps:
            if not deduplicated_steps:
                deduplicated_steps.append(step)
            else:
                last = deduplicated_steps[-1]
                if last.get("tool") == step.get("tool") and last.get("arguments") == step.get("arguments"):
                    logger.warning(f"Deduplicated consecutive identical step: {step.get('tool')}")
                    continue
                deduplicated_steps.append(step)
        return {"steps": deduplicated_steps}
    elif isinstance(res_data, dict):
        if "steps" in res_data:
            processed_steps = [process_tool_call(s) for s in res_data["steps"] if isinstance(s, dict)]
            # Deduplicate consecutive identical steps
            deduplicated_steps = []
            for step in processed_steps:
                if not deduplicated_steps:
                    deduplicated_steps.append(step)
                else:
                    last = deduplicated_steps[-1]
                    if last.get("tool") == step.get("tool") and last.get("arguments") == step.get("arguments"):
                        logger.warning(f"Deduplicated consecutive identical step: {step.get('tool')}")
                        continue
                    deduplicated_steps.append(step)
            res_data["steps"] = deduplicated_steps
            return res_data
        return process_tool_call(res_data)
    else:
        return {"reply": f"Could not parse LLM response: {res_data}"}

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
            "You MUST respond with a JSON object (or JSON list of objects for multi-step tasks) in one of the following formats:\n"
            "If executing a single tool:\n"
            "{\n"
            "  \"transcription\": \"exact transcribed spoken command from the user\",\n"
            "  \"tool\": \"tool_name\",\n"
            "  \"arguments\": {\"param_name\": \"value\"}\n"
            "}\n"
            "If executing multiple actions sequentially (such as opening VS Code and creating a python file), return a JSON list of tool objects, e.g.:\n"
            "[\n"
            "  {\"tool\": \"open_vscode\", \"arguments\": {}},\n"
            "  {\"tool\": \"write_file\", \"arguments\": {\"path\": \"~/Desktop/script.py\", \"content\": \"print('hello')\"}}\n"
            "]\n"
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
            "IMPORTANT: when using `screencapture` to capture the screen, never use the '-i' (interactive) flag as it pauses execution; "
            "always run it instantly and silently using `screencapture -x [filepath.png]`. "
            "If the user asks to create a file and open it (or work on it in VS Code), you MUST return both steps in a JSON list: "
            "first write the file using `write_file`, and then open it using `open_vscode` (passing the path argument). "
            "If the user asks to write or send an email, you MUST use the `send_email` tool to actually send the email. "
            "Only use `open_chrome` with a Gmail compose URL if the user explicitly wants to manually compose/draft "
            "it in the browser without automatically sending it."
            "If the user asks to play a song, play music, or search for a song (e.g. 'play any new kannada song'), "
            "you MUST call the play_media tool, passing the song/artist query and the target platform ('youtube' or 'youtube_music')."
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
            if isinstance(res_data, list):
                res_data = {"steps": res_data}
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
