import inspect
import traceback

import requests

from mcp import StdioServerParameters
from MCPClientSessionManager import MCPClientSessionManager
from helperFun import myLogger,serialize_MCPCallToResult

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
    def __init__(self, llmModel,systemPrompt,toolCallMaxTry=10):
        self.mcpClientSessionManager = MCPClientSessionManager()
        self.llmModel=llmModel

        self.toolCallMaxTry=toolCallMaxTry

        self.chatContextWindowSize=20
        self.chatContext=[]
        systemMessage={
                    "role": "system",
                    "content": systemPrompt
                    }
        self.chatContext.append(systemMessage)

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
                 # 打印调用栈信息
                 traceback.print_exc()

    async def tryCallTools(self):
        for tryCount in range(self.toolCallMaxTry):
            print(f"Try Tool calling <#{tryCount}>")
            print(f"dialog context: {self.chatContext}")
            choice = self.llmModel.Chat(self.chatContext, self.mcpClientSessionManager.get_mcp_tools())
            self.llmModel.addMessageFromChoice(self.chatContext,choice)

            toolsToCall=self.llmModel.ParseToolCallMessage(choice)
            if toolsToCall is None:
                """No tool call needed.
                """
                role, content = self.llmModel.getMessageFromChoice(choice)
                return content

            allToolCallFailed=True
            for funName, funcArgs, tool_call_id in toolsToCall:
                from mcp.types import TextContent
                from typing import Optional
                toolCallResult: Optional[TextContent] = None
                toolCallResult=await self.mcpClientSessionManager.execute_tool(funName, funcArgs)

                content=toolCallResult.content
                isError=toolCallResult.isError
                if isError==False:
                    allToolCallFailed=False

                # result=restfulAPICall(func_name,func_args)
                myLogger(f"<Fun:{inspect.currentframe().f_code.co_name}> tool_call\n\tfun name:{funName}\n\t isError:{isError}\n\treturn content:{content}")
                #myLogger(f"<Fun:{inspect.currentframe().f_code.co_name}> tool_call content[0].\n   type:{type(content[0])}\n   content:{content[0]}")

                toolMessage = {"role": "tool",
                               "tool_call_id": tool_call_id,
                               "content": serialize_MCPCallToResult(toolCallResult)}
                self.chatContext.append(toolMessage)

            if allToolCallFailed:
                userMessage={
                    "role": "user",
                    "content": "请重新尝试找到合适的工具,再回答我的的问题."
                }
                self.chatContext.append(userMessage)
            else:
                break

        choice = self.llmModel.Chat(self.chatContext,tools=self.mcpClientSessionManager.get_mcp_tools())
        role,content=self.llmModel.getMessageFromChoice(choice)
        return content

    async def process_query(self, query: str) -> str:
        """Process a query using LLMModel and available tools"""
        if len(self.chatContext)>self.chatContextWindowSize:
            del self.chatContext[1:(len(self.chatContext)-self.chatContextWindowSize+2)]

        userMessage = {
                    "role": "user",
                    "content": query
                }
        self.chatContext.append(userMessage)
        content= await self.tryCallTools()
        return f"Assistant>\t {content}"

