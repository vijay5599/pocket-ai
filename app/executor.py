import logging
from typing import Dict, Any, Tuple
from app.tools import TOOLS_MAP

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def execute_tool(tool_name: str, arguments: Dict[str, Any]) -> Tuple[str, Any]:
    """
    Executes a tool by name with the given arguments.
    Returns:
        (status, result) where status is 'success' or 'error', and result is the output/message or error description.
    """
    logger.info(f"Requested tool: {tool_name} with arguments: {arguments}")
    
    if tool_name not in TOOLS_MAP:
        logger.error(f"Tool '{tool_name}' not found.")
        return "error", f"Tool '{tool_name}' is not supported by the Mac Agent."
    
    tool_func = TOOLS_MAP[tool_name]
    try:
        # Check if arguments are needed, or handle general case:
        # If the function takes parameters, pass them as keyword arguments
        # If the arguments is empty, call it without parameters
        import inspect
        sig = inspect.signature(tool_func)
        has_var_keyword = any(p.kind == inspect.Parameter.VAR_KEYWORD for p in sig.parameters.values())
        
        if arguments and sig.parameters:
            if has_var_keyword:
                filtered_args = arguments
            else:
                filtered_args = {k: v for k, v in arguments.items() if k in sig.parameters}
            result = tool_func(**filtered_args)
        else:
            result = tool_func()
            
        logger.info(f"Successfully executed tool '{tool_name}'. Result: {result}")
        return "success", result
    except Exception as e:
        logger.exception(f"Error executing tool '{tool_name}': {e}")
        return "error", str(e)
