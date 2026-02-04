import asyncio
import os
from typing import Any

import zendriver as zd
from loguru import logger

from getgather.mcp.dpage import zen_dpage_with_action
from getgather.mcp.registry import AppUIConfig, GatherMCP
from getgather.zen_actions import parse_response_json
from getgather.zen_distill import load_distillation_patterns, run_distillation_loop

GARMIN_SIGNIN_UI_URI = "ui://garmin/signin"

garmin_app_ui = AppUIConfig(
    resource_uri=GARMIN_SIGNIN_UI_URI,
    template_content=None,
    csp_resource_domains=["https://unpkg.com"],
)
garmin_mcp = GatherMCP(
    brand_id="garmin",
    name="Garmin MCP",
    app_ui=garmin_app_ui,
)


ERROR_HTML_TEMPLATE = """<!DOCTYPE html>
<html><head><title>{title}</title></head>
<body><p style='color: #b91c1c; text-align: center; padding: 2rem;'>{body}</p></body>
</html>"""

SIGNIN_UI_HTML = """<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>Garmin Sign In</title>
    <style>
        * {{ margin: 0; padding: 0; }}
        body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; background: #f5f5f5; }}
        #container {{ display: flex; flex-direction: column; height: 100vh; }}
        #iframe-wrapper {{ flex: 1; position: relative; }}
        #iframe-wrapper iframe {{ width: 100%; height: 100%; border: 0; }}
        #status {{ padding: 1rem; background: #f0f9ff; border-bottom: 1px solid #bfdbfe; text-align: center; color: #1e40af; font-size: 0.875rem; display: none; }}
        #status.show {{ display: block; }}
    </style>
</head>
<body>
    <div id="container">
        <div id="status"></div>
        <div id="iframe-wrapper">
            <iframe src="{url}"></iframe>
        </div>
    </div>
    <script type="module">
        import {{ App }} from "https://unpkg.com/@modelcontextprotocol/ext-apps@0.4.0/app-with-deps";
        
        let signinId = null;
        let pollCount = 0;
        const MAX_POLLS = 60; // 5 minutes with 5s intervals
        const POLL_INTERVAL = 5000; // 5 seconds
        let pollTimer = null;
        
        const statusEl = document.getElementById("status");
        
        function setStatus(msg) {{
            statusEl.textContent = msg;
            statusEl.classList.add("show");
        }}
        
        function clearStatus() {{
            statusEl.classList.remove("show");
        }}
        
        const app = new App({{
            name: "Garmin Sign In",
            version: "1.0.0"
        }});
        
        app.ontoolresult = (result) => {{
            // Get signin_id from the initial tool result (e.g., from show_signin_ui or get_activities)
            if (result.structuredContent?.signin_id) {{
                signinId = result.structuredContent.signin_id;
                console.log("Sign-in ID received:", signinId);
                startPolling();
            }}
        }};
        
        async function checkSigninStatus() {{
            try {{
                const result = await app.callServerTool({{
                    name: "check_signin",
                    arguments: {{ signin_id: signinId }}
                }});
                
                const status = result.structuredContent?.status || result.status;
                console.log("Check signin status:", status);
                
                if (status === "SUCCESS") {{
                    setStatus("Sign-in successful! Fetching activities...");
                    clearPolling();
                    
                    await new Promise(resolve => setTimeout(resolve, 1000));
                    const activitiesResult = await app.callServerTool({{
                        name: "garmin_get_activities",
                        arguments: {{}}
                    }});
                    
                    setStatus("Activities loaded!");
                    if (!activitiesResult.isError && (activitiesResult.content?.length || activitiesResult.structuredContent)) {{
                        try {{
                            await app.updateModelContext({{
                                content: activitiesResult.content,
                                structuredContent: activitiesResult.structuredContent
                            }});
                            await app.sendMessage({{
                                role: "user",
                                content: [{{ type: "text", text: "Garmin sign-in is complete and activities have been loaded. Please summarize or display the activities for the user." }}]
                            }});
                        }} catch (e) {{
                            console.warn("Could not continue conversation:", e);
                        }}
                    }}
                }}
            }} catch (err) {{
                console.error("Error checking sign-in status:", err);
            }}
        }}
        
        function startPolling() {{
            pollCount = 0;
            setStatus("Waiting for sign-in to complete...");
            
            pollTimer = setInterval(async () => {{
                pollCount++;
                if (pollCount > MAX_POLLS) {{
                    clearStatus();
                    clearPolling();
                    return;
                }}
                await checkSigninStatus();
            }}, POLL_INTERVAL);
        }}
        
        function clearPolling() {{
            if (pollTimer) {{
                clearInterval(pollTimer);
                pollTimer = null;
            }}
        }}
        
        // Connect to the app
        await app.connect();
    </script>
</body>
</html>"""

MCP_APP_HTML_MIME = "text/html;profile=mcp-app"
_signin_url: str | None = None


@garmin_mcp.resource(uri=GARMIN_SIGNIN_UI_URI, mime_type=MCP_APP_HTML_MIME)
async def _garmin_signin_ui_resource() -> str:  # pyright: ignore[reportUnusedFunction]
    """Serve the MCP App UI for Garmin sign-in with auto-continue on success."""
    from getgather.mcp.dpage import active_pages

    signin_id = next(reversed(active_pages), None) if active_pages else None
    if not signin_id or signin_id not in active_pages:
        return ERROR_HTML_TEMPLATE.format(
            title="Session Expired",
            body="Sign-in session not found or expired. Please try again.",
        )

    url = _signin_url
    if not url:
        return ERROR_HTML_TEMPLATE.format(
            title="Error",
            body="No sign-in URL available. Start the sign-in flow again.",
        )
    return SIGNIN_UI_HTML.format(url=url)


@garmin_mcp.tool(meta=garmin_app_ui.tool_meta())
async def show_signin_ui(signin_id: str) -> dict[str, Any]:
    """Open the Garmin sign-in UI so the user can enter credentials. Call this with the signin_id returned by get_activities or get_activity_stats when sign-in is required. The UI will receive this signin_id and use it when calling submit_dpage_signin."""
    return {
        "signin_id": signin_id,
        "ui_resource_uri": GARMIN_SIGNIN_UI_URI,
        "message": "Enter your Garmin credentials in the sign-in form.",
    }


@garmin_mcp.tool
async def get_activities() -> dict[str, Any]:
    """Get the activity history from a user's account."""
    global _signin_url

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

    result = await zen_dpage_with_action(
        "https://connect.garmin.com/modern/activities",
        action=add_activity_ids_action,
    )
    signin_id_val = result.get("signin_id")
    if signin_id_val:
        _signin_url = result.get("url") or None
        result["ui_resource_uri"] = GARMIN_SIGNIN_UI_URI
        result["system_message"] = (
            "Sign-in is required. Call show_signin_ui with the signin_id from this response so the user can sign in. "
            "After the user submits the form, you can call check_signin(signin_id) to get the result, or the result may be returned directly from submit_dpage_signin."
        )
    return result


@garmin_mcp.tool
async def get_activity_stats(activity_id: str) -> dict[str, Any]:
    """Get the stats for a specific activity."""
    global _signin_url

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

    result = await zen_dpage_with_action(
        f"https://connect.garmin.com/modern/activity/{activity_id}",
        action,
    )
    signin_id_val = result.get("signin_id")
    if signin_id_val:
        _signin_url = result.get("url") or None
        result["ui_resource_uri"] = GARMIN_SIGNIN_UI_URI
        result["system_message"] = (
            "Sign-in is required. Call show_signin_ui with the signin_id from this response so the user can sign in. "
            "After the user submits the form, you can call check_signin(signin_id) to get the result, or the result may be returned directly from submit_dpage_signin."
        )
    return result


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
