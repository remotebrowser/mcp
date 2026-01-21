import json
import re
from dataclasses import dataclass
from glob import glob
from pathlib import Path
from typing import Any, cast

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
    """Extract text or attribute value from a BeautifulSoup Tag."""
    if attribute:
        value = item.get(attribute)
        if isinstance(value, list):
            value = value[0] if value else ""
        return value.strip() if isinstance(value, str) else ""
    return item.get_text(strip=True)


def _load_converter_from_file(json_path: Path) -> dict[str, Any] | None:
    """Load converter configuration from a JSON file."""
    if not json_path.exists():
        return None

    try:
        with open(json_path, "r", encoding="utf-8") as f:
            return cast(dict[str, Any], json.load(f))
    except Exception as error:
        logger.warning(f"Failed to load converter from {json_path}: {error}")
        return None


async def convert(distilled: str, pattern_path: str | None = None):
    """Convert distilled HTML to structured data using converter configuration.

    The function tries to load the converter in this order (first match wins):
    1. Embedded JSON in script tag content (backward compatible with old pattern files)
    2. External JSON file specified by script tag's src attribute (if pattern_path provided)

    Args:
        distilled: The distilled HTML string
        pattern_path: Optional path to the pattern HTML file. If provided, will look for
                      external JSON file from script src attribute after checking embedded JSON.

    Returns:
        ConversionResult: List of dictionaries containing converted data, or None if conversion fails
    """
    document = BeautifulSoup(distilled, "html.parser")
    converter = None
    snippet = document.find("script", {"type": "application/json"})

    # First, try extracting from HTML script tag content (old method, backward compatible)
    if snippet:
        script_content = snippet.get_text().strip()
        if script_content:
            logger.info("Found converter in HTML script tag")
            try:
                converter = json.loads(script_content)
            except Exception as error:
                logger.error(f"Failed to parse converter from HTML: {error}")
                return None

    # Fall back to loading converter from external JSON file if src attribute is specified
    if converter is None and pattern_path and snippet and isinstance(snippet, Tag):
        src_attr = snippet.get("src")
        if isinstance(src_attr, str) and src_attr:
            pattern_dir = Path(pattern_path).parent
            json_path = pattern_dir / src_attr
            logger.info(f"Loading converter from explicit src: {json_path}")
            converter = _load_converter_from_file(json_path)
            if converter:
                logger.info(f"Loaded converter from {json_path}")

    if converter is None:
        logger.debug("No converter found")
        return None

    # Perform conversion
    try:
        rows_selector = converter.get("rows", "")
        if not isinstance(rows_selector, str) or not rows_selector:
            logger.warning("Converter missing 'rows' selector")
            return None

        raw_columns = converter.get("columns", [])
        if not isinstance(raw_columns, list):
            logger.warning("Converter 'columns' must be a list")
            return None
        columns = cast(list[dict[str, Any]], raw_columns)

        logger.info(f"Converting using converter with {len(columns)} columns")
        rows = document.select(str(rows_selector))
        logger.info(f"Found {len(rows)} rows")

        converted: ConversionResult = []
        for el in rows:
            kv: dict[str, str | list[str]] = {}
            for col_dict in columns:
                name = col_dict.get("name")
                selector = col_dict.get("selector")
                if not name or not selector:
                    continue

                attribute = col_dict.get("attribute")
                kind = col_dict.get("kind")

                if kind == "list":
                    items = el.select(str(selector))
                    kv[name] = [extract_value(item, attribute) for item in items]
                else:
                    item = el.select_one(str(selector))
                    if item:
                        kv[name] = extract_value(item, attribute)

            if kv:
                converted.append(kv)

        logger.info(f"Conversion done: {len(converted)} entries")
        return converted
    except Exception as error:
        logger.error(f"Conversion error: {error}")
        return None


async def terminate(distilled: str) -> bool:
    """Check if distillation should terminate based on gg-stop attributes."""
    document = BeautifulSoup(distilled, "html.parser")
    stops = document.find_all(attrs={"gg-stop": True})
    if stops:
        logger.info("Found stop elements, terminating session...")
        return True
    return False


async def check_error(distilled: str) -> bool:
    """Check if distillation found error elements with gg-error attributes."""
    document = BeautifulSoup(distilled, "html.parser")
    errors = document.find_all(attrs={"gg-error": True})
    if errors:
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
