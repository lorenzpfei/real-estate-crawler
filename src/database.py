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
                id                      TEXT PRIMARY KEY,
                portal                  TEXT NOT NULL,
                title                   TEXT,
                url                     TEXT,

                warm_rent               REAL,
                cold_rent               REAL,
                extra_costs             REAL,
                deposit                 REAL,

                buy_price               REAL,
                hausgeld                REAL,
                commission_percent      REAL,
                original_price          REAL,

                price_per_sqm           REAL,
                listing_type            TEXT DEFAULT '',
                renovation_surcharge    REAL,

                rooms                   REAL,
                living_space            REAL,
                plot_space              REAL,
                floor                   INTEGER,
                total_floors            INTEGER,
                bedrooms                REAL,
                bathrooms               REAL,
                property_type           TEXT DEFAULT '',

                city                    TEXT DEFAULT '',
                zip_code                TEXT DEFAULT '',
                district                TEXT DEFAULT '',
                street                  TEXT DEFAULT '',
                latitude                REAL,
                longitude               REAL,

                description             TEXT DEFAULT '',
                equipment               TEXT DEFAULT '',
                location_description    TEXT DEFAULT '',
                other_info              TEXT DEFAULT '',

                year_built              INTEGER,
                year_renovated          INTEGER,
                condition               TEXT DEFAULT '',
                energy_class            TEXT DEFAULT '',
                heating_type            TEXT DEFAULT '',

                has_balcony             BOOLEAN,
                has_garden              BOOLEAN,
                has_parking             BOOLEAN,
                has_elevator            BOOLEAN,
                has_cellar              BOOLEAN,
                has_fitted_kitchen      BOOLEAN,
                num_units_in_building   INTEGER,
                available_from          TEXT DEFAULT '',
                pets_allowed            BOOLEAN,
                is_temporary            BOOLEAN,

                is_private              BOOLEAN,
                published_at            TIMESTAMPTZ,
                images                  TEXT[] DEFAULT '{}',

                sent_at                 TIMESTAMPTZ,
                timestamp               TIMESTAMPTZ NOT NULL
            )
            """
        )
        # Migrations for existing databases
        conn.execute("""
            ALTER TABLE apartments ADD COLUMN IF NOT EXISTS renovation_surcharge REAL
        """)


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
                warm_rent, cold_rent, extra_costs, deposit,
                buy_price, hausgeld, commission_percent, original_price,
                price_per_sqm, listing_type, renovation_surcharge,
                rooms, living_space, plot_space, floor, total_floors, bedrooms, bathrooms,
                property_type,
                city, zip_code, district, street, latitude, longitude,
                description, equipment, location_description, other_info,
                year_built, year_renovated, condition, energy_class, heating_type,
                has_balcony, has_garden, has_parking, has_elevator, has_cellar,
                has_fitted_kitchen, num_units_in_building, available_from,
                pets_allowed, is_temporary,
                is_private, published_at, images, timestamp
            ) VALUES (
                %s, %s, %s, %s,
                %s, %s, %s, %s,
                %s, %s, %s, %s,
                %s, %s, %s,
                %s, %s, %s, %s, %s, %s, %s,
                %s,
                %s, %s, %s, %s, %s, %s,
                %s, %s, %s, %s,
                %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s,
                %s, %s, %s,
                %s, %s,
                %s, %s, %s, %s
            ) ON CONFLICT (id) DO NOTHING
            """,
            (
                listing.id, listing.portal, listing.title, listing.url,
                listing.warm_rent, listing.cold_rent, listing.extra_costs, listing.deposit,
                listing.buy_price, listing.hausgeld, listing.commission_percent,
                listing.original_price,
                listing.price_per_sqm, listing.listing_type, listing.renovation_surcharge,
                listing.rooms, listing.living_space, listing.plot_space,
                listing.floor, listing.total_floors, listing.bedrooms, listing.bathrooms,
                listing.property_type,
                listing.city, listing.zip_code, listing.district, listing.street,
                listing.latitude, listing.longitude,
                listing.description, listing.equipment,
                listing.location_description, listing.other_info,
                listing.year_built, listing.year_renovated, listing.condition,
                listing.energy_class, listing.heating_type,
                listing.has_balcony, listing.has_garden, listing.has_parking,
                listing.has_elevator, listing.has_cellar,
                listing.has_fitted_kitchen, listing.num_units_in_building,
                listing.available_from,
                listing.pets_allowed, listing.is_temporary,
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
