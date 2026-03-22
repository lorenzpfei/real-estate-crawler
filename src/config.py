"""Central configuration via environment variables."""

import os


# Kleinanzeigen (Würzburg, apartment rent + house rent)
KA_QUERY = os.getenv("KA_QUERY", "")
KA_LOCATION_ID = os.getenv("KA_LOCATION_ID", "7667")
KA_DISTANCE = int(os.getenv("KA_DISTANCE", "10"))
KA_CATEGORY_IDS = os.getenv("KA_CATEGORY_IDS", "203,205")  # comma-separated

# ImmoScout24 (Würzburg, apartment rent, 5km radius)
IS24_REAL_ESTATE_TYPE = os.getenv("IS24_REAL_ESTATE_TYPE", "apartmentrent")
IS24_GEOCOORDINATES = os.getenv("IS24_GEOCOORDINATES", "49.79426;9.92748;5.0")
IS24_PRICE_MIN = int(os.getenv("IS24_PRICE_MIN", "0"))
IS24_PRICE_MAX = int(os.getenv("IS24_PRICE_MAX", "0"))

# Immowelt (incl. Immonet) – Würzburg, buy house+apartment
IW_DISTRIBUTION_TYPES = os.getenv("IW_DISTRIBUTION_TYPES", "Buy,Buy_Auction,Compulsory_Auction")
IW_ESTATE_TYPES = os.getenv("IW_ESTATE_TYPES", "House,Apartment")
IW_LOCATIONS = os.getenv("IW_LOCATIONS", "AD08DE7873")

# Scheduling
INTERVAL_MIN = int(os.getenv("INTERVAL_MIN", "300"))   # 5 minutes
INTERVAL_MAX = int(os.getenv("INTERVAL_MAX", "600"))   # 10 minutes
