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
6. Entries older than 30 days are automatically cleaned up

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
- **Meta:** `listing_type` (rent/buy), `portal`, `is_private`, `published_at`, `images`, `sent_at`
