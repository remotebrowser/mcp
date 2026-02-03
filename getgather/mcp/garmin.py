import asyncio
import os
from typing import Any

import zendriver as zd
from loguru import logger

from bs4 import BeautifulSoup

from getgather.mcp.dpage import zen_dpage_with_action
from getgather.mcp.html_renderer import render_form
from getgather.mcp.registry import AppUIConfig, GatherMCP
from getgather.zen_actions import parse_response_json
from getgather.zen_distill import load_distillation_patterns, run_distillation_loop

EMBEDDED_VIEW_HTML = """<!DOCTYPE html>
<html>
<head>
  <meta name="color-scheme" content="light dark">
  <style>
    html, body {
      margin: 0;
      padding: 0;
      overflow: hidden;
      background: transparent;
    }
    body {
      display: flex;
      justify-content: center;
      align-items: center;
      height: 340px;
      width: 340px;
    }
    img {
      width: 300px;
      height: 300px;
      border-radius: 8px;
      box-shadow: 0 2px 8px rgba(0,0,0,0.1);
    }
  </style>
</head>
<body>
  <div id="qr"></div>
  <script type="module">
    import { App } from "https://unpkg.com/@modelcontextprotocol/ext-apps@0.4.0/app-with-deps";

    const app = new App({ name: "QR View", version: "1.0.0" });

    app.ontoolresult = ({ content }) => {
      const img = content?.find(c => c.type === 'image');
      if (img) {
        const qrDiv = document.getElementById('qr');
        qrDiv.innerHTML = '';

        const allowedTypes = ['image/png', 'image/jpeg', 'image/gif'];
        const mimeType = allowedTypes.includes(img.mimeType) ? img.mimeType : 'image/png';

        const image = document.createElement('img');
        image.src = `data:${mimeType};base64,${img.data}`;
        image.alt = "QR Code";
        qrDiv.appendChild(image);
      }
    };

    function handleHostContextChanged(ctx) {
      if (ctx.safeAreaInsets) {
        document.body.style.paddingTop = `${ctx.safeAreaInsets.top}px`;
        document.body.style.paddingRight = `${ctx.safeAreaInsets.right}px`;
        document.body.style.paddingBottom = `${ctx.safeAreaInsets.bottom}px`;
        document.body.style.paddingLeft = `${ctx.safeAreaInsets.left}px`;
      }
    }

    app.onhostcontextchanged = handleHostContextChanged;

    await app.connect();
    const ctx = app.getHostContext();
    if (ctx) {
      handleHostContextChanged(ctx);
    }
  </script>
</body>
</html>"""

GARMIN_SIGNIN_HTML_PATH = os.path.join(
    os.path.dirname(__file__), "patterns", "garmin-signin.html"
)
with open(GARMIN_SIGNIN_HTML_PATH, encoding="utf-8") as f:
    GARMIN_SIGNIN_HTML_RAW = f.read()

GARMIN_SIGNIN_SOUP = BeautifulSoup(GARMIN_SIGNIN_HTML_RAW, "html.parser")
GARMIN_SIGNIN_BODY = GARMIN_SIGNIN_SOUP.find("body")
GARMIN_SIGNIN_CONTENT = (
    str(GARMIN_SIGNIN_BODY) if GARMIN_SIGNIN_BODY else GARMIN_SIGNIN_HTML_RAW
)
GARMIN_SIGNIN_TITLE_EL = GARMIN_SIGNIN_SOUP.find("title")
GARMIN_SIGNIN_TITLE = (
    GARMIN_SIGNIN_TITLE_EL.get_text(strip=True) if GARMIN_SIGNIN_TITLE_EL else "Garmin Sign In"
)
GARMIN_ACTIVITIES_UI_HTML = render_form(
    GARMIN_SIGNIN_CONTENT,
    title=GARMIN_SIGNIN_TITLE,
    action="",
)

garmin_app_ui = AppUIConfig(
    resource_uri="ui://garmin/activities",
    template_content=GARMIN_ACTIVITIES_UI_HTML,
    csp_resource_domains=["https://unpkg.com"],
)
garmin_mcp = GatherMCP(
    brand_id="garmin",
    name="Garmin MCP",
    app_ui=garmin_app_ui,
)


@garmin_mcp.resource(uri=garmin_app_ui.resource_uri)
def _garmin_activities_ui_resource() -> str:  # pyright: ignore[reportUnusedFunction]
    """Serve the MCP App UI for Garmin activities."""
    return garmin_app_ui.template_content or ""


@garmin_mcp.tool(meta=garmin_app_ui.tool_meta())
async def show_activities_ui() -> dict[str, Any]:
    """Open the Garmin activities UI (test tool for MCP App). Use this to verify the embedded UI loads."""
    return {
        "message": "Garmin activities UI test",
        "status": "ok",
    }


@garmin_mcp.tool
async def get_activities() -> dict[str, Any]:
    """Get the activity history from a user's account."""

    async def add_activity_ids_action(tab: zd.Tab, browser: zd.Browser) -> dict[str, Any]:
        path = os.path.join(os.path.dirname(__file__), "patterns", "garmin-activities.html")
        patterns = load_distillation_patterns(path)

        _terminated, _distilled, converted = await run_distillation_loop(
            location=tab.url or "",
            patterns=patterns,
            browser=browser,
            timeout=10,
            page=tab,
            close_page=False,
            interactive=False,
        )

        activities = converted if converted else []
        logger.info(f"Activities: {activities}")

        for activity in activities:
            activity_url = activity.get("activity_url", "")
            if isinstance(activity_url, str) and activity_url:
                parts = activity_url.split("/")
                if len(parts) > 0:
                    activity_id = parts[-1]
                    activity["activity_id"] = activity_id
                    activity["activity_url"] = f"https://connect.garmin.com{activity_url}"
                    logger.info(f"Activity: {activity}")

        return {"garmin_activity_history": activities}

    return await zen_dpage_with_action(
        "https://connect.garmin.com/modern/activities",
        action=add_activity_ids_action,
    )


@garmin_mcp.tool
async def get_activity_stats(activity_id: str) -> dict[str, Any]:
    """Get the stats for a specific activity."""

    async def action(tab: zd.Tab, _) -> dict[str, Any]:
        try:

            async def get_stats():
                async with tab.expect_response(
                    f".*activity-service/activity/{activity_id}.*"
                ) as resp:
                    data = await parse_response_json(resp, {}, "garmin activity stats")
                return data

            data = await asyncio.wait_for(get_stats(), timeout=30)
            return {"garmin_activity_stats": data}
        except asyncio.TimeoutError:
            logger.error(
                f"Timeout waiting for activity stats API response for activity {activity_id}. "
                "The API request may not have been triggered or the endpoint pattern doesn't match."
            )
            return {"garmin_activity_stats": {}}

    return await zen_dpage_with_action(
        f"https://connect.garmin.com/modern/activity/{activity_id}",
        action,
    )


@garmin_mcp.tool
async def calculate_calories_burned(avg_power: float, seconds: int) -> dict[str, Any]:
    """Get the fueling strategy for a specific activity."""
    mechanical_work = avg_power * seconds
    calories_burned = mechanical_work / (0.25 * 4.184)
    return {
        "calories_burned": calories_burned,
    }


@garmin_mcp.tool
async def calculate_tss(
    seconds: int, norm_power: float, intensity_factor: float, ftp: float
) -> dict[str, Any]:
    """Calculate the TSS for a specific activity. Ask FTP first from user first."""
    tss = (seconds * norm_power * intensity_factor) / (ftp * 3600) * 100
    return {
        "tss": tss,
    }

