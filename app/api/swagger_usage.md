
# Swagger UI Guide for the API

## 🚀 Quick Start

### 1. Run the Server

```bash
python server.py
```

### 2. Open Swagger UI

Go to: [http://localhost:8000/docs](http://localhost:8000/docs)

### 3. Enable Authorization

1. Click the **"Authorize"** button at the top right of the page
2. Enter your **Google API Key** in the "Value" field
3. Click **"Authorize"**
4. Then click **"Close"**

---

## 📋 Available Endpoints

### 🧪 Test Chat (Easiest to Start With)

* **Endpoint**: `POST /test_chat`
* **Purpose**: Quickly test the agent
* **Parameters**:

  * `message`: The input message (default: "Hello, how are you?")
  * `model`: The model name (default: "gemini-2.5-flash")
  * `temperature`: Response randomness (default: 0.7)

**Usage Example:**

1. Find "Test Chat"
2. Click "Try it out"
3. Enter your message
4. Click "Execute"

---

### 💬 Chat Completions (OpenAI Compatible)

* **Endpoint**: `POST /chat/openai/v1/chat/completions`
* **Purpose**: OpenAI-compatible API

**Example JSON:**

```json
{
  "model": "gemini-2.5-flash",
  "messages": [
    {
      "role": "user",
      "content": "Hi, try the get_project_units tool"
    }
  ],
  "temperature": 0.7,
  "max_tokens": 1000,
  "stream": false
}
```

---

### 🏥 Health Check

* **Endpoint**: `GET /health`
* **Purpose**: Check server status
* **No authorization required**

---

### 🔄 New Session

* **Endpoint**: `POST /start_new_session`
* **Purpose**: Reset memory and cache
* **No authorization required**

---

## 🤖 Supported Models

| Model              | Description       | Preferred Use         |
| ------------------ | ----------------- | --------------------- |
| `gemini-2.5-flash` | Fastest (default) | General conversations |
| `gemini-1.5-pro`   | Most accurate     | Complex tasks         |
| `gemini-1.5-flash` | Balanced          | General use           |

---

## ⚙️ Temperature Settings

| Value   | Effect                          |
| ------- | ------------------------------- |
| 0.0–0.3 | Focused and deterministic       |
| 0.4–0.7 | Balanced (default: 0.7)         |
| 0.8–1.0 | Creative and diverse            |
| 1.1–2.0 | Highly random and unpredictable |

---

## 🛠️ Supported Tools

* `get_project_units`: Fetch project units
* `search_units_in_memory`: Search saved units
* `navigate_to_page`: Navigate between pages
* `click_element`: Click on page elements
* `save_lead`: Save potential customer info

---

## 🔧 Troubleshooting

### Error 401 - Unauthorized

* **Cause**: API Key not provided
* **Fix**: Click "Authorize" and enter your Google API Key

### Error 404 - Model not found

* **Cause**: Incorrect model name
* **Fix**: Use one of the supported models

### Error 500 - Internal Server Error

* **Cause**: Server or API Key issue
* **Fix**: Check server logs and API Key validity

---

## 📱 Example Messages

### General Messages:

* "Hello, how are you?"
* "Tell me about yourself"
* "What can you do?"

### Tool-related Messages:

* "Use the get\_project\_units tool"
* "Find units with 100 sqm area"
* "Save client info for Ahmad"

### Real Estate Messages:

* "I want an apartment with 120 sqm"
* "What are the available unit prices?"
* "Tell me about the Flamant project"

---

## 🔗 Useful Links

* **Swagger UI**: [http://localhost:8000/docs](http://localhost:8000/docs)
* **ReDoc**: [http://localhost:8000/redoc](http://localhost:8000/redoc)
* **Health Check**: [http://localhost:8000/health](http://localhost:8000/health)
* **Test Chat**: [http://localhost:8000/test\_chat](http://localhost:8000/test_chat)

