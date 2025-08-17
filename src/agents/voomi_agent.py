import json
from venv import logger

from langchain_google_genai import ChatGoogleGenerativeAI
from langchain.agents import create_structured_chat_agent, AgentExecutor
from langchain.memory import ConversationBufferMemory

import config as config
from prompts.voomi_prompt import custom_agent_prompt
from tools import (get_project_units, save_lead)


def Voomi(project_id: str, agent_name: str, agent_gender: str, dialect: str, languages_skills: list[str] = None):
    # 1. Initialize LLM
    llm = ChatGoogleGenerativeAI(model="gemini-2.5-flash", temperature=0.7)

    # 2. Gather the tools (now with the upgraded get_project_units)
    tools = [
        get_project_units,
        save_lead,
    ]

    # 3. Use your custom prompt
    prompt = custom_agent_prompt(project_id=project_id, agent_name=agent_name, agent_gender=agent_gender,dialect=dialect, languages_skills=languages_skills)

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

    def get_agent_response(user_input: str, gender: str, **kwargs):
        """Runs the Agent and gets the final response."""

        original_dialect = kwargs.get('original_dialect', None)
        if original_dialect:
            proper_dialect = original_dialect
            logger.info(f"Using original WebSocket dialect: {proper_dialect}")

        # dialect_instruction = f"Style: {proper_dialect} dialect, {gender} voice persona (model's persona, not user), friendly and engaging tone, normal speed, use more vocabulary and expressions from {proper_dialect}. Text: {user_input}"
        dialect_instruction = "".join([
        f"Generate the response in the {proper_dialect} Arabic dialect with a {gender} persona, this is your persona, not user. ",
        f"Use only colloquial {proper_dialect} vocabulary and expressions, avoiding Modern Standard Arabic, for a natural tone. ",
        f"Keep the tone warm, friendly, and culturally sensitive, aligned with the {gender} persona. ",
        f"The input text is: {user_input}"
    ])
        response = agent_executor.invoke({"input": dialect_instruction})
        # logger.info(f"Agent key args: {response}")

        return json.loads(response["output"])

    return get_agent_response

