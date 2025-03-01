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

BASE_URL = "https://www.solarkcloud.com"
LOGIN_URL = BASE_URL + "/login"
SITES_URL = BASE_URL + "/plants"
OVERVIEW_URL = SITES_URL + "/overview"

from api_keys import SOLARK_EMAIL, SOLARK_PASSWORD


def create_driver():
    options = Options()
    # options.add_argument("--headless")
    options.add_argument("--disable-gpu")
    options.add_argument("--no-sandbox")

    service = Service(ChromeDriverManager(chrome_type=ChromeType.CHROMIUM).install())
    driver = webdriver.Chrome(service=service, options=options)
    return driver


class SolArkPlatform(SolarPlatform.SolarPlatform):
    @classmethod
    def get_vendorcode(cls):
        return "SA"

    _driver = None

    @classmethod
    def get_driver(cls):
        if cls._driver is None:
            cls._driver = create_driver()

            wait = WebDriverWait(cls._driver, 10)

            cls._driver.get(LOGIN_URL)

            email_field = wait.until(EC.presence_of_element_located(
                    (By.XPATH, "//input[@placeholder='Please input your E-mail']")))
            email_field.clear()
            email_field.send_keys(SOLARK_EMAIL)

            password_field = wait.until(EC.presence_of_element_located((
                    By.XPATH, "//input[@placeholder='Please re-enter password' and @name='txtPassword']")))

            password_field.clear()
            password_field.send_keys(SOLARK_PASSWORD)

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
        driver = cls.get_driver()

        # Navigate to the overview page for battery SOE.
        url = OVERVIEW_URL + f"/{site_id}/2"
        driver.get(url)
        time.sleep(5)  # Allow time for JavaScript to execute

        soup = BeautifulSoup(driver.page_source, "html.parser")
        soc_element = soup.find("div", {"class": "soc"})

        if soc_element:
            try:
                return float(soc_element.text.strip().replace('%', ''))
            except ValueError:
                return None
        else:
            return None

    @classmethod
    @SolarPlatform.disk_cache(SolarPlatform.CACHE_EXPIRE_WEEK)
    def get_sites_map(cls):
        driver = cls.get_driver()

        driver.get(SITES_URL)
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

        # For alerts, assume the main page displays alert information.
        driver.get(BASE_URL)
        time.sleep(5)  # Allow time for JavaScript to execute

        soup = BeautifulSoup(driver.page_source, "html.parser")
        alert_elements = soup.find_all("div", {"class": "alert"})
        alerts = []
        for element in alert_elements:
            alert_text = element.text.strip()
            if alert_text:
                # Create a generic alert for the platform; using "SA:ALL" as a placeholder site.
                alert = SolarPlatform.SolarAlert(
                    site_id=cls.add_vendorcodeprefix("ALL"),
                    alert_type="ALERT",
                    severity=50,  # Default severity value; adjust as needed.
                    details=alert_text,
                    first_triggered=datetime.utcnow()
                )
                alerts.append(alert)
        return alerts

def main():
    platform = SolArkPlatform()

    try:
        sites = platform.get_sites_map()
        for site, site_name in sites.items():
            soe = platform.get_batteries_soe(site)
            platform.log(f"Site: {site_name}, SOC: {soe}%")

        # Fetch production data for the first site (if available)
        if sites:
            first_site = next(iter(sites.keys()))
            production = platform.get_production(first_site, None)
            platform.log(f"Production for site {sites[first_site]}: {production} kW")

        # Fetch and log alerts
        alerts = platform.get_alerts()
        for alert in alerts:
            platform.log(f"Alert: {alert.details}")
    finally:
        # driver = cls.get_driver()
        # if driver:
        #     driver.quit()


# Example usage:
if __name__ == "__main__":
    main()


