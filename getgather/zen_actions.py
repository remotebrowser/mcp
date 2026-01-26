import json
from typing import Any, TypeVar

from loguru import logger

T = TypeVar("T", list[dict[str, Any]], dict[str, Any])


async def parse_response_json(
    resp: Any,
    default: T,
    context: str = "response",
) -> T:
    """Parse JSON from a zendriver expect_response context.

    Args:
        resp: The response context from tab.expect_response()
        default: Default value to return on parse failure ([] or {})
        context: Description for logging (e.g., "cart", "order history")

    Returns:
        Parsed JSON data or default value on failure
    """
    response_event = await resp.value
    logger.info(
        f"Received {context} response: {response_event.response.status} "
        f"{response_event.response.url}"
    )

    body, _ = await resp.response_body
    try:
        result: T = json.loads(body)
        return result
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse {context} JSON response: {e}")
        return default
