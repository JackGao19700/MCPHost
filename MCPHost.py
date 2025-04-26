import inspect
import os
import dotenv

import re
import requests
import json

import asyncio
from contextlib import AsyncExitStack
from typing import Optional

from dotenv import load_dotenv
from mcp import ClientSession,StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.client.sse import sse_client
from mcp.types import CallToolResult

from MCPClientSessionManager import MCPClientSessionManager
from helperFun import myLogger,toolDescriptionForLLM,serialize_MCPCallToResult
from llmModel import llmModelWrapper,OpenAIModel,localOllamaModel

def restfulAPICall(funcName,funcArgsJson):
    # 调用你的本地 Flask 服务
    flask_response = requests.post(
        "http://localhost:5000/add",
        json=funcArgsJson
    )
    json=flask_response.json() #["result"]
    result = flask_response.json()["result"]
    myLogger(f"<Fun:{inspect.currentframe().f_code.co_name}->> Restful API call result: {result}")

    return str(result)

class MCPHost:
    def __init__(self, llmModel,systemPrompt):
        self.mcpClientSessionManager = MCPClientSessionManager()
        self.llmModel=llmModel
        self.systemPrompt=systemPrompt

    async def connect_to_stdio_server(self,serverParameters:StdioServerParameters):
        await self.mcpClientSessionManager.connect_to_stdio_server(serverParameters)
    async def connect_to_sse_server(self, server_url: str):
        await self.mcpClientSessionManager.connect_to_sse_server(server_url)

    async def cleanup(self):
        await self.mcpClientSessionManager.cleanup()

    async def chatLoop(self):
        """Run an interactive chat loop"""
        print("\nMCP Host Started!")
        print("Type your queries or 'quit' to exit.")
        while True:
            try:
                user_query = input("\nQuery:").strip()
                if user_query.lower() == "quit":
                    break
                response=await self.process_query(user_query)
                print("\n" + response)
            except Exception as e:
                 print(f"Error: {e}")

    async def process_query(self, query: str) -> str:
        """Process a query using LLMModel and available tools"""
        messages = []
        systemMessage={
                    "role": "system",
                    "content": self.systemPrompt
                    }
        messages.append(systemMessage)
        userMessage = {
                    "role": "user",
                    "content": query
                }
        messages.append(userMessage)
        choice = self.llmModel.Chat(messages, self.mcpClientSessionManager.get_mcp_tools())
        self.llmModel.addMessageFromChoice(messages,choice)

        toolsToCall=self.llmModel.ParseToolCallMessage(choice)
        for funName, funcArgs, tool_call_id in toolsToCall:
            from mcp.types import TextContent
            from typing import Optional
            toolCallResult: Optional[TextContent] = None
            toolCallResult=await self.mcpClientSessionManager.execute_tool(funName, funcArgs)

            content=toolCallResult.content
            isError=toolCallResult.isError

            # result=restfulAPICall(func_name,func_args)
            myLogger(f"<Fun:{inspect.currentframe().f_code.co_name}> tool_call\n\tfun name:{funName}\n\t isError:{isError}\n\treturn content:{content}")
            #myLogger(f"<Fun:{inspect.currentframe().f_code.co_name}> tool_call content[0].\n   type:{type(content[0])}\n   content:{content[0]}")

            toolMessage = {"role": "tool",
                           "tool_call_id": tool_call_id,
                           "content": serialize_MCPCallToResult(toolCallResult)}
            messages.append(toolMessage)

        choice = self.llmModel.Chat(messages,tools=None)
        role,content=self.llmModel.getMessageFromChoice(choice)
        return f"Assistant>\t {content}"

