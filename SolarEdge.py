from SolarPlatform import SolarPlatform
import requests
from datetime import datetime, timedelta
from api_keys import SOLAREDGE_V2_API_KEY, SOLAREDGE_V2_ACCOUNT_KEY

SOLAREDGE_BASE_URL = 'https://monitoringapi.solaredge.com/v2'

SOLAREDGE_HEADERS = {
    "X-API-Key": SOLAREDGE_V2_API_KEY,
    "Accept": "application/json",
    "X-Account-Key": SOLAREDGE_V2_ACCOUNT_KEY
}

class SolarEdgePlatform(SolarPlatform):
    @classmethod
    def get_vendorcode(cls):
        return "SE"

    @classmethod
    def get_sites(cls):
        url = f'{SOLAREDGE_BASE_URL}/sites'
        params = {"page": 1, "sites-in-page": 50}
        all_sites = []
        
        while True:
            response = requests.get(url, headers=SOLAREDGE_HEADERS, params=params)
            response.raise_for_status()
            sites = response.json()
            
            for site in sites:
                all_sites.append({
                    'siteId': site.get('siteId'),
                    'name': site.get('name'),
                })
            
            if len(sites) < params["sites-in-page"]:
                break
            params["page"] += 1        
        return all_sites

    @classmethod
    def get_batteries(cls, site_id):
        url = f'{SOLAREDGE_BASE_URL}/sites/{site_id}/devices'
        params = {"types": ["BATTERY"]}
        
        response = requests.get(url, headers=SOLAREDGE_HEADERS, params=params)
        response.raise_for_status()
        devices = response.json()
        
        batteries = [device for device in devices if device.get('type') == 'BATTERY']
        return batteries

    @classmethod
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
    def get_batteries_soc(cls, site_id):
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
    def get_alerts(cls, site_id):
        #site_id = '1868399'
        url = f'{SOLAREDGE_BASE_URL}/site/{site_id}/alerts'
        
        try:
            response = requests.get(url, headers=SOLAREDGE_HEADERS)
            response.raise_for_status()
            alerts = response.json().get('alerts', [])
            return alerts if alerts else []
        except requests.exceptions.RequestException as e:
            print(f"Failed to retrieve SolarEdge alerts: {e}")
            return []
        
def main():
    platform = SolarEdgePlatform()

    platform.log("Testing get_sites() API call...")
    try:
        sites = platform.get_sites()
        if sites:
            platform.log("Retrieved Sites:")
            for site in sites:
                site_id = site['siteId']
                battery_data = platform.get_batteries_soc(site_id)
                platform.log(f"Site {site_id} Battery Data: {battery_data}")
        else:
            platform.log("No sites found.")
            return  # Nothing to test if no sites are found.
    except Exception as e:
        platform.log(f"Error while fetching sites: {e}")
        return

    #Fetch all SolarEdge alerts
    platform.log("\nFetching alerts and other info for each site:")
    for site in sites:
        site_id = site['id']
        platform.log(f"\nSite ID: {site_id} - {site['name']}")
        try:
            alerts = platform.get_alerts(site_id)
            if alerts is not None:
                for alert in alerts:
                    platform.log("Retrieved Alerts:")
                    platform.log(f"  Alert ID: {alert}")
            else:
                platform.log("No alerts found for this site.")
        except Exception as e:
            platform.log(f"Error while fetching alerts for site {site_id}: {e}")

# if __name__ == "__main__":
#     main()