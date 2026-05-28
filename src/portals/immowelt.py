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
from src.models import Listing, parse_datetime

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

_PRICE_RE = re.compile(r"[\d.,]+")


def _parse_price(price_str: str) -> float | None:
    match = _PRICE_RE.search(price_str)
    if not match:
        return None
    raw = match.group().replace(".", "").replace(",", ".")
    try:
        return float(raw)
    except ValueError:
        return None


def _extract_classifieds(html: str) -> list[dict]:
    """Extract listings from the HTML."""
    match = _FETCHER_RE.search(html)
    if not match:
        raise ValueError("__UFRN_FETCHER__ script not found")

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


def _get_fact(facts: list[dict], fact_type: str) -> str:
    """Get a fact value by type from the facts list."""
    for fact in facts:
        if fact.get("type") == fact_type:
            return fact.get("splitValue", "")
    return ""


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

    is_rent = "Rent" in distribution_types

    listings: list[Listing] = []
    for item in items:
        listing_id = item.get("id", "")
        if not listing_id:
            continue

        hard_facts = item.get("hardFacts", {})
        title = hard_facts.get("title", "")

        # Prices — parse labeled entries (Kaltmiete / Warmmiete / Nebenkosten)
        cold_rent: float | None = None
        warm_rent: float | None = None
        extra_costs: float | None = None
        buy_price: float | None = None
        for p in hard_facts.get("prices", []):
            label = p.get("label", "")
            val = _parse_price(p.get("value", ""))
            if "Kaltmiete" in label or "Kaufpreis" in label:
                if is_rent:
                    cold_rent = val
                else:
                    buy_price = val
            elif "Warmmiete" in label:
                warm_rent = val
            elif "Nebenkosten" in label or "Betriebskosten" in label:
                extra_costs = val
            elif "Hausgeld" in label:
                extra_costs = val

        # Fallback: main price field
        if cold_rent is None and warm_rent is None and buy_price is None:
            main_val = _parse_price(hard_facts.get("price", {}).get("value", ""))
            addition = hard_facts.get("price", {}).get("addition", {}).get("value", "")
            if "Warm" in addition:
                warm_rent = main_val
            elif not is_rent:
                buy_price = main_val
            else:
                cold_rent = main_val

        # Price per sqm
        ppsqm_str = hard_facts.get("price", {}).get("additionalInformation", "")
        price_per_sqm = _parse_price(ppsqm_str) if ppsqm_str and "€" in ppsqm_str else None

        # Facts (rooms, living space, plot space, floor, availability)
        facts = hard_facts.get("facts", [])
        rooms = _parse_price(_get_fact(facts, "numberOfRooms"))
        living_space = _parse_price(_get_fact(facts, "livingSpace"))
        plot_space = _parse_price(_get_fact(facts, "plotSpace"))
        floor_raw = _parse_price(_get_fact(facts, "numberOfFloors"))
        floor = int(floor_raw) if floor_raw is not None else None
        # availability fact: splitValue="frei", label="ab 01.09.2026" or "ab sofort"
        available_from = ""
        for f in facts:
            if f.get("type") == "availability":
                available_from = f.get("label", "")
                break

        # Property sub-type from rawData
        property_type = item.get("rawData", {}).get("propertySubType", "")

        # Location
        loc = item.get("location", {}).get("address", {})
        city = loc.get("city", "")
        zip_code = loc.get("zipCode", "")
        district = loc.get("district", "")

        # Description
        raw_desc = item.get("mainDescription", "")
        if isinstance(raw_desc, dict):
            description = raw_desc.get("description", "")
        else:
            description = raw_desc or ""

        # Energy class
        energy_class = item.get("energyClass", "")

        # Private or professional
        provider_type = item.get("type", "")
        is_private = provider_type == "PRIVATE" if provider_type else None

        # Metadata dates
        metadata = item.get("metadata", {})
        published_at = parse_datetime(metadata.get("creationDate", ""))

        # Images from gallery
        images: list[str] = []
        for img in item.get("gallery", {}).get("images", []):
            img_url = img.get("url", "")
            if img_url:
                images.append(img_url)

        # URL
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
                url=url,
                buy_price=buy_price,
                cold_rent=cold_rent,
                warm_rent=warm_rent,
                extra_costs=extra_costs,
                price_per_sqm=price_per_sqm,
                rooms=rooms,
                living_space=living_space,
                plot_space=plot_space,
                floor=floor,
                property_type=property_type,
                available_from=available_from,
                listing_type="rent" if is_rent else "buy",
                city=city,
                zip_code=zip_code,
                district=district,
                description=description,
                energy_class=energy_class,
                is_private=is_private,
                published_at=published_at,
                images=images,
            )
        )

    logger.info("Immowelt: %d listings found", len(listings))
    return listings
