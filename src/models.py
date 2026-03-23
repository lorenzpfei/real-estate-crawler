"""Shared data models."""

from dataclasses import dataclass, field


@dataclass
class Listing:
    id: str
    portal: str
    title: str
    url: str

    # Price
    price: float | None = None
    warm_rent: float | None = None
    cold_rent: float | None = None
    extra_costs: float | None = None
    price_per_sqm: float | None = None
    deposit: float | None = None

    # Property details
    rooms: float | None = None
    living_space: float | None = None
    plot_space: float | None = None
    floor: int | None = None
    total_floors: int | None = None
    bedrooms: float | None = None
    bathrooms: float | None = None
    property_type: str = ""       # e.g. "Etagenwohnung", "Einfamilienhaus"
    listing_type: str = ""        # "rent" or "buy"

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

    # Meta
    is_private: bool | None = None
    published_at: str = ""
    images: list[str] = field(default_factory=list)
