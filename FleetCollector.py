from datetime import datetime, timedelta
from typing import List
import sys
import math
import time
import requests

from bs4 import BeautifulSoup
import pandas as pd
import numpy as np
from webdriver_manager.chrome import ChromeDriverManager

import SqlModels as Sql
import SolarPlatform
import Database as db

# Initialize database

def update_alert_history(vendor_code, system_id, alert_type, message):
    pass

from SolarEdge import SolarEdgePlatform

def collect_platform(platform):
    sites = None
    platform.log("Testing get_sites_map() API call...")
    production_set = set()
    reference_date = SolarPlatform.get_recent_noon()

    try:
        sites = platform.get_sites_map()
        for site_id in sites.keys():
            site = sites[site_id]
            latitude, longitude = SolarPlatform.get_coordinates(sites[site_id].zipcode)

            #This needs to be moved to later when we have the nearest site information
            db.add_site_if_not_exists(platform.get_vendorcode(), site_id, sites[site_id].name, site.url, "nearest_vendorcode", "nearest_siteid", "nearest_distance")

            battery_data = platform.get_batteries_soe(site_id)
            for battery in battery_data:                    
                db.update_battery_data(platform.get_vendorcode(), site_id, battery['serialNumber'], battery['model'], battery['stateOfEnergy'])
                platform.log(f"Site {site_id} Battery Data: {battery_data}")

            # Fetch production data and put into set
            site_production = platform.get_production(site_id, reference_date)

            #Todo this is supposed to be a ProductionRecord. However, I need this other data
            #elsewhere .
            if site_production is not None:
                new_production = SolarPlatform.ProductionRecord(
                    vendor_code=platform.get_vendorcode(),
                    site_id=site_id,
                    production_kw=site_production,     
                )
                production_set.add(new_production)
                platform.log(f"Site {site_id} Production Data: {site_production} kW")

        # Add production data to database
        db.process_bulk_solar_production(reference_date, production_set, False, 3.0)

    except Exception as e:
        platform.log(f"Error while fetching sites: {e}")
        return

    try:
        alerts = platform.get_alerts() 
        for alert in alerts:
            db.add_alert_if_not_exists(platform.get_vendorcode(), alert.site_id, str(alert.alert_type), alert.details, alert.severity, alert.first_triggered)

    except Exception as e:
        platform.log(f"Error while fetching alerts: {e}")
        return

def run_collection():
    platform = SolarEdgePlatform()
    collect_platform(platform)