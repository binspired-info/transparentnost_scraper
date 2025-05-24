import os
import sys
# Ensure console handles Unicode code
sys.stdout.reconfigure(encoding='utf-8')
sys.stderr.reconfigure(encoding='utf-8')
import time
import glob
import logging
import datetime
import requests
import traceback
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.wait import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import NoSuchElementException
from bq_handler import BQHandler
from google.cloud import storage

""" --- Configuration --- """
PRODUCTION = os.getenv("PRODUCTION", "False").lower() == "true"
HEADLESS = PRODUCTION
SNAPSHOTS = False
# Set download directory based on environment
if PRODUCTION:
    # Cloud Run: download into /tmp (ephemeral storage)
    DOWNLOAD_DIR = os.getenv("DOWNLOAD_DIR", "/tmp/downloads")
    LOG_DIR = os.getenv("LOG_DIR", DOWNLOAD_DIR)
    LOG_FILE = os.path.join(LOG_DIR, "transparentnost_scraper.log")
    if SNAPSHOTS:
        SNAPSHOT_DIR = os.getenv("SNAPSHOT_DIR", "/tmp/snapshots")
else:
    # Local development: download into your OneDrive csvs folder
    MAIN_DIR = os.path.dirname(os.path.abspath(__file__))
    DOWNLOAD_DIR = os.path.join(MAIN_DIR, "csvs")
    LOG_DIR = os.path.join(MAIN_DIR, "logger")
    LOG_FILE = os.path.join(LOG_DIR, "transparentnost_scraper.log")
    if SNAPSHOTS:
        SNAPSHOT_DIR = os.path.join(MAIN_DIR, "snapshots")
    CLEAN_DIR = False
os.makedirs(DOWNLOAD_DIR, exist_ok=True)
if SNAPSHOTS:
    os.makedirs(SNAPSHOT_DIR, exist_ok=True)

""" --- Slack alerting --- """
# Slack webhook URL (set via env var in Cloud Run or locally)
SLACK_WEBHOOK = os.getenv("SLACK_WEBHOOK_URL")
def alert_slack(message: str):
    if SLACK_WEBHOOK:
        try:
            requests.post(SLACK_WEBHOOK, json={"text": message}, timeout=5)
        except Exception as e:
            logging.error(f"Failed to send Slack alert: {e}")

""" --- Logging setup --- """
logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(LOG_FILE, encoding='utf-8'),
            logging.StreamHandler()
        ]
    )
logger = logging.getLogger(__name__)

class GCSHandler:
    """Google Cloud Storage handler for uploading files.
    Jedino se koristi za upload screenshot-ova stranice, ako se to želi (SNAPSHOTS=True).
    """

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
                blob_name = f"{self.run_id}/{relative_path}"
                
                blob = self.bucket.blob(blob_name)
                blob.upload_from_filename(local_path)
                logger.info(f"Uploaded {local_path} to gs://{self.bucket_name}/{blob_name}")

class TransparentnostScraper():
    def __init__(self):
        """ --- Initial settings --- """
        # production mode
        logger.info(f"--- Running in {'production' if PRODUCTION else 'development'} mode.")
        # Check for already downloaded dates
        #self.already_downloaded_dates = self._check_for_downloaded_dates()
        # Get the last date from BigQuery (a datetime.date)
        last = BQHandler().get_last_date()
        self.last_date_tbl = last.date() if last else datetime.datetime(2024, 1, 1)

        if SNAPSHOTS: # Create a unique subdirectory for each run (always local)
            self.run_id = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            self.snapshot_dir = os.path.join(SNAPSHOT_DIR, self.run_id)
            os.makedirs(self.snapshot_dir, exist_ok=True)
            self.snapshot_counter = 1
            if PRODUCTION:
                self.gcs = GCSHandler()
    
    def upload_snapshots(self):
        """Upload all results to GCS."""
        try:
            if SNAPSHOTS and hasattr(self, 'snapshot_dir'):
                self.gcs.upload_directory(self.snapshot_dir)
            logger.info("All files uploaded to GCS successfully")
        except Exception as e:
            logger.error(f"Failed to upload to GCS: {e}")
            raise

    def _take_snapshot(self, driver, label, current_date=None):
        """Take a screenshot with a numerated label and optional date. Always save locally."""
        time.sleep(0.5)
        if SNAPSHOTS:
            try:
                date_str = current_date.strftime('%Y_%m_%d') if current_date else "nodate"
                fname = f"{self.snapshot_counter:02d}_{label}_{date_str}.png"
                path = os.path.join(self.snapshot_dir, fname)
                driver.save_screenshot(path)
                logger.info(f"Snapshot saved: {fname}")
                self.snapshot_counter += 1
            except Exception as e:
                logger.error(f"Failed to save snapshot: {e}")

    def _check_for_downloaded_dates(self):
        """Check for already downloaded dates in the download directory."""
        downloaded_files = glob.glob(os.path.join(DOWNLOAD_DIR, '*.csv'))
        if CLEAN_DIR:
            for f in downloaded_files:
                os.remove(f)
            logger.info("Download directory cleaned.")
            return []
        dates = []
        for file in downloaded_files:
            parts = os.path.basename(file).split('_')
            if len(parts) >= 2:
                datestr = parts[1].replace('.csv','')
                try:
                    dates.append(datetime.datetime.strptime(datestr, "%Y_%m_%d"))
                except:
                    continue
        dates.sort()
        logger.info(f"Found {len(dates)} downloaded dates.")
        return dates

    def set_dates(self, date_interval=None):
        """Set the date interval for scraping."""
        if date_interval:
            # date_interval contains two datetime.datetime objects
            self.start_date, self.end_date = date_interval
        else:
            # If our last loaded date is before 2024, start at Jan 2, 2024
            if self.last_date_tbl.year < 2024:
                self.start_date = datetime.datetime(2024, 1, 2)
            else:
                # Next day after last_date_tbl
                self.start_date = self.last_date_tbl + datetime.timedelta(days=1)
            # Use current time as the end of the interval
            self.end_date = datetime.datetime.now().date()
        self.days_to_scrape = (self.end_date - self.start_date).days
        logger.info(f"--- Scraping from dates {self.start_date} to {self.end_date} ({self.days_to_scrape} days) ---")

    def webscrape(self):
        def _get_webdriver():
            """ --- Settings --- """
            if not PRODUCTION:
                from webdriver_manager.chrome import ChromeDriverManager
                service = Service(ChromeDriverManager().install())
                options = webdriver.ChromeOptions()
            else:
                service = Service('/usr/bin/chromedriver')
                options = webdriver.ChromeOptions()
                options.binary_location = '/usr/bin/chromium'

            # 1) Set the download directory
            options.add_experimental_option('prefs', {'download.default_directory': DOWNLOAD_DIR})

            # 2) Required flags for headless Chrome in container environments
            if HEADLESS:
                options.add_argument('--headless=new')          # or '--headless' for older Chrome versions
                options.add_argument('--no-sandbox')            # bypass OS security model
                options.add_argument('--disable-dev-shm-usage') # overcome limited /dev/shm
                options.add_argument('--disable-gpu')           # recommended for headless
                options.add_argument('--remote-debugging-port=9222')
                options.add_argument('--single-process')    # disable extensions

            try:
                logger.info("Creating Chrome driver...")
                driver = webdriver.Chrome(service=service, options=options)
            except Exception as e:
                logger.error(f"Failed to create Chrome driver: {e}")
                raise
            driver.get("https://transparentnost.zagreb.hr/isplate/sc-isplate")
            logger.info(f"Driver setup complete. Current URL: {driver.current_url}")
            return driver


        def _date_filter_activated(timeout=15):
            end = time.time() + timeout

            # First check if filter_xpath window is open
            filter_xpath = base_xpath + 'content/main/isplate-details-component/section/div/div/filters/button'
            filter_base = base_xpath + 'content/main/isplate-details-component/section/div/div/filters/div/div/div[3]/div[2]/div/filter-input/'
            # Check if filter panel is open by checking for the presence of the date filter input
            try:
                driver.find_element(By.XPATH, filter_base + 'filter-input-value-type[1]/filter-date-picker/div/input')
                # Filter panel is already open, continue
            except NoSuchElementException:
                # Filter panel is not open, click to open it
                WebDriverWait(driver, 10).until(EC.element_to_be_clickable((By.XPATH, filter_xpath))).click()

            # Click on the date filter button
            WebDriverWait(driver, 10).until(EC.element_to_be_clickable((By.XPATH, filter_base+'button'))).click()
            
            # Confirm the date filter has been activated
            applied_filter_xpath = base_xpath + 'content/main/isplate-details-component/section/div/div[2]/filters/div/div'
            while time.time() < end:
                try:
                    applied_filter_text = driver.find_element(By.XPATH, applied_filter_xpath).text
                    date_to_check = current_date.strftime('%d.%m.%Y.')
                    if PRODUCTION:
                        date_to_check = (current_date - datetime.timedelta(days=1)).strftime('%d.%m.%Y.')
                    if ('Datum:' in applied_filter_text) and (date_to_check in applied_filter_text):
                        logger.info(f"2) Filter active: {repr(applied_filter_text)}")
                        return True
                except:
                    pass
                time.sleep(1)
            return False
        
        def _wait_for_table_or_content_date(expected_date, timeout=30):
            """
            Wait for either:
            - The table's first row to match the expected date, or
            - If no table after timeout, treat as weekend/holiday (return False)
            """
            end = time.time() + timeout
            first_date_xpath = base_xpath + '/content/main/isplate-details-component/section/div/table-component/div/div[2]/table-row-component[1]/a/div/div[1]/span'
            content_xpath = base_xpath + '/content/main/isplate-details-component/section/div/div[1]/span'
            loop_count = 0
            last_content = ""
            while time.time() < end:
                try:
                    first_date_in_tbl = driver.find_element(By.XPATH, first_date_xpath).text
                    if expected_date.strftime('%d.%m.%Y.') in first_date_in_tbl:
                        logger.info(f"3a) Table content loaded: {repr(first_date_in_tbl)} (checked {loop_count+1} times)")
                        return True
                except NoSuchElementException:
                    pass
                try:
                    content = driver.find_element(By.XPATH, content_xpath).text
                    last_content = content
                except Exception:
                    pass
                loop_count += 1
                time.sleep(1)
            # Only after timeout, decide if it's really a no-data day
            if last_content == 'Suma filtriranih stavki: 0,00':
                logger.info(f"3a) No data for {expected_date.strftime('%d.%m.%Y.')}, likely weekend/holiday.")
                return False
            logger.warning(f"Table/content did not update to expected date {expected_date.strftime('%d.%m.%Y.')}")
            return False
        
        def _download_click(timeout=10):
            end = time.time() + timeout
            # Download button path
            download_xpath = base_xpath + 'content/main/isplate-details-component/section/div/div[2]/div'
            while time.time() < end:
                try:
                    driver.find_element(By.XPATH, download_xpath).click()
                    logger.info("4) Download button clicked")
                    return True
                except:
                    pass
                time.sleep(1)
            logger.info("4) Download button not clickable")
            return False

        def _download_success(filename, timeout=30):
            end = time.time() + timeout
            while time.time() < end:
                path = os.path.join(DOWNLOAD_DIR, filename)
                if os.path.exists(path) and not os.path.exists(path + '.crdownload'):
                    logger.info(f"5) Download completed.")
                    return True
                time.sleep(1)
            return False

        def _rename_csv():
            original = os.path.join(DOWNLOAD_DIR, 'isplate.csv')
            newname = f"isplate_{current_date.strftime('%Y_%m_%d')}.csv"
            dest = os.path.join(DOWNLOAD_DIR, newname)
            if os.path.exists(dest):
                # Remove the old file
                os.remove(dest)
            os.rename(original, dest)
            return dest, newname

        driver = None
        try:
            driver = _get_webdriver()
            current_date = self.start_date
            base_xpath = '/html/body/app-root/home-component/'
            days_processed = 0
            bq = BQHandler()
            logger.info(" === Starting web scraping === ")

            # Accept cookies
            WebDriverWait(driver, 10).until(EC.element_to_be_clickable(
                (By.XPATH, base_xpath + 'content/main/cookies/div/div[4]/div[4]/button')
            )).click()
            self._take_snapshot(driver, "after_cookies", current_date)

            # Open filter panel
            WebDriverWait(driver, 10).until(EC.element_to_be_clickable(
                (By.XPATH, base_xpath+'content/main/isplate-details-component/section/div/div/filters/button')
            )).click()

            # Open date filter
            WebDriverWait(driver, 10).until(EC.element_to_be_clickable(
                (By.XPATH, base_xpath+'content/main/isplate-details-component/section/div/div/filters/div/div/div[3]/div[1]')
            )).click()

            # Date filter paths
            filter_base = base_xpath + 'content/main/isplate-details-component/section/div/div/filters/div/div/div[3]/div[2]/div/filter-input/'
            from_xpath = filter_base + 'filter-input-value-type[1]/filter-date-picker/div/input'
            to_xpath   = filter_base + 'filter-input-value-type[2]/filter-date-picker/div/input'
            # Filter button path
            filter_xpath = base_xpath + 'content/main/isplate-details-component/section/div/div/filters/button'

            while current_date <= self.end_date:
                logger.info(f"1) Curr. date: {current_date.strftime('%d.%m.%Y.')}| Wkday: {current_date.strftime('%A')} | Progress: {days_processed}/{self.days_to_scrape}")

                if False: # puni neovisno o tome što je skinuto
                    if self.already_downloaded_dates and current_date <= self.already_downloaded_dates[-1]:
                        logger.info(f"Skipping {current_date.date()} (already downloaded)")
                        current_date += datetime.timedelta(days=1)
                        continue
                
                # Set date filter
                elem_from = WebDriverWait(driver, 10).until(EC.element_to_be_clickable((By.XPATH, from_xpath)))
                elem_to   = WebDriverWait(driver, 10).until(EC.element_to_be_clickable((By.XPATH, to_xpath)))
                elem_from.clear(); elem_to.clear()
                date_to_insert = current_date.strftime('%d.%m.%Y.')
                if PRODUCTION:
                    date_to_insert = (current_date - datetime.timedelta(days=1)).strftime('%d.%m.%Y.')
                elem_from.send_keys(date_to_insert)
                elem_to.send_keys(date_to_insert)
                self._take_snapshot(driver, "after_set_date", current_date)

                if _date_filter_activated():
                    self._take_snapshot(driver, "after_filter_activated", current_date)
                    if _wait_for_table_or_content_date(current_date):
                        self._take_snapshot(driver, "after_table_content", current_date)
                        if _download_click():
                            self._take_snapshot(driver, "after_download_click", current_date)
                            if _download_success('isplate.csv', 60):
                                try:
                                    final_csv, newname = _rename_csv()
                                    bq.load_csv(final_csv, current_date.date())
                                    logger.info(f"6) Loaded into BigQuery: {newname}")
                                except Exception as e:
                                    self._take_snapshot(driver, "bq_load_error", current_date)
                                    logger.error(f"6) BQ load error for {current_date.date()}: {e}")
                                    alert_slack(f":red_circle: BQ load failed for {current_date.date()}\n```{traceback.format_exc()}```")
                                    raise Exception(f"Load failed for {current_date.date()}")
                            else:
                                self._take_snapshot(driver, "download_timeout", current_date)
                                logger.error(f"5) Download timeout/Rename error for {current_date.date()}")
                                alert_slack(f":red_circle: Download failed for {current_date.date()}")
                                raise Exception(f"Download failed for {current_date.date()}")
                        else:
                            self._take_snapshot(driver, "download_not_available", current_date)
                            logger.info(f"4) Download not available for: {current_date.date()}")
                            alert_slack(f":red_circle: Scrape/download failed for {current_date.date()}\n```{traceback.format_exc()}```")
                    else:
                        self._take_snapshot(driver, "content_not_updated", current_date)
                        logger.error(f"3a) No data or content not updated for {current_date.date()}")
                        alert_slack(f":red_circle: Content not updated for {current_date.date()}")
                else:
                    self._take_snapshot(driver, "filter_activation_failed", current_date)
                    logger.error(f"2) Date filter activation failed for {current_date.date()}")
                    alert_slack(f":red_circle: Filter failed for {current_date.date()}")
                    raise Exception(f"Filter failed for {current_date.date()}")

                # Re-open filter for next iteration
                WebDriverWait(driver, 10).until(EC.element_to_be_clickable((By.XPATH, filter_xpath))).click()
                self._take_snapshot(driver, "after_reopen_filter", current_date)
                current_date += datetime.timedelta(days=1)
                days_processed += 1
        
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
                logger.info("--- Web scraping completed! ---")

if __name__ == '__main__':
    exe_start = datetime.datetime.now()
    try:
        app = TransparentnostScraper()
        if PRODUCTION:
            date_interval = None
            #date_interval = (datetime.datetime(2024, 3, 24), datetime.datetime(2024, 4, 3))
        else:  # For local testing, set a specific date range
            date_interval = (datetime.datetime(2024, 3, 27), datetime.datetime(2024, 3, 27))
        app.set_dates(date_interval=date_interval)
        app.webscrape()
    except Exception:
        tb = traceback.format_exc()
        alert_slack(f":red_circle: Scraper failed:\n```{tb}```")
        raise
    else:
        duration = datetime.datetime.now() - exe_start
        logger.info(f"Execution completed in: {duration}")
        alert_slack(f":white_check_mark: Completed in: {duration}")