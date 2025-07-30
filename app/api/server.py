# server.py
from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.openapi.utils import get_openapi
from dotenv import load_dotenv
import uvicorn
import logging
from langchain_openai_api_bridge.fastapi import LangchainOpenaiApiBridgeFastAPI
from langchain_openai_api_bridge.assistant import (
    InMemoryThreadRepository, 
    InMemoryMessageRepository, 
    InMemoryRunRepository
)
from langchain_openai_api_bridge.core import BaseAgentFactory
from langchain_openai_api_bridge.core.create_agent_dto import CreateAgentDto
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain.agents import create_structured_chat_agent, AgentExecutor
from langchain.memory import ConversationBufferMemory
from langchain_core.messages import HumanMessage, AIMessage
from langchain_core.runnables import Runnable
import app.core.config as config
from app.core.prompts import custom_agent_prompt
from app.tools.tools import (
    get_project_units, 
    search_units_in_memory, 
    navigate_to_page, 
    click_element, 
    save_lead, 
    clear_unit_cache
)
from app.api.agent_wrapper import AgentWrapper

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Setup security scheme
security = HTTPBearer(auto_error=False)

# 1. Define AgentFactory class that inherits from BaseAgentFactory
class MyAgentFactory(BaseAgentFactory):
    def create_agent(self, dto: CreateAgentDto) -> Runnable:
        """Create a new agent based on the sent DTO"""
        try:
            # Correct model name if it's wrong
            model_name = dto.model
            if not model_name or model_name == "string" or model_name == "":
                model_name = "gemini-2.5-flash"
                logger.info(f"Model name corrected to: {model_name}")
            
            # Correct temperature if it's wrong
            temperature = dto.temperature
            if temperature is None or temperature < 0 or temperature > 2:
                temperature = 0.7
                logger.info(f"Temperature corrected to: {temperature}")
            
            logger.info(f"Creating agent with model: {model_name}, temperature: {temperature}")
            
            llm = ChatGoogleGenerativeAI(
                model=model_name,
                google_api_key=config.GOOGLE_API_KEY,
                temperature=temperature,
                streaming=True
            )

            tools = [get_project_units, search_units_in_memory, navigate_to_page, click_element, save_lead]
            prompt = custom_agent_prompt
            memory = ConversationBufferMemory(memory_key="chat_history", return_messages=True)

            agent = create_structured_chat_agent(llm, tools, prompt)
            agent_executor = AgentExecutor(
                agent=agent,
                tools=tools,
                verbose=True,
                memory=memory,
                handle_parsing_errors=True,
                return_intermediate_steps=False
            )
            
            # Wrap the AgentExecutor in wrapper for compatibility
            wrapped_agent = AgentWrapper(agent_executor)
            
            logger.info("Agent created successfully")
            return wrapped_agent
            
        except Exception as e:
            logger.error(f"Error creating agent: {str(e)}")
            raise HTTPException(status_code=500, detail=f"Failed to create agent: {str(e)}")

# 2. Create in-memory repository instances
thread_repository = InMemoryThreadRepository()
message_repository = InMemoryMessageRepository()
run_repository = InMemoryRunRepository()

# 3. Setup FastAPI application with enhanced documentation support
def custom_openapi():
    if app.openapi_schema:
        return app.openapi_schema
    
    openapi_schema = get_openapi(
        title="LangChain Agent OpenAI API Bridge",
        version="1.0.0",
        description="""
        ## OpenAI-compatible API for LangChain Agent
        
        This API is OpenAI-compatible and supports:
        - Chat Completion API
        - Streaming responses
        - Assistant API
        - Custom real estate tools
        
        ### Authentication
        Use Bearer token with Google API Key:
        ```
        Authorization: Bearer YOUR_GOOGLE_API_KEY
        ```
        
        ### Model Names
        Use one of the following models:
        - `gemini-2.5-flash` (default - fastest)
        - `gemini-1.5-pro` (more accurate)
        - `gemini-1.5-flash`
        
        ### Endpoints
        - **Chat Completion**: `/chat/openai/v1/chat/completions`
        - **Assistant API**: `/assistant/openai/v1/threads`
        - **Health Check**: `/health`
        - **Test Chat**: `/test_chat` (for quick testing)
        - **New Session**: `/start_new_session`
        """,
        routes=app.routes,
    )
    
    # Add security scheme
    openapi_schema["components"]["securitySchemes"] = {
        "BearerAuth": {
            "type": "http",
            "scheme": "bearer",
            "bearerFormat": "API Key",
            "description": "Enter your Google API Key"
        }
    }
    
    # Update schema for chat completions to fix default values
    chat_completion_path = "/chat/openai/v1/chat/completions"
    if chat_completion_path in openapi_schema["paths"] and "post" in openapi_schema["paths"][chat_completion_path]:
        request_body = openapi_schema["paths"][chat_completion_path]["post"]["requestBody"]["content"]["application/json"]["schema"]
        
        # Update default values
        if "properties" in request_body:
            if "model" in request_body["properties"]:
                request_body["properties"]["model"].update({
                    "default": "gemini-2.5-flash",
                    "example": "gemini-2.5-flash",
                    "enum": ["gemini-2.5-flash", "gemini-1.5-pro", "gemini-1.5-flash"]
                })
            if "temperature" in request_body["properties"]:
                request_body["properties"]["temperature"].update({
                    "default": 0.7,
                    "minimum": 0.0,
                    "maximum": 2.0
                })
            if "max_tokens" in request_body["properties"]:
                request_body["properties"]["max_tokens"].update({
                    "default": 1000,
                    "minimum": 1,
                    "maximum": 4000
                })
    
    # Apply security to required endpoints
    for path in openapi_schema["paths"]:
        for method in openapi_schema["paths"][path]:
            if path not in ["/health", "/docs", "/openapi.json"] and method.lower() in ["post", "put", "delete"]:
                openapi_schema["paths"][path][method]["security"] = [{"BearerAuth": []}]
    
    app.openapi_schema = openapi_schema
    return app.openapi_schema

app = FastAPI(
    title="LangChain Agent OpenAI API Bridge",
    version="1.0",
    description="OpenAI-compatible API for LangChain Agent",
    docs_url="/docs",
    redoc_url="/redoc"
)

app.openapi = custom_openapi

# Add CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Modify this according to your security needs
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 4. Setup the bridge
bridge = LangchainOpenaiApiBridgeFastAPI(
    app=app,
    agent_factory_provider=MyAgentFactory()
)

# 5. Bind Assistant API interface
bridge.bind_openai_assistant_api(
    thread_repository_provider=lambda: thread_repository,
    message_repository_provider=lambda: message_repository,
    run_repository_provider=lambda: run_repository,
    prefix="/assistant"
)

# 6. Bind Chat Completion API interface
bridge.bind_openai_chat_completion(prefix="/chat")

# 7. Endpoint for session cleanup (without authentication)
@app.post("/start_new_session", tags=["Utilities"])
async def start_new_session_endpoint():
    """Clear session and start a new session"""
    try:
        logger.info("Starting new session...")
        
        # Clear tools cache
        clear_unit_cache()
        
        # Clear repositories - create new instances
        global thread_repository, message_repository, run_repository
        thread_repository.threads.clear()
        message_repository.messages.clear()
        run_repository.runs.clear()
        
        logger.info("Session cleared successfully")
        return {"message": "New session started. Cache and memory cleared.", "status": "success"}
    except Exception as e:
        logger.error(f"Error starting new session: {str(e)}")
        return {"message": f"Error starting new session: {str(e)}", "status": "error"}

# 8. Endpoint for server health check (without authentication)
@app.get("/health", tags=["Utilities"])
async def health_check():
    """Check server health"""
    try:
        # Quick test to create agent
        factory = MyAgentFactory()
        test_dto = CreateAgentDto(model="gemini-2.5-flash", temperature=0.7)
        agent = factory.create_agent(test_dto)
        
        return {
            "status": "healthy",
            "message": "LangChain OpenAI API Bridge is running",
            "agent_status": "ready",
            "endpoints": {
                "chat_completion": "/chat/openai/v1/chat/completions",
                "assistant_threads": "/assistant/openai/v1/threads",
                "health": "/health",
                "new_session": "/start_new_session"
            }
        }
    except Exception as e:
        logger.error(f"Health check failed: {str(e)}")
        return {
            "status": "unhealthy",
            "message": f"Error: {str(e)}",
            "agent_status": "error"
        }

# 9. Test endpoint for testing from Swagger UI
@app.post("/test_chat", tags=["Testing"], summary="Test Chat (for Swagger UI)")
async def test_chat_endpoint(
    message: str = "Hello, how are you?",
    model: str = "gemini-2.5-flash",
    temperature: float = 0.7,
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """
    Endpoint for testing from Swagger UI
    
    - **message**: The message you want to send to the agent
    - **model**: Model name (gemini-2.5-flash, gemini-1.5-pro, gemini-1.5-flash)
    - **temperature**: Temperature (0.0 - 2.0)
    - Requires Bearer token (Google API Key)
    """
    if not credentials:
        raise HTTPException(status_code=401, detail="Missing authorization header")
    
    api_key = credentials.credentials
    
    # Correct model name if it's wrong
    if not model or model == "string" or model == "":
        model = "gemini-2.5-flash"
    
    # Correct temperature
    if temperature is None or temperature < 0 or temperature > 2:
        temperature = 0.7
    
    try:
        # Create agent
        factory = MyAgentFactory()
        dto = CreateAgentDto(model=model, temperature=temperature, api_key=api_key)
        agent = factory.create_agent(dto)
        
        # Execute conversation
        result = agent.invoke({"input": message})
        
        return {
            "message": message,
            "model_used": model,
            "temperature_used": temperature,
            "response": result.get("output", "No response"),
            "status": "success"
        }
        
    except Exception as e:
        logger.error(f"Error in test chat: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Chat error: {str(e)}")

# 10. Global error handler
@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    logger.error(f"Global exception: {str(exc)}")
    return {
        "error": {
            "message": str(exc),
            "type": "internal_server_error"
        }
    }

# 11. Add middleware for logging
@app.middleware("http")
async def log_requests(request, call_next):
    logger.info(f"Request: {request.method} {request.url}")
    response = await call_next(request)
    logger.info(f"Response status: {response.status_code}")
    return response

# 12. Run the application
if __name__ == "__main__":
    load_dotenv()
    
    # Check for environment variables
    if not config.GOOGLE_API_KEY:
        logger.error("GOOGLE_API_KEY is not set in environment variables")
        exit(1)
    
    logger.info("🚀 Starting LangChain OpenAI API Bridge Server...")
    logger.info("📡 Chat Completion API: http://localhost:8000/chat/openai/v1/chat/completions")
    logger.info("🧵 Assistant API: http://localhost:8000/assistant/openai/v1/threads")
    logger.info("📋 Swagger UI: http://localhost:8000/docs")
    logger.info("📖 ReDoc: http://localhost:8000/redoc")
    logger.info("❤️ Health Check: http://localhost:8000/health")
    logger.info("🔄 New Session: http://localhost:8000/start_new_session")
    logger.info("🧪 Test Chat: http://localhost:8000/test_chat")
    
    uvicorn.run(
        app, 
        host="localhost", 
        port=8000,
        log_level="info",
        reload=False  # Disable reload to avoid issues
    )