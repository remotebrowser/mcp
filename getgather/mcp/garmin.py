import asyncio
import os
from typing import Any

import zendriver as zd
from fastmcp.tools.tool import ToolResult
from loguru import logger

from getgather.mcp.dpage import zen_dpage_with_action
from getgather.mcp.registry import GatherMCP
from getgather.zen_actions import parse_response_json
from getgather.zen_distill import load_distillation_patterns, run_distillation_loop

garmin_mcp = GatherMCP(brand_id="garmin", name="Garmin MCP")


@garmin_mcp.tool
async def get_activities() -> ToolResult:
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
        return_ui_resource=True,
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
