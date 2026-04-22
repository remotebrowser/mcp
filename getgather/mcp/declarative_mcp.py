from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel

from getgather.mcp.dpage import remote_zen_dpage_mcp_tool
from getgather.mcp.registry import MCPTool
from getgather.zen_distill import short_lived_mcp_tool

YAML_CONFIG_PATH = Path(__file__).parent / "mcp-tools.yaml"


class ToolConfig(BaseModel):
    function_name: str
    description: str
    result_key: str
    url: str | None = None
    timeout: int | None = None
    short_lived: bool = False
    pattern_wildcard: str | None = None
    hostname: str | None = None


class McpConfig(BaseModel):
    id: str
    name: str
    tools: list[ToolConfig]


def _load_mcp_config() -> list[McpConfig]:
    with open(YAML_CONFIG_PATH) as f:
        data = yaml.safe_load(f)
    return [McpConfig(**item) for item in data]


DECLARATIVE_MCP_CONFIG: list[McpConfig] = _load_mcp_config()


def create_declarative_mcp_tools() -> None:
    """Create and register MCP tools from configuration array.

    This function generates MCPTool instances and their tools dynamically
    from the DECLARATIVE_MCP_CONFIG array. Tools can be either remote zen dpage tools
    or short-lived tools.
    """

    for config in DECLARATIVE_MCP_CONFIG:
        gather_mcp = MCPTool(brand_id=config.id, name=config.name)

        for tool_config in config.tools:
            function_name: str = tool_config.function_name
            description: str = tool_config.description
            short_lived: bool = tool_config.short_lived

            if short_lived:
                url: str = tool_config.url or ""
                pattern_wildcard: str = tool_config.pattern_wildcard or ""
                result_key: str = tool_config.result_key
                hostname: str = tool_config.hostname or ""

                def make_short_lived_tool_fn(
                    url: str = url,
                    pattern_wildcard: str = pattern_wildcard,
                    result_key: str = result_key,
                    hostname: str = hostname,
                ):
                    async def tool_func() -> dict[str, Any]:
                        terminated, result = await short_lived_mcp_tool(
                            location=url,
                            pattern_wildcard=pattern_wildcard,
                            result_key=result_key,
                            url_hostname=hostname,
                        )
                        if not terminated:
                            raise ValueError(f"Failed to retrieve {result_key}")
                        return result

                    return tool_func

                tool_func = make_short_lived_tool_fn()

            else:
                url: str = tool_config.url or ""
                result_key: str = tool_config.result_key
                timeout: int = tool_config.timeout if tool_config.timeout is not None else 2

                def make_remote_tool_fn(
                    url: str = url,
                    result_key: str = result_key,
                    timeout: int = timeout,
                ):
                    async def tool_func() -> dict[str, Any]:
                        return await remote_zen_dpage_mcp_tool(url, result_key, timeout=timeout)

                    return tool_func

                tool_func = make_remote_tool_fn()

            tool_func.__name__ = function_name
            tool_func.__doc__ = description
            gather_mcp.tool(tool_func)
