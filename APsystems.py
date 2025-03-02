from typing import List
import requests
import time
from datetime import datetime
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager
from webdriver_manager.core.os_manager import ChromeType


import SolarPlatform

# https://www.apsystemsema.com/ema/index.action

# https://www.apsystemsema.com/ema/security/optmainmenu/intoUserListBelowInstaller.action?language=en_US

BASE_URL = "https://apsystemsema.com/ema"
LOGIN_URL = BASE_URL + "/index.action"
SITE_URL = BASE_URL + "/plants"
OVERVIEW_URL = BASE_URL + "security/optmainmenu/intoUserListBelowInstaller.action?language=en_US"

from api_keys import APSYSTEMS_EMAIL, APSYSTEMS_PASSWORD


def create_driver():
    options = Options()
    # options.add_argument("--headless")
    options.add_argument("--disable-gpu")
    options.add_argument("--no-sandbox")

    service = Service(ChromeDriverManager(chrome_type=ChromeType.CHROMIUM).install())
    driver = webdriver.Chrome(service=service, options=options)
    return driver


class APsystemsPlatform(SolarPlatform.SolarPlatform):
    @classmethod
    def get_vendorcode(cls):
        return "AP"

    _driver = None

    @classmethod
    def get_driver(cls):
        if cls._driver is None:
            cls._driver = create_driver()

            wait = WebDriverWait(cls._driver, 10)

            cls._driver.get(LOGIN_URL)

            email_field = wait.until(EC.presence_of_element_located(
                    (By.XPATH, "Login Account")))
            email_field.clear()
            email_field.send_keys(APSYSTEMS_EMAIL)

            password_field = wait.until(EC.presence_of_element_located((
                    By.XPATH, "//input[@placeholder='Please re-enter password' and @name='txtPassword']")))

            password_field.clear()
            password_field.send_keys(APSYSTEMS_PASSWORD)

            checkbox = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, "span.el-checkbox__inner")))
            checkbox.click()

            login_button = wait.until(EC.element_to_be_clickable(
                    (By.XPATH, "//button[@type='button' and contains(.,'Log In')]")))
            login_button.click()

            wait.until(EC.url_changes(LOGIN_URL))

            time.sleep(3)
            
        return cls._driver


    @classmethod
    @SolarPlatform.disk_cache(SolarPlatform.CACHE_EXPIRE_HOUR)
    def get_batteries_soe(cls, site_id):
        pass

    #TODO: add pagination
    @classmethod
    @SolarPlatform.disk_cache(SolarPlatform.CACHE_EXPIRE_WEEK)
    def get_sites_map(cls):
        driver = cls.get_driver()

        driver.get(OVERVIEW_URL)
        time.sleep(5)  # Allow time for JavaScript to execute

        soup = BeautifulSoup(driver.page_source, "html.parser")
        site_links = soup.find_all("a", href=True)

        sites = {}
        for link in site_links:
            if "/plants/overview/" in link["href"]:
                # Expected URL format: /plants/overview/{site_id}/...
                parts = link["href"].split("/")
                if len(parts) >= 4:
                    site_id = parts[-2]
                    site_name = link.text.strip()
                    # Prefix with vendor code
                    full_site_id = cls.add_vendorcodeprefix(site_id)
                    sites[full_site_id] = site_name
        return sites

    #TODO: For now, it's just one Inverter per site, and only fetches current values
    @classmethod
    @SolarPlatform.disk_cache(SolarPlatform.CACHE_EXPIRE_HOUR)
    def get_production(cls, site_id, reference_time) -> List[float]:
        driver = cls.get_driver()
        return

        # Assume production data is available on an overview page.
        url = OVERVIEW_URL + f"/{site_id}/overview"
        driver.get(url)
        time.sleep(5)  # Allow time for JavaScript to execute

        soup = BeautifulSoup(driver.page_source, "html.parser")
        production_element = soup.find("div", {"class": "production"})

        if production_element:
            prod_text = production_element.text.strip().replace('kW', '').strip()
            try:
                return [float(prod_text)]
            except ValueError:
                return [0.0]
        return[0.0]

    @classmethod
    def get_site_energy(cls, site_id, start_date, end_date):
        pass

    @classmethod
    @SolarPlatform.disk_cache(SolarPlatform.CACHE_EXPIRE_HOUR)
    def get_alerts(cls) -> list:
        driver = cls.get_driver()

        # Navigate to the APS Systems EMA user list page
        driver.get("https://www.apsystemsema.com:443/ema/security/optmainmenu/intoUserListBelowInstaller.action")

        # Wait for the table body to load (timeout after 10 seconds)
        wait = WebDriverWait(driver, 10)
        wait.until(EC.presence_of_element_located((By.ID, "inverterTable")))

        # Parse the page source with BeautifulSoup
        soup = BeautifulSoup(driver.page_source, "html.parser")
        table_body = soup.find("tbody", {"id": "inverterTable"})
        rows = table_body.find_all("tr")

        # Define status descriptions and severity mappings based on the HTML
        status_descriptions = {
            "green": "The system is functioning normally",
            "grey": "No data has been uploaded from this ECU yet",
            "red": "ECU network connection issue detected",
            "yellow": "Some micro-inverters have alarms or are not properly registered"
        }

        severity_map = {
            "red": 80,    # High severity for network issues
            "yellow": 50, # Medium severity for inverter issues
            "grey": 30    # Low severity for no data
        }

        alerts = []

        # Process each table row
        for row in rows:
            tds = row.find_all("td")
            if len(tds) >= 18:  # Ensure the row has all expected columns
                # Extract system name from the second column (index 1)
                system_name = tds[1].find("a").text.strip()

                # Extract ECU ID from the third column (index 2)
                ecu_id = tds[2].text.strip()

                # Extract status from the 18th column (index 17)
                status_td = tds[17]
                status_input = status_td.find("input", {"type": "hidden"})
                
                if status_input:
                    status = status_input["value"]
                    if status != "green":
                        # Get description and severity, with defaults for unknown statuses
                        description = status_descriptions.get(status, "Unknown status")
                        severity = severity_map.get(status, 0)

                        # Create a SolarAlert object
                        alert = SolarPlatform.SolarAlert(
                            site_id=cls.add_vendorcodeprefix(ecu_id),  # Prefix ECU ID with vendor code
                            alert_type="SYSTEM_STATUS",
                            severity=severity,
                            details=f"System {system_name} has status: {status} - {description}",
                            first_triggered=datetime.utcnow()
                        )
                        alerts.append(alert)

        return alerts

def main():
    platform = APsystemsPlatform()

    try:
        sites = platform.get_sites_map()
        # for site, site_name in sites.items():
            # soe = platform.get_batteries_soe(site)
            # platform.log(f"Site: {site_name}, SOC: {soe}%")

        # Fetch production data for the first site (if available)
        # if sites:
        #     first_site = next(iter(sites.keys()))
        #     production = platform.get_production(first_site, None)
        #     platform.log(f"Production for site {sites[first_site]}: {production} kW")

        # Fetch and log alerts
        alerts = platform.get_alerts()
        for alert in alerts:
            platform.log(f"Alert: {alert.details}")
    finally:
        pass
        # driver = cls.get_driver()
        # if driver:
        #     driver.quit()


# Example usage:
if __name__ == "__main__":
    main()
