"""Kleinanzeigen Mobile API – fetch listings."""

import logging

import httpx

from src.client import fetch
from src.models import Listing

logger = logging.getLogger(__name__)

BASE_URL = "https://api.kleinanzeigen.de/api/ads.json"

HEADERS = {
    "Authorization": "Basic KA_AUTH_PLACEHOLDER",
    "User-Agent": "okhttp/4.10.0",
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

        # Attributes – try both rent and buy prefixes
        prefix = "wohnung_mieten" if category_id == "203" else "haus_mieten" if category_id == "205" else ""
        rooms = _safe_float(_get_attr(ad, f"{prefix}.zimmer")) if prefix else None
        living_space = _safe_float(_get_attr(ad, f"{prefix}.qm")) if prefix else None
        floor = _safe_int(_get_attr(ad, f"{prefix}.etage")) if prefix else None
        bedrooms = _safe_float(_get_attr(ad, f"{prefix}.schlafzimmer")) if prefix else None
        bathrooms = _safe_float(_get_attr(ad, f"{prefix}.badezimmer")) if prefix else None

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
        published_at = ad.get("start-date-time", {}).get("value", "")

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
                price=price,
                cold_rent=price if is_rent else None,
                rooms=rooms,
                living_space=living_space,
                floor=floor,
                bedrooms=bedrooms,
                bathrooms=bathrooms,
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
