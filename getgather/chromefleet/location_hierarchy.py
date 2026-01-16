"""Config-driven location hierarchy builder for proxy fallback.

This module builds location hierarchies based on configuration, allowing
flexible fallback strategies for different proxy providers.

The hierarchy is controlled by the `hierarchy_levels` config option, which
specifies each level as a list of fields to include together.
"""

from enum import Enum

from loguru import logger

from getgather.chromefleet.models import HierarchyLevel, Location

logger = logger.bind(topic="chromefleet_hierarchy")


class LocationField(str, Enum):
    """Valid location fields for hierarchy configuration.

    These correspond to fields in the Location model that can be used
    for proxy geo-targeting.
    """

    POSTAL_CODE = "postal_code"
    CITY = "city"
    STATE = "state"

    @classmethod
    def is_valid(cls, value: str) -> bool:
        """Check if a string is a valid location field."""
        return value in {f.value for f in cls}


# Default hierarchy if not specified in config
DEFAULT_HIERARCHY_LEVELS: list[HierarchyLevel] = [
    HierarchyLevel(fields=["postal_code"]),
    HierarchyLevel(fields=["city"]),
    HierarchyLevel(fields=["state"]),
]


def build_location_hierarchy(
    location: Location,
    hierarchy_levels: list[HierarchyLevel] | None = None,
) -> list[Location]:
    """Build location hierarchy based on config-driven level specification.

    Each HierarchyLevel specifies which fields to include together at that level.
    Country is always included automatically.

    Args:
        location: Location with country, state, city, postal_code fields
        hierarchy_levels: List of HierarchyLevel objects defining fallback order.
            Each level specifies which fields to combine.
            None: Uses DEFAULT_HIERARCHY_LEVELS

    Returns:
        List of Location objects ordered from most to least specific,
        always ending with country-only fallback.

    Examples:
        >>> # Mutually exclusive fallback
        >>> loc = Location(country="us", state="california", city="los_angeles")
        >>> levels = [HierarchyLevel(fields=["city"]), HierarchyLevel(fields=["state"])]
        >>> hierarchy = build_location_hierarchy(loc, levels)
        >>> # Level 1: Location(country="us", city="los_angeles")   # city + country
        >>> # Level 2: Location(country="us", state="california")   # state + country
        >>> # Level 3: Location(country="us")                       # country only

        >>> # Combined fields fallback
        >>> loc = Location(country="us", state="california", city="los_angeles")
        >>> levels = [
        ...     HierarchyLevel(fields=["city", "state"]),  # Try both together
        ...     HierarchyLevel(fields=["city"]),
        ...     HierarchyLevel(fields=["state"]),
        ... ]
        >>> hierarchy = build_location_hierarchy(loc, levels)
        >>> # Level 1: Location(country="us", state="california", city="los_angeles")
        >>> # Level 2: Location(country="us", city="los_angeles")   # city + country
        >>> # Level 3: Location(country="us", state="california")   # state + country
        >>> # Level 4: Location(country="us")                       # country only
    """
    if not location or not location.country:
        logger.warning("Cannot build hierarchy: no country provided")
        return []

    if hierarchy_levels is None:
        hierarchy_levels = DEFAULT_HIERARCHY_LEVELS
        logger.debug("Using default hierarchy levels", levels=len(hierarchy_levels))

    hierarchy: list[Location] = []

    for level in hierarchy_levels:
        # Validate field names
        invalid_fields = [f for f in level.fields if not LocationField.is_valid(f)]
        if invalid_fields:
            logger.warning(
                f"Skipping hierarchy level with invalid fields: {invalid_fields}",
                valid_fields=[f.value for f in LocationField],
            )
            continue

        loc_dict = _build_location_dict(location, list(level.fields))
        if loc_dict:
            hierarchy.append(Location(**loc_dict))
            logger.debug(
                f"Added hierarchy level: {level.fields} + country",
                location=loc_dict,
            )

    # Always add country-only as final fallback (we already returned early if no country)
    country_only = Location(country=location.country)
    if not hierarchy or hierarchy[-1].model_dump(exclude_none=True) != country_only.model_dump(
        exclude_none=True
    ):
        hierarchy.append(country_only)
        logger.debug(
            "Added hierarchy level: country only",
            country=location.country,
        )

    logger.info(
        f"Built location hierarchy with {len(hierarchy)} levels",
        original_location=location.model_dump(exclude_none=True),
        hierarchy_levels=[lvl.fields for lvl in hierarchy_levels],
        levels=len(hierarchy),
    )

    return hierarchy


def _build_location_dict(location: Location, fields: list[str]) -> dict[str, str | None] | None:
    """Build location dict with specified fields plus country.

    Args:
        location: Source location object
        fields: List of field names to include (e.g., ["city", "state"])

    Returns:
        Dict with country and specified fields, or None if any required field is missing

    Example:
        >>> loc = Location(country="us", state="california", city="los_angeles")
        >>> _build_location_dict(loc, ["city", "state"])
        {'country': 'us', 'city': 'los_angeles', 'state': 'california'}
    """
    loc_dict: dict[str, str | None] = {"country": location.country}

    for field in fields:
        value = getattr(location, field, None)
        if not value:
            # Required field is missing, skip this combination
            logger.debug(
                f"Skipping hierarchy level: missing field '{field}'",
                fields=fields,
            )
            return None
        loc_dict[field] = value

    return loc_dict
