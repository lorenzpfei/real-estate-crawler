"""PostgreSQL database for deduplication and state persistence."""

import os
from datetime import datetime, timedelta, timezone

import psycopg
from psycopg.rows import tuple_row

from src.models import Listing

DATABASE_URL = os.getenv("DATABASE_URL", "")
RETENTION_DAYS = 30


def _get_connection() -> psycopg.Connection:
    return psycopg.connect(DATABASE_URL, row_factory=tuple_row)


def init_db() -> None:
    """Create the table if it doesn't exist yet."""
    with _get_connection() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS apartments (
                id                    TEXT PRIMARY KEY,
                portal                TEXT NOT NULL,
                title                 TEXT,
                url                   TEXT,

                price                 REAL,
                warm_rent             REAL,
                cold_rent             REAL,
                extra_costs           REAL,
                price_per_sqm         REAL,
                deposit               REAL,

                rooms                 REAL,
                living_space          REAL,
                plot_space            REAL,
                floor                 INTEGER,
                total_floors          INTEGER,
                bedrooms              REAL,
                bathrooms             REAL,
                property_type         TEXT DEFAULT '',
                listing_type          TEXT DEFAULT '',

                city                  TEXT DEFAULT '',
                zip_code              TEXT DEFAULT '',
                district              TEXT DEFAULT '',
                street                TEXT DEFAULT '',
                latitude              REAL,
                longitude             REAL,

                description           TEXT DEFAULT '',
                equipment             TEXT DEFAULT '',
                location_description  TEXT DEFAULT '',
                other_info            TEXT DEFAULT '',

                year_built            INTEGER,
                year_renovated        INTEGER,
                condition             TEXT DEFAULT '',
                energy_class          TEXT DEFAULT '',
                heating_type          TEXT DEFAULT '',

                is_private            BOOLEAN,
                published_at          TEXT DEFAULT '',
                images                TEXT[] DEFAULT '{}',

                timestamp             TIMESTAMPTZ NOT NULL
            )
            """
        )


def exists(listing_id: str) -> bool:
    """Check if a listing already exists in the DB."""
    with _get_connection() as conn:
        row = conn.execute(
            "SELECT 1 FROM apartments WHERE id = %s LIMIT 1",
            (listing_id,),
        ).fetchone()
    return row is not None


def insert(listing: Listing) -> None:
    """Store a new listing."""
    with _get_connection() as conn:
        conn.execute(
            """
            INSERT INTO apartments (
                id, portal, title, url,
                price, warm_rent, cold_rent, extra_costs, price_per_sqm, deposit,
                rooms, living_space, plot_space, floor, total_floors, bedrooms, bathrooms,
                property_type, listing_type,
                city, zip_code, district, street, latitude, longitude,
                description, equipment, location_description, other_info,
                year_built, year_renovated, condition, energy_class, heating_type,
                is_private, published_at, images, timestamp
            ) VALUES (
                %s, %s, %s, %s,
                %s, %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s, %s, %s,
                %s, %s,
                %s, %s, %s, %s, %s, %s,
                %s, %s, %s, %s,
                %s, %s, %s, %s, %s,
                %s, %s, %s, %s
            ) ON CONFLICT (id) DO NOTHING
            """,
            (
                listing.id, listing.portal, listing.title, listing.url,
                listing.price, listing.warm_rent, listing.cold_rent,
                listing.extra_costs, listing.price_per_sqm, listing.deposit,
                listing.rooms, listing.living_space, listing.plot_space,
                listing.floor, listing.total_floors, listing.bedrooms, listing.bathrooms,
                listing.property_type, listing.listing_type,
                listing.city, listing.zip_code, listing.district, listing.street,
                listing.latitude, listing.longitude,
                listing.description, listing.equipment,
                listing.location_description, listing.other_info,
                listing.year_built, listing.year_renovated, listing.condition,
                listing.energy_class, listing.heating_type,
                listing.is_private, listing.published_at,
                listing.images, datetime.now(timezone.utc),
            ),
        )


def cleanup_old_entries() -> int:
    """Delete entries older than RETENTION_DAYS. Returns the number of deleted rows."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=RETENTION_DAYS)
    with _get_connection() as conn:
        cursor = conn.execute(
            "DELETE FROM apartments WHERE timestamp < %s",
            (cutoff,),
        )
    return cursor.rowcount
