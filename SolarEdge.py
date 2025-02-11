import requests
from typing import List, Dict
from datetime import datetime, timedelta
import random

import SolarPlatform
from api_keys import SOLAREDGE_V2_API_KEY, SOLAREDGE_V2_ACCOUNT_KEY

SOLAREDGE_BASE_URL = 'https://monitoringapi.solaredge.com/v2'
SOLAREDGE_SITE_URL = 'https://monitoring.solaredge-web/p/site/'

SOLAREDGE_HEADERS = {
    "X-API-Key": SOLAREDGE_V2_API_KEY,
    "Accept": "application/json",
    "X-Account-Key": SOLAREDGE_V2_ACCOUNT_KEY
}

class SolarEdgePlatform(SolarPlatform.SolarPlatform):
    @classmethod
    def get_vendorcode(cls):
        return "SE"

    @classmethod
    @SolarPlatform.disk_cache(SolarPlatform.CACHE_EXPIRE_WEEK)
    def get_sites_list(cls):
        url = f'{SOLAREDGE_BASE_URL}/sites'
        params = {"page": 1, "sites-in-page": 500}
        all_sites = []
        
        while True:
            cls.log("Fetching all sites from SolarEdge API...")
            response = requests.get(url, headers=SOLAREDGE_HEADERS, params=params)
            response.raise_for_status()
            sites = response.json()
            
            for site in sites:
                all_sites.append(site)
                
            if len(sites) < params["sites-in-page"]:
                break
            params["page"] += 1        
        return all_sites

    @classmethod
    #@SolarPlatform.disk_cache(SolarPlatform.CACHE_EXPIRE_HOUR)
    def get_sites_map(cls) -> Dict[str, SolarPlatform.SiteInfo]:
        sites = cls.get_sites_list()

        sites_dict = {}

        for site in sites:
            site_id = site.get('siteId')
            site_url = SOLAREDGE_SITE_URL + str(site_id)
            site_info = SolarPlatform.SiteInfo(site.get('siteId'), site.get('name'), site_url, site['location']['zip'])
            sites_dict[site_id] = site_info
                
        return sites_dict

    @classmethod
    @SolarPlatform.disk_cache(SolarPlatform.CACHE_EXPIRE_MONTH())
    def get_batteries(cls, site_id):
        url = f'{SOLAREDGE_BASE_URL}/sites/{site_id}/devices'
        params = {"types": ["BATTERY"]}
        
        response = requests.get(url, headers=SOLAREDGE_HEADERS, params=params)
        response.raise_for_status()
        devices = response.json()

        batteries = [device for device in devices if device.get('type') == 'BATTERY']
        return batteries

    @classmethod
    @SolarPlatform.disk_cache(SolarPlatform.CACHE_EXPIRE_WEEK)
    def get_production(cls, site_id, reference_time):
        end_time = reference_time + timedelta(minutes=15)

        url = SOLAREDGE_BASE_URL + f'/sites/{site_id}/power'    
        params = {
            'from': reference_time.isoformat() + 'Z',
            'to': end_time.isoformat() + 'Z',
            'resolution': 'QUARTER_HOUR',
            'unit': 'PERCENTAGE'
        }
        
        response = requests.get(url, headers=SOLAREDGE_HEADERS, params=params)
        response.raise_for_status()
        power = response.json().get('values', [])
        
        latest_value = next((entry['value'] for entry in reversed(power) if entry['value'] is not None), None)
        return latest_value


    @classmethod
    @SolarPlatform.disk_cache(SolarPlatform.CACHE_EXPIRE_HOUR * 4)
    def get_battery_state_of_energy(cls, site_id, serial_number):
        end_time = datetime.utcnow()
        start_time = end_time - timedelta(minutes=15)
        
        url = f'{SOLAREDGE_BASE_URL}/sites/{site_id}/storage/{serial_number}/state-of-energy'
        params = {
            'from': start_time.isoformat() + 'Z',
            'to': end_time.isoformat() + 'Z',
            'resolution': 'QUARTER_HOUR',
            'unit': 'PERCENTAGE'
        }
        
        response = requests.get(url, headers=SOLAREDGE_HEADERS, params=params)
        response.raise_for_status()
        soe_data = response.json().get('values', [])
        
        latest_value = next((entry['value'] for entry in reversed(soe_data) if entry['value'] is not None), None)
        return latest_value

    @classmethod
    def get_batteries_soe(cls, site_id):
        batteries = cls.get_batteries(site_id)
        battery_states = []
        
        for battery in batteries:
            serial_number = battery.get('serialNumber')
            soe = cls.get_battery_state_of_energy(site_id, serial_number)
            
            battery_states.append({
                'serialNumber': serial_number,
                'model': battery.get('model'),
                'stateOfEnergy': soe
            })
        
        return battery_states

    @classmethod
    @SolarPlatform.disk_cache(SolarPlatform.CACHE_EXPIRE_HOUR)
    def get_alerts(cls) -> List[SolarPlatform.SolarAlert]:
        url = f'{SOLAREDGE_BASE_URL}/alerts'
        sites_dict = cls.get_sites_map()
        all_alerts = []

        try:
            response = requests.get(url, headers=SOLAREDGE_HEADERS)
            response.raise_for_status()
            alerts = response.json()
            for alert in alerts:
                a_site_id = alert.get('siteId')
                alert_details = ''
                solarAlert = SolarPlatform.SolarAlert(a_site_id, alert.get('type'), alert.get('impact'), alert_details, alert.get('firstTriggered'))
                all_alerts.append(solarAlert)

            return all_alerts
        except requests.exceptions.RequestException as e:
            print(f"Failed to retrieve SolarEdge alerts: {e}")
            return []
        
def main():
    platform = SolarEdgePlatform()

    platform.log("Testing get_sites_map() API call...")
    try:
        sites = platform.get_sites_map()
        if sites:
            platform.log("Retrieved Sites:")
            for site_id in sites.keys():
                pass
                
                #battery_data = platform.get_batteries_soe(site_id)
                #platform.log(f"Site {site_id} Battery Data: {battery_data}")
        else:
            platform.log("No sites found.")
            return  # Nothing to test if no sites are found.
    except Exception as e:
        platform.log(f"Error while fetching sites: {e}")
        return

    #Fetch all SolarEdge alerts
    platform.log("\nFetching alerts for all sites")
    try:
        alerts = platform.get_alerts()
        if alerts is not None:
            for alert in alerts:
                platform.log("Retrieved Alerts:")
                platform.log(f"  Alert ID: {alert}")
        else:
            platform.log("No alerts found for this site.")
    except Exception as e:
        platform.log(f"Error while fetching alerts for site {site_id}: {e}")

if __name__ == "__main__":
    main()