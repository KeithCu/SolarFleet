from SolarPlatform import SolarPlatform
import requests
from datetime import datetime, timedelta
from api_keys import SOLAREDGE_API_KEY

SOLAREDGE_BASE_URL = f'https://monitoringapi.solaredge.com'
SOLAREDGE_V2_URL = SOLAREDGE_BASE_URL + f'/v2'

class SolarEdgePlatform(SolarPlatform):
    def __init__(self):
        self.api_key = SOLAREDGE_API_KEY

    def get_sites(self):
        url = SOLAREDGE_BASE_URL + f'/sites/list?api_key={self.api_key}'
        response = requests.get(url)
        response.raise_for_status()
        sites = response.json().get('sites', {}).get('site', [])
        return [{'id': site['id'], 'name': site['name']} for site in sites]

    def get_batteries_soc(self, site_id):
        """Retrieve the latest state of energy for all batteries at a specific SolarEdge site."""
        end_time = datetime.now()
        start_time = end_time - timedelta(minutes=15)
        start_time_str = start_time.strftime('%Y-%m-%d %H:%M:%S')
        end_time_str = end_time.strftime('%Y-%m-%d %H:%M:%S')

        url = f'{SOLAREDGE_BASE_URL}/site/{site_id}/storageData'
        params = {
            'api_key': SOLAREDGE_API_KEY,
            'startTime': start_time_str,
            'endTime': end_time_str
        }

        try:
            response = requests.get(url, params=params)
            response.raise_for_status()
            storage_data = response.json().get('storageData', {})
            batteries = storage_data.get('batteries', [])
            battery_states = []

            for battery in batteries:
                serial_number = battery.get('serialNumber', 'Unknown Serial Number')
                model_number = battery.get('modelNumber', 'Unknown Model Number')
                telemetries = battery.get('telemetries', [])

                if telemetries:
                    latest_telemetry = telemetries[-1]
                    soe = latest_telemetry.get('batteryPercentageState')
                    battery_states.append({
                        'serialNumber': serial_number,
                        'modelNumber': model_number,
                        'stateOfEnergy': soe
                    })
                else:
                    battery_states.append({
                        'serialNumber': serial_number,
                        'modelNumber': model_number,
                        'stateOfEnergy': None
                    })

            return battery_states

        except requests.exceptions.RequestException as e:
            self.log(f"Error retrieving SolarEdge battery data for site {site_id}: {e}")
            return []
    

    def get_alerts(self, site_id):
        site_id = '1868399'
        """Retrieve the list of SolarEdge alerts for a specific site."""
        url = SOLAREDGE_V2_URL + f'/site/{site_id}/alerts'
        try:
            headers = {
            "X-Account-Key": "",
            "Accept": "application/json, application/problem+json",
            "X-API-Key": self.api_key
            }
            response = requests.get(url)
            response.raise_for_status()
            alert = response.json().get('details').get('')
            if alert > 0:
                return [alert]
            return []
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
                platform.log(f"  ID: {site['id']}, Name: {site['name']}")
        else:
            platform.log("No sites found.")
            return  # Nothing to test if no sites are found.
    except Exception as e:
        platform.log(f"Error while fetching sites: {e}")
        return

    # Fetch all SolarEdge alerts
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

if __name__ == "__main__":
    main()