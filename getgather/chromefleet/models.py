"""Pydantic models for ChromeFleet proxy configuration.

This module contains models for:
- Location: Validated and normalized location data
- HierarchyLevel: Configuration for location fallback hierarchy
- ChromeFleetContainer: Response from ChromeFleet container start
- ConfiguredProxy: Final result with CDP URL
- ProxyValidationResult: Validation outcome
"""

from typing import Any, Literal, TypeAlias

from loguru import logger
from pydantic import BaseModel, IPvAnyAddress, field_validator, model_validator

logger = logger.bind(topic="chromefleet")

# Location defaults for fallback
DEFAULT_COUNTRY = "us"
DEFAULT_STATE = "california"

# Valid US states for proxy targeting (plain state names, underscore-separated)
VALID_US_STATES: set[str] = {
    "alabama",
    "alaska",
    "arizona",
    "arkansas",
    "california",
    "colorado",
    "connecticut",
    "delaware",
    "florida",
    "georgia",
    "hawaii",
    "idaho",
    "illinois",
    "indiana",
    "iowa",
    "kansas",
    "kentucky",
    "louisiana",
    "maine",
    "maryland",
    "massachusetts",
    "michigan",
    "minnesota",
    "mississippi",
    "missouri",
    "montana",
    "nebraska",
    "nevada",
    "new_hampshire",
    "new_jersey",
    "new_mexico",
    "new_york",
    "north_carolina",
    "north_dakota",
    "ohio",
    "oklahoma",
    "oregon",
    "pennsylvania",
    "rhode_island",
    "south_carolina",
    "south_dakota",
    "tennessee",
    "texas",
    "utah",
    "vermont",
    "virginia",
    "washington",
    "west_virginia",
    "wisconsin",
    "wyoming",
}

LocationFieldName: TypeAlias = Literal["city", "state", "postal_code"]


class Location(BaseModel):
    """Location information for proxy configuration.

    Automatically validates and normalizes location data on construction.

    Validation rules:
    - Country: Must be 2-char ISO code and alphabetic, normalized to lowercase
    - State: Normalized to lowercase with underscores, validated against US states for US
    - Non-US countries: postal_code and state are stripped (not supported by most providers)
    - Invalid country: Falls back to DEFAULT_COUNTRY/DEFAULT_STATE
    """

    country: str | None = None
    state: str | None = None
    city: str | None = None
    city_compacted: str | None = None
    postal_code: str | None = None

    @model_validator(mode="before")
    @classmethod
    def validate_and_normalize(cls, data: Any) -> dict[str, str | None]:
        """Validate and normalize location data before model construction."""
        if not isinstance(data, dict):
            return {"country": DEFAULT_COUNTRY, "state": DEFAULT_STATE}

        d: dict[str, Any] = dict(data)  # type: ignore[arg-type]
        raw_country: str | None = d.get("country")
        raw_state: str | None = d.get("state")
        raw_city = d.get("city")
        raw_postal_code = d.get("postal_code")

        country: str = (str(raw_country) if raw_country else "").lower().strip()
        state: str = (str(raw_state) if raw_state else "").lower().strip().replace(" ", "_")
        city: str | None = str(raw_city) if raw_city else None
        postal_code: str | None = str(raw_postal_code) if raw_postal_code else None

        # Validate country: must be 2-char alphabetic ISO code
        if not country or len(country) != 2 or not country.isalpha():
            if raw_country:  # Only log if there was an invalid value
                logger.warning(
                    "Invalid country code, using default",
                    original_country=raw_country,
                    default_country=DEFAULT_COUNTRY,
                    default_state=DEFAULT_STATE,
                )
            return {
                "country": DEFAULT_COUNTRY,
                "state": DEFAULT_STATE,
                "city": None,
                "postal_code": None,
            }

        # For non-US countries, strip postal_code and state (not widely supported)
        if country != "us":
            if postal_code:
                logger.debug(
                    "Removing postal_code for non-US country",
                    country=country,
                    postal_code=postal_code,
                )
                postal_code = None
            if state:
                logger.debug(
                    "Removing state for non-US country",
                    country=country,
                    state=state,
                )
                state = ""

        # Validate US state
        if country == "us" and state:
            if state not in VALID_US_STATES:
                logger.warning(
                    "Invalid US state, removing from location",
                    original_state=raw_state,
                    valid_states_sample=list(VALID_US_STATES)[:5],
                )
                state = ""

        # Compute city_compacted: remove dashes, underscores, and spaces
        city_compacted: str | None = None
        if city:
            city_compacted = city.lower().replace("-", "").replace("_", "").replace(" ", "")

        return {
            "country": country,
            "state": state if state else None,
            "city": city,
            "city_compacted": city_compacted,
            "postal_code": postal_code,
        }

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


class HierarchyLevel(BaseModel):
    """A single level in the location hierarchy.

    Each level specifies which location fields to include together.
    """

    fields: list[LocationFieldName]

    @field_validator("fields")
    @classmethod
    def validate_fields_not_empty(cls, v: list[LocationFieldName]) -> list[LocationFieldName]:
        """Ensure fields list is not empty."""
        if not v:
            raise ValueError("fields cannot be empty")
        return v


class ChromeFleetContainer(BaseModel):
    """Response from ChromeFleet container start.

    Attributes:
        machine_id: Unique identifier for the container
        ip_address: IP address of the container
        cdp_url: Chrome DevTools Protocol URL for browser automation
    """

    machine_id: str
    ip_address: str
    cdp_url: str


class ConfiguredProxy(BaseModel):
    """Result of successful proxy configuration.

    Attributes:
        cdp_url: Ready-to-use CDP endpoint
        machine_id: ChromeFleet container ID
        validated_ip: External IP address obtained through proxy
        location: Location that was successfully configured
    """

    cdp_url: str
    machine_id: str
    validated_ip: IPvAnyAddress
    location: Location


class ProxyValidationResult(BaseModel):
    """Result of proxy validation.

    Attributes:
        success: Whether validation succeeded
        ip_address: The validated IP address (None if validation failed)
        error: Error message if validation failed (None if succeeded)
        is_location_error: True if failure was location-specific (should try next level)
    """

    success: bool
    ip_address: IPvAnyAddress | None = None
    error: str | None = None
    is_location_error: bool = False
