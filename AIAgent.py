import inspect

import re
import requests
import json

import asyncio
from contextlib import AsyncExitStack
from typing import Optional

from mcp import ClientSession,StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.types import CallToolResult

from helperFun import myLogger,toolDeclare,serialize_MCPCallToResult
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
        # Initialize session and client objects
        self.mcpClientSession: Optional[ClientSession] = None
        self.exit_stack = AsyncExitStack()

        self.llmModel=llmModel
        self.systemPrompt=systemPrompt

    async def connect_to_stdio_server(self,serverParameters:StdioServerParameters):
        self._streams_context = stdio_client(serverParameters)
        streams = await self._streams_context.__aenter__()

        self._session_context = ClientSession(*streams)
        self.mcpClientSession: ClientSession = await self._session_context.__aenter__()

        # Initialize
        myLogger(f"<Fun:{inspect.currentframe().f_code.co_name}> Initialized stdio client...")
        await self.mcpClientSession.initialize()

        # List available tools to verify connection
        myLogger(f"<Fun:{inspect.currentframe().f_code.co_name}> Listing tools...")
        response = await self.mcpClientSession.list_tools()
        tools = response.tools
        myLogger(f"<Fun:{inspect.currentframe().f_code.co_name}> Connected to server with tools: {[tool.name for tool in tools]}")
        self.mcp_tools=[toolDeclare(tool.name,tool.description, tool.inputSchema) for tool in tools]

    async def cleanup(self):
        """Properly clean up the session and streams"""
        try:
            if self._session_context:
                await self._session_context.__aexit__(None, None, None)
            if self._streams_context:
                await self._streams_context.__aexit__(None, None, None)
        except Exception as e:
            myLogger(f"<Fun:{inspect.currentframe().f_code.co_name}> Cleanup error: {e}")

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

    async def execute_tool(self, funcName, funcArgs):
        """Execute the tool function with the provided arguments"""
        # MCP tool_call response:
        # 1.content: list[TextContent | ImageContent | EmbeddedResource]
        # 2.isError: bool = False
        result: CallToolResult = await self.mcpClientSession.call_tool(funcName, funcArgs)
        return result

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
        choice = self.llmModel.Chat(messages, self.mcp_tools)
        self.llmModel.addMessageFromChoice(messages,choice)

        toolsToCall=self.llmModel.ParseToolCallMessage(choice)
        for funName, funcArgs, tool_call_id in toolsToCall:
            from mcp.types import TextContent
            from typing import Optional
            toolCallResult: Optional[TextContent] = None
            toolCallResult=await self.execute_tool(funName, funcArgs)

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

async def main(llmModel:llmModelWrapper,systemPrompt:str,serverParameters:StdioServerParameters):
    # if len(sys.argv)<2:
    #     print("Usage: uv run client.py <URL of SSE MCP server (i.e. http://localhost:8080/sse)>")
    #     sys.exit(1)

    myMCPHost=MCPHost(llmModel,systemPrompt)
    try:
        await myMCPHost.connect_to_stdio_server(serverParameters)
        await myMCPHost.chatLoop()
    except Exception as e:
        print(f"An error occurred: {e}")
        myLogger(f"<Fun:{inspect.currentframe().f_code.co_name}> running error: {e}")
    finally:
        await myMCPHost.cleanup()

if __name__ == "__main__":
    api_key_name = "DEEPSEEK_API_KEY"
    api_base_url="https://api.deepseek.com"
    llmModel=OpenAIModel(api_key_name,api_base_url,"deepseek-chat")
    #llmModel=localOllamaModel("qwen2.5:latest")

    systemPrompt="你是一个智能助手，你的名字叫Jack.请调用工具,然后回答用户问题"
    serverParameters=StdioServerParameters(
        command="npx",  # Executable
        args=[
                "-y",
                "@modelcontextprotocol/server-filesystem",
                "J:\\",
                "J:\\mcpserverDemo\\mcpClient"
            ],
        env={"MCP_SERVER": "weather"}
    )

    # 使用 asyncio.run 来运行异步函数
    asyncio.run(main(llmModel,systemPrompt,serverParameters))

