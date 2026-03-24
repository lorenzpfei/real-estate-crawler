"""Main module – async scraper loop with jitter."""

import asyncio
import logging
import random

from dotenv import load_dotenv
load_dotenv()

from src import database
from src.client import build_client
from src.enrichment import enrich_listing
from src.models import Listing
from src.config import (
    INTERVAL_MAX,
    INTERVAL_MIN,
    IS24_GEOCOORDINATES,
    IS24_PRICE_MAX,
    IS24_PRICE_MIN,
    IS24_REAL_ESTATE_TYPES,
    IW_SEARCHES,
    IW_LOCATIONS,
    KA_CATEGORY_IDS,
    KA_DISTANCE,
    KA_LOCATION_ID,
    KA_QUERY,
)
from src.portals import kleinanzeigen, immoscout, immowelt

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


def _estimate_renovation_surcharge(listing: Listing) -> float:
    """Estimate renovation cost based on energy class and year built."""
    sqm = listing.living_space or 0
    if sqm <= 0:
        return 0.0

    # Energy class surcharge per m²
    ec = (listing.energy_class or "").upper().strip()
    energy_surcharge = {
        "A+": 0, "A": 0, "B": 0,
        "C": 200, "D": 200,
        "E": 500, "F": 500,
        "G": 800, "H": 800,
    }.get(ec, 400)  # unknown = 400

    # Year built surcharge per m²
    yb = listing.year_built
    if yb is None:
        year_surcharge = 300
    elif yb >= 2000:
        year_surcharge = 0
    elif yb >= 1980:
        year_surcharge = 150
    elif yb >= 1960:
        year_surcharge = 350
    else:
        year_surcharge = 500

    return round((energy_surcharge + year_surcharge) * sqm)


async def _process_listings(client, listings: list[Listing]) -> int:
    """Store new listings and return the count of newly added entries."""
    _SKIP_PREFIXES = ("suche ", "suchen ", "ich suche", "wir suche", "familie sucht", "paar sucht")
    _SKIP_KEYWORDS = ("zwischenmiete",)
    new_count = 0
    for listing in listings:
        title_lower = listing.title.lower() if listing.title else ""
        if title_lower.startswith(_SKIP_PREFIXES):
            continue
        if any(kw in title_lower for kw in _SKIP_KEYWORDS):
            continue
        if not database.exists(listing.id):
            # Calculate price_per_sqm: cold rent for rentals, buy price for purchases
            if listing.price_per_sqm is None and listing.living_space:
                base = listing.cold_rent if listing.listing_type == "rent" else listing.buy_price
                if base:
                    listing.price_per_sqm = round(base / listing.living_space, 2)
            # Calculate renovation surcharge for buy listings
            if listing.listing_type == "buy" and listing.buy_price and listing.living_space:
                listing.renovation_surcharge = _estimate_renovation_surcharge(listing)
            # AI enrichment
            listing = await enrich_listing(client, listing)
            database.insert(listing)
            logger.info(
                "NEW: [%s] [%s] %s → %s",
                listing.portal,
                listing.listing_type,
                listing.title,
                listing.url,
            )
            new_count += 1
    return new_count


async def run_once() -> None:
    """Run a full scrape cycle across all portals."""
    async with build_client() as client:
        # Kleinanzeigen (one search per category)
        for cat_id in KA_CATEGORY_IDS.split(","):
            cat_id = cat_id.strip()
            if not cat_id:
                continue
            try:
                ka_listings = await kleinanzeigen.search(
                    client,
                    query=KA_QUERY,
                    location_id=KA_LOCATION_ID,
                    distance=KA_DISTANCE,
                    category_id=cat_id,
                )
                await _process_listings(client, ka_listings)
            except Exception:
                logger.exception("Error fetching Kleinanzeigen (category %s)", cat_id)

        # ImmoScout24 (one search per real estate type)
        for re_type in IS24_REAL_ESTATE_TYPES.split(","):
            re_type = re_type.strip()
            if not re_type:
                continue
            try:
                is24_listings = await immoscout.search(
                    client,
                    real_estate_type=re_type,
                    geocoordinates=IS24_GEOCOORDINATES,
                    price_min=IS24_PRICE_MIN,
                    price_max=IS24_PRICE_MAX,
                )
                await _process_listings(client, is24_listings)
            except Exception:
                logger.exception("Error fetching ImmoScout24 (%s)", re_type)

        # Immowelt (one search per distribution+estate combo)
        for search_def in IW_SEARCHES.split(";"):
            search_def = search_def.strip()
            if not search_def or "|" not in search_def:
                continue
            dist_types, estate_types = search_def.split("|", 1)
            try:
                iw_listings = await immowelt.search(
                    client,
                    distribution_types=dist_types.strip(),
                    estate_types=estate_types.strip(),
                    locations=IW_LOCATIONS,
                )
                await _process_listings(client, iw_listings)
            except Exception:
                logger.exception("Error fetching Immowelt (%s)", search_def)

    # Clean up old entries
    deleted = database.cleanup_old_entries()
    if deleted:
        logger.info("%d old entries cleaned up", deleted)


async def main() -> None:
    """Infinite loop with randomized interval (jitter), active only during configured hours."""
    from zoneinfo import ZoneInfo
    from src.config import ACTIVE_HOUR_START, ACTIVE_HOUR_END, TIMEZONE

    tz = ZoneInfo(TIMEZONE)
    database.init_db()
    logger.info("Scraper started (active %d:00–%d:00 %s)", ACTIVE_HOUR_START, ACTIVE_HOUR_END, TIMEZONE)

    while True:
        from datetime import datetime
        hour = datetime.now(tz).hour
        if ACTIVE_HOUR_START <= hour < ACTIVE_HOUR_END:
            await run_once()
            sleep_seconds = random.randint(INTERVAL_MIN, INTERVAL_MAX)
            logger.info("Next run in %d minutes", sleep_seconds // 60)
        else:
            now = datetime.now(tz)
            next_start = now.replace(hour=ACTIVE_HOUR_START, minute=0, second=0, microsecond=0)
            if now >= next_start:
                from datetime import timedelta
                next_start += timedelta(days=1)
            sleep_seconds = int((next_start - now).total_seconds())
            logger.info("Outside active hours, sleeping until %s", next_start.strftime("%H:%M"))
        await asyncio.sleep(sleep_seconds)


if __name__ == "__main__":
    asyncio.run(main())
