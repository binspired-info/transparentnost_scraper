import os

# Determine production mode from environment (default: True in Cloud Run)
PRODUCTION = False

# ─── CONFIG ─────────────────────────────────────────────────────────────────────────
PROJECT    = "zagreb-viz"
DATASET    = "transparentnost"
TABLE      = "isplate_master"
CSV_BUCKET = "zagreb-viz-raw-csvs"  # or None to skip archiving
# ────────────────────────────────────────────────────────────────────────────────────

# Set download directory based on environment
if not PRODUCTION:
    # Local development: download into your OneDrive csvs folder
    MAIN_DIR = os.path.dirname(os.path.abspath(__file__))
    DOWNLOAD_DIR = os.path.join(MAIN_DIR, "csvs")
    SNAPSHOT_DIR = os.path.join(MAIN_DIR, "screenshots")
    LOG_FILE = os.path.join(MAIN_DIR, "transparentnost_scraper.log")
    HEADLESS = False
else:
    # Production (Cloud Run): use /tmp/downloads or override via env var
    HEADLESS = True