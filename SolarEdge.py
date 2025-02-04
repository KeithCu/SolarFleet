from SolarPlatform import SolarPlatform
import requests
from datetime import datetime, timedelta
from api_keys import SOLAREDGE_API_KEY

SOLAREDGE_BASE_URL = f'https://monitoringapi.solaredge.com'

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
            print(f"Error retrieving SolarEdge battery data for site {site_id}: {e}")
            return []
    
    def get_alerts(self, site_id):
        """Retrieve the list of SolarEdge alerts for a specific site."""
        url = SOLAREDGE_BASE_URL + f'/site/{site_id}/alerts?api_key={self.api_key}'
        try:
            response = requests.get(url)
            response.raise_for_status()
            return response.json().get('alerts', [])
        except requests.exceptions.RequestException as e:
            print(f"Failed to retrieve SolarEdge alerts: {e}")
            return []
        
def main():
    platform = SolarEdgePlatform()

    print("Testing get_sites() API call...")
    try:
        sites = platform.get_sites()
        if sites:
            print("Retrieved Sites:")
            for site in sites:
                print(f"  ID: {site['id']}, Name: {site['name']}")
        else:
            print("No sites found.")
            return  # Nothing to test if no sites are found.
    except Exception as e:
        print(f"Error while fetching sites: {e}")
        return

    # Loop over each site to test the battery SoC retrieval robustly.
    print("\nTesting get_batteries_soc() API call for each site:")
    for site in sites:
        site_id = site['id']
        print(f"\nSite ID: {site_id} - {site['name']}")
        try:
            batteries = platform.get_batteries_soc(site_id)
            if batteries:
                for battery in batteries:
                    soc = battery.get('stateOfEnergy')
                    print(f"  Battery Serial Number: {battery.get('serial_number')}, "
                          f"Model: {battery.get('model_number')}, "
                          f"SoC: {soc if soc is not None else 'N/A'}")
            else:
                print("  No battery data found for this site.")
        except Exception as e:
            print(f"  Error fetching battery data for site {site_id}: {e}")

    # Optionally, also test alerts if needed.
    print("\nTesting get_alerts() API call for the first site:")
    first_site_id = sites[0]['id']
    try:
        alerts = platform.get_alerts(first_site_id)
        if alerts:
            print("Retrieved Alerts:")
            for alert in alerts:
                print(f"  Alert ID: {alert.get('id')}, Message: {alert.get('message')}")
        else:
            print("No alerts found for this site.")
    except Exception as e:
        print(f"Error while fetching alerts for site {first_site_id}: {e}")

if __name__ == "__main__":
    main()