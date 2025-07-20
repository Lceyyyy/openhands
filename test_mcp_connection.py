#!/usr/bin/env python3
"""
详细调试测试脚本
"""
import asyncio
import traceback
import sys

async def detailed_mcp_test():
    print("=== 详细 MCP 连接测试 ===")
    
    try:
        from mcp.client.sse import sse_client
        from mcp import ClientSession
        print("✓ MCP 库导入成功")
    except ImportError as e:
        print(f"✗ 无法导入 MCP 库: {e}")
        return False
    
    server_url = "http://localhost:8000/sse"
    print(f"尝试连接到: {server_url}")
    
    try:
        async with sse_client(url=server_url, timeout=10.0) as streams:
            print("✓ SSE 连接成功建立")
            
            async with ClientSession(*streams) as session:
                print("✓ MCP 会话创建成功")
                
                # 初始化会话
                print("开始初始化会话...")
                await session.initialize()
                print("✓ 会话初始化成功")
                
                # 尝试获取工具列表，添加更多调试信息
                print("开始获取工具列表...")
                try:
                    # 设置较短的超时时间来快速失败
                    response = await asyncio.wait_for(session.list_tools(), timeout=5.0)
                    print(f"✓ 成功获取到 {len(response.tools)} 个工具:")
                    
                    for tool in response.tools:
                        print(f"  - {tool.name}: {tool.description}")
                    
                    return True
                    
                except asyncio.TimeoutError:
                    print("✗ 获取工具列表超时")
                    print("这可能意味着 mcp-server-fetch 没有正确响应")
                    return False
                    
                except Exception as e:
                    print(f"✗ 获取工具列表失败: {type(e).__name__}: {e}")
                    print("详细错误信息:")
                    print(traceback.format_exc())
                    return False
                
    except Exception as e:
        print(f"✗ 连接失败: {type(e).__name__}: {e}")
        print("详细错误信息:")
        print(traceback.format_exc())
        return False

async def test_mcp_server_fetch_directly():
    """测试是否可以直接连接到 mcp-server-fetch"""
    print("\n=== 测试直接连接到 mcp-server-fetch ===")
    
    try:
        from mcp.client.stdio import stdio_client
        from mcp import ClientSession
        import subprocess
        
        # 启动 mcp-server-fetch 进程
        print("启动 mcp-server-fetch 进程...")
        process = subprocess.Popen(
            ["uvx", "mcp-server-fetch"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        
        try:
            # 连接到 stdio
            async with stdio_client(process.stdin, process.stdout) as streams:
                print("✓ stdio 连接成功")
                
                async with ClientSession(*streams) as session:
                    print("✓ 直接会话创建成功")
                    
                    await session.initialize()
                    print("✓ 直接会话初始化成功")
                    
                    response = await asyncio.wait_for(session.list_tools(), timeout=5.0)
                    print(f"✓ 直接连接获取到 {len(response.tools)} 个工具:")
                    
                    for tool in response.tools:
                        print(f"  - {tool.name}: {tool.description}")
                    
                    return True
                    
        finally:
            # 清理进程
            process.terminate()
            process.wait()
            
    except Exception as e:
        print(f"✗ 直接连接失败: {type(e).__name__}: {e}")
        return False

if __name__ == "__main__":
    print("开始详细测试...")
    
    # 测试通过 mcp-proxy 连接
    success1 = asyncio.run(detailed_mcp_test())
    
    # 测试直接连接到 mcp-server-fetch
    success2 = asyncio.run(test_mcp_server_fetch_directly())
    
    if success1:
        print("\n🎉 通过 mcp-proxy 连接成功!")
    elif success2:
        print("\n⚠️  mcp-server-fetch 工作正常，但 mcp-proxy 有问题")
        print("建议重新启动 mcp-proxy")
    else:
        print("\n❌ 所有测试都失败了")
        print("请检查:")
        print("1. mcp-server-fetch 是否正确安装")
        print("2. mcp-proxy 日志中的错误信息")