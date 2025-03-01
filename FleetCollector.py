from datetime import datetime, timedelta, time
from typing import List
import sys
import math
import time as pytime
import requests
from zoneinfo import ZoneInfo

from bs4 import BeautifulSoup
import pandas as pd
import numpy as np
from webdriver_manager.chrome import ChromeDriverManager

import SqlModels as Sql
import SolarPlatform
import Database as db

# The list of all platforms to collect data from
from SolarEdge import SolarEdgePlatform
from Enphase import EnphasePlatform
# from SolArk import SolArkPlatform
# from Solis import SolisPlatform


def get_recent_noon() -> datetime:
    now = SolarPlatform.get_now()
    tz = ZoneInfo(SolarPlatform.cache.get('TimeZone', SolarPlatform.DEFAULT_TIMEZONE))
    today = now.date()

    threshold = datetime.combine(today, time(12, 30), tzinfo=tz)  # Threshold in specified tz

    measurement_date = today if now >= threshold else today - timedelta(days=1)

    noon_local = datetime.combine(measurement_date, time(12, 0), tzinfo=tz) # Noon in specified tz
    noon_utc = noon_local.astimezone(ZoneInfo("UTC")) # Convert to UTC

    return noon_utc

def collect_platform(platform):
    sites = None
    platform.log("Starting collection at " + str(datetime.now()))
    production_set = set()
    reference_date = get_recent_noon()
    sites = platform.get_sites_map()

    try:
        for site_id in sites.keys():
            db.add_site_if_not_exists(site_id)

            battery_data = platform.get_batteries_soe(site_id)
            for battery in battery_data:
                db.update_battery_data(site_id, battery['serialNumber'], battery['model'], battery['stateOfEnergy'])

            # Fetch production data and put into set
            site_production_dict = platform.get_production(site_id, reference_date)

            if site_production_dict is not None:
                new_production = SolarPlatform.ProductionRecord(
                    site_id = site_id,
                    production_kw = site_production_dict,
                )
                production_set.add(new_production)

        platform.log("Data collection complete")
        # Add production data to database
        db.process_bulk_solar_production(reference_date, production_set, False, 3.0)

    except Exception as e:
        platform.log(f"Error while fetching sites: {e}")
        return

    try:
        alerts = platform.get_alerts()
        for alert in alerts:
            db.add_alert_if_not_exists(alert.site_id, str(alert.alert_type), alert.details, alert.severity, alert.first_triggered)

    except Exception as e:
        platform.log(f"Error while fetching alerts: {e}")
        return


#Make this multi-threaded so that it runs all platforms at the same time.
def run_collection():
    platform_solaredge = SolarEdgePlatform()
    collect_platform(platform_solaredge)

    platform_enphase = EnphasePlatform()
    collect_platform(platform_enphase)

    # platform_solark = SolArkPlatform()
    # collect_platform(platform_solark)

    # platform_solis = SolisPlatform()
    # collect_platform(platform_solis)
