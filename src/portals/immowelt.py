"""Immowelt (incl. Immonet) – fetch listings via classified-search.

The data is embedded in the HTML inside the __UFRN_FETCHER__ script tag as JSON.parse(...).
The value under the key "classified-serp-init-data" is LZ-String Base64 compressed.
"""

import json
import logging
import re

import httpx
import lzstring

from src.client import fetch
from src.models import Listing

logger = logging.getLogger(__name__)

BASE_URL = "https://www.immowelt.de/classified-search"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Linux; Android 14; Pixel 8 Pro) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Mobile Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "de-DE,de;q=0.9,en;q=0.8",
}

_FETCHER_RE = re.compile(
    r'<script id="__UFRN_FETCHER__">window\["__UFRN_FETCHER__"\]=JSON\.parse\("(.+?)"\);</script>',
    re.DOTALL,
)


def _extract_classifieds(html: str) -> list[dict]:
    """Extract listings from the HTML."""
    match = _FETCHER_RE.search(html)
    if not match:
        raise ValueError("__UFRN_FETCHER__ script not found")

    # Double-escaped JSON: unicode_escape first, then parse JSON
    raw = match.group(1).encode().decode("unicode_escape")
    fetcher = json.loads(raw)

    compressed = fetcher.get("data", {}).get("classified-serp-init-data", "")
    if not compressed:
        raise ValueError("classified-serp-init-data not found in fetcher data")

    decompressed = lzstring.LZString().decompressFromBase64(compressed)
    if not decompressed:
        raise ValueError("LZ-String decompression failed")

    data = json.loads(decompressed)
    classifieds_data = data.get("pageProps", {}).get("classifiedsData", {})

    if isinstance(classifieds_data, dict):
        return list(classifieds_data.values())
    if isinstance(classifieds_data, list):
        return classifieds_data
    return []


async def search(
    client: httpx.AsyncClient,
    distribution_types: str = "Rent",
    estate_types: str = "Apartment",
    locations: str = "",
    page: int = 1,
) -> list[Listing]:
    """Search listings on Immowelt."""
    params: dict = {
        "distributionTypes": distribution_types,
        "estateTypes": estate_types,
        "page": page,
    }
    if locations:
        params["locations"] = locations

    response = await fetch(client, BASE_URL, headers=HEADERS, params=params)

    try:
        items = _extract_classifieds(response.text)
    except ValueError as e:
        logger.warning("Immowelt: %s", e)
        return []

    listings: list[Listing] = []
    for item in items:
        listing_id = item.get("id", "")
        if not listing_id:
            continue

        hard_facts = item.get("hardFacts", {})
        title = hard_facts.get("title", "")
        price = hard_facts.get("price", {}).get("value", "")

        raw_url = item.get("url", "")
        if raw_url.startswith("http"):
            url = raw_url
        elif raw_url:
            url = f"https://www.immowelt.de{raw_url}"
        else:
            url = ""

        listings.append(
            Listing(
                id=f"iw-{listing_id}",
                portal="immowelt",
                title=title,
                price=price,
                url=url,
            )
        )

    logger.info("Immowelt: %d listings found", len(listings))
    return listings
