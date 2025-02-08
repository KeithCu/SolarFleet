import requests
import time
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.core.os_manager import ChromeType

import SolarPlatform

SOLARK_BASE_URL = "https://www.solarkcloud.com"
SOLARK_LOGIN_URL = SOLARK_BASE_URL + f"/login"
SOLARK_SITES_URL = SOLARK_BASE_URL + f"/plants"

from api_keys import SOLARK_EMAIL, SOLARK_PASSWORD

g_driver = None

def create_driver():
    options = Options()
    #options.add_argument("--headless")
    options.add_argument("--disable-gpu")
    options.add_argument("--no-sandbox")
    
    service = Service(ChromeDriverManager(chrome_type=ChromeType.CHROMIUM).install())
    driver = webdriver.Chrome(service=service, options=options)
    return driver


class SolArkPlatform(SolarPlatform):
    def __init__(self):
        pass
    
    @classmethod
    def get_vendorcode():
        return "SA"

    @staticmethod
    def solark_login(login_url, user_email, user_password):
        wait = WebDriverWait(g_driver, 10)
        
        # Open the login page.
        g_driver.get(login_url)
        
        # Locate the email input using its placeholder text.
        email_field = wait.until(
            EC.presence_of_element_located((By.XPATH, "//input[@placeholder='Please input your E-mail']"))
        )
        email_field.clear()
        email_field.send_keys(user_email)
        
        # Locate the password field using its placeholder and name attributes.
        password_field = wait.until(
            EC.presence_of_element_located((
                By.XPATH, "//input[@placeholder='Please re-enter password' and @name='txtPassword']"
            ))
        )
        password_field.clear()
        password_field.send_keys(user_password)
        
        # Locate and click the checkbox. (Assumes there is a single element matching this selector.)
        checkbox = wait.until(
            EC.element_to_be_clickable((By.CSS_SELECTOR, "span.el-checkbox__inner"))
        )
        checkbox.click()
        
        # Locate and click the login button.
        # This example assumes the button is of type 'submit'.
        login_button = wait.until(
            EC.element_to_be_clickable((By.XPATH, "//button[@type='button' and contains(.,'Log In')]"))
        )
        login_button.click()
        
        # Wait until the URL changes (indicating a successful login).
        wait.until(EC.url_changes(login_url))
        
        # Optionally pause to ensure all JS processes complete.
        time.sleep(3)
        
        # Return cookies from the session.
        return g_driver.get_cookies()

    @staticmethod
    @SolarPlatform.disk_cache(SolarPlatform.CACHE_EXPIRE_HOUR)
    def get_batteries_soe(driver, site):
        if g_driver is None:
            g_driver = create_driver()
            SolArkPlatform.solark_login(SOLARK_LOGIN_URL, SOLARK_EMAIL, SOLARK_PASSWORD)

        g_driver.get(url)
        time.sleep(5)  # Give time for JS to execute
        
        # Extract the page source after JavaScript has been processed
        soup = BeautifulSoup(driver.page_source, "html.parser")
        soc_element = soup.find("div", {"class": "soc"})
        
        if soc_element:
            return float(soc_element.text.strip().replace('%', ''))
        else:
            return None

    @staticmethod
    @SolarPlatform.disk_cache(SolarPlatform.CACHE_EXPIRE_DAY)
    def get_sites_map():
        if g_driver is None:
            g_driver = create_driver()
            SolArkPlatform.solark_login(SOLARK_LOGIN_URL, SOLARK_EMAIL, SOLARK_PASSWORD)

        g_driver.get(SOLARK_SITES_URL)
        time.sleep(5)  # Give time for JS to execute
        
        # Extract the page source after JavaScript has been processed
        soup = BeautifulSoup(g_driver.page_source, "html.parser")
        site_links = soup.find_all("a", href=True)
        
        sites = {}
        for link in site_links:
            if "/plants/overview/" in link["href"]:
                site_id = link["href"].split("/")[-2]
                site_name = link.text.strip()
                sites[site_id] = site_name
        
        return sites


# Example usage:
if __name__ == "__main__":
    platform = SolArkPlatform()

    try:
        sites = platform.get_sites_map()

        for site in sites.keys():
            soe = platform.get_batteries_soe(site)
            platform.log(f"Site: {sites[site]}, SOC: {soe}%")

    finally:
        g_driver.quit()

