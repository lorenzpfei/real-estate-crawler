"""Main module – async scraper loop with jitter."""

import asyncio
import logging
import random

from src import database
from src.client import build_client
from src.models import Listing
from src.config import (
    INTERVAL_MAX,
    INTERVAL_MIN,
    IS24_GEOCOORDINATES,
    IS24_PRICE_MAX,
    IS24_PRICE_MIN,
    IS24_REAL_ESTATE_TYPE,
    IW_DISTRIBUTION_TYPES,
    IW_ESTATE_TYPES,
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


async def _process_listings(listings: list[Listing]) -> int:
    """Store new listings and return the count of newly added entries."""
    new_count = 0
    for listing in listings:
        if not database.exists(listing.id):
            # Calculate price_per_sqm if missing but derivable
            if listing.price_per_sqm is None and listing.price and listing.living_space:
                listing.price_per_sqm = round(listing.price / listing.living_space, 2)
            database.insert(listing)
            logger.info(
                "NEW: [%s] %s – %s → %s",
                listing.portal,
                listing.title,
                listing.price,
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
                await _process_listings(ka_listings)
            except Exception:
                logger.exception("Error fetching Kleinanzeigen (category %s)", cat_id)

        # ImmoScout24
        try:
            is24_listings = await immoscout.search(
                client,
                real_estate_type=IS24_REAL_ESTATE_TYPE,
                geocoordinates=IS24_GEOCOORDINATES,
                price_min=IS24_PRICE_MIN,
                price_max=IS24_PRICE_MAX,
            )
            await _process_listings(is24_listings)
        except Exception:
            logger.exception("Error fetching ImmoScout24")

        # Immowelt (incl. Immonet)
        try:
            iw_listings = await immowelt.search(
                client,
                distribution_types=IW_DISTRIBUTION_TYPES,
                estate_types=IW_ESTATE_TYPES,
                locations=IW_LOCATIONS,
            )
            await _process_listings(iw_listings)
        except Exception:
            logger.exception("Error fetching Immowelt")

    # Clean up old entries
    deleted = database.cleanup_old_entries()
    if deleted:
        logger.info("%d old entries cleaned up", deleted)


async def main() -> None:
    """Infinite loop with randomized interval (jitter)."""
    database.init_db()
    logger.info("Scraper started")

    while True:
        await run_once()
        sleep_seconds = random.randint(INTERVAL_MIN, INTERVAL_MAX)
        logger.info("Next run in %d seconds", sleep_seconds)
        await asyncio.sleep(sleep_seconds)


if __name__ == "__main__":
    asyncio.run(main())
