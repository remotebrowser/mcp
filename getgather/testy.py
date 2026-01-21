import asyncio
import time
import urllib.parse
from typing import cast
from urllib.parse import ParseResult

import httpx
import nanoid
import zendriver as zd

FRIENDLY_CHARS = "23456789abcdefghijkmnpqrstuvwxyz"

browser_args = [
    "--start-maximized",
    "--no-dbus",  # avoids chromium probing real DBus sockets inside the container which are not needed
    "--proxy-server=http://127.0.0.1:8119",
]
CHROMEFLEET_URL = "http://100.78.7.128"


async def wait_for_cdp(host: str, port: int, timeout_s: float = 30.0) -> None:
    url = f"http://{host}:{port}/json/list"
    deadline = asyncio.get_event_loop().time() + timeout_s
    async with httpx.AsyncClient() as client:
        while asyncio.get_event_loop().time() < deadline:
            try:
                r = await client.get(url, timeout=2.0)
                if r.status_code == 200:
                    print("CDP is ready")
                    return
                print(f"CDP not ready, status code: {r.status_code}")
            except Exception as r:
                print(f"CDP not ready, exception occurred: {r}")
                pass
            await asyncio.sleep(0.25)
    raise TimeoutError(f"CDP not ready at {url} after {timeout_s}s")


async def main():
    browser_id = "BID-TEST-" + nanoid.generate(FRIENDLY_CHARS, 6)
    url = f"{CHROMEFLEET_URL}/api/v1/start/{browser_id}"

    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.get(url)
        response.raise_for_status()
        data = response.json()

    cdp_url = data["cdp_url"]
    ip_address = data.get("ip_address")
    parsed = cast(ParseResult, urllib.parse.urlparse(cdp_url))
    host: str = str(parsed.hostname) if parsed.hostname else "localhost"
    port: int = int(parsed.port) if parsed.port else 9222
    print(f"PORT: {port} HOST: {host}, port type: {type(port)} host type: {type(host)}")
    t = time.time()
    await wait_for_cdp(host=host, port=port)
    print(f"CDP ready after {time.time() - t:.2f}s")
    browser = await zd.Browser.create(
        host=host, port=port, sandbox=False, browser_args=browser_args
    )
    page = await browser.get("about:blank")
    await page.send(zd.cdp.page.navigate("http://example.com"))


if __name__ == "__main__":
    asyncio.run(main())
