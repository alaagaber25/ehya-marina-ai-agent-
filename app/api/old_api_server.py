# api_server.py

import uvicorn
import time
import uuid
import json
import tiktoken
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from typing import List, Literal, Optional

# Import the global response function and session starter
from app.agents.agent_setup import get_agent_response, start_new_session

# --- Pydantic Models for OpenAI Compatibility ---

class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str

class OpenAIChatRequest(BaseModel):
    messages: List[ChatMessage]
    # user_id is no longer needed for a single-session model

class UsageStats(BaseModel):
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int

class ChatCompletionChoice(BaseModel):
    index: int = 0
    message: ChatMessage
    finish_reason: str = "stop"

class OpenAIChatResponse(BaseModel):
    id: str = Field(default_factory=lambda: f"chatcmpl-{uuid.uuid4().hex}")
    object: str = "chat.completion"
    created: int = Field(default_factory=lambda: int(time.time()))
    model: str = "voomy-agent-v1.0"
    choices: List[ChatCompletionChoice]
    usage: UsageStats

# --- Tokenizer Helper ---
def count_tokens(text: str, model: str = "gpt-4") -> int:
    try:
        encoding = tiktoken.encoding_for_model(model)
    except KeyError:
        encoding = tiktoken.get_encoding("cl100k_base")
    return len(encoding.encode(text))

# --- FastAPI App Initialization ---
app = FastAPI(title="VOOM AI Agent - Single Session API")

# --- API Endpoints ---

@app.post("/v1/session/start", tags=["Session Management"])
async def start_new_chat_session():
    """
    Clears the agent's memory to start a new conversation.
    Call this endpoint to reset the chat.
    """
    start_new_session()
    return {"status": "success", "message": "New session started."}

@app.post("/v1/chat/completions", response_model=OpenAIChatResponse, tags=["Chat Completions"])
async def chat_completions(request: OpenAIChatRequest):
    if not request.messages or request.messages[-1].role != "user":
        raise HTTPException(status_code=400, detail="No valid user message found.")
    
    user_input = request.messages[-1].content

    # Get the response from the single, global agent instance
    agent_raw_output = get_agent_response(user_input)

    # Parse response and calculate tokens
    try:
        agent_json_output = json.loads(agent_raw_output)
        final_text = agent_json_output.get("responseText", str(agent_raw_output))
    except (json.JSONDecodeError, TypeError):
        final_text = str(agent_raw_output)

    prompt_tokens = count_tokens(user_input)
    completion_tokens = count_tokens(final_text)
    usage = UsageStats(
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        total_tokens=prompt_tokens + completion_tokens
    )
    
    response_message = ChatMessage(role="assistant", content=final_text)
    choice = ChatCompletionChoice(message=response_message)
    
    return OpenAIChatResponse(choices=[choice], usage=usage)

# --- Server Startup ---
if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)