# immo-crawler

Async Python scraper that monitors German real estate portals for new listings. Uses mobile APIs exclusively – no headless browser needed. New listings are enriched via GPT and stored in PostgreSQL.

## Portals

- **Kleinanzeigen** – Android Mobile API
- **ImmoScout24** – iOS Mobile App API (incl. expose detail fetch)
- **Immowelt** (incl. Immonet) – HTML with LZ-String compressed JSON

## How it works

1. All portals are queried sequentially via `httpx` (rent + buy)
2. New listings are deduplicated against PostgreSQL
3. GPT extracts structured data from descriptions (balcony, parking, etc.)
4. Random pause (37-77 min jitter), then repeat
5. Only active during configured hours (default 8:00-22:00)
6. Optionally cleans up entries older than `RETENTION_DAYS` (default: 0 = keep forever)

## Quickstart

```bash
cp .env.example .env
# Edit .env with your values (see Configuration below)
pip install -r requirements.txt
python -m src.main
```

### Docker

```bash
cp .env.example .env
# Edit .env
docker compose up -d
docker compose logs -f
```

## Configuration

All settings are controlled via `.env`. Copy `.env.example` and adjust:

### Database

| Variable | Description | Example |
|---|---|---|
| `DATABASE_URL` | PostgreSQL connection string | `postgresql://user:pass@host:port/db` |

### OpenAI (for AI enrichment)

| Variable | Description | Default |
|---|---|---|
| `OPENAI_API_KEY` | Your OpenAI API key | required |
| `OPENAI_MODEL` | Model for data extraction | `gpt-5.4-mini` |

If no API key is set, enrichment is skipped gracefully.

### Kleinanzeigen

| Variable | Description | Example |
|---|---|---|
| `KA_LOCATION_ID` | Location ID | `7667` |
| `KA_DISTANCE` | Search radius in km | `10` |
| `KA_CATEGORY_IDS` | Categories, comma-separated | `203,205,196,208` |
| `KA_QUERY` | Optional search query | `` |

**Category IDs:**
- `203` – Apartment rent (Wohnung mieten)
- `205` – House rent (Haus mieten)
- `196` – Apartment buy (Wohnung kaufen)
- `208` – House buy (Haus kaufen)

**Finding your location ID:** Go to [kleinanzeigen.de](https://www.kleinanzeigen.de), search for your city, and look at the URL. It contains e.g. `l7667` – that number is your `KA_LOCATION_ID`.

### ImmoScout24

| Variable | Description | Example |
|---|---|---|
| `IS24_REAL_ESTATE_TYPES` | Types, comma-separated | `apartmentrent,apartmentbuy,housebuy` |
| `IS24_GEOCOORDINATES` | `lat;lon;radius_km` | `49.79426;9.92748;5.0` |
| `IS24_PRICE_MIN` | Min price filter (0 = off) | `0` |
| `IS24_PRICE_MAX` | Max price filter (0 = off) | `0` |

**Real estate types:** `apartmentrent`, `apartmentbuy`, `houserent`, `housebuy`

**Finding your coordinates:** Go to [immobilienscout24.de](https://www.immobilienscout24.de), search for your area, and look at the URL. It contains `geocoordinates=49.79426;9.92748;5.0` (lat;lon;radius).

### Immowelt

| Variable | Description | Example |
|---|---|---|
| `IW_SEARCHES` | Search definitions, separated by `;` | `Rent\|Apartment,House;Buy\|House,Apartment` |
| `IW_LOCATIONS` | Location ID | `AD08DE7873` |

Each search is formatted as `distributionTypes|estateTypes`. Use `;` to define multiple searches.

**Distribution types:** `Rent`, `Buy`, `Buy_Auction`, `Compulsory_Auction`
**Estate types:** `Apartment`, `House`

**Finding your location ID:** Go to [immowelt.de](https://www.immowelt.de), search for your city, and look at the URL. It contains `locations=AD08DE7873` – that's your `IW_LOCATIONS`.

### Scheduling

| Variable | Description | Default |
|---|---|---|
| `INTERVAL_MIN` | Min pause between runs (seconds) | `2220` (37 min) |
| `INTERVAL_MAX` | Max pause between runs (seconds) | `4620` (77 min) |
| `ACTIVE_HOUR_START` | Start of active window (hour) | `8` |
| `ACTIVE_HOUR_END` | End of active window (hour) | `22` |
| `TIMEZONE` | Timezone for active hours | `Europe/Berlin` |
| `RETENTION_DAYS` | Delete listings older than N days (0 = keep forever) | `0` |

### Proxy (optional)

| Variable | Description | Example |
|---|---|---|
| `PROXY_URL` | Residential proxy | `http://user:pass@proxy:port` |

## Database schema

Listings are stored in a PostgreSQL `apartments` table with 52 columns including:

- **Rent fields:** `warm_rent`, `cold_rent`, `extra_costs`, `deposit`
- **Buy fields:** `buy_price`, `hausgeld`, `commission_percent`, `original_price`
- **Property:** `rooms`, `living_space`, `plot_space`, `floor`, `bedrooms`, `bathrooms`
- **Location:** `city`, `zip_code`, `district`, `street`, `latitude`, `longitude`
- **Texts:** `description`, `equipment`, `location_description`
- **Building:** `year_built`, `year_renovated`, `condition`, `energy_class`, `heating_type`
- **AI-extracted:** `has_balcony`, `has_garden`, `has_parking`, `has_elevator`, `has_cellar`, `has_fitted_kitchen`, `num_units_in_building`, `pets_allowed`, `is_temporary`
- **Meta:** `listing_type` (rent/buy), `portal`, `is_private`, `published_at`, `images`, `timestamp`

Per-user send/seen tracking is stored separately in `listing_user_status` (n:m between `apartments` and `users`).

---

## Deploying the API (Cloudflare Worker)

The `worker/` directory contains a Cloudflare Worker that serves the listings API.

### Prerequisites

- [Node.js](https://nodejs.org) + [pnpm](https://pnpm.io)
- A [Cloudflare account](https://cloudflare.com) with a domain

### Setup

```bash
cd worker
pnpm install
pnpm wrangler login
```

Create the KV namespace for API key caching:

```bash
pnpm wrangler kv namespace create API_KEY_CACHE
# Copy the returned ID into worker/wrangler.jsonc
```

Set your Supabase URL in `worker/wrangler.jsonc`:

```jsonc
"vars": {
  "SUPABASE_URL": "https://your-project.supabase.co"
}
```

Set your Supabase service role key as a secret:

```bash
pnpm wrangler secret put SUPABASE_SERVICE_ROLE_KEY
```

Update the route in `worker/wrangler.jsonc` to your domain:

```jsonc
"routes": [
  { "pattern": "immo.yourdomain.com/*", "zone_name": "yourdomain.com" }
]
```

Deploy:

```bash
pnpm wrangler deploy
```

### Adding users

Insert users directly into the `users` table in your database:

```sql
INSERT INTO users (name, api_key) VALUES ('Alice', gen_random_uuid());
SELECT name, api_key FROM users;
```

---

## API

Base URL: `https://immo.example.com`

All endpoints require authentication via the `X-API-Key` header.

### Authentication

```
X-API-Key: <your-api-key>
```

Keys are managed in the `users` table. Contact the admin to get a key.

---

### `GET /listings`

Returns real estate listings.

**Query Parameters**

| Parameter | Type | Description |
|---|---|---|
| `listing_type` | `rent` \| `buy` | Filter by listing type |
| `portal` | `kleinanzeigen` \| `immoscout24` \| `immowelt` | Filter by source portal |
| `city` | string | Case-insensitive partial match on city name |
| `zip_code` | string | Exact match on zip code |
| `min_rooms` | number | Minimum number of rooms |
| `min_space` | number | Minimum living space in m² |
| `max_price` | number | Max cold rent (if `listing_type=rent`) or max buy price (if `listing_type=buy`) |
| `since` | date (`YYYY-MM-DD`) | Only listings crawled on or after this date |
| `limit` | number | Number of results (default: 500, `0` = all) |
| `offset` | number | Pagination offset (default: 0) |
| `sort` | `desc` \| `asc` | Sort by timestamp (default: `desc`) |
| `format` | `json` \| `csv` | Response format (default: `json`, CSV defaults to all rows) |

Results are ordered by `timestamp` descending. Responses are cached for 5 minutes at the edge.

**Examples**

```bash
# All rent listings with ≥3 rooms
curl -H "X-API-Key: <key>" "https://immo.example.com/listings?listing_type=rent&min_rooms=3"

# Buy listings under 400k as CSV
curl -H "X-API-Key: <key>" "https://immo.example.com/listings?listing_type=buy&max_price=400000&format=csv" -o listings.csv

# Listings crawled today
curl -H "X-API-Key: <key>" "https://immo.example.com/listings?since=2026-05-27"

# Paginate through all results
curl -H "X-API-Key: <key>" "https://immo.example.com/listings?limit=1000&offset=1000"
```

**Error Responses**

| Status | Meaning |
|---|---|
| 401 | Missing `X-API-Key` header |
| 403 | Invalid API key |
| 404 | Unknown endpoint |
| 502 | Database error |

---

### `PATCH /listings/:id/sent`

Marks a listing as sent (and seen) for the authenticated user. Creates the record if it doesn't exist yet.

```bash
curl -X PATCH -H "X-API-Key: <key>" "https://immo.example.com/listings/ka-12345/sent"
# → {"ok":true}
```

---

### `PATCH /listings/:id/seen`

Marks a listing as seen for the authenticated user. Updates the `seen_at` timestamp on an existing record.

```bash
curl -X PATCH -H "X-API-Key: <key>" "https://immo.example.com/listings/ka-12345/seen"
# → {"ok":true}
```

---

### `GET /listings?unsent=true`

Returns only listings that have not yet been sent to the authenticated user. Supports all the same filters as `GET /listings`.

```bash
curl -H "X-API-Key: <key>" "https://immo.example.com/listings?unsent=true&listing_type=rent"
```
