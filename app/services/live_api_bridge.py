# In a new file, e.g., app/services/live_api_bridge.py

from app.agents.agent_setup import agent_executor
from app.api.agent_wrapper import AgentWrapper
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Wrap the existing agent_executor for compatibility
# This ensures we use the same processing logic as your FastAPI server
wrapped_agent = AgentWrapper(agent_executor)

def process_text_with_agent(transcribed_text: str) -> str:
    """
    Sends transcribed text to the LangChain agent and returns the textual response.

    This function serves as the bridge between the LiveAPI's transcription output
    and the agent's input. It uses the existing AgentWrapper to ensure
    consistent input/output processing.

    Args:
        transcribed_text: The final, transcribed text from the user's speech,
                          provided by the LiveAPI.

    Returns:
        The agent's final text response ('responseText') to be synthesized
        into audio by the LiveAPI.
    """
    if not transcribed_text:
        logger.warning("Received empty or null text. Skipping agent call.")
        return "Sorry, I didn't catch that. Could you please repeat yourself?"

    try:
        logger.info(f"Sending transcribed text to agent: '{transcribed_text}'")

        # The AgentWrapper expects a dictionary input.
        # The _process_input method in AgentWrapper handles this format.
        agent_input = {"input": transcribed_text}

        # Invoke the agent using the wrapper
        # The invoke method calls the agent_executor and then formats the output.
        agent_response_dict = wrapped_agent.invoke(agent_input)

        # The _process_output method extracts the 'output' key.
        final_text_response = agent_response_dict.get("output", "I am not sure how to respond to that.")
        
        logger.info(f"Received agent response: '{final_text_response}'")

        return final_text_response

    except Exception as e:
        logger.error(f"An error occurred while processing text with the agent: {e}", exc_info=True)
        return "I seem to be having some technical difficulties. Please try again in a moment."

# --- Example Usage (for testing purposes) ---
if __name__ == '__main__':
    # Simulating a transcribed text from LiveAPI
    sample_text_from_live_api = "Show me available 2.5 bedroom units in BLDG 2 of the flamant project."
    
    # Process the text through the bridge function
    response_for_tts = process_text_with_agent(sample_text_from_live_api)
    
    # This response would then be sent back to LiveAPI for audio synthesis
    print("---")
    print(f"Text to be sent to LiveAPI for audio synthesis: {response_for_tts}")
    print("---")