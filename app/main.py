# main.py
from app.agents.agent_setup import get_agent_response
from app.services.tts_utils import speak 

def start_chat():
    print("--------------------------------------------------")
    print("VOOM AI Agent is online. Start chatting.")
    print("Type 'exit' to end the conversation.")
    print("--------------------------------------------------")

    while True:
        try:
            user_input = input("You: ")
            if user_input.lower() in ['exit', 'quit']:
                goodbye_message = "Goodbye!"
                print(f"Agent: {goodbye_message}")
                # speak(goodbye_message)
                break

            # Get Agent response as text
            agent_response = get_agent_response(user_input)
            # Print the text response to the console
            print(f"Agent: {agent_response}")
            # NEW: Convert the text response to speech and play it
            speak(agent_response)

        except KeyboardInterrupt:
            goodbye_message = "Conversation stopped. Goodbye!"
            print(f"\nAgent: {goodbye_message}")
            break
        except Exception as e:
            error_message = f"An error occurred: {e}"
            print(error_message)
            break

if __name__ == "__main__":
    start_chat()

# Show me available 2.5 bedroom units in BLDG 2 of the flamant project.