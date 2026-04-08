import asyncio
import os
from typing import Any

import zendriver as zd
from loguru import logger

from getgather.mcp.dpage import remote_zen_dpage_with_action
from getgather.mcp.registry import GatherMCP
from getgather.zen_distill import (
    load_distillation_patterns,
    parse_response_json,
    run_distillation_loop,
)

GARMIN_TIMEOUT_SECONDS = 15

garmin_mcp = GatherMCP(brand_id="garmin", name="Garmin MCP")


async def _garmin_add_activity_ids_action(tab: zd.Tab, browser: zd.Browser) -> dict[str, Any]:
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


def _make_activity_stats_action(aid: str):
    async def action(tab: zd.Tab, _: Any) -> dict[str, Any]:
        try:

            async def get_stats():
                async with tab.expect_response(f".*activity-service/activity/{aid}.*") as resp:
                    data = await parse_response_json(resp, {}, "garmin activity stats")
                return data

            data = await asyncio.wait_for(get_stats(), timeout=30)
            return {"garmin_activity_stats": data}
        except asyncio.TimeoutError:
            logger.error(
                f"Timeout waiting for activity stats API response for activity {aid}. "
                "The API request may not have been triggered or the endpoint pattern doesn't match."
            )
            return {"garmin_activity_stats": {}}

    return action


@garmin_mcp.tool
async def get_activities() -> dict[str, Any]:
    """Get the activity history from a user's account."""
    return await remote_zen_dpage_with_action(
        "https://connect.garmin.com/modern/activities",
        action=_garmin_add_activity_ids_action,
        timeout=GARMIN_TIMEOUT_SECONDS,
    )


@garmin_mcp.tool
async def get_activity_stats(activity_id: str) -> dict[str, Any]:
    """Get the stats for a specific activity."""
    return await remote_zen_dpage_with_action(
        f"https://connect.garmin.com/modern/activity/{activity_id}",
        _make_activity_stats_action(activity_id),
        timeout=GARMIN_TIMEOUT_SECONDS,
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
