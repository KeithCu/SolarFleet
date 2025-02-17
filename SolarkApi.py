import requests
import json
from datetime import datetime
from zoneinfo import ZoneInfo  # Requires Python 3.9+

# Configuration – update these values accordingly
energy_api_username = "your@email.com"
energy_api_password = "top_secret_password"
energy_api_plant_id = "your_plant_id"  # e.g. "123456"

base_url = "https://www.solarkcloud.com"
plant_id = energy_api_plant_id

# Step 1: Obtain an access token via POST to /oauth/token
token_url = f"{base_url}/oauth/token"
headers = {
    "Content-Type": "application/json;charset=UTF-8",
    "origin": f"{base_url}/oauth/token",
    "referer": f"{base_url}/oauth/token"
}
params = {
    "client_id": "csp-web",
    "grant_type": "password",
    "username": energy_api_username,
    "password": energy_api_password,
}

try:
    token_response = requests.post(token_url, headers=headers, json=params)
    token_response.raise_for_status()
except requests.RequestException as e:
    print("Error obtaining token:", e)
    exit(1)

body_data = token_response.json()
data = body_data.get("data", {})
access_token = data.get("access_token")
print("Access Token:", access_token)

# Step 2: Get the current date in America/New_York timezone
current_datetime = datetime.now(ZoneInfo("America/New_York"))
current_date = current_datetime.strftime("%Y-%m-%d")
print("Current Date:", current_date)

# Step 3: Build the URL for retrieving energy data
# (The PHP code builds several URLs; here we use the 'flow' endpoint.)
action_url = f"{base_url}/api/v1/plant/energy/{plant_id}/flow"

# Define query parameters
user_params = {
    "date": current_date,
    "id": energy_api_plant_id,
    "lan": "en"
}

# Step 4: Make a GET request to the energy data endpoint using the token for authorization
headers_get = {
    "Authorization": f"Bearer {access_token}",
    "Accept": "application/json",
}

try:
    data_response = requests.get(action_url, headers=headers_get, params=user_params)
    data_response.raise_for_status()
except requests.RequestException as e:
    print("Error fetching energy data:", e)
    exit(1)

# Print the raw response text
print("Raw Energy Data Response:")
print(data_response.text)

# Parse and pretty-print the JSON 'data' field
data_body = data_response.json()
energy_data = data_body.get("data")
print("Parsed Energy Data:")
print(json.dumps(energy_data, indent=2))
