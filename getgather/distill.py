import json
import re
from dataclasses import dataclass
from glob import glob

from bs4 import BeautifulSoup
from bs4.element import Tag

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
