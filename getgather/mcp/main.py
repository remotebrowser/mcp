import asyncio
import json
from dataclasses import dataclass
from functools import cache, cached_property
from typing import Any, Literal

from fastmcp import Context, FastMCP
from fastmcp.server.dependencies import get_http_headers
from fastmcp.server.http import StarletteWithLifespan
from fastmcp.server.middleware import CallNext, Middleware, MiddlewareContext
from fastmcp.server.providers.fastmcp_provider import FastMCPProviderTool
from loguru import logger
from mcp.types import ToolExecution
from pydantic import BaseModel

from getgather.auth.auth import get_auth_user
from getgather.mcp.auto_import import auto_import
from getgather.mcp.calendar_utils import calendar_mcp
from getgather.mcp.dpage import dpage_check, dpage_finalize, zen_dpage_mcp_tool
from getgather.mcp.registry import GatherMCP
from getgather.request_info import RequestInfo, request_info

# Ensure calendar MCP is registered by importing its module
try:
    from getgather.mcp import calendar_utils  # type: ignore
except Exception as e:
    logger.warning(f"Failed to register calendar MCP: {e}")


def _patch_mounted_tool_execution_advertisement() -> None:
    if getattr(FastMCPProviderTool, "_getgather_execution_patch", False):
        return

    original_to_mcp_tool = FastMCPProviderTool.to_mcp_tool

    def patched_to_mcp_tool(self: FastMCPProviderTool, **overrides: Any):
        if self.task_config.supports_tasks() and "execution" not in overrides:
            overrides["execution"] = ToolExecution(taskSupport=self.task_config.mode)
        return original_to_mcp_tool(self, **overrides)

    FastMCPProviderTool.to_mcp_tool = patched_to_mcp_tool  # type: ignore[method-assign]
    setattr(FastMCPProviderTool, "_getgather_execution_patch", True)


class LocationProxyMiddleware(Middleware):
    # type: ignore
    async def on_call_tool(self, context: MiddlewareContext[Any], call_next: CallNext[Any, Any]):
        if not context.fastmcp_context:
            return await call_next(context)

        headers = get_http_headers(include_all=True)

        # Build logging context with session IDs
        log_context = {}
        mcp_session_id = headers.get("mcp-session-id")
        browser_session_id = headers.get("x-browser-session-id")

        if mcp_session_id:
            log_context["mcp_session_id"] = mcp_session_id
        if browser_session_id:
            log_context["browser_session_id"] = browser_session_id

        # Initialize request_info data
        info_data: dict[str, str | None] = {}

        # Handle x-location header (contains city, state, country, postal_code)
        location = headers.get("x-location", None)
        if location is not None:
            try:
                location_data: dict[str, str | None] = json.loads(location)
                info_data.update(location_data)
            except json.JSONDecodeError:
                with logger.contextualize(**log_context):
                    logger.warning(f"Failed to parse x-location header as JSON, {location}")

        # Handle x-proxy-type header (e.g., "proxy-0", "proxy-1", etc.)
        proxy_type = headers.get("x-proxy-type", None)
        if proxy_type is not None:
            info_data["proxy_type"] = proxy_type

        # Set request_info if we have any data
        if info_data:
            request_info.set(RequestInfo(**info_data))  # type: ignore[arg-type]

        tool = await context.fastmcp_context.fastmcp.get_tool(context.message.name)  # type: ignore
        if tool is None:
            return await call_next(context)

        if "general_tool" in tool.tags:
            with logger.contextualize(**log_context):
                return await call_next(context)

        brand_id = context.message.name.split("_")[0]
        await context.fastmcp_context.set_state("brand_id", brand_id)

        # Use contextualize to set context for all logs during tool execution
        with logger.contextualize(**log_context):
            logger.info(f"[AuthMiddleware Context]: {context.message}")
            if proxy_type:
                logger.info(f"Received x-proxy-type header: {proxy_type}")
            return await call_next(context)


MCP_BUNDLES: dict[str, list[str]] = {
    "media": ["bbc", "cnn", "espn", "groundnews", "npr", "nytimes"],
    "books": ["goodreads"],
    "shopping": ["amazon", "amazonca", "shopee", "wayfair"],
    "sports": ["garmin"],
    "media": ["bbc", "cnn", "espn", "groundnews", "npr", "nytimes"],
}


@dataclass
class MCPApp:
    name: str
    type: Literal["brand", "category", "all"]
    route: str
    brand_ids: list[str]

    @cached_property
    def app(self) -> StarletteWithLifespan:
        return _create_mcp_app(self.name, self.brand_ids)


@cache
def create_mcp_apps() -> list[MCPApp]:
    auto_import("getgather.mcp")

    apps: list[MCPApp] = []
    apps.append(
        MCPApp(
            name="all",
            type="all",
            route="/mcp",
            brand_ids=list(GatherMCP.registry.keys()),
        )
    )
    # Add individual brand MCPs from GatherMCP registry
    apps.extend([
        MCPApp(
            name=brand_id,
            type="brand",
            route=f"/mcp-{brand_id}",
            brand_ids=[brand_id],
        )
        for brand_id in GatherMCP.registry.keys()
    ])
    apps.extend([
        MCPApp(
            name=category,
            type="category",
            route=f"/mcp-{category}",
            brand_ids=MCP_BUNDLES[category],
        )
        for category in MCP_BUNDLES.keys()
    ])

    return apps


def _create_mcp_app(bundle_name: str, brand_ids: list[str]):
    """Create and return the MCP ASGI app.

    This performs plugin discovery/registration and mounts brand MCPs.
    """
    _patch_mounted_tool_execution_advertisement()

    mcp = FastMCP[Context](name=f"Getgather {bundle_name} MCP")
    mcp.add_middleware(LocationProxyMiddleware())

    @mcp.tool(tags={"general_tool"})
    def get_user_info():  # type: ignore[reportUnusedFunction]
        """Get information about the authenticated user."""
        user = get_auth_user()
        return user.dump()

    @mcp.tool(tags={"general_tool"})
    async def check_signin(ctx: Context, signin_id: str) -> dict[str, Any]:  # pyright: ignore[reportUnusedFunction]
        result = await dpage_check(id=signin_id)
        if result is None:
            return {
                "status": "ERROR",
                "message": "Sign in not completed within the time limit. Please try again.",
            }
        return {
            "status": "SUCCESS",
            "message": "Sign in completed successfully.",
            "result": result,
        }

    @mcp.tool(tags={"general_tool"})
    async def finalize_signin(ctx: Context, signin_id: str) -> dict[str, Any]:  # pyright: ignore[reportUnusedFunction]
        await dpage_finalize(id=signin_id)
        return {
            "status": "SUCCESS",
            "message": "Sign in finalized successfully.",
        }

    @mcp.tool(tags={"general_tool"})
    async def get_browser_ip_address() -> dict[str, Any]:  # pyright: ignore[reportUnusedFunction]
        return await _get_browser_ip_address()

    @mcp.tool(tags={"general_tool"})
    async def get_zen_browser_ip_address() -> dict[str, Any]:  # pyright: ignore[reportUnusedFunction]
        return await _get_browser_ip_address()

    async def _get_browser_ip_address() -> dict[str, Any]:
        return await zen_dpage_mcp_tool(
            initial_url="https://ip.fly.dev/ip", result_key="ip_address"
        )

    for brand_id in brand_ids:
        brand_id_str = brand_id
        if brand_id_str in GatherMCP.registry:
            gather_mcp = GatherMCP.registry[brand_id_str]
            logger.info(
                f"Mounting {gather_mcp.name} (distillation-based) to MCP bundle {bundle_name}"
            )
            mcp.mount(server=gather_mcp, prefix=gather_mcp.brand_id)

    mcp.mount(server=calendar_mcp, prefix="calendar")

    return mcp.http_app(path="/")


class MCPToolDoc(BaseModel):
    name: str
    description: str


class MCPDoc(BaseModel):
    name: str
    type: Literal["brand", "category", "all"]
    route: str
    tools: list[MCPToolDoc]


async def mcp_app_docs(mcp_app: MCPApp) -> MCPDoc:
    return MCPDoc(
        name=mcp_app.name,
        type=mcp_app.type,
        route=mcp_app.route,
        tools=[
            MCPToolDoc(
                name=tool.name,
                description=tool.description or "No description provided",
            )
            for tool in (await mcp_app.app.state.fastmcp_server.get_tools()).values()
        ],
    )
