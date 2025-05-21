import os
import time
import logging
import datetime
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from google.cloud import storage

# Basic logging setup
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Basic configuration
PRODUCTION = os.getenv("PRODUCTION", "False").lower() == "true"
HEADLESS = PRODUCTION
SNAPSHOTS = True

# Download directory setup
if PRODUCTION:
    DOWNLOAD_DIR = os.getenv("DOWNLOAD_DIR", "/tmp/downloads")  # Use env var or default
    if SNAPSHOTS:
        SNAPSHOT_DIR = os.getenv("SNAPSHOT_DIR", "/tmp/snapshots")
else:
    MAIN_DIR = os.path.dirname(os.path.abspath(__file__))
    DOWNLOAD_DIR = os.path.join(MAIN_DIR, "csvs")
    if SNAPSHOTS:
        SNAPSHOT_DIR = os.path.join(MAIN_DIR, "snapshots")

# Create download directory if it doesn't exist
os.makedirs(DOWNLOAD_DIR, exist_ok=True)
logger.info(f"Download directory: {DOWNLOAD_DIR}")

class GCSHandler:
    def __init__(self, bucket_name=None):
        self.bucket_name = bucket_name or os.getenv('OUTPUT_BUCKET', '').replace('gs://', '')
        self.client = storage.Client(project="zagreb-viz")
        self.bucket = self.client.bucket(self.bucket_name)
        self.run_id = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")

    def upload_directory(self, local_dir: str):
        """Upload entire directory to GCS, maintaining folder structure."""
        if not os.path.exists(local_dir):
            logger.warning(f"Directory does not exist: {local_dir}")
            return

        for root, _, files in os.walk(local_dir):
            for file in files:
                local_path = os.path.join(root, file)
                relative_path = os.path.relpath(local_path, local_dir)
                # Store directly in run_id folder
                blob_name = f"{self.run_id}/{relative_path}"
                
                blob = self.bucket.blob(blob_name)
                blob.upload_from_filename(local_path)
                logger.info(f"Uploaded {local_path} to gs://{self.bucket_name}/{blob_name}")

class TransparentnostScraper():
    def __init__(self):
        # Create a unique subdirectory for each run (always local)
        if SNAPSHOTS:
            self.run_id = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            self.snapshot_dir = os.path.join(SNAPSHOT_DIR, self.run_id)
            os.makedirs(self.snapshot_dir, exist_ok=True)
            self.snapshot_counter = 1

        # Initialize GCS handler
        if PRODUCTION:
            self.gcs = GCSHandler()
    
    def upload_snapshots(self):
        """Upload all results to GCS."""
        try:
            # Upload screenshots if enabled
            if SNAPSHOTS and hasattr(self, 'snapshot_dir'):
                self.gcs.upload_directory(self.snapshot_dir)
            logger.info("All files uploaded to GCS successfully")
        except Exception as e:
            logger.error(f"Failed to upload to GCS: {e}")
            raise

    def _take_snapshot(self, driver, label, current_date=None):
        """Take a screenshot with a numerated label and optional date."""
        time.sleep(1)  # Allow time for the page to load
        try:
            date_str = current_date.strftime('%Y_%m_%d') if current_date else "nodate"
            fname = f"{self.snapshot_counter:02d}_{label}_{date_str}.png"
            path = os.path.join(self.snapshot_dir, fname)
            
            driver.save_screenshot(path)
            logger.info(f"Snapshot saved: {fname}")
            self.snapshot_counter += 1
        except Exception as e:
            logger.error(f"Failed to save snapshot: {e}")

    def webscrape(self):
        driver = None
        try:
            # Chrome setup
            if not PRODUCTION:
                from webdriver_manager.chrome import ChromeDriverManager
                service = Service(ChromeDriverManager().install())
                options = webdriver.ChromeOptions()
            else:
                service = Service('/usr/bin/chromedriver')
                options = webdriver.ChromeOptions()
                options.binary_location = '/usr/bin/chromium'

            # Required flags for headless Chrome
            if HEADLESS:
                options.add_argument('--headless=new')
                options.add_argument('--no-sandbox')
                options.add_argument('--disable-dev-shm-usage')
                options.add_argument('--disable-gpu')

            logger.info("Creating Chrome driver...")
            driver = webdriver.Chrome(service=service, options=options)
            
            logger.info("Loading target page...")
            driver.get("https://transparentnost.zagreb.hr/isplate/sc-isplate")
            self._take_snapshot(driver, "after_page_load")
            logger.info(f"Current URL: {driver.current_url}")
            
        except Exception as e:
            logger.error(f"Scraper failed: {e}")
            if driver:
                self._take_snapshot(driver, "error")
            raise
        finally:
            if driver:
                self._take_snapshot(driver, "final")
                if SNAPSHOTS and PRODUCTION:
                    self.upload_snapshots()
                driver.quit()
                logger.info("Browser closed")

if __name__ == '__main__':
    try:
        app = TransparentnostScraper()
        app.webscrape()
    except Exception as e:
        logger.error(f"Scraper failed: {e}")
        raise
    else:
        logger.info("Scraper completed successfully")