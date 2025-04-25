import inspect
from contextlib import AsyncExitStack

from mcp import StdioServerParameters, stdio_client, ClientSession
from mcp.client.sse import sse_client
from mcp.types import CallToolResult

from helperFun import myLogger, toolDescriptionForLLM

class MCPClientSessionManager:
    def __init__(self):
        self._mcpStreamContexts = []
        self._mcpSessionContexts = []
        self._mcpClients = []

        self.mcp_tools = []
        self.toolname2MCPClient={}

        self.exit_stack = AsyncExitStack()

    def get_mcp_tools(self):
        return self.mcp_tools
    async def connect_to_stdio_server(self, serverParameters: StdioServerParameters):
        streams_context = stdio_client(serverParameters)
        self._mcpStreamContexts.append(streams_context)
        streams = await streams_context.__aenter__()

        session_context = ClientSession(*streams)
        self._mcpSessionContexts.append(session_context)
        mcpClientSession: ClientSession = await session_context.__aenter__()
        self._mcpClients.append(mcpClientSession)

        # Initialize
        await self.initMCPClient(mcpClientSession)

    async def connect_to_sse_server(self, server_url: str):
        """Connect to an MCP server running with SSE transport"""
        # Store the context managers so they stay alive
        streams_context = sse_client(url=server_url)
        self._mcpStreamContexts.append(streams_context)
        streams = await streams_context.__aenter__()

        session_context = ClientSession(*streams)
        self._mcpSessionContexts.append(session_context)
        mcpClientSession: ClientSession = await session_context.__aenter__()
        self._mcpClients.append(mcpClientSession)

        # Initialize
        await self.initMCPClient(mcpClientSession)
    async def initMCPClient(self,mcpClientSession):
        # Initialize
        myLogger(f"<Fun:{inspect.currentframe().f_code.co_name}> Initialized stdio client...")
        await mcpClientSession.initialize()

        # List available tools to verify connection
        myLogger(f"<Fun:{inspect.currentframe().f_code.co_name}> Listing tools...")
        response = await mcpClientSession.list_tools()
        tools = response.tools
        myLogger(
            f"<Fun:{inspect.currentframe().f_code.co_name}> Connected to server with tools: {[tool.name for tool in tools]}")

        for tool in tools:
            if tool.name in self.toolname2MCPClient:
                myLogger(
                    f"<Fun:{inspect.currentframe().f_code.co_name}> tool <{tool.name}> already exits in {self.toolname2MCPClient[tool.name]}")
                raise ValueError(f"Tool name {tool.name} already exists in the manager.")

            self.toolname2MCPClient[tool.name] = mcpClientSession
            self.mcp_tools.append(toolDescriptionForLLM(tool.name, tool.description, tool.inputSchema))

    async def execute_tool(self, funcName, funcArgs):
        if funcName not in self.toolname2MCPClient:
            raise ValueError(f"Tool name {funcName} does not exist in the manager.")

        mcpClientSession = self.toolname2MCPClient[funcName]

        """Execute the tool function with the provided arguments"""
        # MCP tool_call response:
        # 1.content: list[TextContent | ImageContent | EmbeddedResource]
        # 2.isError: bool = False
        result: CallToolResult = await mcpClientSession.call_tool(funcName, funcArgs)
        return result

    async def cleanup(self):
        """Properly clean up the session and streams"""
        try:
            for session_context in self._mcpSessionContexts:
                if session_context:
                    await session_context.__aexit__(None, None, None)

            for streams_context in self._mcpStreamContexts:
                if streams_context:
                    await streams_context.__aexit__(None, None, None)
        except Exception as e:
            myLogger(f"<Fun:{inspect.currentframe().f_code.co_name}> Cleanup error: {e}")
