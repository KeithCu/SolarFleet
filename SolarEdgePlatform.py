from SolarPlatform import SolarPlatform
import requests

class SolarEdgePlatform(SolarPlatform):
    def __init__(self, api_key):
        self.api_key = api_key

    def get_sites(self):
        url = f'https://monitoringapi.solaredge.com/sites/list?api_key={self.api_key}'
        response = requests.get(url)
        response.raise_for_status()
        sites = response.json().get('sites', {}).get('site', [])
        return [{'id': site['id'], 'name': site['name']} for site in sites]

    def get_battery_soc(self, site_id):
        url = f'https://monitoringapi.solaredge.com/site/{site_id}/storageData?api_key={self.api_key}'
        response = requests.get(url)
        response.raise_for_status()
        batteries = response.json().get('storageData', {}).get('batteries', [])
        return [{'serial_number': battery['serialNumber'], 'model_number': battery['modelNumber'], 'state_of_energy': battery.get('stateOfEnergy')} for battery in batteries]