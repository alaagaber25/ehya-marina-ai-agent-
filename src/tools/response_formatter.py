from typing import Optional, Dict, Any
from langchain.tools import tool

def finalize_response(action: str, responseText: str, action_data: Optional[Dict[str, Any]] = None, **kwargs) -> Dict[str, Any]:
    """
    Use this tool for EVERY final response to the user.
    It formats the output consistently for the frontend application.
    Never respond directly with text. Always use this tool to wrap your final answer.

    Parameters:
    - action (str): The type of action for the frontend ('answer', 'navigate-url', 'navigate-tour', 'end').
    - responseText (str): The natural language text to be spoken to the user.
    - action_data (dict, optional): Any additional data needed for the action, like a URL or tour location.
    """
    # The tool's job is to structure the data.
    # The live_agent will then send this structured data.
    return {
        "action": action,
        "action_data": action_data,
        "responseText": responseText
    }