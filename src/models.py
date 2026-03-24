"""Shared data models."""

import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from dateutil import parser as dateparser

_RELATIVE_DE = re.compile(
    r"vor\s+(\d+)\s+(Minute|Stunde|Tag|Woche|Monat|Jahr)(?:n|en|e)?",
    re.IGNORECASE,
)
_RELATIVE_UNIT_MAP = {
    "minute": "minutes",
    "stunde": "hours",
    "tag": "days",
    "woche": "weeks",
    "monat": "months",
    "jahr": "years",
}


@dataclass
class Listing:
    id: str
    portal: str
    title: str
    url: str

    # Price – rent fields
    warm_rent: float | None = None
    cold_rent: float | None = None
    extra_costs: float | None = None
    deposit: float | None = None

    # Price – buy fields
    buy_price: float | None = None
    hausgeld: float | None = None
    commission_percent: float | None = None
    original_price: float | None = None     # before reduction

    # Price – shared
    price_per_sqm: float | None = None
    listing_type: str = ""                  # "rent" or "buy"
    renovation_surcharge: float | None = None   # estimated renovation cost in €

    # Property details
    rooms: float | None = None
    living_space: float | None = None
    plot_space: float | None = None
    floor: int | None = None
    total_floors: int | None = None
    bedrooms: float | None = None
    bathrooms: float | None = None
    property_type: str = ""

    # Location
    city: str = ""
    zip_code: str = ""
    district: str = ""
    street: str = ""
    latitude: float | None = None
    longitude: float | None = None

    # Texts
    description: str = ""
    equipment: str = ""
    location_description: str = ""
    other_info: str = ""

    # Building
    year_built: int | None = None
    year_renovated: int | None = None
    condition: str = ""
    energy_class: str = ""
    heating_type: str = ""

    # AI-extracted fields (from description via GPT)
    has_balcony: bool | None = None
    has_garden: bool | None = None
    has_parking: bool | None = None
    has_elevator: bool | None = None
    has_cellar: bool | None = None
    has_fitted_kitchen: bool | None = None
    num_units_in_building: int | None = None
    available_from: str = ""
    pets_allowed: bool | None = None
    is_temporary: bool | None = None

    # Meta
    is_private: bool | None = None
    published_at: datetime | None = None
    images: list[str] = field(default_factory=list)


def parse_datetime(value: str) -> datetime | None:
    """Parse any datetime string into a timezone-aware datetime.

    Handles ISO formats, German relative strings ("vor 3 Tagen"), etc.
    """
    if not value:
        return None

    match = _RELATIVE_DE.search(value)
    if match:
        amount = int(match.group(1))
        unit = match.group(2).lower()
        eng_unit = _RELATIVE_UNIT_MAP.get(unit)
        if eng_unit:
            now = datetime.now(timezone.utc)
            if eng_unit == "months":
                return now - timedelta(days=amount * 30)
            if eng_unit == "years":
                return now - timedelta(days=amount * 365)
            return now - timedelta(**{eng_unit: amount})

    try:
        dt = dateparser.parse(value)
        if dt and dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except (ValueError, OverflowError):
        return None
