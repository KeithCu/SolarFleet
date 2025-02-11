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
    try:
        sites = platform.get_sites_map()
        for site_id in sites.keys():
            site = sites[site_id]

            #This needs to be moved to later when we have the nearest site information
            db.add_site_if_not_exists(platform.get_vendorcode(), site_id, sites[site_id].name, site.url, "nearest_vendorcode", "nearest_siteid", "nearest_distance")

            battery_data = platform.get_batteries_soe(site_id)
            for battery in battery_data:                    
                db.update_battery_data(platform.get_vendorcode(), site_id, battery['serialNumber'], battery['model'], battery['stateOfEnergy'], "")
                platform.log(f"Site {site_id} Battery Data: {battery_data}")



            # if not existing_production:
            #     # Fetch production data
            #     reference_time = datetime.utcnow()
            #     production = platform.get_production(site_id, reference_time)
            #     if production is not None:
            #         new_production = SolarPlatform.SolarProduction(
            #             site_id=site_id,
            #             site_name=sites[site_id].name,
            #             site_zipcode=sites[site_id].zipcode,
            #             site_production=production,
            #             site_url=sites[site_id].url
            #         )
            #         db.process_bulk_solar_production([new_production])
            #         platform.log(f"Site {site_id} Production Data: {production} kW")
    except Exception as e:
        platform.log(f"Error while fetching sites: {e}")
        return

    try:
        alerts = platform.get_alerts() 
        for alert in alerts:
            db.add_alert_if_not_exists(platform.get_vendorcode(), alert.site_id,  str(alert.alert_type), alert.details, alert.severity, alert.first_triggered)

    except Exception as e:
        platform.log(f"Error while fetching alerts: {e}")
        return

def collect_all():

#    platform = SolarEdgePlatform()

    if False and is_data_recent():
        print("Skipping updates as data is recent enough.")
        return

if __name__ == '__main__':
    collect_all()
