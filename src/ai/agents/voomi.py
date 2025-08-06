import json
from venv import logger

from langchain_google_genai import ChatGoogleGenerativeAI
from langchain.agents import create_structured_chat_agent, AgentExecutor
from langchain.memory import ConversationBufferMemory

import config as config
from ai.prompts.v_agent import custom_agent_prompt
from ai.tools import (
    get_project_units,
    search_units_in_memory,
    # navigate_to_page,
    # click_element,
    save_lead,
    # clear_unit_cache, # this is bad!
)


def Voomi(dialect: str):
    # 1. Initialize LLM
    llm = ChatGoogleGenerativeAI(model="gemini-2.5-flash", temperature=0.7)

    # 2. Gather the tools (now with the upgraded get_project_units)
    tools = [
        get_project_units,
        search_units_in_memory,
        # navigate_to_page,
        # click_element,
        save_lead,
    ]

    # 3. Use your custom prompt
    prompt = custom_agent_prompt

    # 4. Create memory
    memory = ConversationBufferMemory(memory_key="chat_history", return_messages=True)

    # 5. Create the Agent
    agent = create_structured_chat_agent(llm, tools, prompt)  # type: # type: ignore

    # 6. Create the Agent Executor
    agent_executor = AgentExecutor(
        agent=agent,
        tools=tools,
        verbose=True,
        memory=memory,
        handle_parsing_errors=True,
        max_iterations=5,
    )

    def get_agent_response(user_input: str, dialect: str, **kwargs): 
        """Runs the Agent and gets the final response."""

        original_dialect = kwargs.get('original_dialect', None)
        if original_dialect:
            proper_dialect = original_dialect
            logger.info(f"Using original WebSocket dialect: {proper_dialect}")
        dialect_instruction = f"IMPORTANT: You must respond in {proper_dialect} dialect. User's message: {user_input}"
        response = agent_executor.invoke({"input": dialect_instruction})
        logger.info(f"Agent key args: {response}")

        return json.loads(response["output"])

    return get_agent_response


# def start_new_session():
#     """Clears memory and tool caches for a new user session."""
#     clear_unit_cache()
#     memory.clear()
#     print("--- New session started. Cache and memory cleared. ---")
