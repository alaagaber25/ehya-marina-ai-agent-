# AI Coding Instructions for Voomi Real Estate Agent

## Project Overview
This is a real-time voice AI assistant for Flamant real estate built with FastAPI and Google's Live API. The system handles Arabic dialects (Saudi/Egyptian) and English, providing voice-based property searches and lead generation through WebSocket connections.

## Core Architecture & Data Flow

### WebSocket Threading Pattern
The system uses a **dual-threading WebSocket architecture** in `src/main.py`:
- `receive_thread()` processes incoming audio/text from clients
- `send_thread()` streams AI responses back to clients
- Both threads coordinate through `asyncio.Queue` for message passing

### Critical Message Flow
```python
# Always follow this pattern for streaming responses
await send_json_streaming(type_, data, content_type)
# Then save complete messages via MessageAccumulator
await message_accumulator.save_accumulated_message(db, chat.id)
```

### Agent Layering
1. **Live Agent** (`agents/live_agent.py`): Wraps Google Live API with custom `MessageType` enum and VAD configuration
2. **Voomi Agent** (`agents/voomi_agent.py`): LangChain-based structured chat agent for property queries
3. **Tool Layer** (`tools/__init__.py`): Real estate search tools with strict caching patterns

## Development Conventions

### Environment Setup
- **Virtual Environment**: Pre-configured in `agent_venv/` - activate with `& agent_venv\Scripts\Activate.ps1`
- **Required .env Variables**: `DATABASE_URL`, `GOOGLE_API_KEY`, `GOOGLE_LiveAPI_KEY`, `LIVEAPI_MODEL`
- **Configuration Pattern**: All config validation in `src/config.py` with descriptive error messages

### Database Patterns
- **Chat Sessions**: Each WebSocket creates a new `Chat` in `db/service.py`
- **Message Storage**: Uses `MessageDirection` (incoming/outgoing) and `MessageType` from `live_agent.py`
- **Async Operations**: All DB operations use SQLModel with AsyncSession and retry logic

### Tool Development Rules
```python
# CRITICAL: Only use last_search_results cache - global caches cause corruption
last_search_results: List[Dict[str, Any]] = []

@tool
def your_tool(...):
    """Tool docstrings are used by LangChain for agent decision-making"""
    global last_search_results  # Only allowed global cache
```

### Audio Processing Pipeline
- **Codec**: `utils/audio_codec.py` converts PCM to WAV for browser compatibility
- **Base64 Transport**: All audio sent as base64 strings in WebSocket messages
- **Stream Termination**: Use `audio_stream_end: true` signal to properly end audio input

## Key File Responsibilities

- **`main.py`**: WebSocket endpoint, threading coordination, dialect mapping
- **`agents/live_agent.py`**: Google Live API wrapper with custom message types
- **`agents/voomi_agent.py`**: LangChain agent with tools integration
- **`utils/message_accumulator.py`**: Buffers streaming responses before DB persistence
- **`prompts/live_prompt.py`**: Unified system prompt template for all dialects
- **`tools/property_search.py`**: Real estate API integration with caching strategy

## Critical Patterns & Gotchas

### Streaming Response Handling
- **Never save partial responses** directly to DB - always use MessageAccumulator
- **Tool-only responses**: Live API system prompt enforces tool-only responses to prevent duplication
- **Voice configuration**: First WebSocket message contains dialect/persona for voice selection

### Error Handling
```python
# WebSocket disconnection pattern
try:
    # WebSocket operations
except WebSocketDisconnect:
    logger.info("WebSocket disconnected")
# Database retry pattern  
for attempt in range(max_retries):
    try:
        # DB operation
        break
    except Exception as e:
        if attempt == max_retries - 1:
            raise
```

### Language & Dialect Handling
- **Dialect Mapping**: `"EGYPTIAN" → "ar-EG"` in main.py
- **Voice Selection**: `"Zephyr" if PERSONA == "female" else "Orus"`
- **Unified Prompts**: Single template in `live_prompt.py` handles all dialects

### Tool Cache Management
- **Only use `last_search_results`** - global unit caches removed due to data corruption
- **Initial vs. Refinement**: `get_project_units` for first search, `search_units_in_memory` for filtering
- **Cache Clearing**: Call `clear_unit_cache()` for new sessions

## Testing & Debugging

### Voice Feature Testing
- Send voice config as first WebSocket message: `{"dialect": "EGYPTIAN", "persona": "female"}`
- Test different language codes: `ar-EG`, `ar-SA`, `en-US`
- Check WebSocket state with `ws.client_state` before operations

### Development Workflow
```bash
# Environment activation
& agent_venv\Scripts\Activate.ps1
pip install -e .

# Run with live reload
uvicorn src.main:app --reload --host 0.0.0.0 --port 8000
```