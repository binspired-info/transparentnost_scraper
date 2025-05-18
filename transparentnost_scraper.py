import os
import sys
# Ensure console handles Unicode code
sys.stdout.reconfigure(encoding='utf-8')
sys.stderr.reconfigure(encoding='utf-8')
import time
import pytz
import glob
import logging
import datetime
import requests
import traceback
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.wait import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

from bq_handler import BQHandler
from __init__ import PRODUCTION, DOWNLOAD_DIR, HEADLESS, LOG_FILE
if not PRODUCTION:
    from webdriver_manager.chrome import ChromeDriverManager

# Slack webhook URL (set via env var in Cloud Run or locally)
SLACK_WEBHOOK = os.getenv("SLACK_WEBHOOK_URL")
def alert_slack(message: str):
    if SLACK_WEBHOOK:
        try:
            requests.post(SLACK_WEBHOOK, json={"text": message}, timeout=5)
        except Exception as e:
            logging.error(f"Failed to send Slack alert: {e}")

# Configure logging with UTF-8 handlers
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(LOG_FILE, encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)
CLEAN_DIR = False
tz = pytz.timezone('Europe/Zagreb')

class TransparentnostScraper():
    def __init__(self):
        """ --- Initial settings --- """
        # production mode
        logger.info(f"--- Running in {'production' if PRODUCTION else 'development'} mode.")
        # Check for already downloaded dates
        #self.already_downloaded_dates = self._check_for_downloaded_dates()
        # Get the last date from BigQuery (a datetime.date)
        last = BQHandler().get_last_date()
        if last:
            # Combine the date with midnight to get a Python datetime
            self.last_date_tbl = datetime.datetime.combine(last, datetime.time(0, 0, 0), tzinfo=tz)
        else:
            # Fallback start date
            self.last_date_tbl = datetime.datetime(2024, 1, 1, tzinfo=tz)

    def _check_for_downloaded_dates(self):
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
        if date_interval:
            # date_interval contains two datetime.datetime objects
            self.start_date, self.end_date = date_interval
        else:
            # If our last loaded date is before 2024, start at Jan 2, 2024
            if self.last_date_tbl.year < 2024:
                self.start_date = tz.localize(datetime.datetime(2024, 1, 2))
            else:
                # Next day after last_date_tbl
                dt = self.last_date_tbl + datetime.timedelta(days=1)
                if dt.tzinfo is None:
                    self.start_date = tz.localize(dt)
                else:
                    self.start_date = dt
            # Use current time as the end of the interval
            self.end_date = datetime.datetime.now(tz)
        self.days_to_scrape = (self.end_date - self.start_date).days
        logger.info(f"--- Scraping from dates {self.start_date.date()} to {self.end_date.date()} ({self.days_to_scrape} days) ---")

    def webscrape(self):
        def _date_filter_active(timeout=15):
            end = time.time() + timeout
            xpath = base_xpath + 'content/main/isplate-details-component/section/div/div[2]/filters/div/div'
            while time.time() < end:
                try:
                    text = driver.find_element(By.XPATH, xpath).text
                    if 'Datum:' in text and current_date.strftime('%d.%m.%Y.') in text:
                        print("Filter active: ",text)
                        return True
                except:
                    pass
                time.sleep(1)
            return False

        def _content_not_empty(timeout=10):
            time.sleep(1) # Wait for the content to load
            end = time.time() + timeout
            xpath = base_xpath + '/content/main/isplate-details-component/section/div/div[1]/span'
            while time.time() < end: # Wait for the content to load and check for 10 times before giving up
                content = driver.find_element(By.XPATH, xpath).text
                if content != 'Suma filtriranih stavki: 0,00':
                    print("Content: ",content)
                    return True
                time.sleep(1)
            print("Content empty: ",content)
            return False # False if the content is empty
        
        def _download_click(timeout=10):
            end = time.time() + timeout
            # Download button path
            download_xpath = base_xpath + 'content/main/isplate-details-component/section/div/div[2]/div'
            while time.time() < end:
                try:
                    driver.find_element(By.XPATH, download_xpath).click()
                    print("Download button clicked")
                    return True
                except:
                    pass
                time.sleep(1)
            print("Download button not clickable")
            return False

        def _download_success(filename, timeout=30):
            end = time.time() + timeout
            while time.time() < end:
                path = os.path.join(DOWNLOAD_DIR, filename)
                if os.path.exists(path) and not os.path.exists(path + '.crdownload'):
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
            return dest

        """ --- Settings --- """
        if not PRODUCTION:
            service = Service(ChromeDriverManager().install())
            options = webdriver.ChromeOptions()
        else:
            service = Service('/usr/bin/chromedriver')
            options = webdriver.ChromeOptions()
            options.binary_location = '/usr/bin/chromium'

        # 1) Set the download directory
        options.add_experimental_option('prefs', {
            'download.default_directory': DOWNLOAD_DIR
        })

        # 2) Required flags for headless Chrome in container environments
        if HEADLESS:
            options.add_argument('--headless=new')          # or '--headless' for older Chrome versions
            options.add_argument('--no-sandbox')            # bypass OS security model
            options.add_argument('--disable-dev-shm-usage') # overcome limited /dev/shm
            options.add_argument('--disable-gpu')           # recommended for headless
            options.add_argument('--remote-debugging-port=9222')

        driver = webdriver.Chrome(service=service, options=options)
        driver.get("https://transparentnost.zagreb.hr/isplate/sc-isplate")
        base_xpath = '/html/body/app-root/home-component/'

        """ --- Start scraping --- """
        logger.info(" === Starting web scraping === ")
        current_date = self.start_date
        days_processed = 0
        bq = BQHandler()

        # Accept cookies
        WebDriverWait(driver, 10).until(EC.element_to_be_clickable(
            (By.XPATH, base_xpath + 'content/main/cookies/div/div[4]/div[4]/button')
        )).click()
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
        # Download button path
        download_xpath = base_xpath + 'content/main/isplate-details-component/section/div/div[2]/div'
        # Filter button path
        filter_xpath = base_xpath + 'content/main/isplate-details-component/section/div/div/filters/button'

        while current_date <= self.end_date:
            logger.info(f"Curr. date: {current_date}| Wkday: {current_date.strftime('%A')} | Progress: {days_processed}/{self.days_to_scrape}")

            if False: # puni neovisno o tome što je skinuto
                if self.already_downloaded_dates and current_date <= self.already_downloaded_dates[-1]:
                    logger.info(f"Skipping {current_date.date()} (already downloaded)")
                    current_date += datetime.timedelta(days=1)
                    continue
            
            # Set date filter
            elem_from = WebDriverWait(driver, 10).until(EC.element_to_be_clickable((By.XPATH, from_xpath)))
            elem_to   = WebDriverWait(driver, 10).until(EC.element_to_be_clickable((By.XPATH, to_xpath)))
            elem_from.clear(); elem_to.clear() # Clear previous date values
            elem_from.send_keys(current_date.strftime('%d.%m.%Y.'))
            elem_to.send_keys(current_date.strftime('%d.%m.%Y.'))
            # Click on the date filter button
            WebDriverWait(driver, 10).until(EC.element_to_be_clickable((By.XPATH, filter_base+'button'))).click()

            if _date_filter_active(): # Apply filter
                if _content_not_empty(): # "Suma filtriranih stavki" nije 0,00
                    if _download_click(): # Try to click the download button
                        if _download_success('isplate.csv', 60): # Wait for the download to complete
                            try:
                                final_csv = _rename_csv()
                                logger.info(f"Downloaded CSV: {final_csv}")
                                # Load into BigQuery
                                bq.load_csv(final_csv, current_date.date())
                                logger.info(f"Loaded into BigQuery")
                            except Exception as e:
                                logger.error(f"Rename CSV/BQ load error for {current_date.date()}: {e}")
                                alert_slack(f":red_circle: BQ load failed for {current_date.date()}\n```{traceback.format_exc()}```")
                                raise
                        else:
                            logger.error(f"Download timeout for {current_date.date()}")
                            alert_slack(f":red_circle: Download failed for {current_date.date()}")
                            raise
                    else:
                        logger.info(f"Download not available for: {current_date.date()}")
                        alert_slack(f":red_circle: Scrape/download failed for {current_date.date()}\n```{traceback.format_exc()}```")
                else:
                    logger.info(f"Content empty for {current_date.date()}. Skipping...")
            else:
                logger.error(f"Date filter activation failed for {current_date.date()}")
                alert_slack(f":red_circle: Filter failed for {current_date.date()}")
                raise Exception("Filter activation failed")

            # Re-open filter for next iteration
            WebDriverWait(driver, 10).until(EC.element_to_be_clickable((By.XPATH, filter_xpath))).click()
            # Continue to the next date
            current_date += datetime.timedelta(days=1)
            days_processed += 1

        driver.quit()
        logger.info("--- Web scraping completed! ---")

if __name__ == '__main__':
    exe_start = datetime.datetime.now(tz)
    try:
        app = TransparentnostScraper()
        date_interval = None
        if not PRODUCTION:
            # For local testing, set a specific date range
            date_interval = (datetime.datetime(2024, 1, 18), datetime.datetime(2024, 1, 23))
        app.set_dates(date_interval=date_interval)
        app.webscrape()
    except Exception:
        tb = traceback.format_exc()
        alert_slack(f":red_circle: Scraper failed:\n```{tb}```")
        raise
    else:
        duration = datetime.datetime.now(tz) - exe_start
        logger.info(f"Execution completed in: {duration}")
        alert_slack(f":white_check_mark: Completed in: {duration}")