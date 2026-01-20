from pathlib import Path
from urllib.parse import urlparse

import aiofiles

from getgather.config import PROJECT_DIR
from getgather.logs import logger

blocked_domains: frozenset[str] | None = None
allowed_domains: frozenset[str] = frozenset(["amazon.ca", "wayfair.com"])


def _get_domain_variants(domain: str) -> list[str]:
    parts = domain.split(".")
    variants: list[str] = []
    for i in range(len(parts) - 1):
        if len(parts) - i >= 2:
            variants.append(".".join(parts[i:]))
    return variants


async def _load_blocklist_from_file(path: Path) -> frozenset[str]:
    logger.debug(f"Loading blocked domains from {path}...")
    async with aiofiles.open(path, "r") as f:
        lines = await f.readlines()
        domains = frozenset(line.strip() for line in lines if line.strip())
        logger.debug(f"Loaded {len(domains)} domains from {path}")
        return domains


def _extract_domain(url: str) -> str:
    try:
        parsed = urlparse(url)
        return parsed.netloc.lower()
    except Exception:
        return ""


async def load_blocklists() -> None:
    global blocked_domains
    logger.info("Loading blocklists...")
    all_domains: set[str] = set()

    blocklist_files = list(PROJECT_DIR.glob("blocklists-*.txt"))
    if blocklist_files:
        for blocklist_file in blocklist_files:
            logger.debug(f"Loading blocklist file: {blocklist_file.name}")
            domains = await _load_blocklist_from_file(blocklist_file)
            all_domains.update(domains)

        filtered_domains = all_domains - allowed_domains
        blocked_domains = frozenset(filtered_domains)
    else:
        logger.warning("No blocklist files found matching pattern 'blocklists-*.txt'")
        blocked_domains = frozenset()

    logger.info(f"Blocklists loaded: {len(blocked_domains)} total domains")


async def should_be_blocked(url: str) -> bool:
    domain = _extract_domain(url)
    if not domain:
        return False

    if blocked_domains is None:
        return False

    for variant in _get_domain_variants(domain):
        if variant in blocked_domains:
            return True

    return False
