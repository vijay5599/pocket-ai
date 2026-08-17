import os
import logging
from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.responses import HTMLResponse, FileResponse
from pydantic import BaseModel
from typing import Dict, Any, List
from app.llm import query_brain, query_brain_with_audio
from app.tts import speak
from app.speech import record_audio
from app.memory import add_message, log_tool_call, get_recent_history, set_value, get_value

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="PocketDev AI - Brain Service", version="1.0")

class CommandRequest(BaseModel):
    command: str

class MemoryRequest(BaseModel):
    key: str
    value: str

def execute_pipeline(user_prompt: str) -> str:
    """
    Executes the command pipeline: user prompt -> query brain -> execute tool -> speak response.
    """
    # 1. Log user request in history
    add_message("user", user_prompt)
    
    # 2. Consult LLM brain
    ai_response = query_brain(user_prompt)
    
    def run_single_tool(tool_name: str, arguments: dict) -> dict:
        # Execute tool directly in Python
        from app.executor import execute_tool
        status, result = execute_tool(tool_name, arguments)
        
        # Log tool execution to memory
        log_tool_call(tool_name, arguments, status, result)
        
        # Generate UI and spoken responses
        if status == "success":
            if isinstance(result, dict) and "exit_code" in result:
                if result["exit_code"] == 0:
                    ui_text = result["stdout"].strip() if result.get("stdout") else f"Successfully ran {tool_name}."
                    # Short speech response if the output is long
                    if len(ui_text) > 150:
                        tts_text = f"Command executed successfully."
                    else:
                        tts_text = ui_text
                else:
                    err_text = result['stderr'].strip() if result.get('stderr') else f"Command failed with exit code {result['exit_code']}."
                    ui_text = f"Command failed with error: {err_text}"
                    if len(err_text) > 150:
                        tts_text = "Command failed with an error."
                    else:
                        tts_text = ui_text
            else:
                ui_text = str(result)
                if len(ui_text) > 150:
                    tts_text = f"Successfully executed {tool_name}."
                else:
                    tts_text = ui_text
        else:
            ui_text = f"Failed to execute {tool_name}. {result}"
            tts_text = ui_text
            
        return {"ui": ui_text, "tts": tts_text}

    # 3. Handle response
    if "steps" in ai_response:
        ui_parts = []
        tts_parts = []
        for step in ai_response["steps"]:
            if "tool" in step:
                res = run_single_tool(step["tool"], step.get("arguments", {}))
                ui_parts.append(res["ui"])
                tts_parts.append(res["tts"])
            elif "reply" in step:
                ui_parts.append(step["reply"])
                tts_parts.append(step["reply"])
        ui_text = "\n\n".join(ui_parts)
        tts_text = " ".join(tts_parts)
        add_message("assistant", ui_text)
        speak(tts_text)
        return ui_text
        
    elif "tool" in ai_response:
        res = run_single_tool(ai_response["tool"], ai_response.get("arguments", {}))
        add_message("assistant", res["ui"])
        speak(res["tts"])
        return res["ui"]
        
    else:
        # Conversational reply
        spoken_text = ai_response.get("reply", "I'm not sure how to respond.")
        add_message("assistant", spoken_text)
        speak(spoken_text)
        return spoken_text

def execute_pipeline_with_audio(audio_filepath: str) -> str:
    """
    Executes the pipeline using a recorded audio file.
    """
    ai_response = query_brain_with_audio(audio_filepath)
    transcription = ai_response.get("transcription", "[Voice Command]")
    print("=== USER ===", transcription)
    add_message("user", transcription)
    
    def run_single_tool(tool_name: str, arguments: dict) -> dict:
        # Execute tool directly in Python
        from app.executor import execute_tool
        status, result = execute_tool(tool_name, arguments)
        log_tool_call(tool_name, arguments, status, result)
        
        # Generate UI and spoken responses
        if status == "success":
            if isinstance(result, dict) and "exit_code" in result:
                if result["exit_code"] == 0:
                    ui_text = result["stdout"].strip() if result.get("stdout") else f"Successfully ran {tool_name}."
                    # Short speech response if the output is long
                    if len(ui_text) > 150:
                        tts_text = f"Command executed successfully."
                    else:
                        tts_text = ui_text
                else:
                    err_text = result['stderr'].strip() if result.get('stderr') else f"Command failed with exit code {result['exit_code']}."
                    ui_text = f"Command failed with error: {err_text}"
                    if len(err_text) > 150:
                        tts_text = "Command failed with an error."
                    else:
                        tts_text = ui_text
            else:
                ui_text = str(result)
                if len(ui_text) > 150:
                    tts_text = f"Successfully executed {tool_name}."
                else:
                    tts_text = ui_text
        else:
            ui_text = f"Failed to execute {tool_name}. {result}"
            tts_text = ui_text
            
        return {"ui": ui_text, "tts": tts_text}

    if "steps" in ai_response:
        ui_parts = []
        tts_parts = []
        for step in ai_response["steps"]:
            if "tool" in step:
                res = run_single_tool(step["tool"], step.get("arguments", {}))
                ui_parts.append(res["ui"])
                tts_parts.append(res["tts"])
            elif "reply" in step:
                ui_parts.append(step["reply"])
                tts_parts.append(step["reply"])
        ui_text = "\n\n".join(ui_parts)
        tts_text = " ".join(tts_parts)
        add_message("assistant", ui_text)
        speak(tts_text)
        return ui_text
        
    elif "tool" in ai_response:
        res = run_single_tool(ai_response["tool"], ai_response.get("arguments", {}))
        add_message("assistant", res["ui"])
        speak(res["tts"])
        return res["ui"]
        
    else:
        spoken_text = ai_response.get("reply", "I'm not sure how to respond.")
        add_message("assistant", spoken_text)
        speak(spoken_text)
        return spoken_text

@app.get("/")
def read_root():
    return {"status": "online", "agent": "phone-brain"}

@app.get("/ui", response_class=HTMLResponse)
def serve_ui():
    """
    Serves the premium glassmorphism Assistant Web UI.
    """
    static_file_path = os.path.join(os.path.dirname(__file__), "static", "index.html")
    if os.path.exists(static_file_path):
        return FileResponse(static_file_path)
    raise HTTPException(status_code=404, detail="UI index.html not found.")

@app.post("/command")
def run_text_command(req: CommandRequest):
    """
    Sends a text command to the brain, executes any tool, speaks, and returns the result.
    """
    try:
        spoken_result = execute_pipeline(req.command)
        return {"status": "success", "response": spoken_result}
    except Exception as e:
        logger.exception("Error running command:")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/voice-command")
def trigger_voice_command(background_tasks: BackgroundTasks, duration: int = 5):
    """
    Triggers microphone recording, queries LLM with audio, executes tool, and speaks back.
    Runs asynchronously in the background.
    """
    def voice_pipeline_task():
        temp_audio = "input_recording.wav"
        recorded_path = record_audio(temp_audio, duration=duration)
        execute_pipeline_with_audio(recorded_path)
            
    background_tasks.add_task(voice_pipeline_task)
    return {"status": "success", "message": "Voice command pipeline triggered."}

@app.get("/history")
def get_history(limit: int = 20):
    return {"history": get_recent_history(limit)}

@app.post("/memory")
def write_memory(req: MemoryRequest):
    set_value(req.key, req.value)
    return {"status": "success", "message": f"Saved {req.key}."}

@app.get("/memory/{key}")
def read_memory(key: str):
    val = get_value(key)
    if val is None:
        raise HTTPException(status_code=404, detail="Key not found in memory.")
    return {"key": key, "value": val}
