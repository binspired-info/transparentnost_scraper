import os

# Determine production mode from environment (default: True in Cloud Run)
PRODUCTION = os.getenv("PRODUCTION", "true").lower() in ("1", "true", "yes")

# Directory where CSVs are downloaded
# In Cloud Run, set DOWNLOAD_DIR via env var; default to /tmp/downloads
DOWNLOAD_DIR = os.getenv("DOWNLOAD_DIR", "/tmp/downloads")
# Ensure the download directory exists
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

# Log file location
# You can override LOG_DIR via env var; defaults to DOWNLOAD_DIR
LOG_DIR = os.getenv("LOG_DIR", DOWNLOAD_DIR)
LOG_FILE = os.path.join(LOG_DIR, "transparentnost_scraper.log")
