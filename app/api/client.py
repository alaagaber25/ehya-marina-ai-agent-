# client.py

import requests
import json
import time
import os
from dotenv import load_dotenv

load_dotenv()

# Test configuration
BASE_URL = "http://localhost:8000"
API_KEY = os.getenv("GOOGLE_API_KEY", "dummy")

def test_server_connection():
    """Test server connection"""
    print("🔗 Testing server connection...")
    try:
        response = requests.get(f"{BASE_URL}/health", timeout=5)
        if response.status_code == 200:
            print("✅ Server is running")
            data = response.json()
            print(f"   Status: {data.get('status')}")
            print(f"   Agent Status: {data.get('agent_status')}")
            return True
        else:
            print(f"❌ Server returned status: {response.status_code}")
            return False
    except requests.exceptions.ConnectionError:
        print("❌ Cannot connect to server. Is it running?")
        return False
    except Exception as e:
        print(f"❌ Connection error: {e}")
        return False

def test_chat_api():
    """Test Chat Completion API"""
    print("\n💬 Testing Chat API...")
    
    url = f"{BASE_URL}/chat/openai/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json"
    }
    
    data = {
        "model": "gemini-2.5-flash",
        "messages": [
            {"role": "user", "content": "مرحبا! قل لي شيئاً جميلاً"}
        ],
        "temperature": 0.7,
        "max_tokens": 150,
        "stream": False
    }
    
    try:
        response = requests.post(url, headers=headers, json=data, timeout=30)
        print(f"   Response status: {response.status_code}")
        
        if response.status_code == 200:
            result = response.json()
            message = result["choices"][0]["message"]["content"]
            print("✅ Chat API working!")
            print(f"   Response: {message[:100]}...")
            return True
        else:
            print(f"❌ Chat API error: {response.status_code}")
            print(f"   Response: {response.text}")
            return False
            
    except Exception as e:
        print(f"❌ Chat API exception: {e}")
        return False

def test_streaming_api():
    """Test Streaming API"""
    print("\n🌊 Testing Streaming API...")
    
    url = f"{BASE_URL}/chat/openai/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json"
    }
    
    data = {
        "model": "gemini-2.5-flash", 
        "messages": [
            {"role": "user", "content": "عد من 1 إلى 5"}
        ],
        "temperature": 0.7,
        "max_tokens": 100,
        "stream": True
    }
    
    try:
        response = requests.post(url, headers=headers, json=data, stream=True, timeout=30)
        print(f"   Response status: {response.status_code}")
        
        if response.status_code == 200:
            print("✅ Streaming API working!")
            print("   Stream content: ", end="")
            
            chunk_count = 0
            for line in response.iter_lines():
                if line:
                    line = line.decode('utf-8')
                    if line.startswith('data: '):
                        data_part = line[6:]  # Remove 'data: '
                        if data_part == '[DONE]':
                            break
                        try:
                            chunk_data = json.loads(data_part)
                            if 'choices' in chunk_data and len(chunk_data['choices']) > 0:
                                delta = chunk_data['choices'][0].get('delta', {})
                                content = delta.get('content', '')
                                if content:
                                    print(content, end='', flush=True)
                                    chunk_count += 1
                        except json.JSONDecodeError:
                            pass
                        
                        # Maximum limit for chunks
                        if chunk_count > 20:
                            break
            
            print(f"\n   Received {chunk_count} chunks")
            return True
        else:
            print(f"❌ Streaming API error: {response.status_code}")
            print(f"   Response: {response.text}")
            return False
            
    except Exception as e:
        print(f"❌ Streaming API exception: {e}")
        return False

def main():
    """Run all tests"""
    print("🚀 Simple API Test\n")
    
    # Test connection
    if not test_server_connection():
        print("\n⚠️  Server is not accessible. Please:")
        print("   1. Make sure server.py is running")
        print("   2. Check that port 8000 is available")
        print("   3. Verify GOOGLE_API_KEY is set")
        return
    
    print("\n" + "="*50)
    
    # Test Chat API
    chat_success = test_chat_api()
    
    print("\n" + "="*50)
    
    # Test Streaming API
    streaming_success = test_streaming_api()
    
    print("\n" + "="*50)
    
    # Final results
    print(f"\n📊 Test Results:")
    print(f"   Chat API: {'✅' if chat_success else '❌'}")
    print(f"   Streaming API: {'✅' if streaming_success else '❌'}")
    
    if chat_success and streaming_success:
        print("\n🎉 All tests passed! API is working correctly.")
    else:
        print("\n⚠️  Some tests failed. Check the logs above.")

if __name__ == "__main__":
    main()