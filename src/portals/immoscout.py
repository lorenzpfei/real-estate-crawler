"""ImmoScout24 Mobile App API – fetch listings.

Uses the undocumented mobile app API (api.mobile.immobilienscout24.de)
which requires no authentication. Fetches search results, then loads
expose details for description, attributes, and full image set.
"""

import logging
import re

import httpx

from src.client import fetch, post
from src.models import Listing, parse_datetime

logger = logging.getLogger(__name__)

SEARCH_URL = "https://api.mobile.immobilienscout24.de/search/list"
EXPOSE_URL = "https://api.mobile.immobilienscout24.de/expose"

HEADERS = {
    "User-Agent": "IS24_USER_AGENT_PLACEHOLDER",
    "Content-Type": "application/json",
}

_PRICE_RE = re.compile(r"[\d.,]+")


def _parse_price(price_str: str) -> float | None:
    """Extract numeric price from formatted string like '330 €' or '1.200,50 €'."""
    match = _PRICE_RE.search(price_str)
    if not match:
        return None
    raw = match.group().replace(".", "").replace(",", ".")
    try:
        return float(raw)
    except ValueError:
        return None


def _find_attr(attributes: list[dict], label_prefix: str) -> str:
    """Find attribute text by label prefix."""
    for attr in attributes:
        lbl = attr.get("label", "")
        if lbl.startswith(label_prefix):
            return attr.get("text", "")
    return ""


async def _fetch_expose(client: httpx.AsyncClient, listing_id: str) -> dict:
    """Fetch expose detail for a single listing."""
    try:
        response = await fetch(
            client, f"{EXPOSE_URL}/{listing_id}",
            headers={"User-Agent": HEADERS["User-Agent"]},
        )
        if response.status_code == 200:
            return response.json()
    except Exception:
        logger.debug("Failed to fetch expose %s", listing_id)
    return {}


def _parse_expose(data: dict) -> dict:
    """Extract all useful fields from expose detail response."""
    result: dict = {
        "description": "",
        "equipment": "",
        "location_description": "",
        "other_info": "",
        "images": [],
        "cold_rent": None,
        "warm_rent": None,
        "extra_costs": None,
        "price_per_sqm": None,
        "deposit": None,
        "rooms": None,
        "living_space": None,
        "floor": None,
        "total_floors": None,
        "bedrooms": None,
        "bathrooms": None,
        "property_type": "",
        "year_built": None,
        "year_renovated": None,
        "condition": "",
        "energy_class": "",
        "heating_type": "",
    }

    for section in data.get("sections", []):
        stype = section.get("type", "")

        if stype == "TEXT_AREA":
            title = section.get("title", "")
            text = section.get("text", "")
            if "Objektbeschreibung" in title:
                result["description"] = text
            elif "Ausstattung" in title:
                result["equipment"] = text
            elif "Lage" in title:
                result["location_description"] = text
            elif "Sonstiges" in title:
                result["other_info"] = text

        elif stype == "MEDIA":
            for media in section.get("media", []):
                url = media.get("fullImageUrl", "") or media.get("previewImageUrl", "")
                if url and media.get("type") == "PICTURE":
                    result["images"].append(url)

        elif stype == "TOP_ATTRIBUTES":
            for attr in section.get("attributes", []):
                label = attr.get("label", "")
                text = attr.get("text", "")
                if "Zimmer" in label and not "Schlaf" in label:
                    result["rooms"] = _parse_price(text)
                elif "Wohnfläche" in label:
                    result["living_space"] = _parse_price(text)
                elif "Warmmiete" in label:
                    result["warm_rent"] = _parse_price(text)
                elif "Kaltmiete" in label:
                    result["cold_rent"] = _parse_price(text)
                    result["price_per_sqm"] = _parse_price(label)

        elif stype == "ATTRIBUTE_LIST":
            attrs = section.get("attributes", [])
            title = section.get("title", "")

            if "Hauptkriterien" in title:
                result["property_type"] = _find_attr(attrs, "Wohnungstyp") or _find_attr(attrs, "Haustyp")
                result["bedrooms"] = _parse_price(_find_attr(attrs, "Schlafzimmer"))
                result["bathrooms"] = _parse_price(_find_attr(attrs, "Badezimmer"))

                floor_str = _find_attr(attrs, "Etage")
                if floor_str:
                    parts = floor_str.split(" von ")
                    result["floor"] = _parse_price(parts[0])
                    if len(parts) > 1:
                        result["total_floors"] = _parse_price(parts[1])

            elif "Kosten" in title:
                cold = _find_attr(attrs, "Kaltmiete")
                if cold:
                    result["cold_rent"] = _parse_price(cold)
                extra = _find_attr(attrs, "Nebenkosten")
                if extra and not extra.startswith("nicht"):
                    result["extra_costs"] = _parse_price(extra)
                total = _find_attr(attrs, "Gesamtmiete")
                if total:
                    result["warm_rent"] = _parse_price(total)
                deposit = _find_attr(attrs, "Kaution")
                if deposit:
                    result["deposit"] = _parse_price(deposit)
                ppsqm = _find_attr(attrs, "Preis/m")
                if ppsqm:
                    result["price_per_sqm"] = _parse_price(ppsqm)

            elif "Energieausweis" in title or "Bausubstanz" in title:
                bj = _find_attr(attrs, "Baujahr")
                if bj:
                    result["year_built"] = _parse_price(bj)
                    if result["year_built"]:
                        result["year_built"] = int(result["year_built"])
                ren = _find_attr(attrs, "Letzte Modernisierung")
                if ren:
                    result["year_renovated"] = _parse_price(ren)
                    if result["year_renovated"]:
                        result["year_renovated"] = int(result["year_renovated"])
                result["condition"] = _find_attr(attrs, "Objektzustand")
                result["heating_type"] = _find_attr(attrs, "Heizungsart")
                result["energy_class"] = _find_attr(attrs, "Energieausweis")

    return result


async def search(
    client: httpx.AsyncClient,
    real_estate_type: str = "apartmentrent",
    geocoordinates: str = "",
    price_min: int = 0,
    price_max: int = 0,
    page_size: int = 20,
) -> list[Listing]:
    """Search listings via the ImmoScout24 Mobile App API."""
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
        client, SEARCH_URL, headers=HEADERS, params=params, json=body
    )

    if response.status_code != 200:
        logger.warning("ImmoScout24: HTTP %d", response.status_code)
        return []

    data = response.json()
    is_rent = real_estate_type.endswith("rent")
    listings: list[Listing] = []

    for result in data.get("resultListItems", []):
        if result.get("type") != "EXPOSE_RESULT":
            continue

        item = result.get("item", {})
        listing_id = str(item.get("id", ""))
        if not listing_id:
            continue

        title = item.get("title", "")

        # Price from search result
        attributes = item.get("attributes", [])
        price_str = attributes[0].get("value", "") if attributes else ""
        price = _parse_price(price_str)

        # Address from search result
        addr = item.get("address", {})
        addr_line = addr.get("line", "")
        lat = addr.get("lat")
        lon = addr.get("lon")

        # Parse city/zip from address line like "Mariannhillstr. 1B, 97074 Würzburg, Mönchberg"
        city, zip_code, street, district = "", "", "", ""
        if addr_line:
            parts = [p.strip() for p in addr_line.split(",")]
            # Find the part that contains a zip code (5 digits)
            import re as _re
            for i, part in enumerate(parts):
                zip_match = _re.search(r"\b(\d{5})\b", part)
                if zip_match:
                    zip_code = zip_match.group(1)
                    city = part.replace(zip_code, "").strip()
                    # Everything before this part is the street
                    street = ", ".join(parts[:i]).strip()
                    # Everything after is the district
                    district = ", ".join(parts[i+1:]).strip()
                    break

        is_private = item.get("isPrivate")
        published_at = parse_datetime(item.get("published", ""))
        url = f"https://www.immobilienscout24.de/expose/{listing_id}"

        # Fetch expose detail
        expose = await _fetch_expose(client, listing_id)
        detail = _parse_expose(expose) if expose else {}

        # Images: prefer expose (full set), fall back to search result
        images = detail.get("images", [])
        if not images:
            title_pic = item.get("titlePicture", {})
            if title_pic.get("full"):
                images.append(title_pic["full"])
            for pic in item.get("pictures", []):
                url_tmpl = pic.get("urlScaleAndCrop", "")
                if url_tmpl:
                    images.append(url_tmpl.replace("%WIDTH%", "800").replace("%HEIGHT%", "600"))

        listings.append(
            Listing(
                id=f"is24-{listing_id}",
                portal="immoscout24",
                title=title,
                url=url,
                price=price,
                warm_rent=detail.get("warm_rent") if is_rent else None,
                cold_rent=detail.get("cold_rent") if is_rent else None,
                extra_costs=detail.get("extra_costs"),
                price_per_sqm=detail.get("price_per_sqm"),
                deposit=detail.get("deposit"),
                rooms=detail.get("rooms"),
                living_space=detail.get("living_space"),
                floor=int(detail["floor"]) if detail.get("floor") else None,
                total_floors=int(detail["total_floors"]) if detail.get("total_floors") else None,
                bedrooms=detail.get("bedrooms"),
                bathrooms=detail.get("bathrooms"),
                property_type=detail.get("property_type", ""),
                listing_type="rent" if is_rent else "buy",
                city=city,
                zip_code=zip_code,
                district=district,
                street=street,
                latitude=lat,
                longitude=lon,
                description=detail.get("description", ""),
                equipment=detail.get("equipment", ""),
                location_description=detail.get("location_description", ""),
                other_info=detail.get("other_info", ""),
                year_built=detail.get("year_built"),
                year_renovated=detail.get("year_renovated"),
                condition=detail.get("condition", ""),
                energy_class=detail.get("energy_class", ""),
                heating_type=detail.get("heating_type", ""),
                is_private=is_private,
                published_at=published_at,
                images=images,
            )
        )

    logger.info("ImmoScout24: %d listings found", len(listings))
    return listings
