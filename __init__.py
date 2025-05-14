import os

# Determine production mode from environment (default: True in Cloud Run)
PRODUCTION = os.getenv("PRODUCTION", "true").lower() in ("1", "true", "yes")
#PRODUCTION = False

# Set download directory based on environment
if not PRODUCTION:
    # Local development: download into your OneDrive csvs folder
    DOWNLOAD_DIR = r"C:\Users\grand\OneDrive\ZagrebVIz\transparentnost_scraper\csvs"
else:
    # Production (Cloud Run): use /tmp/downloads or override via env var
    DOWNLOAD_DIR = os.getenv("DOWNLOAD_DIR", "/tmp/downloads")
print(f"Download directory: {DOWNLOAD_DIR}")

# Ensure the download directory exists
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

# Log file location
# You can override LOG_DIR via env var; defaults to DOWNLOAD_DIR
LOG_DIR = os.getenv("LOG_DIR", DOWNLOAD_DIR)
LOG_FILE = os.path.join(LOG_DIR, "transparentnost_scraper.log")



