import asyncio
from collections.abc import Awaitable, Callable
from typing import TypeVar

import zendriver as zd
from loguru import logger

T = TypeVar("T")


async def retry_with_navigation(
    tab: zd.Tab,
    operation: Callable[[], Awaitable[T]],
    navigation_url: str | None = None,
    max_retries: int = 3,
    timeout_seconds: float | None = None,
    exceptions: tuple[type[Exception], ...] = (Exception,),
    default_on_max_retries: T | None = None,
    re_raise_on_max_retries: bool = False,
    operation_name: str = "operation",
) -> T:
    """
    Retry an async operation with optional navigation before each attempt.

    Args:
        tab: The zendriver Tab instance
        operation: The async operation to retry (should be a coroutine function that takes no args)
                   The operation should handle setting up expect_response listeners if needed.
                   Note: If using expect_response, set it up INSIDE the operation, then trigger
                   navigation/action. The retry function will navigate BEFORE calling operation,
                   so if you need expect_response to catch a response triggered by navigation,
                   you may need to handle navigation inside the operation instead.
        navigation_url: Optional URL to navigate to before each retry attempt
        max_retries: Maximum number of retry attempts (default: 3)
        timeout_seconds: Optional timeout for the operation (uses asyncio.wait_for)
        exceptions: Tuple of exception types to catch and retry on (default: Exception)
        default_on_max_retries: Default value to return if max retries reached and re_raise_on_max_retries is False
        re_raise_on_max_retries: If True, re-raise the exception on max retries instead of returning default
        operation_name: Name of the operation for logging purposes

    Returns:
        The result of the operation, or default_on_max_retries if max retries reached

    Raises:
        The last exception if re_raise_on_max_retries is True and max retries reached
    """
    from getgather.browser import zen_navigate_with_retry

    for attempt in range(1, max_retries + 1):
        logger.info(f"{operation_name} attempt {attempt}/{max_retries}")

        try:
            # Navigate before each attempt if URL is provided
            # Note: For expect_response patterns, you may need to navigate INSIDE the operation
            # to ensure the listener is set up before navigation triggers the response
            if navigation_url:
                await zen_navigate_with_retry(tab, navigation_url, wait_for_ready=False)

            # Execute the operation with optional timeout
            if timeout_seconds is not None:
                result = await asyncio.wait_for(operation(), timeout=timeout_seconds)
            else:
                result = await operation()

            logger.info(f"Successfully completed {operation_name}.")
            return result

        except exceptions as e:
            error_type = type(e).__name__
            logger.warning(
                f"{operation_name} attempt {attempt}/{max_retries} failed with {error_type}: {e}"
            )

            if attempt == max_retries:
                logger.error(f"Max retries reached for {operation_name}.")
                if re_raise_on_max_retries:
                    raise
                if default_on_max_retries is not None:
                    return default_on_max_retries
                # If no default provided and not re-raising, return empty result based on type
                # This shouldn't happen in practice, but provides a fallback
                raise ValueError(
                    f"Max retries reached for {operation_name} and no default value or re-raise specified"
                )

            logger.info(f"Retrying {operation_name}...")

    # This should never be reached, but type checker needs it
    if default_on_max_retries is not None:
        return default_on_max_retries
    raise RuntimeError(f"Unexpected end of retry loop for {operation_name}")
