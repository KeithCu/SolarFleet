from SolarPlatform import SolarPlatform
import requests

class SolarEdgePlatform(SolarPlatform):
    def __init__(self, api_key):
        self.api_key = api_key

    def get_sites(self):
        """Retrieve the list of SolarEdge sites."""
        url = f'https://monitoringapi.solaredge.com/sites/list?api_key={api_key}'
        try:
            response = requests.get(url)
            response.raise_for_status()
            return response.json().get('sites', {}).get('site', [])
        except requests.exceptions.RequestException as e:
            print(f"Failed to retrieve SolarEdge sites: {e}")
            return []

def get_batteries_state_of_energy(api_key, site_id):
    """Retrieve SolarEdge battery state of energy."""
    url = f'https://monitoringapi.solaredge.com/site/{site_id}/storageData?api_key={api_key}'
    try:
        response = requests.get(url)
        response.raise_for_status()
        return response.json().get('storageData', {}).get('batteries', [])
    except requests.exceptions.RequestException as e:
        print(f"Failed to retrieve SolarEdge battery data: {e}")
        return []

def get_solaredge_alerts(api_key, site_id):
    """Retrieve the list of SolarEdge alerts for a specific site."""
    url = f'https://monitoringapi.solaredge.com/site/{site_id}/alerts?api_key={api_key}'
    try:
        response = requests.get(url)
        response.raise_for_status()
        return response.json().get('alerts', [])
    except requests.exceptions.RequestException as e:
        print(f"Failed to retrieve SolarEdge alerts: {e}")
        return []