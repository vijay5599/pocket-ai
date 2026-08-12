import logging
import google.generativeai as genai
from app.config import GEMINI_API_KEY
from app.memory import get_recent_history, resolve_project_path, get_db_connection

logger = logging.getLogger(__name__)

# Define mock function schemas for Gemini tool calling
def open_vscode():
    """Opens Visual Studio Code on the MacBook."""
    pass

def open_chrome():
    """Opens Google Chrome on the MacBook."""
    pass

def open_terminal():
    """Opens the Terminal application on the MacBook."""
    pass

def open_finder():
    """Opens Finder at the home directory on the MacBook."""
    pass

def open_folder(path: str):
    """
    Opens a specific folder path in Finder on the MacBook.
    
    Args:
        path: The absolute path of the folder to open (e.g., '~/Projects/flutter' or '~/Downloads').
    """
    pass

def take_screenshot():
    """Takes a screenshot of the MacBook screen."""
    pass

def list_downloads():
    """Lists the files inside the Downloads directory on the MacBook."""
    pass

def lock_screen():
    """Locks the MacBook screen immediately."""
    pass

def shutdown():
    """Shuts down the MacBook."""
    pass

def restart():
    """Restarts the MacBook."""
    pass

def run_command(command: str):
    """
    Runs a general terminal shell command on the MacBook. Use this ONLY if there is no other specific tool available.
    
    Args:
        command: The exact shell command to run.
    """
    pass

# Map of available tools
ALL_TOOLS = [
    open_vscode,
    open_chrome,
    open_terminal,
    open_finder,
    open_folder,
    take_screenshot,
    list_downloads,
    lock_screen,
    shutdown,
    restart,
    run_command
]

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
    Queries Gemini with context (history + saved projects) and tool definitions.
    Returns:
        A dict with either:
        - {"tool": "tool_name", "arguments": {...}}
        - {"reply": "conversational text response"}
    """
    if not GEMINI_API_KEY:
        logger.warning("GEMINI_API_KEY is not set. Falling back to rule-based parser for demonstration.")
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
        else:
            return {"reply": f"Mock Brain: I heard you say '{user_prompt}'"}
        
    genai.configure(api_key=GEMINI_API_KEY)
    
    # Compile history and system instructions
    history = get_recent_history(10)
    projects_context = get_known_projects()
    
    system_instruction = (
        "You are PocketDev AI, a personal AI brain running on an Android phone that controls a MacBook worker. "
        "Your task is to understand the user's command and decide if it can be fulfilled by executing a tool "
        "on the Mac, or if you should respond conversationally.\n\n"
        "Here is the context of saved project folders on the Mac:\n"
        f"{projects_context}\n\n"
        "If the user asks to open a specific project (e.g. 'open my flutter project'), check the list of known projects. "
        "If it matches, call open_folder with the saved path. If it does not match but you can guess the path, "
        "use open_folder. If it's a general conversation, reply directly without calling any tools.\n"
        "Maintain a friendly, assistant-like tone. Keep replies short and concise so they can be spoken clearly."
    )
    
    try:
        model = genai.GenerativeModel(
            model_name="gemini-2.5-flash",
            tools=ALL_TOOLS,
            system_instruction=system_instruction
        )
        
        # Format chat history for Gemini
        chat = model.start_chat()
        for msg in history:
            # We map history to chat
            # Note: Gemini chat expects roles: user, model
            role = "user" if msg["role"] == "user" else "model"
            # Chat history must alternate correctly. For robustness, we can just feed past exchanges
            # to make sure the conversational flow works.
            # But to be simple and bulletproof, we can also pass the history as part of the prompt,
            # or use standard start_chat with history. Let's do a simple prompt formatting to be safe
            # and avoid alternating role error issues if roles are unbalanced.
            pass

        # Construct prompt with conversation context
        prompt_with_context = ""
        if history:
            prompt_with_context += "Recent history:\n"
            for msg in history:
                prompt_with_context += f"{msg['role']}: {msg['content']}\n"
            prompt_with_context += "\n"
        prompt_with_context += f"User: {user_prompt}"
        
        logger.info(f"Querying Gemini with prompt: '{user_prompt}'")
        response = model.generate_content(prompt_with_context)
        
        # Check if model wants to call a tool
        if response.candidates and response.candidates[0].content.parts:
            parts = response.candidates[0].content.parts
            # Look for function call part
            for part in parts:
                if part.function_call:
                    func_call = part.function_call
                    tool_name = func_call.name
                    # Convert MapComposite to dict
                    args = {}
                    for k, v in func_call.args.items():
                        args[k] = v
                        
                    logger.info(f"Gemini decided to call tool: {tool_name} with arguments: {args}")
                    
                    # If path argument exists, check if we should resolve it from memory
                    if "path" in args:
                        resolved = resolve_project_path(args["path"])
                        if resolved:
                            args["path"] = resolved
                            
                    return {
                        "tool": tool_name,
                        "arguments": args
                    }
                    
        # Otherwise, it's a normal conversational reply
        reply_text = response.text if response.text else "I couldn't understand that command."
        logger.info(f"Gemini conversational reply: '{reply_text}'")
        return {"reply": reply_text}
        
    except Exception as e:
        logger.exception(f"Error querying Gemini API: {e}")
        return {"reply": f"Sorry, I ran into an error connecting to the AI: {str(e)}"}
