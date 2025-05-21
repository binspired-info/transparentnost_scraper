import os
import time
import logging
import uuid
import datetime
from selenium import webdriver
from selenium.webdriver.chrome.service import Service

# Basic logging setup
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Basic configuration
PRODUCTION = os.getenv("PRODUCTION", "False").lower() == "true"
HEADLESS = True

# Download directory setup
if PRODUCTION:
    DOWNLOAD_DIR = os.getenv("DOWNLOAD_DIR", "/tmp/downloads")  # Use env var or default
else:
    MAIN_DIR = os.path.dirname(os.path.abspath(__file__))
    DOWNLOAD_DIR = os.path.join(MAIN_DIR, "csvs")

# Create download directory if it doesn't exist
os.makedirs(DOWNLOAD_DIR, exist_ok=True)
logger.info(f"Download directory: {DOWNLOAD_DIR}")

class TransparentnostScraper():
    def __init__(self):
        # Create unique run ID for this session
        self.run_id = datetime.datetime.now().strftime("%Y%m%d_%H%M%S") + "_" + str(uuid.uuid4())[:8]
        # Create snapshots directory
        self.snapshot_dir = os.path.join(DOWNLOAD_DIR, "screenshots", self.run_id)
        os.makedirs(self.snapshot_dir, exist_ok=True)
        self.snapshot_counter = 1
        logger.info(f"Snapshot directory: {self.snapshot_dir}")

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

        try:
            logger.info("Creating Chrome driver...")
            driver = webdriver.Chrome(service=service, options=options)
            self._take_snapshot(driver, "after_driver_creation")
            
            logger.info("Loading target page...")
            driver.get("https://transparentnost.zagreb.hr/isplate/sc-isplate")
            self._take_snapshot(driver, "after_page_load")
            logger.info(f"Current URL: {driver.current_url}")
            
            
        except Exception as e:
            logger.error(f"Failed to create/use Chrome driver: {e}")
            raise
        finally:
            if 'driver' in locals():
                self._take_snapshot(driver, "final")
                driver.quit()
                logger.info("Browser closed")

if __name__ == '__main__':
    app = TransparentnostScraper()
    app.webscrape()