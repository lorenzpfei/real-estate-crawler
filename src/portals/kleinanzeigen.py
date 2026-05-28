"""Kleinanzeigen Mobile API – fetch listings."""

import logging
import os

import httpx

from src.client import fetch
from src.models import Listing, parse_datetime

logger = logging.getLogger(__name__)

BASE_URL = "https://api.kleinanzeigen.de/api/ads.json"

HEADERS = {
    "Authorization": f"Basic {os.getenv('KA_AUTH', '')}",
    "User-Agent": os.getenv("KA_USER_AGENT", "okhttp/4.10.0"),
    "Accept": "application/json",
}


def _get_attr(ad: dict, name: str) -> str | None:
    """Extract an attribute value by name from the attributes list."""
    for attr in ad.get("attributes", {}).get("attribute", []):
        if attr.get("name") == name:
            values = attr.get("value", [])
            if values:
                return values[0].get("value")
    return None


def _safe_float(val: str | None) -> float | None:
    if val is None:
        return None
    try:
        return float(val)
    except (ValueError, TypeError):
        return None


def _safe_int(val: str | None) -> int | None:
    if val is None:
        return None
    try:
        return int(float(val))
    except (ValueError, TypeError):
        return None


async def search(
    client: httpx.AsyncClient,
    query: str = "",
    location_id: str = "",
    distance: int = 0,
    category_id: str = "",
    size: int = 41,
) -> list[Listing]:
    """Search listings via the Kleinanzeigen Mobile API."""
    params: dict = {"size": size}
    if query:
        params["q"] = query
    if location_id:
        params["locationId"] = location_id
    if distance:
        params["search-distance"] = distance
    if category_id:
        params["categoryId"] = category_id

    response = await fetch(client, BASE_URL, headers=HEADERS, params=params)
    data = response.json()

    ads_wrapper = data.get("{http://www.ebayclassifiedsgroup.com/schema/ad/v1}ads", {})
    ad_list = ads_wrapper.get("value", {}).get("ad", [])

    # Determine listing_type from category
    is_rent = category_id in ("203", "205")

    _PREFIX_MAP = {
        "203": "wohnung_mieten",
        "205": "haus_mieten",
        "196": "wohnung_kaufen",
        "208": "haus_kaufen",
    }

    listings: list[Listing] = []
    for ad in ad_list:
        if ad.get("ad-type", {}).get("value", "") != "OFFERED":
            continue

        ad_id = str(ad.get("id", ""))
        if not ad_id:
            continue

        title = ad.get("title", {}).get("value", "")
        description = ad.get("description", {}).get("value", "")

        # Price
        amount = ad.get("price", {}).get("amount", {}).get("value", None)
        price = float(amount) if amount is not None else None

        # Address
        addr = ad.get("ad-address", {})
        city = addr.get("state", {}).get("value", "")
        zip_code = addr.get("zip-code", {}).get("value", "")
        street = addr.get("street", {}).get("value", "")
        lat = _safe_float(addr.get("latitude", {}).get("value"))
        lon = _safe_float(addr.get("longitude", {}).get("value"))

        # Attributes – map category to attribute prefix
        prefix = _PREFIX_MAP.get(category_id, "")
        rooms = _safe_float(_get_attr(ad, f"{prefix}.zimmer")) if prefix else None
        living_space = _safe_float(_get_attr(ad, f"{prefix}.qm")) if prefix else None
        floor = _safe_int(_get_attr(ad, f"{prefix}.etage")) if prefix else None
        bedrooms = _safe_float(_get_attr(ad, f"{prefix}.schlafzimmer")) if prefix else None
        bathrooms = _safe_float(_get_attr(ad, f"{prefix}.badezimmer")) if prefix else None

        # Extra costs, deposit, warm rent
        extra_costs = _safe_float(_get_attr(ad, f"{prefix}.nebenkosten")) if prefix else None
        deposit = _safe_float(_get_attr(ad, f"{prefix}.kaution")) if prefix else None
        warm_rent = _safe_float(_get_attr(ad, f"{prefix}.warmmiete")) if prefix and is_rent else None

        # Buy-only fields
        hausgeld = _safe_float(_get_attr(ad, f"{prefix}.hausgeld")) if prefix and not is_rent else None

        # Building
        year_built = _safe_int(_get_attr(ad, f"{prefix}.baujahr")) if prefix else None
        plot_space = _safe_float(_get_attr(ad, f"{prefix}.grundstuecksflaeche")) if prefix else None
        total_floors = _safe_int(_get_attr(ad, f"{prefix}.anzahl_etagen")) if prefix else None

        # Amenities
        def _is_true(val: str | None) -> bool:
            return (val or "").lower() in ("true", "1", "yes")

        has_balcony = (
            _is_true(_get_attr(ad, f"{prefix}.balcony"))
            or _is_true(_get_attr(ad, f"{prefix}.terrace"))
        ) if prefix else None
        has_garden = _is_true(_get_attr(ad, f"{prefix}.garden")) if prefix else None
        has_fitted_kitchen = _is_true(_get_attr(ad, f"{prefix}.built_in_kitchen")) if prefix else None
        has_cellar = _is_true(_get_attr(ad, f"{prefix}.celler_loft")) if prefix else None
        has_parking = _is_true(_get_attr(ad, f"{prefix}.garage")) if prefix else None
        has_elevator = _is_true(_get_attr(ad, f"{prefix}.lift")) if prefix else None
        pets_allowed = _is_true(_get_attr(ad, f"{prefix}.pets_allowed")) if prefix else None

        # Available from
        available_from = _get_attr(ad, f"{prefix}.verfuegbardate") if prefix else None

        # Property type
        property_type = ""
        if prefix:
            pt_val = _get_attr(ad, f"{prefix}.wohnungstyp") or _get_attr(ad, f"{prefix}.haustyp")
            if pt_val:
                property_type = pt_val

        # Private or commercial
        poster_type = ad.get("poster-type", {}).get("value", "")
        is_private = poster_type == "PRIVATE" if poster_type else None

        # Published date
        published_at = parse_datetime(ad.get("start-date-time", {}).get("value", ""))

        # Images
        images: list[str] = []
        for pic in ad.get("pictures", {}).get("picture", []):
            for link in pic.get("link", []):
                if link.get("rel") == "large":
                    images.append(link.get("href", ""))
                    break
                if link.get("rel") == "teaser":
                    images.append(link.get("href", ""))
                    break

        # URL
        url = ""
        for link in ad.get("link", []):
            if link.get("rel") == "self-public-website":
                url = link.get("href", "")
                break

        listings.append(
            Listing(
                id=f"ka-{ad_id}",
                portal="kleinanzeigen",
                title=title,
                url=url,
                buy_price=price if not is_rent else None,
                cold_rent=price if is_rent else None,
                warm_rent=warm_rent,
                extra_costs=extra_costs,
                deposit=deposit,
                hausgeld=hausgeld,
                rooms=rooms,
                living_space=living_space,
                plot_space=plot_space,
                floor=floor,
                total_floors=total_floors,
                bedrooms=bedrooms,
                bathrooms=bathrooms,
                year_built=year_built,
                has_balcony=has_balcony if has_balcony else None,
                has_garden=has_garden if has_garden else None,
                has_fitted_kitchen=has_fitted_kitchen if has_fitted_kitchen else None,
                has_cellar=has_cellar if has_cellar else None,
                has_parking=has_parking if has_parking else None,
                has_elevator=has_elevator if has_elevator else None,
                pets_allowed=pets_allowed if pets_allowed else None,
                available_from=available_from,
                property_type=property_type,
                listing_type="rent" if is_rent else "buy",
                city=city,
                zip_code=zip_code,
                street=street,
                latitude=lat,
                longitude=lon,
                description=description,
                is_private=is_private,
                published_at=published_at,
                images=images,
            )
        )

    logger.info("Kleinanzeigen: %d listings found", len(listings))
    return listings
