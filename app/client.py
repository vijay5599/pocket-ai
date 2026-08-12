import logging
import requests
from app.config import MAC_AGENT_URL, MAC_AGENT_AUTH_TOKEN

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def send_command(tool_name: str, arguments: dict = None) -> dict:
    """
    Sends a tool execution command to the Mac Agent.
    """
    if arguments is None:
        arguments = {}
        
    url = f"{MAC_AGENT_URL}/execute"
    payload = {
        "tool": tool_name,
        "arguments": arguments
    }
    
    headers = {
        "Content-Type": "application/json"
    }
    if MAC_AGENT_AUTH_TOKEN:
        headers["Authorization"] = f"Bearer {MAC_AGENT_AUTH_TOKEN}"
        
    logger.info(f"Sending command to Mac Agent: {payload} at {url}")
    
    try:
        response = requests.post(url, json=payload, headers=headers, timeout=30)
        if response.status_code == 200:
            logger.info("Mac Agent executed successfully.")
            return response.json()
        else:
            logger.error(f"Mac Agent returned error status {response.status_code}: {response.text}")
            try:
                return response.json().get("detail", {"status": "error", "message": response.text})
            except Exception:
                return {"status": "error", "message": f"Server error: {response.text}"}
    except requests.exceptions.RequestException as e:
        logger.error(f"Failed to connect to Mac Agent at {url}: {e}")
        return {"status": "error", "message": f"Connection failed: {e}"}
