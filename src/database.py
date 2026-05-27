"""PostgreSQL database for deduplication and state persistence."""

import os
from datetime import datetime, timedelta, timezone

import psycopg
from psycopg.rows import tuple_row

from src.models import Listing

DATABASE_URL = os.getenv("DATABASE_URL", "")
RETENTION_DAYS = int(os.getenv("RETENTION_DAYS", "0"))


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

                timestamp               TIMESTAMPTZ NOT NULL
            )
            """
        )
        # Migrations for existing databases
        conn.execute("""
            ALTER TABLE apartments ADD COLUMN IF NOT EXISTS renovation_surcharge REAL
        """)
        # Runs log table
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS scrape_runs (
                id              SERIAL PRIMARY KEY,
                started_at      TIMESTAMPTZ NOT NULL,
                finished_at     TIMESTAMPTZ,
                portal          TEXT,
                search_type     TEXT,
                listings_found  INTEGER DEFAULT 0,
                listings_new    INTEGER DEFAULT 0,
                listings_skipped INTEGER DEFAULT 0,
                error           TEXT
            )
            """
        )
        # Users
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                id       SERIAL PRIMARY KEY,
                name     TEXT NOT NULL UNIQUE,
                api_key  TEXT NOT NULL UNIQUE
            )
            """
        )
        # Per-user listing status (n:m)
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS listing_user_status (
                listing_id  TEXT REFERENCES apartments(id) ON DELETE CASCADE,
                user_id     INTEGER REFERENCES users(id) ON DELETE CASCADE,
                sent_at     TIMESTAMPTZ,
                seen_at     TIMESTAMPTZ,
                PRIMARY KEY (listing_id, user_id)
            )
            """
        )
        # Indices
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_apartments_timestamp ON apartments(timestamp)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_lus_user_id ON listing_user_status(user_id)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_lus_sent_at ON listing_user_status(sent_at) WHERE sent_at IS NULL"
        )
        # One-time migration: seed Lorenz and carry over legacy sent_at → seen_at
        conn.execute(
            """
            INSERT INTO users (name, api_key)
            VALUES ('Lorenz', 'replace-me')
            ON CONFLICT DO NOTHING
            """
        )
        conn.execute(
            """
            DO $$
            BEGIN
                IF EXISTS (
                    SELECT 1 FROM information_schema.columns
                    WHERE table_name = 'apartments' AND column_name = 'sent_at'
                ) THEN
                    INSERT INTO listing_user_status (listing_id, user_id, sent_at, seen_at)
                    SELECT a.id, u.id, a.sent_at, a.sent_at
                    FROM apartments a
                    JOIN users u ON u.name = 'Lorenz'
                    WHERE a.sent_at IS NOT NULL
                    ON CONFLICT DO NOTHING;
                END IF;
            END $$
            """
        )
        conn.execute("ALTER TABLE apartments DROP COLUMN IF EXISTS sent_at")


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
    if RETENTION_DAYS == 0:
        return 0
    cutoff = datetime.now(timezone.utc) - timedelta(days=RETENTION_DAYS)
    with _get_connection() as conn:
        cursor = conn.execute(
            "DELETE FROM apartments WHERE timestamp < %s",
            (cutoff,),
        )
    return cursor.rowcount


def log_run_start(portal: str, search_type: str) -> int:
    """Log the start of a scrape run. Returns the run ID."""
    with _get_connection() as conn:
        row = conn.execute(
            "INSERT INTO scrape_runs (started_at, portal, search_type) VALUES (%s, %s, %s) RETURNING id",
            (datetime.now(timezone.utc), portal, search_type),
        ).fetchone()
    return row[0]


def log_run_end(run_id: int, found: int, new: int, skipped: int, error: str | None = None) -> None:
    """Log the result of a scrape run."""
    with _get_connection() as conn:
        conn.execute(
            """UPDATE scrape_runs
               SET finished_at = %s, listings_found = %s, listings_new = %s,
                   listings_skipped = %s, error = %s
               WHERE id = %s""",
            (datetime.now(timezone.utc), found, new, skipped, error, run_id),
        )
