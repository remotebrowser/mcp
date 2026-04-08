import ast
import asyncio
import json
from contextlib import AsyncExitStack, asynccontextmanager
from datetime import datetime
from typing import Any, Awaitable, Callable, Final

from fastapi import FastAPI, Request
from fastapi.responses import (
    HTMLResponse,
    PlainTextResponse,
    Response,
)
from fastapi.routing import APIRoute
from loguru import logger

from getgather.auth.auth import setup_mcp_auth
from getgather.config import settings
from getgather.logs import instrument_fastapi
from getgather.mcp.browser import browser_manager
from getgather.mcp.dpage import remote_zen_dpage_mcp_tool, router as dpage_router
from getgather.mcp.main import MCPDoc, create_mcp_apps, mcp_app_docs

# Create MCP apps once and reuse for lifespan and mounting
mcp_apps = create_mcp_apps()


def custom_generate_unique_id(route: APIRoute) -> str:
    tag = route.tags[0] if route.tags else "no-tag"
    return f"{tag}-{route.name}"


@asynccontextmanager
async def lifespan(app: FastAPI):
    if not settings.CHROMEFLEET_URL:
        logger.error("CHROMEFLEET_URL is not set. Exiting.")
        raise SystemExit(1)

    stop_event = asyncio.Event()

    async def timer_loop():
        while not stop_event.is_set():
            try:
                await browser_manager.cleanup_incognito_browsers()
            except Exception as e:
                logger.error(f"Error in cleanup_incognito_browsers: {e}", exc_info=True)
            try:
                await asyncio.wait_for(stop_event.wait(), timeout=5 * 60)
            except asyncio.TimeoutError:
                pass  # Timeout = 5 minutes passed, continue loop

    background_task = asyncio.create_task(timer_loop())

    async with AsyncExitStack() as stack:
        for mcp_app in mcp_apps:
            await stack.enter_async_context(mcp_app.app.lifespan(app))
        yield

        stop_event.set()
        await background_task


app = FastAPI(
    title="Get Gather",
    description="GetGather mcp, frontend, and api",
    version="0.1.0",
    generate_unique_id_function=custom_generate_unique_id,
    lifespan=lifespan,
)
instrument_fastapi(app)


@app.get("/health")
def health():
    return PlainTextResponse(
        content=f"OK {int(datetime.now().timestamp())} GIT_REV: {settings.GIT_REV}"
    )


IP_CHECK_URL: Final[str] = "https://ip.fly.dev/ip"


@app.get("/extended-health")
async def extended_health():
    try:
        result = await remote_zen_dpage_mcp_tool(
            initial_url="https://ip.fly.dev/ip", result_key="ip_address", timeout=3
        )
        ip_text = str(result.get("ip_address", "Unknown"))[:100]
        ip_list = ast.literal_eval(ip_text)
        ip_address = ip_list[0]["ip_address"]
        logger.debug(f"IP address: {ip_address}")
        return PlainTextResponse(content=f"OK IP: {ip_address}")
    except Exception as e:
        return PlainTextResponse(content=f"Error: {e}")


@app.middleware("http")
async def mcp_logging_context_middleware(
    request: Request, call_next: Callable[[Request], Awaitable[Response]]
):
    """Set logging context with session IDs for MCP requests."""
    if request.url.path.startswith("/mcp"):
        # Extract session IDs from headers
        browser_session_id = request.headers.get("x-browser-session-id")
        mcp_session_id = request.headers.get("mcp-session-id")

        # Build context dict
        context = {}
        if browser_session_id:
            context["browser_session_id"] = browser_session_id
            request.state.browser_session_id = browser_session_id
        if mcp_session_id:
            context["mcp_session_id"] = mcp_session_id
            request.state.mcp_session_id = mcp_session_id

        # Try to extract signin_id from request body if POST
        if request.method == "POST":
            try:
                body = await request.body()
                if body:
                    body_json: Any = json.loads(body.decode("utf-8"))
                    if isinstance(body_json, dict):
                        params: Any = body_json.get("params", {})  # type: ignore[misc]
                        if isinstance(params, dict):  # type: ignore[arg-type]
                            signin_id: Any = params.get("signin_id")  # type: ignore[misc]
                            if signin_id:  # type: ignore[arg-type]
                                context["signin_id"] = signin_id
            except Exception:
                pass

        # Use contextualize to set context for all logs in this request
        with logger.contextualize(**context):
            logger.info(f"[MIDDLEWARE] Processing MCP request to {request.url.path}")
            response = await call_next(request)

            # Extract mcp-session-id from response if not in request
            if not mcp_session_id and "mcp-session-id" in response.headers:
                with logger.contextualize(mcp_session_id=response.headers["mcp-session-id"]):
                    logger.debug("Added mcp_session_id from response")

            return response

    return await call_next(request)


@app.middleware("http")
async def mcp_slash_middleware(
    request: Request, call_next: Callable[[Request], Awaitable[Response]]
):
    """Make /mcp* and /mcp*/ behave the same without actual redirect."""
    path = request.url.path
    if path.startswith("/mcp") and not path.endswith("/"):
        request.scope["path"] = f"{path}/"
        if request.scope.get("raw_path"):
            request.scope["raw_path"] = f"{path}/".encode()
    return await call_next(request)


# Mount routers and apps AFTER middleware
app.include_router(dpage_router)

for mcp_app in mcp_apps:
    app.mount(mcp_app.route, mcp_app.app)

setup_mcp_auth(app, [mcp_app.route for mcp_app in mcp_apps])


@app.get("/docs-mcp")
async def mcp_docs() -> list[MCPDoc]:
    return await asyncio.gather(*[mcp_app_docs(mcp_app) for mcp_app in create_mcp_apps()])


@app.get("/")
def homepage():
    html = f"""<!DOCTYPE html>
<html lang="en">
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>GetGather</title>
<style>html,body{{margin:0;padding:0;height:100%;overflow:hidden}}iframe{{border:none;width:100%;height:100%}}</style>
</head>
<body><iframe src="{settings.CHROMEFLEET_URL}"></iframe></body>
</html>"""
    return HTMLResponse(content=html)
