"""
The interface for configuring a proxy with location.
"""

from typing import Any

from pydantic import BaseModel


class Location(BaseModel):
    """Location information for proxy configuration.

    Typically comes from x-location-info or x-location headers.

    NOTE: for Shabrina, this is just a ported example. May not have everything we want.
    """

    country: str | None = None
    state: str | None = None
    city: str | None = None
    city_compacted: str | None = None
    postal_code: str | None = None

    def model_post_init(self, __context: Any) -> None:
        """Compute city_compacted from city."""
        if self.city and not self.city_compacted:
            # Remove dashes, underscores, and spaces
            self.city_compacted = (
                self.city.lower().replace("-", "").replace("_", "").replace(" ", "")
            )

    def to_template_values(self) -> dict[str, Any]:
        """Convert to dict for template replacement.

        Returns normalized values suitable for template placeholders.
        """
        values: dict[str, Any] = {}

        if self.country:
            values["country"] = self.country.lower()
            # Only include state for US requests
            if self.state and self.country.lower() == "us":
                values["state"] = self.state.lower().replace(" ", "_")

        if self.city:
            values["city"] = self.city.lower().replace(" ", "_")
            if self.city_compacted:
                values["city_compacted"] = self.city_compacted

        if self.postal_code:
            values["postal_code"] = self.postal_code

        return values


async def configure_proxy(location: Location, server_id: str) -> str | None:
    """Configure a proxy based on location and server ID.
    If the the proxy is unable to be configured with a valid location, returns None.
    Assumes a valid server_id that is in the fleet and will raise otherwise.
    """
    return server_id  # Placeholder implementation
