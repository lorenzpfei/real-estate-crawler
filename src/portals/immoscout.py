"""ImmoScout24 Mobile App API – fetch listings.

Uses the undocumented mobile app API (api.mobile.immobilienscout24.de)
which requires no authentication.
"""

import logging

import httpx

from src.client import post
from src.models import Listing

logger = logging.getLogger(__name__)

BASE_URL = "https://api.mobile.immobilienscout24.de/search/list"

HEADERS = {
    "User-Agent": "IS24_USER_AGENT_PLACEHOLDER",
    "Content-Type": "application/json",
}


async def search(
    client: httpx.AsyncClient,
    real_estate_type: str = "apartmentrent",
    geocoordinates: str = "",
    price_min: int = 0,
    price_max: int = 0,
    page_size: int = 20,
) -> list[Listing]:
    """Search listings via the ImmoScout24 Mobile App API (POST)."""
    params: dict = {
        "realestatetype": real_estate_type,
        "pagenumber": 1,
    }

    if geocoordinates:
        params["searchType"] = "radius"
        params["geocoordinates"] = geocoordinates
    else:
        params["searchType"] = "region"

    if real_estate_type.endswith("rent"):
        params["pricetype"] = "calculatedtotalrent"

    if price_min:
        params["price_min"] = price_min
    if price_max:
        params["price_max"] = price_max

    body = {"supportedREsultListType": [], "userData": {}}

    response = await post(
        client, BASE_URL, headers=HEADERS, params=params, json=body
    )

    if response.status_code != 200:
        logger.warning("ImmoScout24: HTTP %d", response.status_code)
        return []

    data = response.json()
    listings: list[Listing] = []

    for result in data.get("resultListItems", []):
        if result.get("type") != "EXPOSE_RESULT":
            continue

        item = result.get("item", {})
        listing_id = str(item.get("id", ""))
        if not listing_id:
            continue

        title = item.get("title", "")

        # Price is in the first attribute
        attributes = item.get("attributes", [])
        price = attributes[0].get("value", "") if attributes else ""

        url = f"https://www.immobilienscout24.de/expose/{listing_id}"

        listings.append(
            Listing(
                id=f"is24-{listing_id}",
                portal="immoscout24",
                title=title,
                price=price,
                url=url,
            )
        )

    logger.info("ImmoScout24: %d listings found", len(listings))
    return listings
