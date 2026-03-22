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

    listings: list[Listing] = []
    for ad in ad_list:
        ad_id = str(ad.get("id", ""))
        if not ad_id:
            continue

        title = ad.get("title", {}).get("value", "")

        price_obj = ad.get("price", {})
        amount = price_obj.get("amount", {}).get("value", "")
        currency_obj = price_obj.get("currency-iso-code", {}).get("value", {})
        currency = currency_obj.get("value", "EUR") if isinstance(currency_obj, dict) else "EUR"
        price = f"{amount} {currency}" if amount else ""

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
                price=price,
                url=url,
            )
        )

    logger.info("Kleinanzeigen: %d listings found", len(listings))
    return listings
