import json
import os
import re
from typing import TYPE_CHECKING, Optional, Tuple

if TYPE_CHECKING:
    from openhands.controller.agent import Agent

from openhands.core.config.mcp_config import MCPConfig, MCPSSEServerConfig
from openhands.core.logger import openhands_logger as logger
from openhands.events.action.mcp import MCPAction
from openhands.events.observation.mcp import MCPObservation
from openhands.events.observation.observation import Observation
from openhands.mcp.client import MCPClient
from openhands.runtime.base import Runtime


# 全局变量存储当前正在评估的SWE-Bench任务信息
_current_swe_bench_instance_id: Optional[str] = None
_current_swe_bench_repo: Optional[str] = None
_current_swe_bench_issue_number: Optional[int] = None


def set_current_swe_bench_task(instance_id: str):
    """
    设置当前正在评估的SWE-Bench任务信息
    instance_id格式: {org}__{repo}-{number}
    例如: django__django-11099
    """
    global _current_swe_bench_instance_id, _current_swe_bench_repo, _current_swe_bench_issue_number
    
    _current_swe_bench_instance_id = instance_id
    
    # 解析instance_id获取repo和issue number
    # 格式: {org}__{repo}-{number}
    match = re.match(r'^([^_]+)__([^-]+)-(\d+)$', instance_id)
    if match:
        org, repo, number = match.groups()
        _current_swe_bench_repo = f"{org}/{repo}"
        _current_swe_bench_issue_number = int(number)
        logger.info(f"Set current SWE-Bench task: repo={_current_swe_bench_repo}, issue_number={_current_swe_bench_issue_number}")
    else:
        logger.warning(f"Could not parse SWE-Bench instance_id: {instance_id}")
        _current_swe_bench_repo = None
        _current_swe_bench_issue_number = None


def get_current_swe_bench_task() -> Tuple[Optional[str], Optional[str], Optional[int]]:
    """
    获取当前正在评估的SWE-Bench任务信息
    返回: (instance_id, repo, issue_number)
    """
    return _current_swe_bench_instance_id, _current_swe_bench_repo, _current_swe_bench_issue_number


def should_block_swe_bench_issue(issue: dict) -> bool:
    """
    检查是否应该屏蔽这个issue（基于当前SWE-Bench任务）
    支持从 repository.full_name 或 repository_url 提取 repo 名
    """
    # 如果没有设置当前任务，不屏蔽任何issue
    if _current_swe_bench_repo is None or _current_swe_bench_issue_number is None:
        return False

    # 优先用 repository.full_name
    issue_repo = issue.get("repository", {}).get("full_name")
    if not issue_repo:
        # 尝试从 repository_url 提取 owner/repo
        repo_url = issue.get("repository_url", "")
        # 例：https://api.github.com/repos/PetteriAimonen/focus-stack
        if repo_url:
            parts = repo_url.rstrip("/").split("/")
            if len(parts) >= 2:
                issue_repo = f"{parts[-2]}/{parts[-1]}"
            else:
                issue_repo = ""
        else:
            issue_repo = ""
    issue_number = issue.get("number")

    if issue_repo == _current_swe_bench_repo and issue_number == _current_swe_bench_issue_number:
        logger.info(f"Blocking SWE-Bench issue: {issue_repo}#{issue_number}")
        return True

    return False


def filter_swe_bench_issues(issues: list) -> list:
    """
    过滤掉当前SWE-Bench任务对应的issue
    """
    if not issues:
        return issues
    
    filtered_issues = []
    blocked_count = 0
    
    for issue in issues:
        if should_block_swe_bench_issue(issue):
            blocked_count += 1
        else:
            filtered_issues.append(issue)
    
    if blocked_count > 0:
        logger.info(f"Filtered {blocked_count} SWE-Bench task issue(s) from search results")
    
    return filtered_issues


def convert_mcp_clients_to_tools(mcp_clients: list[MCPClient] | None) -> list[dict]:
    """
    Converts a list of MCPClient instances to ChatCompletionToolParam format
    that can be used by CodeActAgent.

    Args:
        mcp_clients: List of MCPClient instances or None

    Returns:
        List of dicts of tools ready to be used by CodeActAgent
    """
    if mcp_clients is None:
        logger.warning('mcp_clients is None, returning empty list')
        return []

    all_mcp_tools = []
    try:
        for client in mcp_clients:
            # Each MCPClient has an mcp_clients property that is a ToolCollection
            # The ToolCollection has a to_params method that converts tools to ChatCompletionToolParam format
            for tool in client.tools:
                mcp_tools = tool.to_param()
                if(mcp_tools["function"]["name"] == "search_issues" or mcp_tools["function"]["name"] == "search_repositories" or mcp_tools["function"]["name"] == "search_code"):
                    # 为search_issues工具添加过滤说明
                    if mcp_tools["function"]["name"] == "search_issues":
                        if "description" in mcp_tools["function"]:
                            mcp_tools["function"]["description"] += " (Note: Current SWE-bench task issues are filtered out for evaluation purposes)"
                    all_mcp_tools.append(mcp_tools)
    except Exception as e:
        logger.error(f'Error in convert_mcp_clients_to_tools: {e}')
        return []
    return all_mcp_tools


async def create_mcp_clients(
    sse_servers: list[MCPSSEServerConfig],
) -> list[MCPClient]:
    mcp_clients: list[MCPClient] = []
    # Initialize SSE connections
    if sse_servers:
        for server_url in sse_servers:
            logger.info(
                f'Initializing MCP agent for {server_url} with SSE connection...'
            )

            client = MCPClient()
            try:
                await client.connect_sse(server_url.url, api_key=server_url.api_key)
                # Only add the client to the list after a successful connection
                mcp_clients.append(client)
                logger.info(f'Connected to MCP server {server_url} via SSE')
            except Exception as e:
                logger.error(f'Failed to connect to {server_url}: {str(e)}')
                try:
                    await client.disconnect()
                except Exception as disconnect_error:
                    logger.error(
                        f'Error during disconnect after failed connection: {str(disconnect_error)}'
                    )

    return mcp_clients


async def fetch_mcp_tools_from_config(mcp_config: MCPConfig) -> list[dict]:
    """
    Retrieves the list of MCP tools from the MCP clients.

    Returns:
        A list of tool dictionaries. Returns an empty list if no connections could be established.
    """
    mcp_clients = []
    mcp_tools = []
    try:
        logger.debug(f'Creating MCP clients with config: {mcp_config}')
        # Create clients - this will fetch tools but not maintain active connections
        mcp_clients = await create_mcp_clients(
            mcp_config.sse_servers,
        )

        if not mcp_clients:
            logger.debug('No MCP clients were successfully connected')
            return []

        # Convert tools to the format expected by the agent
        mcp_tools = convert_mcp_clients_to_tools(mcp_clients)

        # Always disconnect clients to clean up resources
        for mcp_client in mcp_clients:
            try:
                await mcp_client.disconnect()
            except Exception as disconnect_error:
                logger.error(f'Error disconnecting MCP client: {str(disconnect_error)}')

    except Exception as e:
        logger.error(f'Error fetching MCP tools: {str(e)}')
        return []

    logger.debug(f'MCP tools: {mcp_tools}')
    return mcp_tools


async def call_search_issues_with_filter(mcp_clients: list[MCPClient], action: MCPAction) -> Observation:
    """
    调用search_issues工具并过滤当前SWE-Bench任务对应的issue
    """
    # 检查是否启用了swe-bench过滤
    if os.environ.get('SWE_BENCH_MCP_FILTER', 'false').lower() != 'true':
        # 如果没有启用过滤，正常调用
        return await call_tool_mcp(mcp_clients, action)
    
    # 获取当前SWE-Bench任务信息
    instance_id, repo, issue_number = get_current_swe_bench_task()
    
    if instance_id:
        logger.info(f"Filtering GitHub issues for SWE-Bench task: {instance_id} ({repo}#{issue_number})")
    
    # 正常调用search_issues工具
    matching_client = None
    for client in mcp_clients:
        if "search_issues" in [tool.name for tool in client.tools]:
            matching_client = client
            break
    
    if matching_client is None:
        raise ValueError('No matching MCP agent found for search_issues tool')
    
    # 调用原始工具
    response = await matching_client.call_tool(action.name, action.arguments)
    response_data = response.model_dump(mode='json')
    
    # 过滤结果中的当前SWE-Bench任务对应的issue
    if "items" in response_data:
        original_count = len(response_data["items"])
        response_data["items"] = filter_swe_bench_issues(response_data["items"])
        filtered_count = len(response_data["items"])
        
        response_data["total_count"] = filtered_count
        
        # 添加过滤说明
        if filtered_count < original_count:
            response_data["filter_note"] = f"Filtered {original_count - filtered_count} SWE-Bench task issue(s) for evaluation purposes"
            logger.info(f"Filtered {original_count - filtered_count} SWE-Bench task issue(s) from search results")
    
    return MCPObservation(content=json.dumps(response_data))


async def call_tool_mcp(mcp_clients: list[MCPClient], action: MCPAction) -> Observation:
    """
    Call a tool on an MCP server and return the observation.

    Args:
        mcp_clients: The list of MCP clients to execute the action on
        action: The MCP action to execute

    Returns:
        The observation from the MCP server
    """
    if not mcp_clients:
        raise ValueError('No MCP clients found')

    logger.debug(f'MCP action received: {action}')

    # 如果是search_issues工具，使用过滤逻辑
    if action.name == "search_issues":
        return await call_search_issues_with_filter(mcp_clients, action)

    # Find the MCP client that has the matching tool name
    matching_client = None
    logger.debug(f'MCP clients: {mcp_clients}')
    logger.debug(f'MCP action name: {action.name}')

    for client in mcp_clients:
        logger.debug(f'MCP client tools: {client.tools}')
        if action.name in [tool.name for tool in client.tools]:
            matching_client = client
            break

    if matching_client is None:
        raise ValueError(f'No matching MCP agent found for tool name: {action.name}')

    logger.debug(f'Matching client: {matching_client}')

    # Call the tool - this will create a new connection internally
    response = await matching_client.call_tool(action.name, action.arguments)
    logger.debug(f'MCP response: {response}')

    return MCPObservation(content=json.dumps(response.model_dump(mode='json')))


async def add_mcp_tools_to_agent(
    agent: 'Agent', runtime: Runtime, mcp_config: MCPConfig
):
    """
    Add MCP tools to an agent.
    """
    print(mcp_config)
    from openhands.runtime.impl.action_execution.action_execution_client import (
        ActionExecutionClient,  # inline import to avoid circular import
    )

    assert isinstance(runtime, ActionExecutionClient), (
        'Runtime must be an instance of ActionExecutionClient'
    )
    assert runtime.runtime_initialized, (
        'Runtime must be initialized before adding MCP tools'
    )

    # Add the runtime as another MCP server
    updated_mcp_config = runtime.get_updated_mcp_config()
    # Fetch the MCP tools
    mcp_tools = await fetch_mcp_tools_from_config(updated_mcp_config)

    logger.info(
        f'Loaded {len(mcp_tools)} MCP tools: {[tool["function"]["name"] for tool in mcp_tools]}'
    )

    # Set the MCP tools on the agent
    agent.set_mcp_tools(mcp_tools)
