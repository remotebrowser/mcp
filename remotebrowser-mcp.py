import os
import sys

frozen = getattr(sys, "frozen", False)
if frozen:
    os.environ["PYDANTIC_DISABLE_PLUGINS"] = "1"

import uvicorn

from getgather.main import app

if __name__ == "__main__":
    port = int(os.getenv("PORT", 23456))
    uvicorn.run(
        app if frozen else "getgather.main:app", host="127.0.0.1", port=port, reload=not frozen
    )
