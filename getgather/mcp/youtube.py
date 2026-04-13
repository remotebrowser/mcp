import json
import os
from typing import Any, cast

import zendriver as zd
from loguru import logger

from getgather.mcp.dpage import remote_zen_dpage_with_action
from getgather.mcp.registry import GatherMCP
from getgather.zen_distill import get_url

youtube_mcp = GatherMCP(brand_id="youtube", name="YouTube MCP")


def _resolve_json_path(obj: dict[str, Any] | list[Any] | None, path: str) -> Any:
    """Resolve a dot-separated path like 'a.b.0.c' through nested dicts/lists."""
    cur: Any = obj
    for key in path.split("."):
        if cur is None:
            return None
        if isinstance(cur, list):
            lst = cast(list[Any], cur)
            if key.lstrip("-").isdigit():
                idx = int(key)
                cur = lst[idx] if abs(idx) <= len(lst) else None
            else:
                return None
        elif isinstance(cur, dict):
            d = cast(dict[str, Any], cur)
            cur = d.get(key)
        else:
            return None
    return cur


def _extract_column(row: dict[str, Any], col: dict[str, Any]) -> str:
    """Extract a single column value from a row using the column schema."""
    value: Any = _resolve_json_path(row, col["path"])

    if not value and "fallback_path" in col:
        value = _resolve_json_path(row, col["fallback_path"])
        if isinstance(value, str) and "fallback_strip_prefix" in col:
            value = value.removeprefix(col["fallback_strip_prefix"])

    if isinstance(value, list) and "join" in col:
        join_key = cast(str, col["join"])
        value = "".join(
            cast(dict[str, Any], item).get(join_key, "")
            for item in cast(list[Any], value)
            if isinstance(item, dict)
        )

    if value and "prefix" in col:
        value = col["prefix"] + str(cast(Any, value))

    return value if isinstance(value, str) else (str(cast(Any, value)) if value else "")


def convert_json(data: dict[str, Any], schema: dict[str, Any]) -> list[dict[str, str]]:
    """Convert JSON data to structured records using a schema.

    Supports two modes:
    - Flat: "rows" path + optional "row_key" + "columns"
    - Sectioned: "sections" path + "renderers" with per-type columns
    """
    if "sections" in schema:
        sections = cast(list[dict[str, Any]], _resolve_json_path(data, schema["sections"]) or [])
        section_key = schema.get("section_key", "")
        columns = cast(list[dict[str, Any]], schema.get("columns", []))

        results: list[dict[str, str]] = []

        # Flat-within-sections mode: each section holds rows via section_items_path + row_key
        if "section_items_path" in schema:
            row_key = schema.get("row_key")
            for section in sections:
                container = cast(
                    dict[str, Any], section.get(section_key) if section_key else section
                )
                if not container:
                    continue
                for item in cast(
                    list[dict[str, Any]],
                    _resolve_json_path(container, schema["section_items_path"]) or [],
                ):
                    row_data = cast(dict[str, Any], item.get(row_key) if row_key else item)
                    if not row_data:
                        continue
                    entry = {col["name"]: _extract_column(row_data, col) for col in columns}
                    if entry:
                        results.append(entry)
            return results

        # Sectioned mode with headers and multiple renderer types (watch history)
        items_key = cast(str, schema.get("section_items", "contents"))
        header_cfg = cast(dict[str, Any], schema.get("section_header", {}))
        renderers = cast(list[dict[str, Any]], schema.get("renderers", []))

        for section in sections:
            container = cast(dict[str, Any], section.get(section_key) if section_key else section)
            if not container:
                continue
            header_value = cast(
                str,
                _resolve_json_path(container, header_cfg["path"]) if header_cfg.get("path") else "",
            )
            for item in cast(list[dict[str, Any]], container.get(items_key, [])):
                for renderer in renderers:
                    row_data = cast(dict[str, Any], item.get(renderer["row_key"]))
                    if not row_data:
                        continue
                    entry = {
                        col["name"]: _extract_column(row_data, col) for col in renderer["columns"]
                    }
                    if header_cfg.get("name"):
                        entry[header_cfg["name"]] = header_value or ""
                    results.append(entry)
                    break
        return results

    rows = cast(list[dict[str, Any]], _resolve_json_path(data, schema["rows"]) or [])
    row_key = schema.get("row_key")
    columns = cast(list[dict[str, Any]], schema.get("columns", []))

    results = []
    for item in rows:
        row_data = cast(dict[str, Any], item.get(row_key) if row_key else item)
        if not row_data:
            continue
        entry = {col["name"]: _extract_column(row_data, col) for col in columns}
        if entry:
            results.append(entry)
    return results


YOUTUBE_BASE = "https://www.youtube.com"
YOUTUBE_TIMEOUT_SECONDS = 15
PATTERNS_DIR = os.path.join(os.path.dirname(__file__), "patterns")


def _load_schema(filename: str) -> dict[str, Any]:
    with open(os.path.join(PATTERNS_DIR, filename)) as f:
        return json.load(f)


def _full_url(path: str) -> str:
    if path.startswith("//"):
        return "https:" + path
    if path.startswith("/"):
        return YOUTUBE_BASE + path
    return path


def _normalize_urls(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    for entry in entries:
        for field in ("url", "channel_url", "thumbnail"):
            val = entry.get(field, "")
            if val:
                entry[field] = _full_url(val)
    return entries


async def _get_yt_initial_data(page: zd.Tab) -> dict[str, Any] | None:
    current_url = await get_url(page)
    logger.info(f"Getting YouTube data from {current_url}")
    if current_url is None or "signin" in current_url or "accounts.google" in current_url:
        raise Exception("User is not signed in")
    raw = cast(Any, await page.evaluate("window.ytInitialData"))
    if raw is None:
        return None
    return cast(dict[str, Any], json.loads(raw) if isinstance(raw, str) else raw)


async def _yt_extract(url: str, result_key: str, schema_file: str) -> dict[str, Any]:
    schema = _load_schema(schema_file)

    async def action(page: zd.Tab, _: Any) -> dict[str, Any]:
        data = await _get_yt_initial_data(page)
        if data is None:
            logger.warning("ytInitialData not found on the page")
            return {result_key: []}
        entries = _normalize_urls(convert_json(data, schema))
        logger.info(f"Extracted {len(entries)} items for {result_key}")
        return {result_key: entries}

    return await remote_zen_dpage_with_action(url, action=action, timeout=YOUTUBE_TIMEOUT_SECONDS)


@youtube_mcp.tool
async def get_liked_videos() -> dict[str, Any]:
    """Get liked videos from YouTube."""
    return await _yt_extract(
        "https://www.youtube.com/playlist?list=LL",
        "youtube_liked_videos",
        "youtube-playlist-videos-script.json",
    )


@youtube_mcp.tool
async def get_watch_history() -> dict[str, Any]:
    """Get watch history from YouTube."""
    return await _yt_extract(
        "https://www.youtube.com/feed/history",
        "youtube_watch_history",
        "youtube-history-script.json",
    )


@youtube_mcp.tool
async def get_watch_later() -> dict[str, Any]:
    """Get watch later playlist from YouTube."""
    return await _yt_extract(
        "https://www.youtube.com/playlist?list=WL",
        "youtube_watch_later",
        "youtube-playlist-videos-script.json",
    )


@youtube_mcp.tool
async def get_channel_subscriptions() -> dict[str, Any]:
    """Get channel subscriptions from YouTube."""
    return await _yt_extract(
        "https://www.youtube.com/feed/channels",
        "youtube_channel_subscriptions",
        "youtube-channel-subscriptions-script.json",
    )
