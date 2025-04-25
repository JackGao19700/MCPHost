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

async def main(llmModel:llmModelWrapper,systemPrompt:str,
               serverParametersList:Optional[list[StdioServerParameters]],
               serverUrlList:Optional[list[str]]):
    # if len(sys.argv)<2:
    #     print("Usage: uv run client.py <URL of SSE MCP server (i.e. http://localhost:8080/sse)>")
    #     sys.exit(1)
    myMCPHost=MCPHost(llmModel,systemPrompt)
    try:
        if serverParametersList:
            for serverParameters in serverParametersList:
                await myMCPHost.connect_to_stdio_server(serverParameters)
        if serverUrlList:
            for serverUrl in serverUrlList:
                await myMCPHost.connect_to_sse_server(serverUrl)

        await myMCPHost.chatLoop()
    except Exception as e:
        print(f"An error occurred: {e}")
        myLogger(f"<Fun:{inspect.currentframe().f_code.co_name}> running error: {e}")
    finally:
        await myMCPHost.cleanup()

if __name__ == "__main__":
    load_dotenv(dotenv_path="./.env")  # load environment variables from.env
    api_key = os.environ.get("DEEPSEEK_API_KEY")
    api_base_url=os.environ.get("DEEPSEEK_API_BASE_URL")
    api_model_name=os.environ.get("DEEPSEEK_API_MODEL_NAME")
    brave_api_key=os.environ.get("BRAVE_API_KEY")

    llmModel=OpenAIModel(api_key,api_base_url,api_model_name)
    #llmModel=localOllamaModel("qwen2.5:latest")

    systemPrompt="你是一个智能助手，你的名字叫Jack.请调用工具,然后回答用户问题"
    serverParametersList=[]
    serverParametersList.append(StdioServerParameters(
        command="npx",  # Executable
        args=[
                "-y",
                "@modelcontextprotocol/server-filesystem",
                "J:\\",
                "J:\\mcpserverDemo\\mcpClient"
            ],
        env={"MCP_SERVER": "weather"}
    ))

    serverParametersList.append(StdioServerParameters(
        command="npx",  # Executable
        args=[
                "-y",
                "@modelcontextprotocol/server-brave-search",
            ],
        env={"BRAVE_API_KEY": brave_api_key}
    ))


    # 使用 asyncio.run 来运行异步函数
    asyncio.run(main(llmModel,systemPrompt,serverParametersList,None))

