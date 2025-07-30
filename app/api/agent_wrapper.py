# agent_wrapper.py
from langchain_core.runnables import Runnable
from langchain_core.messages import BaseMessage, HumanMessage, AIMessage
from typing import Any, Dict, List, Union, AsyncIterator
import asyncio
import logging

logger = logging.getLogger(__name__)

class AgentWrapper(Runnable):
    """
    Wrapper to make AgentExecutor compatible with langchain-openai-api-bridge
    """
    
    def __init__(self, agent_executor):
        self.agent_executor = agent_executor
        
    def invoke(self, input: Union[Dict, List[BaseMessage]], **kwargs) -> Dict[str, Any]:
        """Synchronous execution of the agent"""
        try:
            # Convert input to required format
            processed_input = self._process_input(input)
            logger.info(f"Processing input: {processed_input}")
            
            # Execute the agent
            result = self.agent_executor.invoke(processed_input, **kwargs)
            
            # Convert the result
            return self._process_output(result)
            
        except Exception as e:
            logger.error(f"Error in agent invoke: {str(e)}")
            return {
                "output": f"Sorry, an error occurred: {str(e)}",
                "messages": [AIMessage(content=f"Sorry, an error occurred: {str(e)}")]
            }
    
    async def ainvoke(self, input: Union[Dict, List[BaseMessage]], **kwargs) -> Dict[str, Any]:
        """Asynchronous execution of the agent"""
        try:
            # Run in separate thread
            return await asyncio.to_thread(self.invoke, input, **kwargs)
        except Exception as e:
            logger.error(f"Error in agent ainvoke: {str(e)}")
            return {
                "output": f"Sorry, an error occurred: {str(e)}",
                "messages": [AIMessage(content=f"Sorry, an error occurred: {str(e)}")]
            }
    
    async def astream(self, input: Union[Dict, List[BaseMessage]], **kwargs) -> AsyncIterator[Dict[str, Any]]:
        """Simulate streaming by splitting the result"""
        try:
            # Get complete result
            result = await self.ainvoke(input, **kwargs)
            output = result.get("output", "")
            
            # Split result into chunks
            chunk_size = 50  # Size of each chunk
            for i in range(0, len(output), chunk_size):
                chunk = output[i:i + chunk_size]
                yield {
                    "event": "on_chat_model_stream",
                    "data": {
                        "chunk": AIMessage(content=chunk)
                    }
                }
                await asyncio.sleep(0.05)  # Small delay to simulate streaming
                
        except Exception as e:
            logger.error(f"Error in agent astream: {str(e)}")
            yield {
                "event": "on_chat_model_stream", 
                "data": {
                    "chunk": AIMessage(content=f"Sorry, an error occurred: {str(e)}")
                }
            }
    
    async def astream_events(self, input: Union[Dict, List[BaseMessage]], version: str = "v2", **kwargs) -> AsyncIterator[Dict[str, Any]]:
        """Simulate stream events"""
        try:
            # Get complete result
            result = await self.ainvoke(input, **kwargs)
            output = result.get("output", "")
            
            # Send stream start
            yield {
                "event": "on_chat_model_start",
                "run_id": "run_001", 
                "data": {"input": input}
            }
            
            # Split result into chunks
            chunk_size = 30
            for i in range(0, len(output), chunk_size):
                chunk = output[i:i + chunk_size]
                yield {
                    "event": "on_chat_model_stream",
                    "run_id": "run_001",
                    "data": {
                        "chunk": AIMessage(content=chunk)
                    }
                }
                await asyncio.sleep(0.1)
            
            # Send stream end
            yield {
                "event": "on_chat_model_end",
                "run_id": "run_001",
                "data": {
                    "output": AIMessage(content=output)
                }
            }
            
        except Exception as e:
            logger.error(f"Error in astream_events: {str(e)}")
            yield {
                "event": "on_chat_model_stream",
                "run_id": "run_001", 
                "data": {
                    "chunk": AIMessage(content=f"Sorry, an error occurred: {str(e)}")
                }
            }
    
    def _process_input(self, input: Union[Dict, List[BaseMessage]]) -> Dict[str, Any]:
        """Process input to convert it to the required format for the agent"""
        if isinstance(input, dict):
            if "messages" in input:
                # Convert from messages format to input
                messages = input["messages"]
                if messages and len(messages) > 0:
                    last_message = messages[-1]
                    if isinstance(last_message, dict):
                        return {"input": last_message.get("content", "")}
                    elif isinstance(last_message, BaseMessage):
                        return {"input": last_message.content}
                return {"input": ""}
            elif "input" in input:
                return input
            else:
                # Assume the input is text directly
                return {"input": str(input)}
        
        elif isinstance(input, list):
            # List of messages
            if input and len(input) > 0:
                last_message = input[-1]
                if isinstance(last_message, dict):
                    return {"input": last_message.get("content", "")}
                elif isinstance(last_message, BaseMessage):
                    return {"input": last_message.content}
            return {"input": ""}
        
        elif isinstance(input, str):
            return {"input": input}
        
        else:
            return {"input": str(input)}
    
    def _process_output(self, result: Any) -> Dict[str, Any]:
        """Process output to convert it to the required format"""
        if isinstance(result, dict):
            if "output" in result:
                output = result["output"]
                return {
                    "output": output,
                    "messages": [AIMessage(content=str(output))]
                }
            elif "result" in result:
                output = result["result"]
                return {
                    "output": output,
                    "messages": [AIMessage(content=str(output))]
                }
            else:
                # Try to extract result from different keys
                for key in ["answer", "response", "text"]:
                    if key in result:
                        output = result[key]
                        return {
                            "output": output,
                            "messages": [AIMessage(content=str(output))]
                        }
                
                # If we didn't find a suitable key, take the result as is
                output = str(result)
                return {
                    "output": output,
                    "messages": [AIMessage(content=output)]
                }
        
        else:
            # If the result is not a dict
            output = str(result)
            return {
                "output": output,
                "messages": [AIMessage(content=output)]
            }