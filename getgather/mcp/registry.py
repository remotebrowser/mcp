from typing import ClassVar

from fastmcp import Context, FastMCP
from loguru import logger

from getgather.mcp.ui import ToolUI, ui_to_meta_dict


class GatherMCP(FastMCP[Context]):
    registry: ClassVar[dict[str, "GatherMCP"]] = {}

    def __init__(
        self,
        *,
        brand_id: str,
        name: str,
        app_ui: ToolUI | None = None,
    ) -> None:
        super().__init__(name=name)  # type: ignore[reportUnknownMemberType]
        self.brand_id = brand_id
        self.app_ui = app_ui
        GatherMCP.registry[self.brand_id] = self
        logger.debug(f"Registered GatherMCP with brand_id '{brand_id}' and name '{name}'")

    def app_ui_tool_meta(self) -> dict[str, dict[str, str]]:
        """Return meta for tool registration (MCP Apps spec).

        Attach to tools via @server.tool(meta=server.app_ui_tool_meta()).
        Returns the ui_to_meta_dict format for the registered ToolUI.
        """
        if self.app_ui:
            return {"ui": ui_to_meta_dict(self.app_ui)}
        return {}
