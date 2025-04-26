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

from MCPHost import MCPHost
from helperFun import myLogger,toolDescriptionForLLM,serialize_MCPCallToResult
from llmModel import llmModelWrapper,OpenAIModel,localOllamaModel
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

env_pattern = re.compile(r'\$\{([^}]+)\}')
def replace_env_vars_recursive(data):
    if isinstance(data, dict):
        new_dict = {}
        for key, value in data.items():
            new_dict[key] = replace_env_vars_recursive(value)
        return new_dict
    elif isinstance(data, list):
        new_list = []
        for item in data:
            new_list.append(replace_env_vars_recursive(item))
        return new_list
    elif isinstance(data, str):
        matches = env_pattern.findall(data)
        for match in matches:
            env_value = os.environ.get(match, '')
            if not env_value:
                myLogger(f"<Fun:{inspect.currentframe().f_code.co_name}> 环境变量 {match} 未找到，将其替换为空字符串。")
            data = data.replace(f"${{{match}}}", env_value)
        return data
    else:
        return data

def getMCPServersConfig(file_path):
    import json

    stdio_servers = []
    try:
        with open(file_path, 'r', encoding='utf-8') as file:
            config_data = json.load(file)
            # 预处理配置数据，替换环境变量
            config_data = replace_env_vars_recursive(config_data)
            mcp_servers = config_data.get('mcpServers', {})

            for server_name, server_config in mcp_servers.items():
                myLogger(f"<Fun:{inspect.currentframe().f_code.co_name}> server name:{server_name}")
                try:
                    stdio_server = StdioServerParameters(**server_config)
                    stdio_servers.append(stdio_server)
                except Exception as e:
                    myLogger(f"<Fun:{inspect.currentframe().f_code.co_name}> server config error:\n\tname:{server_name}\n\tconfig:{server_config}\n\t error:{e}")
                finally:
                    continue

    except FileNotFoundError:
        print(f"文件 {file_path} 未找到。")
        myLogger(f"<Fun:{inspect.currentframe().f_code.co_name}> 文件 {file_path} 未找到。")
    except json.JSONDecodeError as e:
        print(f"解析文件 {file_path} 时发生 JSON 解码错误: {e}")
        myLogger(f"<Fun:{inspect.currentframe().f_code.co_name}> 解析文件 {file_path} 时发生 JSON 解码错误: {e}")
    return stdio_servers

def configReadingTest():
    load_dotenv(dotenv_path="./.env")  # load environment variables from.env
    # 使用示例
    file_path = 'J:/mcpserverDemo/MCPHost/mcpservers.config'
    servers = getMCPServersConfig(file_path)
    for server in servers:
        print(server)

def OpenAIModelTest():
    load_dotenv(dotenv_path="./.env")  # load environment variables from.env

    api_key = os.environ.get("DEEPSEEK_API_KEY")
    api_base_url=os.environ.get("DEEPSEEK_API_BASE_URL")
    api_model_name=os.environ.get("DEEPSEEK_API_MODEL_NAME")
    llmModel=OpenAIModel(api_key,api_base_url,api_model_name)

    file_path = './mcpservers.config'
    serverParametersList = getMCPServersConfig(file_path)
    systemPrompt="你是一个智能助手，你的名字叫Jack.请调用工具,然后回答用户问题"

    # 使用 asyncio.run 来运行异步函数
    asyncio.run(main(llmModel,systemPrompt,serverParametersList,None))

def localOllamaModelTest():
    load_dotenv(dotenv_path="./.env")  # load environment variables from.env
    llmModel=localOllamaModel("qwen2.5:latest")

    systemPrompt="你是一个智能助手，你的名字叫Jack.请调用工具,然后回答用户问题"
    file_path = './mcpservers.config'
    serverParametersList = getMCPServersConfig(file_path)
    systemPrompt="你是一个智能助手，你的名字叫Jack.请调用工具,然后回答用户问题"

    # 使用 asyncio.run 来运行异步函数
    asyncio.run(main(llmModel,systemPrompt,serverParametersList,None))


if __name__ == "__main__":
    #configReadingTest()
    OpenAIModelTest()
    #localOllamaModelTest()
