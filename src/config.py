"""Central configuration via environment variables."""

import os


# Kleinanzeigen
KA_QUERY = os.getenv("KA_QUERY", "")
KA_LOCATION_ID = os.getenv("KA_LOCATION_ID", "")
KA_DISTANCE = int(os.getenv("KA_DISTANCE", "0"))
KA_CATEGORY_IDS = os.getenv("KA_CATEGORY_IDS", "")  # comma-separated

# ImmoScout24
IS24_REAL_ESTATE_TYPE = os.getenv("IS24_REAL_ESTATE_TYPE", "apartmentrent")
IS24_GEOCOORDINATES = os.getenv("IS24_GEOCOORDINATES", "")
IS24_PRICE_MIN = int(os.getenv("IS24_PRICE_MIN", "0"))
IS24_PRICE_MAX = int(os.getenv("IS24_PRICE_MAX", "0"))

# Immowelt (incl. Immonet)
IW_DISTRIBUTION_TYPES = os.getenv("IW_DISTRIBUTION_TYPES", "")
IW_ESTATE_TYPES = os.getenv("IW_ESTATE_TYPES", "")
IW_LOCATIONS = os.getenv("IW_LOCATIONS", "")

# Scheduling
INTERVAL_MIN = int(os.getenv("INTERVAL_MIN", "2220"))   # 37 minutes
INTERVAL_MAX = int(os.getenv("INTERVAL_MAX", "4620"))   # 77 minutes
ACTIVE_HOUR_START = int(os.getenv("ACTIVE_HOUR_START", "8"))
ACTIVE_HOUR_END = int(os.getenv("ACTIVE_HOUR_END", "22"))
TIMEZONE = os.getenv("TIMEZONE", "Europe/Berlin")
