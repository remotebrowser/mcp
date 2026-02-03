from dataclasses import dataclass
from typing import ClassVar

from fastmcp import Context, FastMCP
from loguru import logger


MCP_APP_HTML_MIME_TYPE = "text/html;profile=mcp-app"


@dataclass
class AppUIConfig:
    """Optional MCP Apps (MCP UI) config for a brand.

    When set, the brand can expose interactive HTML UIs to MCP hosts.
    Use resource_uri for the ui:// URI (e.g. ui://garmin/activities).
    Use template_path for the path to the HTML file to serve, or template_content for inline HTML.
    Use csp_resource_domains to allow external script domains (e.g. https://unpkg.com) in the UI.
    """

    resource_uri: str
    template_path: str | None = None
    template_content: str | None = None
    mime_type: str = MCP_APP_HTML_MIME_TYPE
    csp_resource_domains: list[str] | None = None

    def tool_meta(self) -> dict[str, str | dict[str, str]]:
        """Return meta for tool registration (MCP Apps spec).

        Attach to tools via @server.tool(meta=app_ui.tool_meta()).
        Includes resourceUri and legacy ui/resourceUri for host compatibility.
        """
        return {
            "ui": {"resourceUri": self.resource_uri},
            "ui/resourceUri": self.resource_uri,
        }

    def resource_meta(self) -> dict[str, dict[str, dict[str, list[str]]]]:
        """Return meta for resource registration (MCP Apps spec).

        Pass to FastMCP resource (e.g. mime_type + meta) when serving the UI HTML.
        Includes CSP resourceDomains when csp_resource_domains is set.
        """
        meta: dict[str, dict[str, dict[str, list[str]]]] = {"ui": {}}
        if self.csp_resource_domains:
            meta["ui"]["csp"] = {"resourceDomains": self.csp_resource_domains}
        return meta

    def ui_meta(self) -> dict[str, str | dict[str, str]]:
        """Alias for tool_meta() for backward compatibility."""
        return self.tool_meta()


class GatherMCP(FastMCP[Context]):
    registry: ClassVar[dict[str, "GatherMCP"]] = {}

    def __init__(
        self,
        *,
        brand_id: str,
        name: str,
        app_ui: AppUIConfig | None = None,
    ) -> None:
        super().__init__(name=name)  # type: ignore[reportUnknownMemberType]
        self.brand_id = brand_id
        self.app_ui = app_ui
        GatherMCP.registry[self.brand_id] = self
        logger.debug(f"Registered GatherMCP with brand_id '{brand_id}' and name '{name}'")
