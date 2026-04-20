import json
import os
from typing import Any, cast
from urllib.parse import unquote

import zendriver as zd
from loguru import logger

from getgather.browser import get_url
from getgather.mcp.dpage import remote_zen_dpage_with_action
from getgather.mcp.registry import GatherMCP

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
                cur = (
                    lst[idx]
                    if (idx >= 0 and idx < len(lst)) or (idx < 0 and abs(idx) <= len(lst))
                    else None
                )
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

    if isinstance(value, list) and ("join" in col or "join_path" in col):
        join_key = cast(str | None, col.get("join"))
        join_path = cast(str | None, col.get("join_path"))
        join_separator = cast(str, col.get("join_separator", ""))
        parts: list[str] = []
        for item in cast(list[Any], value):
            if not isinstance(item, dict):
                continue
            item_dict = cast(dict[str, Any], item)
            part = (
                _resolve_json_path(item_dict, join_path)
                if join_path
                else item_dict.get(join_key or "", "")
            )
            if part:
                parts.append(str(part))
        value = join_separator.join(parts)

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


def _extract_continuation_token(sections: list[dict[str, Any]]) -> str | None:
    """Return the next-page token from the trailing continuationItemRenderer, if present."""
    if not sections:
        return None
    last = sections[-1]
    cont = last.get("continuationItemRenderer")
    if not cont:
        return None
    return cast(
        "str | None",
        _resolve_json_path(cont, "continuationEndpoint.continuationCommand.token"),
    )


@youtube_mcp.tool
async def get_liked_videos() -> dict[str, Any]:
    """Get liked videos from YouTube."""
    return await _yt_extract(
        "https://www.youtube.com/playlist?list=LL",
        "youtube_liked_videos",
        "youtube-liked-videos-script.json",
    )


@youtube_mcp.tool
async def get_watch_history(token: str | None = None) -> dict[str, Any]:
    """Get watch history from YouTube.

    Returns youtube_watch_history (list of videos) and next_page_token.
    Pass next_page_token from a previous response to retrieve the next page.
    """
    schema = _load_schema("youtube-history-script.json")
    # Tokens extracted from ytInitialData are URL-encoded (%3D → =); decode before sending
    token_json = json.dumps(unquote(token) if token else token)

    async def action(page: zd.Tab, _: Any) -> dict[str, Any]:
        if token:
            raw = cast(
                Any,
                await page.evaluate(
                    "(async () => {"
                    "  const sapisid = document.cookie.split(';').map(c => c.trim()).find(c => c.startsWith('SAPISID='))?.split('=')[1];"
                    "  const ts = Math.floor(Date.now() / 1000);"
                    "  const msg = new TextEncoder().encode(`${ts} ${sapisid} https://www.youtube.com`);"
                    "  const hash = await crypto.subtle.digest('SHA-1', msg);"
                    "  const hashHex = Array.from(new Uint8Array(hash)).map(b => b.toString(16).padStart(2,'0')).join('');"
                    "  const auth = `SAPISIDHASH ${ts}_${hashHex}`;"
                    "  return fetch('https://www.youtube.com/youtubei/v1/browse?prettyPrint=false', {"
                    "    method: 'POST',"
                    "    headers: {"
                    "      'content-type': 'application/json',"
                    "      'x-youtube-client-name': '1',"
                    "      'x-youtube-client-version': '2.20260413.01.00',"
                    "      'authorization': auth,"
                    "      'x-origin': 'https://www.youtube.com',"
                    "    },"
                    f"    body: JSON.stringify({{context: {{client: {{clientName: 'WEB', clientVersion: '2.20260413.01.00'}}}}, continuation: {token_json}}})"
                    "  }).then(r => r.json());"
                    "})()",
                    await_promise=True,
                ),
            )
            raw_dict: dict[str, Any] = raw if isinstance(raw, dict) else {}  # type: ignore[assignment]
            sections = cast(
                list[dict[str, Any]],
                _resolve_json_path(
                    raw_dict,
                    "onResponseReceivedActions.0.appendContinuationItemsAction.continuationItems",
                )
                or [],
            )
        else:
            data = await _get_yt_initial_data(page)
            if data is None:
                logger.warning("ytInitialData not found on the page")
                return {"youtube_watch_history": [], "next_page_token": None}
            sections = cast(
                list[dict[str, Any]],
                _resolve_json_path(data, schema["sections"]) or [],
            )

        next_token = _extract_continuation_token(sections)
        video_sections = sections[:-1] if next_token else sections

        # convert_json expects data + a "sections" path; wrap the pre-resolved list
        entries = _normalize_urls(
            convert_json({"_s": video_sections}, {**schema, "sections": "_s"})
        )
        logger.info(
            f"Extracted {len(entries)} items for youtube_watch_history (token={'yes' if token else 'no'})"
        )
        return {"youtube_watch_history": entries, "next_page_token": next_token}

    return await remote_zen_dpage_with_action(
        "https://www.youtube.com/feed/history",
        action=action,
        timeout=YOUTUBE_TIMEOUT_SECONDS,
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
