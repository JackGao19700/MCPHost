import json

from mcp.types import CallToolResult

from debugLogger import FileLogger

# 配置日志记录器
myLogger=FileLogger("log/mcphost.log",delay=False)

def toolDescriptionForLLM(toolname,toolDescription,toolInputSchema):
    toolStr={
        "type": "function",
        "function": {
            "name": toolname,
            "description": toolDescription,
            "parameters": toolInputSchema
        },
    }
    return toolStr

def serialize_MCPCallToResult(tool_result: CallToolResult) -> str:
    """Convert CallToolResult to a JSON string."""
    serialized_content = []
    for item in tool_result.content:
        if hasattr(item, "text"):  # TextContent
            serialized_content.append({"type": item.type , "text": item.text})
        elif hasattr(item, "data"):  # ImageContent or EmbeddedResource
            serialized_content.append({"type": item.type, "data": item.data,"mimeType":item.mimeType})
        # 其他类型的 content 也可以类似处理

    if not tool_result.isError:
        return json.dumps({
            "content": serialized_content,
            "isError": tool_result.isError,
        })

    return json.dumps({
        "content": "",
        "isError": tool_result.isError,
    })