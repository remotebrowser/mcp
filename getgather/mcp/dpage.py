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
from loguru import logger
from nanoid import generate

from getgather.auth.auth import get_auth_user
from getgather.browser.chromefleet import (
    create_remote_browser,
    get_remote_browser,
    terminate_remote_browser,
)
from getgather.config import settings
from getgather.mcp.browser import browser_manager, terminate_zendriver_browser
from getgather.mcp.html_renderer import DEFAULT_TITLE, render_form
from getgather.zen_distill import (
    ElementConfig,
    Match,
    autoclick as zen_autoclick,
    capture_page_artifacts as zen_capture_page_artifacts,
    check_error,
    convert,
    distill as zen_distill,
    get_new_page,
    get_selector,
    init_zendriver_browser,
    load_distillation_patterns,
    page_query_selector,
    run_distillation_loop as zen_run_distillation_loop,
    safe_close_page,
    terminate,
    wait_for_ready_state,
    zen_navigate_with_retry,
    zen_report_distill_error,
)

router = APIRouter(prefix="/dpage", tags=["dpage"])


active_pages: dict[str, zd.Tab] = {}
distillation_results: dict[str, str | list[dict[str, str | list[str]]] | dict[str, Any]] = {}
pending_actions: dict[str, dict[str, Any]] = {}
element_configs: dict[str, ElementConfig] = {}

FRIENDLY_CHARS: str = "23456789abcdefghijkmnpqrstuvwxyz"


def is_remote_browser(dpage_id: str) -> bool:
    return "--" in dpage_id


async def dpage_add(
    page: zd.Tab,
    location: str,
    profile_id: str | None = None,
    config: ElementConfig | None = None,
):
    id = generate(FRIENDLY_CHARS, 8)

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
    if config:
        element_configs[id] = config
    return id


async def dpage_close(id: str) -> None:
    if id in active_pages:
        page = active_pages[id]
        await safe_close_page(page)
        del active_pages[id]
    if id in element_configs:
        del element_configs[id]


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

    if is_remote_browser(id):
        browser_id, _ = id.split("--")
        if browser := await get_remote_browser(browser_id):
            await terminate_remote_browser(browser)
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
        elif is_remote_browser(id):
            return redirect(id)

    raise HTTPException(status_code=400, detail="Missing page id")


FINISHED_MSG = "Finished! You can close this window now."


@router.post("/{id}", response_class=HTMLResponse)
async def post_dpage(id: str, request: Request) -> HTMLResponse:
    page: zd.Tab | None = None

    if id in active_pages:
        page = active_pages[id]

    if is_remote_browser(id):
        browser_id, page_id = id.split("--")
        browser = await get_remote_browser(browser_id)
        if browser is None:
            raise HTTPException(status_code=404, detail="Remote browser not found")
        for tab in browser.tabs:
            if tab.target_id == page_id:
                page = tab
                break

    if page is None:
        raise HTTPException(status_code=404, detail="Page not found")

    return await zen_post_dpage(page, id, request)


def is_local_address(host: str) -> bool:
    hostname = host.split(":")[0].lower().strip()
    try:
        ip = ipaddress.ip_address(hostname)
        return ip.is_loopback
    except ValueError:
        return hostname in ("localhost", "127.0.0.1")


async def zen_post_dpage(page: zd.Tab, id: str, request: Request) -> HTMLResponse:
    if not is_remote_browser(id):
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

    # Force browser to complete rendering by evaluating document state
    try:
        await wait_for_ready_state(page, timeout=5)
        # Additional wait for any dynamic content/JavaScript to settle
        await page.sleep(1)
        logger.debug("Page ready state is complete")
    except Exception as e:
        logger.warning(f"Error waiting for page ready state: {e}")

    for iteration in range(max):
        logger.debug(f"Iteration {iteration + 1} of {max}")
        await asyncio.sleep(TICK)

        try:
            current_url = str(await page.evaluate("window.location.href", await_promise=True))
        except Exception:
            current_url = page.url
        hostname = str(urllib.parse.urlparse(current_url).hostname) if current_url else None
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

                resume_fn = (
                    remote_zen_dpage_with_action if is_remote_browser(id) else zen_dpage_with_action
                )
                action_result = await resume_fn(
                    initial_url=action_info["initial_url"],
                    action=action_info["action"],
                    timeout=action_info["timeout"],
                    _signin_completed=True,
                    _page_id=id,
                )

                distillation_results[id] = action_result

                del pending_actions[id]
                await dpage_close(id)
                if is_remote_browser(id):
                    await safe_close_page(page)
                return HTMLResponse(render(FINISHED_MSG, options))

            converted = await convert(distilled, pattern_path=match.name)
            await dpage_close(id)
            if is_remote_browser(id):
                await safe_close_page(page)
            if converted is not None:
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
                config = element_configs.get(id)
                element = await page_query_selector(
                    page,
                    selector if selector is not None else "",
                    iframe_selector=frame_selector,
                    config=config,
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
                            config = element_configs.get(id)
                            radio_element = await page_query_selector(
                                page,
                                selector if selector is not None else "",
                                iframe_selector=frame_selector,
                                config=config,
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


async def zen_dpage_mcp_tool(
    initial_url: str,
    result_key: str,
    timeout: int = 2,
    config: ElementConfig | None = None,
) -> dict[str, Any]:
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

    id = await dpage_add(
        page,
        initial_url,
        browser.id,  # type: ignore[attr-defined]
        config=config,
    )

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
    config: ElementConfig | None = None,
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
    if _signin_completed and _page_id is not None and _page_id in pending_actions:
        action_info = pending_actions[_page_id]
        page: zd.Tab | None = None
        if _page_id in active_pages:
            page = active_pages[_page_id]
        elif is_remote_browser(_page_id):
            browser_id, page_id = _page_id.split("--")
            browser = await get_remote_browser(browser_id)
            if browser is not None:
                for tab in browser.tabs:
                    if tab.target_id == page_id:
                        page = tab
                        break
        if page is None:
            raise ValueError(f"Page for signin {_page_id} not found")
        logger.info(f"Resuming action after signin with page_id={_page_id}")
        try:
            await zen_navigate_with_retry(page, initial_url)
        except Exception as e:
            logger.warning(f"Failed to navigate to {initial_url}: {e}")
        result = await action(page, action_info["browser"])
        del pending_actions[_page_id]
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

    id = await dpage_add(
        page,
        initial_url,
        browser_instance.id,  # type: ignore[attr-defined]
        config=config,
    )

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


async def remote_zen_dpage_mcp_tool(
    initial_url: str,
    result_key: str,
    timeout: int = 2,
    config: ElementConfig | None = None,
) -> dict[str, Any]:
    """Generic MCP tool based on distillation with remote Zendriver"""
    path = os.path.join(os.path.dirname(__file__), "patterns", "**/*.html")
    patterns = load_distillation_patterns(path)

    headers = get_http_headers(include_all=True)
    signin_id = headers.get("x-signin-id") or None
    incognito = headers.get("x-incognito", "0") == "1"

    browser = None
    page = None

    if signin_id:
        browser_id, page_id = signin_id.split("--")
        dpage_id = signin_id
        browser = await get_remote_browser(browser_id)
        if browser is None:
            raise HTTPException(status_code=400, detail="Remote browser not found")
        for tab in browser.tabs:
            if tab.target_id == page_id:
                page = tab
                break
        if page is None:
            raise HTTPException(status_code=400, detail="Page not found")
        logger.info(f"Continue with browser {browser_id} and page {page_id}")
    elif incognito:
        prefix = "E"  # for Ephemeral
        browser_id = prefix + generate(FRIENDLY_CHARS, 7)
        browser = await create_remote_browser(browser_id)
        page = await get_new_page(browser)
        dpage_id = f"{browser_id}--{page.target_id}"
        logger.info(f"Start with an ephemeral browser {browser_id}")
    else:
        user_id = get_auth_user().user_id
        browser_id: str = user_id
        browser = await get_remote_browser(browser_id)
        if browser is None:
            browser = await create_remote_browser(browser_id)
        page = await get_new_page(browser)
        dpage_id = f"{browser_id}--{page.target_id}"
        logger.info(f"For user {user_id}: using browser {browser_id}")

    logger.info(f"Navigating remote browser to {initial_url}")
    await zen_navigate_with_retry(page, initial_url)

    terminated, distilled, converted = await zen_run_distillation_loop(
        initial_url, patterns, browser, timeout, interactive=False, close_page=False, page=page
    )
    if terminated:
        await safe_close_page(page)
        distillation_result = converted if converted is not None else distilled
        return {result_key: distillation_result}

    page.hostname = urllib.parse.urlparse(initial_url).hostname  # type: ignore[attr-defined]

    headers = get_http_headers(include_all=True)
    host = headers.get("x-forwarded-host") or headers.get("host")
    if host is None:
        logger.warning("Missing Host header; defaulting to localhost")
        base_url = "http://localhost:23456"
    else:
        default_scheme = "http" if is_local_address(host) else "https"
        scheme = headers.get("x-forwarded-proto", default_scheme)
        base_url = f"{scheme}://{host}"

    url = f"{base_url}/dpage/{dpage_id}"
    logger.info(f"Continue with the sign in at {url}", extra={"url": url, "id": dpage_id})
    return {
        "url": url,
        "message": f"Continue to sign in in your browser at {url}.",
        "signin_id": dpage_id,
        "system_message": (
            f"Try open the url {url} in a browser with a tool if available."
            "Give the url to the user so the user can open it manually in their browser."
            "Then call check_signin tool with the signin_id to check if the sign in process is completed. "
            "Once it is completed successfully, then call this tool again to proceed with the action."
        ),
    }


async def remote_zen_dpage_with_action(
    initial_url: str,
    action: Any,
    timeout: int = 2,
    dpage_timeout: int = 15,
    _signin_completed: bool = False,
    _page_id: str | None = None,
    config: ElementConfig | None = None,
) -> dict[str, Any]:
    """Execute an action after signin completion with remote Zendriver."""
    headers = get_http_headers(include_all=True)
    signin_id = headers.get("x-signin-id") or None
    incognito = headers.get("x-incognito", "0") == "1"

    # Step 1: Resuming after signin completion (same as zen_dpage_with_action; supports remote id)
    if _signin_completed and _page_id is not None and _page_id in pending_actions:
        action_info = pending_actions[_page_id]
        page = None
        if is_remote_browser(_page_id):
            browser_id, page_id = _page_id.split("--")
            browser = await get_remote_browser(browser_id)
            if browser is not None:
                for tab in browser.tabs:
                    if tab.target_id == page_id:
                        page = tab
                        break
        if page is None:
            raise ValueError(f"Page for signin {_page_id} not found")
        logger.info(f"Resuming remote action after signin with page_id={_page_id}")
        try:
            await zen_navigate_with_retry(page, initial_url)
        except Exception as e:
            logger.warning(f"Failed to navigate to {initial_url}: {e}")
        result = await action(page, action_info["browser"])
        del pending_actions[_page_id]
        return result

    # Step 2: Try with existing remote session (no sign-in flow)
    browser = None
    page = None
    if signin_id and is_remote_browser(signin_id):
        browser_id, page_id = signin_id.split("--")
        browser = await get_remote_browser(browser_id)
        if browser is not None:
            for tab in browser.tabs:
                if tab.target_id == page_id:
                    page = tab
                    break
    elif not incognito:
        user_id = get_auth_user().user_id
        browser = await get_remote_browser(user_id)
        if browser is not None:
            page = await get_new_page(browser)

    if browser is not None and page is not None:
        created_new_page = not (signin_id and is_remote_browser(signin_id))
        try:
            logger.info("Trying remote action with existing session...")
            await zen_navigate_with_retry(page, initial_url)
            result = await action(page, browser)
            if created_new_page:
                await safe_close_page(page)
            logger.info("Remote action succeeded with existing session!")
            return result
        except Exception as e:
            logger.info(
                f"remote_zen_dpage_with_action failed with existing session (likely not signed in): {e}"
            )
            if created_new_page:
                await safe_close_page(page)

    # Step 3: Create interactive sign-in flow with pending action
    if signin_id and is_remote_browser(signin_id):
        browser_id, page_id = signin_id.split("--")
        dpage_id = signin_id
        browser = await get_remote_browser(browser_id)
        if browser is None:
            raise HTTPException(status_code=400, detail="Remote browser not found")
        for tab in browser.tabs:
            if tab.target_id == page_id:
                page = tab
                break
        if page is None:
            raise HTTPException(status_code=400, detail="Page not found")
        logger.info(f"Continue with remote browser {browser_id} and page {page_id}")
    elif incognito:
        prefix = "E"
        browser_id = prefix + generate(FRIENDLY_CHARS, 7)
        browser = await create_remote_browser(browser_id)
        page = await get_new_page(browser)
        dpage_id = f"{browser_id}--{page.target_id}"
        logger.info(f"Start with ephemeral remote browser {browser_id}")
    else:
        user_id = get_auth_user().user_id
        browser_id = user_id
        browser = await get_remote_browser(browser_id)
        if browser is None:
            browser = await create_remote_browser(browser_id)
        page = await get_new_page(browser)
        dpage_id = f"{browser_id}--{page.target_id}"
        logger.info(f"For user {user_id}: using remote browser {browser_id}")

    await zen_navigate_with_retry(page, initial_url)
    page.hostname = urllib.parse.urlparse(initial_url).hostname  # type: ignore[attr-defined]

    pending_actions[dpage_id] = {
        "action": action,
        "initial_url": initial_url,
        "timeout": timeout,
        "page_id": dpage_id,
        "browser": browser,
        "dpage_timeout": dpage_timeout,
    }

    host = headers.get("x-forwarded-host") or headers.get("host")
    if host is None:
        logger.warning("Missing Host header; defaulting to localhost")
        base_url = "http://localhost:23456"
    else:
        default_scheme = "http" if is_local_address(host) else "https"
        scheme = headers.get("x-forwarded-proto", default_scheme)
        base_url = f"{scheme}://{host}"

    url = f"{base_url}/dpage/{dpage_id}"
    logger.info(
        f"remote_zen_dpage_with_action: Continue with sign in at {url}",
        extra={"url": url, "id": dpage_id},
    )
    return {
        "url": url,
        "message": f"Continue to sign in in your browser at {url}.",
        "signin_id": dpage_id,
        "system_message": (
            f"Try open the url {url} in a browser with a tool if available. "
            "Give the url to the user so the user can open it manually in their browser. "
            "Then call check_signin tool with the signin_id to check if the sign in process is completed. "
        ),
    }
