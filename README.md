# immo-crawler

Async Python scraper that checks real estate portals for new listings at random intervals (5-10 min). Uses mobile APIs exclusively – no headless browser needed.

## Portals

- **Kleinanzeigen** – Android Mobile API
- **ImmoScout24** – iOS Mobile App API
- **Immowelt** (incl. Immonet) – HTML with LZ-String compressed JSON

## How it works

1. All portals are queried sequentially via `httpx`
2. New listings are stored in a SQLite DB (deduplication)
3. New finds are logged
4. Random pause (5-10 min), then repeat
5. Entries older than 30 days are automatically cleaned up

## Quickstart

### Local

```bash
pip install -r requirements.txt
python -m src.main
```

### Docker

```bash
docker compose up -d
docker compose logs -f
```

## Configuration

Everything via environment variables (defaults in `docker-compose.yml`):

| Variable | Description | Example |
|---|---|---|
| `KA_LOCATION_ID` | Kleinanzeigen location | `7667` (Würzburg) |
| `KA_CATEGORY_IDS` | Categories (comma-separated) | `203,205` |
| `KA_DISTANCE` | Search radius in km | `10` |
| `IS24_GEOCOORDINATES` | lat;lon;radius | `49.79426;9.92748;5.0` |
| `IS24_REAL_ESTATE_TYPE` | Real estate type | `apartmentrent` |
| `IW_LOCATIONS` | Immowelt location ID | `AD08DE7873` |
| `IW_DISTRIBUTION_TYPES` | Rent/Buy | `Rent` or `Buy,Buy_Auction` |
| `IW_ESTATE_TYPES` | Estate type | `Apartment,House` |
| `PROXY_URL` | Residential proxy (optional) | `http://user:pass@proxy:port` |
| `INTERVAL_MIN` / `INTERVAL_MAX` | Pause in seconds | `300` / `600` |

### Finding location IDs

- **Kleinanzeigen:** URL contains e.g. `l7667` → `KA_LOCATION_ID=7667`
- **ImmoScout24:** Coordinates + radius from the search URL
- **Immowelt:** URL contains `locations=AD08DE7873`
