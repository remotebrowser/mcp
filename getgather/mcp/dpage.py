import asyncio
import ipaddress
import os
import urllib.parse
from typing import Any

import zendriver as zd
from bs4 import BeautifulSoup, Tag
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastmcp.server.dependencies import get_http_headers
from nanoid import generate

from getgather.config import settings
from getgather.distill import (
    Match,
    check_error,
    convert,
    get_selector,
    terminate,
)
from getgather.logs import logger
from getgather.mcp.browser import browser_manager, terminate_zendriver_browser
from getgather.mcp.html_renderer import DEFAULT_TITLE, render_form
from getgather.zen_distill import (
    autoclick as zen_autoclick,
    capture_page_artifacts as zen_capture_page_artifacts,
    distill as zen_distill,
    get_new_page,
    init_zendriver_browser,
    load_distillation_patterns,
    page_query_selector,
    run_distillation_loop as zen_run_distillation_loop,
    safe_close_page,
    zen_navigate_with_retry,
    zen_report_distill_error,
)

router = APIRouter(prefix="/dpage", tags=["dpage"])


active_pages: dict[str, zd.Tab] = {}
distillation_results: dict[str, str | list[dict[str, str | list[str]]] | dict[str, Any]] = {}
pending_actions: dict[str, dict[str, Any]] = {}

FRIENDLY_CHARS: str = "23456789abcdefghijkmnpqrstuvwxyz"


async def dpage_add(page: zd.Tab, location: str, profile_id: str | None = None):
    id = generate(FRIENDLY_CHARS, 8)
    if settings.HOSTNAME:
        id = f"{settings.HOSTNAME}-{id}"

    try:
        if not location.startswith("http"):
            location = f"https://{location}"
        await zen_navigate_with_retry(page, location)
    except Exception as error:
        hostname = urllib.parse.urlparse(location).hostname or "unknown"
        await zen_report_distill_error(
            error=error,
            page=page,
            profile_id=profile_id or "unknown",
            location=location,
            hostname=hostname,
            iteration=0,
        )
    active_pages[id] = page
    return id


async def dpage_close(id: str) -> None:
    if id in active_pages:
        page = active_pages[id]
        await safe_close_page(page)
        del active_pages[id]


async def dpage_check(id: str):
    TICK = 1  # seconds
    TIMEOUT = 120  # seconds
    max = TIMEOUT // TICK

    for iteration in range(max):
        logger.debug(f"Checking dpage {id}: {iteration + 1} of {max}")
        await asyncio.sleep(TICK)

        # Check if signin completed
        if id in distillation_results:
            return distillation_results[id]

    return None


async def dpage_finalize(id: str):
    if browser := browser_manager.get_incognito_browser(id):
        await terminate_zendriver_browser(browser)
        browser_manager.remove_incognito_browser(id)
        return True
    raise ValueError(f"Browser profile for signin {id} not found in incognito browser profiles")


def render(content: str, options: dict[str, str] | None = None) -> str:
    """Render HTML template with content and options."""
    if options is None:
        options = {}

    title = options.get("title", DEFAULT_TITLE)
    action = options.get("action", "")

    return render_form(content, title, action)


# Since the browser can't redirect from GET to POST,
# we'll use an auto-submit form to do that.
def redirect(id: str) -> HTMLResponse:
    return HTMLResponse(f"""
    <!DOCTYPE html>
    <html>
    <body>
      <form id="redirect" action="/dpage/{id}" method="post">
      </form>
      <script>document.getElementById('redirect').submit();</script>
    </body>
    </html>
    """)


@router.get("", response_class=HTMLResponse)
@router.get("/{id}", response_class=HTMLResponse)
async def get_dpage(id: str | None = None) -> HTMLResponse:
    if id:
        if id in active_pages:
            return redirect(id)
        raise HTTPException(status_code=404, detail="Invalid page id")

    raise HTTPException(status_code=400, detail="Missing page id")


FINISHED_MSG = "Finished! You can close this window now."


@router.post("/{id}", response_class=HTMLResponse)
async def post_dpage(id: str, request: Request) -> HTMLResponse:
    if id not in active_pages:
        raise HTTPException(status_code=404, detail="Page not found")

    page = active_pages[id]
    return await zen_post_dpage(page, id, request)


def is_local_address(host: str) -> bool:
    hostname = host.split(":")[0].lower().strip()
    try:
        ip = ipaddress.ip_address(hostname)
        return ip.is_loopback
    except ValueError:
        return hostname in ("localhost", "127.0.0.1")


async def zen_post_dpage(page: zd.Tab, id: str, request: Request) -> HTMLResponse:
    browser_manager.update_last_active(id)
    form_data = await request.form()
    fields: dict[str, str] = {k: str(v) for k, v in form_data.items()}

    path = os.path.join(os.path.dirname(__file__), "patterns", "**/*.html")
    patterns = load_distillation_patterns(path)

    logger.info(f"Continuing distillation for page {id}...")
    logger.debug(f"Available distillation patterns: {len(patterns)}")

    TICK = 1  # seconds
    TIMEOUT = pending_actions.get(id, {}).get("dpage_timeout", 15)  # seconds
    max = TIMEOUT // TICK

    current = Match(name="", priority=-1, distilled="")

    if settings.LOG_LEVEL == "DEBUG":
        await zen_capture_page_artifacts(page, identifier=id, prefix="dpage_debug")

    for iteration in range(max):
        logger.debug(f"Iteration {iteration + 1} of {max}")
        await asyncio.sleep(TICK)

        hostname = str(urllib.parse.urlparse(page.url).hostname) if page.url else None

        match = await zen_distill(hostname, page, patterns)
        if not match:
            logger.info("No matched pattern found")
            continue

        distilled = match.distilled
        document = BeautifulSoup(distilled, "html.parser")

        title_element = BeautifulSoup(distilled, "html.parser").find("title")
        title = title_element.get_text() if title_element is not None else DEFAULT_TITLE
        action = f"/dpage/{id}"
        options = {"title": title, "action": action}
        inputs = document.find_all("input")

        if match.distilled == current.distilled:
            logger.info(f"Still the same: {match.name}")
            has_inputs = len(inputs) > 0
            max_reached = iteration == max - 1
            if max_reached and has_inputs:
                logger.info("Still the same after timeout and need inputs, render the page...")
                return HTMLResponse(render(str(document.find("body")), options))
            continue

        current = match

        if await terminate(distilled):
            logger.info("Finished!")

            error = await check_error(distilled)

            if id in pending_actions and not error:
                action_info = pending_actions[id]
                logger.info(f"Signin completed for {id}, resuming action...")

                action_result = await zen_dpage_with_action(
                    initial_url=action_info["initial_url"],
                    action=action_info["action"],
                    timeout=action_info["timeout"],
                    _signin_completed=True,
                    _page_id=id,
                )

                distillation_results[id] = action_result

                del pending_actions[id]
                await dpage_close(id)
                return HTMLResponse(render(FINISHED_MSG, options))

            converted = await convert(distilled)
            await dpage_close(id)
            if converted is not None:
                print(converted)
                distillation_results[id] = converted
            else:
                logger.info("No conversion found")
                distillation_results[id] = distilled
            return HTMLResponse(render(FINISHED_MSG, options))

        names: list[str] = []

        if fields.get("button"):
            button = document.find("button", value=str(fields.get("button")))
            if button:
                logger.info(f"Clicking button button[value={fields.get('button')}]")
                await zen_autoclick(page, distilled, f"button[value={fields.get('button')}]")
                continue

        for input in inputs:
            if isinstance(input, Tag):
                gg_match = input.get("gg-match")
                selector, frame_selector = get_selector(
                    str(gg_match) if gg_match is not None else ""
                )
                element = await page_query_selector(
                    page, selector if selector is not None else "", iframe_selector=frame_selector
                )
                name = input.get("name")
                input_type = input.get("type")

                if element:
                    if input_type == "checkbox":
                        if not name:
                            logger.warning(f"No name for the checkbox {gg_match}")
                            continue
                        value = fields.get(str(name))
                        checked = value and len(str(value)) > 0
                        names.append(str(name))
                        logger.info(f"Status of checkbox {name}={checked}")
                        current_checked_value = (
                            element.element.get("checked") or element.element.get("value") == "true"
                        )
                        if current_checked_value != checked:
                            logger.info(f"Clicking checkbox {name} to set it to {checked}")
                            await element.click()
                    elif input_type == "radio":
                        if name is not None:
                            name_str = str(name)
                            value = fields.get(name_str)
                            if not value or len(value) == 0:
                                logger.warning(f"No form data found for radio button group {name}")
                                continue
                            radio = document.find("input", {"type": "radio", "value": str(value)})
                            if not radio or not isinstance(radio, Tag):
                                logger.warning(f"No radio button found with value {value}")
                                continue
                            logger.info(f"Handling radio button group {name}")
                            logger.info(f"Using form data {name}={value}")
                            radio_gg_match = str(radio.get("gg-match"))
                            selector, frame_selector = get_selector(radio_gg_match)
                            radio_element = await page_query_selector(
                                page,
                                selector if selector is not None else "",
                                iframe_selector=frame_selector,
                            )
                            if radio_element:
                                await radio_element.click()
                                radio["checked"] = "checked"
                                current.distilled = str(document)
                                names.append(str(input.get("id")) if input.get("id") else "radio")
                    elif name is not None:
                        name_str = str(name)
                        value = fields.get(name_str)
                        if value and len(value) > 0:
                            logger.info(f"Using form data {name}")
                            names.append(name_str)
                            input["value"] = value
                            current.distilled = str(document)
                            await element.type_text(value)
                            del fields[name_str]
                        else:
                            logger.info(f"No form data found for {name}")

        await zen_autoclick(page, distilled, "[gg-autoclick]:not(button)")
        SUBMIT_BUTTON = "button[gg-autoclick], button[type=submit]"
        if document.select(SUBMIT_BUTTON):
            if len(names) > 0 and len(inputs) == len(names):
                logger.info("Submitting form, all fields are filled...")
                await zen_autoclick(page, distilled, SUBMIT_BUTTON)
                continue
            logger.warning("Not all form fields are filled")
            return HTMLResponse(render(str(document.find("body")), options))

    hostname_attr: str | None = getattr(page, "hostname", None)  # type: ignore[assignment]
    location = getattr(page, "url", "unknown")  # type: ignore[assignment]
    timeout_error = TimeoutError("Timeout reached in zen_post_dpage")
    await zen_report_distill_error(
        error=timeout_error,
        page=page,
        profile_id=id,
        location=location,
        hostname=hostname_attr or "unknown",
        iteration=max,
    )
    raise HTTPException(status_code=503, detail="Timeout reached")


async def zen_dpage_mcp_tool(initial_url: str, result_key: str, timeout: int = 2) -> dict[str, Any]:
    """Generic MCP tool based on distillation with Zendriver"""
    path = os.path.join(os.path.dirname(__file__), "patterns", "**/*.html")
    patterns = load_distillation_patterns(path)

    headers = get_http_headers(include_all=True)
    incognito = headers.get("x-incognito", "0") == "1"
    signin_id = headers.get("x-signin-id") or None

    if incognito:
        browser = await init_zendriver_browser(signin_id)
    else:
        browser = browser_manager.get_global_browser()
        if browser is None:
            logger.info("Creating global browser for Zendriver...")
            browser = await init_zendriver_browser()
            browser_manager.set_global_browser(browser)
            await get_new_page(browser)
            logger.info(f"Global browser created with id {browser.id}")  # type: ignore[attr-defined]

    if not incognito or signin_id is not None:
        # First, try without any interaction as this will work if the user signed in previously
        terminated, distilled, converted = await zen_run_distillation_loop(
            initial_url, patterns, browser, timeout, interactive=False
        )
        if terminated:
            distillation_result = converted if converted is not None else distilled
            return {result_key: distillation_result}

    page = await get_new_page(browser)
    page.hostname = urllib.parse.urlparse(initial_url).hostname  # type: ignore[attr-defined]

    id = await dpage_add(page, initial_url, browser.id)  # type: ignore[attr-defined]

    if incognito:
        browser_manager.set_incognito_browser(id, browser)

    host = headers.get("x-forwarded-host") or headers.get("host")
    if host is None:
        logger.warning("Missing Host header; defaulting to localhost")
        base_url = "http://localhost:23456"
    else:
        default_scheme = "http" if is_local_address(host) else "https"
        scheme = headers.get("x-forwarded-proto", default_scheme)
        base_url = f"{scheme}://{host}"

    url = f"{base_url}/dpage/{id}"
    logger.info(f"Continue with the sign in at {url}", extra={"url": url, "id": id})
    return {
        "url": url,
        "message": f"Continue to sign in in your browser at {url}.",
        "signin_id": id,
        "system_message": (
            f"Try open the url {url} in a browser with a tool if available."
            "Give the url to the user so the user can open it manually in their browser."
            "Then call check_signin tool with the signin_id to check if the sign in process is completed. "
            "Once it is completed successfully, then call this tool again to proceed with the action."
        ),
    }


async def zen_dpage_with_action(
    initial_url: str,
    action: Any,
    timeout: int = 2,
    dpage_timeout: int = 15,
    _signin_completed: bool = False,
    _page_id: str | None = None,
) -> dict[str, Any]:
    """Execute an action after signin completion with Zendriver.

    Args:
        initial_url: URL to navigate to
        action: Async function that receives a Page and returns a dict
        timeout: Timeout in seconds
        _signin_completed: Whether the signin process is completed
        _page_id: ID of the page to resume from
    Returns:
        Dict with result or signin flow info
    """
    headers = get_http_headers(include_all=True)
    incognito = headers.get("x-incognito", "0") == "1"
    signin_id = headers.get("x-signin-id") or None

    # Step 1: If resuming after signin completion, use the active page directly
    if _signin_completed and _page_id is not None and _page_id in active_pages:
        logger.info(f"Resuming action after signin with page_id={_page_id}")
        page = active_pages[_page_id]
        action_info = pending_actions[_page_id]

        try:
            await zen_navigate_with_retry(page, initial_url)
        except Exception as e:
            logger.warning(f"Failed to navigate to {initial_url}: {e}")

        result = await action(page, action_info["browser"])
        return result

    # Step 2: If global_browser_profile exists, try executing action directly
    # This will work if user signed in previously and session is still valid
    global_browser = browser_manager.get_global_browser()
    if (global_browser and not incognito) or signin_id:
        if global_browser and not incognito:
            browser = global_browser
        else:
            browser = await init_zendriver_browser(signin_id)

        try:
            logger.info("Trying action with existing global browser session...")
            page = await get_new_page(browser)
            await zen_navigate_with_retry(page, initial_url)
            result = await action(page, browser)
            await safe_close_page(page)
            logger.info("Action succeeded with existing session!")
            return result
        except Exception as e:
            logger.info(
                f"zen_dpage_with_action failed with existing session (likely not signed in): {e}"
            )

    # Step 3: User not signed in - create interactive signin flow with action
    browser_instance: zd.Browser
    if incognito:
        browser_instance = await init_zendriver_browser(signin_id)
    else:
        if browser_manager.get_global_browser() is None:
            logger.info("Creating global browser for Zendriver signin flow...")
            global_browser = await init_zendriver_browser()
            browser_manager.set_global_browser(global_browser)
            await get_new_page(global_browser)
        browser_instance = browser_manager.get_global_browser()  # type: ignore

    page = await get_new_page(browser_instance)
    page.hostname = urllib.parse.urlparse(initial_url).hostname  # type: ignore

    id = await dpage_add(page, initial_url, browser_instance.id)  # type: ignore

    # Store action for auto-resumption after signin
    pending_actions[id] = {
        "action": action,
        "initial_url": initial_url,
        "timeout": timeout,
        "page_id": id,
        "browser": browser_instance,
        "dpage_timeout": dpage_timeout,
    }

    if incognito:
        browser_manager.set_incognito_browser(id, browser_instance)

    host = headers.get("x-forwarded-host") or headers.get("host")
    if host is None:
        logger.warning("Missing Host header; defaulting to localhost")
        base_url = "http://localhost:23456"
    else:
        default_scheme = "http" if is_local_address(host) else "https"
        scheme = headers.get("x-forwarded-proto", default_scheme)
        base_url = f"{scheme}://{host}"

    url = f"{base_url}/dpage/{id}"
    logger.info(
        f"zen_dpage_with_action: Continue with sign in at {url}", extra={"url": url, "id": id}
    )

    message = "Continue to sign in in your browser"

    return {
        "url": url,
        "message": f"{message} at {url}.",
        "signin_id": id,
        "system_message": (
            f"Try open the url {url} in a browser with a tool if available."
            "Give the url to the user so the user can open it manually in their browser."
            f"Then call check_signin tool with the signin_id to check if the sign in process is completed. "
        ),
    }
