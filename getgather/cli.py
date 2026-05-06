import os
import sys

frozen = getattr(sys, "frozen", False)
if frozen:
    os.environ["PYDANTIC_DISABLE_PLUGINS"] = "1"

import uvicorn

from getgather.main import app


def main():
    port = int(os.getenv("PORT", 23456))
    uvicorn.run(
        app if frozen else "getgather.main:app",
        host="127.0.0.1",
        port=port,
        reload=not frozen,
    )
