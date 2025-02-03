import requests
import time
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.chrome.options import Options

def get_solar_ark_soc(url):
    # Set up Selenium to handle JavaScript rendering
    options = Options()
    options.add_argument("--headless")  # Run in headless mode
    options.add_argument("--disable-gpu")
    options.add_argument("--no-sandbox")

    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=options)

    try:
        driver.get(url)
        time.sleep(5)  # Give time for JS to execute
        
        # Extract the page source after JavaScript has been processed
        soup = BeautifulSoup(driver.page_source, "html.parser")
        soc_element = soup.find("div", {"class": "soc"})
        
        if soc_element:
            return float(soc_element.text.strip().replace('%', ''))
        else:
            return None
    finally:
        driver.quit()

def get_solar_ark_sites(url):
    # Set up Selenium to handle JavaScript rendering
    options = Options()
    options.add_argument("--headless")  # Run in headless mode
    options.add_argument("--disable-gpu")
    options.add_argument("--no-sandbox")
    
    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=options)
    
    try:
        driver.get(url)
        time.sleep(5)  # Give time for JS to execute
        
        # Extract the page source after JavaScript has been processed
        soup = BeautifulSoup(driver.page_source, "html.parser")
        site_links = soup.find_all("a", href=True)
        
        sites = {}
        for link in site_links:
            if "/plants/overview/" in link["href"]:
                site_id = link["href"].split("/")[-2]
                site_name = link.text.strip()
                sites[site_id] = site_name
        
        return sites
    finally:
        driver.quit()


