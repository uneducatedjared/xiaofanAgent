# tools.py
import asyncio
from langchain_mcp_adapters.client import MultiServerMCPClient

# 初始化客户端（单例模式）
_client = MultiServerMCPClient(
    {
        "sql": {
            "url": "http://localhost:3000/sse",
            "transport": "sse"
        }
    }
)

# 异步获取工具
async def get_tools_async():
    """异步获取工具列表"""
    return await _client.get_tools()

# 同步获取工具（供同步代码调用）
def get_tools():
    """同步获取工具列表（内部使用事件循环）"""
    return asyncio.run(get_tools_async())
