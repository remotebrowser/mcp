import asyncio
import json
import os
import re
import urllib.parse
from dataclasses import dataclass
from datetime import datetime
from glob import glob
from pathlib import Path
from typing import Any, cast

import pwinput
import sentry_sdk
from bs4 import BeautifulSoup
from bs4.element import Tag
from nanoid import generate
from patchright.async_api import Locator, Page

from getgather.browser.profile import BrowserProfile
from getgather.browser.session import browser_session
from getgather.config import settings
from getgather.logs import logger


@dataclass
class Pattern:
    name: str
    pattern: BeautifulSoup


@dataclass
class Match:
    name: str
    priority: int
    distilled: str


ConversionResult = list[dict[str, str | list[str]]]

NETWORK_ERROR_PATTERNS = (
    "err-timed-out",
    "err-ssl-protocol-error",
    "err-tunnel-connection-failed",
    "err-proxy-connection-failed",
    "err-service-unavailable",
)


def _safe_fragment(value: str) -> str:
    fragment = re.sub(r"[^a-zA-Z0-9_-]+", "-", value).strip("-")
    return fragment or "distill"


async def capture_page_artifacts(
    page: Page,
    *,
    identifier: str,
    prefix: str,
    capture_html: bool = True,
) -> tuple[Path, Path | None, str | None]:
    """Capture a screenshot (and optional HTML) for debugging/triage."""

    settings.screenshots_dir.mkdir(parents=True, exist_ok=True)

    base_identifier = _safe_fragment(identifier)
    base_prefix = _safe_fragment(prefix)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    token = generate(size=5)
    filename = f"{base_identifier}_{base_prefix}_{timestamp}_{token}.png"
    screenshot_path = settings.screenshots_dir / filename

    await page.screenshot(path=str(screenshot_path), full_page=True)

    html_path: Path | None = None
    html_content: str | None = None
    if capture_html:
        try:
            html_content = await page.content()
        except Exception as exc:  # ignore navigation races during capture
            logger.debug(f"⚠️ Can't capture page content during navigation: {exc}")
        else:
            html_path = screenshot_path.with_suffix(".html")
            html_path.write_text(html_content, encoding="utf-8")

    logger.debug(
        "📸 Distill artifact saved",
        extra={
            "screenshot": f"file://{screenshot_path}",
            "html": f"file://{html_path}" if html_path else None,
        },
    )

    return screenshot_path, html_path, html_content


async def report_distill_error(
    *,
    error: Exception,
    page: Page | None,
    profile_id: str,
    location: str,
    hostname: str,
    iteration: int,
) -> None:
    screenshot_path: Path | None = None
    html_path: Path | None = None

    if page:
        try:
            screenshot_path, html_path, _ = await capture_page_artifacts(
                page,
                identifier=profile_id,
                prefix="distill_error",
            )
        except Exception as capture_error:
            logger.warning(f"Failed to capture distillation artifacts: {capture_error}")

    context: dict[str, Any] = {
        "location": location,
        "hostname": hostname,
        "iteration": iteration,
    }

    logger.error(
        "Distillation error",
        extra={
            "profile_id": profile_id,
            "location": location,
            "iteration": iteration,
            "screenshot": f"file://{screenshot_path}" if screenshot_path else None,
        },
    )

    if settings.SENTRY_DSN:
        with sentry_sdk.isolation_scope() as scope:
            scope.set_context("distill", context)
            if screenshot_path:
                scope.add_attachment(
                    filename=screenshot_path.name,
                    path=str(screenshot_path),
                )
            if html_path:
                scope.add_attachment(
                    filename=html_path.name,
                    path=str(html_path),
                )

            sentry_sdk.capture_exception(error)


def get_selector(input_selector: str | None) -> tuple[str | None, str | None]:
    pattern = r"^(iframe(?:[^\s]*\[[^\]]+\]|[^\s]+))\s+(.+)$"
    if not input_selector:
        return None, None
    match = re.match(pattern, input_selector)
    if not match:
        return input_selector, None
    return match.group(2), match.group(1)


def extract_value(item: Tag, attribute: str | None = None) -> str:
    if attribute:
        value = item.get(attribute)
        if isinstance(value, list):
            value = value[0] if value else ""
        return value.strip() if isinstance(value, str) else ""
    return item.get_text(strip=True)


async def convert(distilled: str):
    document = BeautifulSoup(distilled, "html.parser")
    snippet = document.find("script", {"type": "application/json"})
    if snippet:
        logger.info(f"Found a data converter.")
        logger.info(snippet.get_text())
        try:
            converter = json.loads(snippet.get_text())
            logger.info(f"Start converting using {converter}")

            rows = document.select(str(converter.get("rows", "")))
            logger.info(f"Found {len(rows)} rows")
            converted: ConversionResult = []
            for _, el in enumerate(rows):
                kv: dict[str, str | list[str]] = {}
                for col in converter.get("columns", []):
                    name = col.get("name")
                    selector = col.get("selector")
                    attribute = col.get("attribute")
                    kind = col.get("kind")
                    if not name or not selector:
                        continue

                    if kind == "list":
                        items = el.select(str(selector))
                        kv[name] = [extract_value(item, attribute) for item in items]
                        continue

                    item = el.select_one(str(selector))
                    if item:
                        kv[name] = extract_value(item, attribute)
                if len(kv.keys()) > 0:
                    converted.append(kv)
            logger.info(f"Conversion done for {len(converted)} entries.")
            return converted
        except Exception as error:
            logger.error(f"Conversion error: {str(error)}")


async def ask(message: str, mask: str | None = None) -> str:
    if mask:
        return pwinput.pwinput(f"{message}: ", mask=mask)
    else:
        return input(f"{message}: ")


async def autofill(page: Page, distilled: str):
    document = BeautifulSoup(distilled, "html.parser")
    root = document.find("html")
    domain = None
    if root:
        domain = cast(Tag, root).get("gg-domain")

    processed: list[str] = []

    for element in document.find_all("input", {"type": True}):
        if not isinstance(element, Tag):
            continue

        input_type = element.get("type")
        name = element.get("name")

        if not name or (isinstance(name, str) and len(name) == 0):
            logger.warning(f"There is an input (of type {input_type}) without a name!")

        selector, frame_selector = get_selector(str(element.get("gg-match", "")))
        if not selector:
            logger.warning(f"There is an input (of type {input_type}) without a selector!")
            continue

        if input_type in ["email", "tel", "text", "password"]:
            field = name or input_type
            logger.debug(f"Autofilling type={input_type} name={name}...")

            source = f"{domain}_{field}" if domain else field
            key = str(source).upper()
            value = os.getenv(key)

            if value and len(value) > 0:
                logger.info(f"Using {key} for {field}")
                if frame_selector:
                    await page.frame_locator(str(frame_selector)).locator(str(selector)).fill(value)
                else:
                    await page.fill(str(selector), value)
                element["value"] = value
            else:
                placeholder = element.get("placeholder")
                prompt = str(placeholder) if placeholder else f"Please enter {field}"
                mask = "*" if input_type == "password" else None
                user_input = await ask(prompt, mask)
                if frame_selector:
                    await (
                        page.frame_locator(str(frame_selector))
                        .locator(str(selector))
                        .fill(user_input)
                    )
                else:
                    await page.fill(str(selector), user_input)
                element["value"] = user_input
            await asyncio.sleep(0.25)
        elif input_type == "radio":
            if not name:
                logger.warning(f"There is no name for radio button with id {element.get('id')}!")
                continue
            if name in processed:
                continue
            processed.append(str(name))

            choices: list[dict[str, str]] = []
            print()
            radio_buttons = document.find_all("input", {"type": "radio"})
            for button in radio_buttons:
                if not isinstance(button, Tag):
                    continue
                if button.get("name") != name:
                    continue
                button_id = button.get("id")
                label_element = (
                    document.find("label", {"for": str(button_id)}) if button_id else None
                )
                label = label_element.get_text() if label_element else None
                choice_id = str(button_id) if button_id else ""
                choice_label = label or str(button_id) if button_id else ""
                choices.append({"id": choice_id, "label": choice_label})
                print(f" {len(choices)}. {choice_label}")

            choice = 0
            while choice < 1 or choice > len(choices):
                answer = await ask(f"Your choice (1-{len(choices)})")
                try:
                    choice = int(answer)
                except ValueError:
                    choice = 0

            logger.info(f"Choosing {choices[choice - 1]['label']}")
            print()

            selected_choice = choices[choice - 1]
            radio = document.find("input", {"type": "radio", "id": selected_choice["id"]})
            if radio and isinstance(radio, Tag):
                selector, frame_selector = get_selector(str(radio.get("gg-match")))
                if frame_selector:
                    await page.frame_locator(str(frame_selector)).locator(str(selector)).check()
                else:
                    await page.check(str(selector))

        elif input_type == "checkbox":
            checked = element.get("checked")
            if checked is not None:
                logger.info(f"Checking {name}")
                if frame_selector:
                    await page.frame_locator(str(frame_selector)).locator(str(selector)).check()
                else:
                    await page.check(str(selector))

    return str(document)


async def locate(locator: Locator) -> Locator | None:
    count = await locator.count()
    if count > 0:
        for i in range(count):
            try:
                el = locator.nth(i)
                if await el.is_visible():
                    return el
            except Exception:
                logger.info("Element may have disappeared or selector can't be queried")
                continue
    return None


async def click(
    page: Page, selector: str, timeout: int = 3000, frame_selector: str | None = None
) -> None:
    LOCATOR_ALL_TIMEOUT = 100
    if frame_selector:
        locator = page.frame_locator(str(frame_selector)).locator(str(selector))
    else:
        locator = page.locator(str(selector))
    try:
        elements = await locator.all()
        logger.debug(f'Found {len(elements)} elements for selector "{selector}"')
        for element in elements:
            logger.debug(f"Checking {element}")
            if await element.is_visible():
                logger.debug(f"Clicking on {element}")
                try:
                    await element.click()
                    return
                except Exception as err:
                    logger.warning(f"Failed to click on {selector} {element}: {err}")
    except Exception as e:
        if timeout > 0 and "TimeoutError" in str(type(e)):
            logger.warning(f"retrying click {selector} {timeout}")
            await click(page, selector, timeout - LOCATOR_ALL_TIMEOUT, frame_selector)
            return
        logger.error(f"Failed to click on {selector}: {e}")
        raise e


async def autoclick(page: Page, distilled: str, expr: str):
    document = BeautifulSoup(distilled, "html.parser")
    elements = document.select(expr)
    for el in elements:
        selector, frame_selector = get_selector(str(el.get("gg-match")))
        if selector:
            logger.info(f"Clicking {selector}")
            await click(page, str(selector), frame_selector=frame_selector)


async def terminate(distilled: str) -> bool:
    document = BeautifulSoup(distilled, "html.parser")
    stops = document.find_all(attrs={"gg-stop": True})
    if len(stops) > 0:
        logger.info("Found stop elements, terminating session...")
        return True
    return False


async def check_error(distilled: str) -> bool:
    document = BeautifulSoup(distilled, "html.parser")
    errors = document.find_all(attrs={"gg-error": True})
    if len(errors) > 0:
        logger.info("Found error elements...")
        return True
    return False


def load_distillation_patterns(path: str) -> list[Pattern]:
    patterns: list[Pattern] = []
    for name in glob(path, recursive=True):
        with open(name, "r", encoding="utf-8") as f:
            content = f.read()
        patterns.append(Pattern(name=name, pattern=BeautifulSoup(content, "html.parser")))
    return patterns


async def distill(
    hostname: str | None,
    page: Page,
    patterns: list[Pattern],
    reload_on_error: bool = True,
    profile_id: str | None = None,
) -> Match | None:
    result: list[Match] = []

    for item in patterns:
        name = item.name
        pattern = item.pattern

        root = pattern.find("html")
        gg_priority = root.get("gg-priority", "-1") if isinstance(root, Tag) else "-1"
        try:
            priority = int(str(gg_priority).lstrip("= "))
        except ValueError:
            priority = -1
        domain = root.get("gg-domain") if isinstance(root, Tag) else None

        if domain and hostname:
            local = "localhost" in hostname or "127.0.0.1" in hostname
            if isinstance(domain, str) and not local and domain.lower() not in hostname.lower():
                logger.debug(f"Skipping {name} due to mismatched domain {domain}")
                continue

        logger.debug(f"Checking {name} with priority {priority}")

        found = True
        match_count = 0

        targets = pattern.find_all(attrs={"gg-match": True}) + pattern.find_all(
            attrs={"gg-match-html": True}
        )

        for target in targets:
            if not isinstance(target, Tag):
                continue

            if not found:
                break

            html = target.get("gg-match-html")
            selector, frame_selector = get_selector(str(html if html else target.get("gg-match")))

            if not selector:
                continue

            if frame_selector:
                source = await locate(page.frame_locator(str(frame_selector)).locator(selector))
            else:
                source = await locate(page.locator(selector))

            if source:
                match_count += 1
                if html:
                    target.clear()
                    fragment = BeautifulSoup(
                        "<div>" + await source.inner_html() + "</div>", "html.parser"
                    )
                    if fragment.div:
                        for child in list(fragment.div.children):
                            child.extract()
                            target.append(child)
                else:
                    raw_text = await source.text_content()
                    if raw_text:
                        target.string = raw_text.strip()

                    tag = await source.evaluate("el => el.tagName.toLowerCase()")
                    if tag in ["input", "textarea", "select"]:
                        try:
                            input_value = await source.input_value()
                        except Exception as e:
                            logger.warning(f"Failed to get input value for {selector}: {e}")
                            input_value = ""
                            await report_distill_error(
                                error=e,
                                page=page,
                                profile_id=profile_id or "",
                                location=page.url,
                                hostname=hostname or "",
                                iteration=0,
                            )
                        target["value"] = input_value
            else:
                optional = target.get("gg-optional") is not None
                logger.debug(f"Optional {selector} has no match")
                if not optional:
                    found = False

        if found and match_count > 0:
            distilled = str(pattern)
            result.append(
                Match(
                    name=name,
                    priority=priority,
                    distilled=distilled,
                )
            )

    result = sorted(result, key=lambda x: x.priority)

    if len(result) == 0:
        logger.debug("No matches found")
        return None
    else:
        logger.debug(f"Number of matches: {len(result)}")
        for item in result:
            logger.debug(f" - {item.name} with priority {item.priority}")
        match = result[0]
        logger.info(f"✓ Best match: {match.name}")

        if reload_on_error and any(pattern in match.name for pattern in NETWORK_ERROR_PATTERNS):
            logger.info(f"Error pattern detected: {match.name}")
            await page.reload(timeout=settings.BROWSER_TIMEOUT, wait_until="domcontentloaded")
            logger.info("Retrying distillation after error...")
            return await distill(hostname, page, patterns, reload_on_error=False)
        return match


async def run_distillation_loop(
    location: str,
    patterns: list[Pattern],
    browser_profile: BrowserProfile | None = None,
    timeout: int = 15,
    interactive: bool = True,
    stop_ok: bool = False,
    close_page: bool = False,
    page: Page | None = None,
) -> tuple[bool, str, ConversionResult | None]:
    """Run the distillation loop.

    Returns:
        terminated: bool indicating successful termination
        distilled: the raw distilled HTML
        converted: the converted JSON if successful, otherwise None
    """
    if len(patterns) == 0:
        logger.error("No distillation patterns provided")
        raise ValueError("No distillation patterns provided")

    hostname = urllib.parse.urlparse(location).hostname or ""

    # Use provided profile or create new one
    profile = browser_profile or BrowserProfile()

    async with browser_session(profile, stop_ok=stop_ok) as session:
        page = page or await session.new_page()

        logger.info(f"Starting browser {profile.id}")
        logger.info(f"Navigating to {location}")
        try:
            await page.goto(location, timeout=settings.BROWSER_TIMEOUT)
        except Exception as error:
            logger.error(f"Failed to navigate to {location}: {error}")
            await report_distill_error(
                error=error,
                page=page,
                profile_id=profile.id,
                location=location,
                hostname=hostname,
                iteration=0,
            )
            raise ValueError(f"Failed to navigate to {location}: {error}")

        if settings.LOG_LEVEL == "DEBUG":
            await capture_page_artifacts(
                page,
                identifier=profile.id,
                prefix="distill_debug",
            )

        TICK = 1  # seconds
        max = timeout // TICK

        current = Match(name="", priority=-1, distilled="")

        for iteration in range(max):
            logger.info("")
            logger.info(f"Iteration {iteration + 1} of {max}")
            await asyncio.sleep(TICK)

            match = await distill(hostname, page, patterns)
            if match:
                if match.distilled == current.distilled:
                    logger.debug(f"Still the same: {match.name}")
                else:
                    distilled = match.distilled
                    current = match

                    if await terminate(distilled):
                        converted = await convert(distilled)
                        if close_page:
                            await page.close()
                        return (True, distilled, converted)

                    if interactive:
                        distilled = await autofill(page, distilled)
                        await autoclick(page, distilled, "[gg-autoclick]:not(button)")
                        await autoclick(
                            page, distilled, "button[gg-autoclick], button[type=submit]"
                        )

                    current.distilled = distilled

            else:
                logger.debug(f"No matched pattern found")

        await report_distill_error(
            error=ValueError("No matched pattern found"),
            page=page,
            profile_id=profile.id,
            location=location,
            hostname=hostname,
            iteration=max,
        )
        await page.close()
        return (False, current.distilled, None)
