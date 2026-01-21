import asyncio
from typing import cast

import websockets
import zendriver as zd
from zendriver.core.connection import ProtocolException

from getgather.browser.proxy import setup_proxy
from getgather.browser.resource_blocker import blocked_domains, load_blocklists, should_be_blocked
from getgather.logs import logger
from getgather.request_info import request_info


async def install_proxy_handler(username: str, password: str, page: zd.Tab):
    """Install proxy authentication handler for the page.

    Note: This only handles authentication challenges. Request continuation
    is handled by the resource blocker in get_new_page().
    """

    async def auth_challenge_handler(event: zd.cdp.fetch.AuthRequired):
        logger.debug("Supplying proxy authentication...")
        await page.send(
            zd.cdp.fetch.continue_with_auth(
                request_id=event.request_id,
                auth_challenge_response=zd.cdp.fetch.AuthChallengeResponse(
                    response="ProvideCredentials",
                    username=username,
                    password=password,
                ),
            )
        )

    page.add_handler(zd.cdp.fetch.AuthRequired, auth_challenge_handler)  # type: ignore[arg-type]
    await page.send(zd.cdp.fetch.enable(handle_auth_requests=True))


async def wait_for_ready_state(
    page: zd.Tab,
    timeout: int = 10,
) -> bool:
    """
    Waits for the page to reach a certain ready state (interactive or complete).
    :param timeout: The maximum number of seconds to wait.
    :type timeout: int
    :raises asyncio.TimeoutError: If the timeout is reached before the ready state is reached.
    :return: True if the ready state is reached.
    :rtype: bool
    """
    loop = asyncio.get_event_loop()
    start_time = loop.time()

    while True:
        state = await page.evaluate("document.readyState")
        if state == "interactive" or state == "complete":
            return True

        if loop.time() - start_time > timeout:
            raise asyncio.TimeoutError("time ran out while waiting for load page until %s" % state)

        await asyncio.sleep(0.1)


async def zen_navigate_with_retry(page: zd.Tab, url: str, wait_for_ready: bool = True) -> zd.Tab:
    """Navigate to URL with retry logic for resilient navigation.

    Args:
        page: Zendriver tab to navigate
        url: URL to navigate to
        wait_for_ready: Whether to wait for page ready state (default True).
            Set to False for simple pages that load instantly.

    Returns:
        The page after successful navigation

    Raises:
        Exception: If navigation fails after all retries
    """
    MAX_RETRIES = 3
    FIRST_TIMEOUT = 45  # seconds, extended for first attempt
    NORMAL_TIMEOUT = 30  # seconds, for retry attempts

    last_error: Exception | None = None
    for attempt in range(MAX_RETRIES):
        timeout = FIRST_TIMEOUT if attempt == 0 else NORMAL_TIMEOUT
        try:

            async def navigate_and_wait() -> zd.Tab:
                _frame_id, _loader_id, error_text = await page.send(zd.cdp.page.navigate(url))

                # Check for navigation errors (connection refused, DNS failure, SSL errors, etc.)
                if error_text:
                    raise ConnectionError(f"Navigation failed: {error_text}")

                if not wait_for_ready:
                    return page

                # Wait for page to be interactive
                try:
                    await wait_for_ready_state(page)
                except Exception:
                    # If wait fails, that's okay - page might already be loaded
                    pass
                return page

            result = await asyncio.wait_for(navigate_and_wait(), timeout=timeout)
            return result
        except Exception as error:
            last_error = error
            if attempt < MAX_RETRIES - 1:
                logger.warning(
                    f"Navigation to {url} failed (attempt {attempt + 1}/{MAX_RETRIES}): {error}. "
                    f"Retrying in 1 second..."
                )
                await asyncio.sleep(1)
            else:
                logger.error(f"Failed to navigate to {url} after {MAX_RETRIES} attempts")

    # This should never be reached, but satisfies type checker
    raise last_error or Exception(f"Failed to navigate to {url}")


async def get_new_page(browser: zd.Browser) -> zd.Tab:
    page = await browser.get("about:blank", new_tab=True)

    if blocked_domains is None:
        await load_blocklists()

    async def handle_request(event: zd.cdp.fetch.RequestPaused) -> None:
        resource_type = event.resource_type
        request_url = event.request.url

        deny_type = resource_type in [
            zd.cdp.network.ResourceType.IMAGE,
            zd.cdp.network.ResourceType.MEDIA,
            zd.cdp.network.ResourceType.FONT,
        ]
        deny_url = await should_be_blocked(request_url)
        should_deny = deny_type or deny_url

        if not should_deny:
            try:
                await page.send(zd.cdp.fetch.continue_request(request_id=event.request_id))
            except (ProtocolException, websockets.ConnectionClosedError) as e:
                if isinstance(e, ProtocolException) and (
                    "Invalid state for continueInterceptedRequest" in str(e)
                    or "Invalid InterceptionId" in str(e)
                ):
                    logger.debug(
                        f"Request already processed or invalid interception ID: {request_url}"
                    )
                elif isinstance(e, websockets.ConnectionClosedError):
                    logger.debug(f"Page closed while continuing request: {request_url}")
                else:
                    raise
            return

        kind = "URL" if deny_url else "resource"
        logger.debug(f" DENY {kind}: {request_url}")

        try:
            await page.send(
                zd.cdp.fetch.fail_request(
                    request_id=event.request_id,
                    error_reason=zd.cdp.network.ErrorReason.BLOCKED_BY_CLIENT,
                )
            )
        except (ProtocolException, websockets.ConnectionClosedError) as e:
            if isinstance(e, ProtocolException) and (
                "Invalid state for continueInterceptedRequest" in str(e)
                or "Invalid InterceptionId" in str(e)
            ):
                logger.debug(f"Request already processed or invalid interception ID: {request_url}")
            elif isinstance(e, websockets.ConnectionClosedError):
                logger.debug(f"Page closed while blocking request: {request_url}")
            else:
                raise

    # Enable fetch domain to intercept requests. Will be overridden if proxy auth is set up.
    await page.send(zd.cdp.fetch.enable())
    page.add_handler(zd.cdp.fetch.RequestPaused, handle_request)  # type: ignore[reportUnknownMemberType]

    id = cast(str, browser.id)  # type: ignore[attr-defined]
    proxy = await setup_proxy(id, request_info.get())
    proxy_username = None
    proxy_password = None
    if proxy:
        proxy_username = proxy["username"]
        proxy_password = proxy["password"]
        if proxy_username or proxy_password:
            logger.debug("Setting up proxy authentication...")
            await install_proxy_handler(proxy_username or "", proxy_password or "", page)

    return page


async def safe_close_page(page: zd.Tab) -> None:
    """Safely close a page by disabling fetch domain first to prevent orphaned tasks.

    When page.close() is called while fetch handlers are pending, it can leave
    orphaned tasks waiting for CDP responses that will never arrive. This function
    disables the fetch domain first to clean up handlers before closing.
    """
    try:
        # Disable fetch domain to cancel pending request handlers
        await page.send(zd.cdp.fetch.disable())
        logger.debug("Fetch domain disabled before page close")
    except (ProtocolException, websockets.ConnectionClosedError) as e:
        # Page/connection already closed, which is fine
        logger.debug(f"Could not disable fetch (connection already closed): {e}")
    except Exception as e:
        # Log but don't fail - we still want to close the page
        logger.warning(f"Unexpected error disabling fetch domain: {e}")

    try:
        await page.close()
        logger.debug("Page closed successfully")
    except Exception as e:
        logger.warning(f"Error closing page: {e}")
