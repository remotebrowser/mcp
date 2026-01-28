import traceback
from typing import Annotated

from cyclopts import App, Parameter
from fastmcp import Client
from rich import print

app = App(help="Manual end-to-end test of the mcp server.")


@app.command(
    help="""Call an mcp tool. Examples:\n
    * python tests/manual.py call-tool
    * python tests/manual.py call-tool --tool npr_get_headlines
    * python tests/manual.py call-tool --mcp media --tool bbc_get_saved_articles
    * python tests/manual.py call-tool --token TOKEN
    """
)
async def call_tool(
    server_url: Annotated[str, Parameter(help="URL of the mcp server")] = "http://localhost:23456",
    mcp: Annotated[str, Parameter(help="name of the mcp server")] = "media",
    tool: Annotated[str, Parameter(help="name of the tool")] = "get_user_info",
    token: Annotated[str, Parameter(help="OAuth token to skip full auth flow")] | None = None,
):
    url = f"{server_url}/mcp-{mcp}"
    result = None
    error = None
    try:
        async with Client(url, auth=(token or "oauth"), timeout=180) as client:
            result = await client.call_tool_mcp(tool, {})
    except Exception:
        error = traceback.format_exc()

    msg = f"Tool call:\n  mcp server: {url}\n  tool: {tool}"
    if token:
        msg = f"{msg}\n  token: {token}"

    print(msg)
    if error:
        print("Error:")
        print(error)
    else:
        print("Result:")
        print(result)


if __name__ == "__main__":
    app()
