import time
import requests
import base64
import json
import os
from api_keys import ENPHASE_CLIENT_ID, ENPHASE_CLIENT_SECRET, ENPHASE_API_KEY, \
                     ENPHASE_USER_EMAIL, ENPHASE_USER_PASSWORD
from SolarPlatform import SolarPlatform

ENPHASE_BASE_URL = "https://api.enphaseenergy.com"
TOKEN_FILE = "EnphaseTokens.json"

class EnphasePlatform(SolarPlatform):

    @classmethod
    def get_vendorcode():
        return "EN"

    @staticmethod
    def get_basic_auth_header(client_id, client_secret):
        credentials = f"{client_id}:{client_secret}"
        encoded_credentials = base64.b64encode(credentials.encode()).decode()
        return {"Authorization": f"Basic {encoded_credentials}"}

    @staticmethod
    def authenticate_enphase(username, password, refresh_token=None):
        url = f"{ENPHASE_BASE_URL}/oauth/token"
        if refresh_token:
            data = {
                "grant_type": "refresh_token",
                "refresh_token": refresh_token
            }
        else:
            data = {
                "grant_type": "password",
                "username": username,
                "password": password
            }
        headers = EnphasePlatform.get_basic_auth_header(ENPHASE_CLIENT_ID, ENPHASE_CLIENT_SECRET)
        try:
            response = requests.post(url, data=data, headers=headers)
            response.raise_for_status()
            tokens = response.json()
            # Expecting the OAuth response to include "expires_in"
            return tokens.get("access_token"), tokens.get("refresh_token"), tokens.get("expires_in")
        except requests.exceptions.RequestException as e:
            SolarPlatform.log(f"Authentication failed: {e}")
            return None, None, None

    @staticmethod
    def get_sites(access_token):
        url = f"{ENPHASE_BASE_URL}/api/v4/systems?key={ENPHASE_API_KEY}"
        headers = {"Authorization": f"Bearer {access_token}"}
        try:
            response = requests.get(url, headers=headers)
            response.raise_for_status()
            return response.json().get("systems", [])
        except requests.exceptions.RequestException as e:
            SolarPlatform.log(f"Failed to retrieve Enphase systems: {e}")
            return []

    @staticmethod
    def get_batteries_soe(system_id, access_token):
        url = f"{ENPHASE_BASE_URL}/api/v4/systems/{system_id}/summary?key={ENPHASE_API_KEY}"
        headers = {"Authorization": f"Bearer {access_token}"}
        try:
            response = requests.get(url, headers=headers)
            response.raise_for_status()
            return response.json().get("batteries", {})
        except requests.exceptions.RequestException as e:
            SolarPlatform.log(f"Failed to retrieve Enphase battery data for system {system_id}: {e}")
            return {}

def load_tokens():
    if os.path.exists(TOKEN_FILE):
        try:
            with open(TOKEN_FILE, 'r') as f:
                tokens = json.load(f)
                return (
                    tokens.get("access_token"),
                    tokens.get("refresh_token"),
                    tokens.get("expires_at")
                )
        except Exception as e:
            SolarPlatform.log(f"Error loading token file: {e}")
    return None, None, None

def save_tokens(access_token, refresh_token, expires_in):
    # Calculate expiration time based on current time and expires_in (seconds)
    expires_at = int(time.time()) + expires_in if expires_in else None
    tokens = {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "expires_at": expires_at
    }
    try:
        with open(TOKEN_FILE, 'w') as f:
            json.dump(tokens, f)
    except Exception as e:
        SolarPlatform.log(f"Error saving token file: {e}")

if __name__ == "__main__":
    current_time = int(time.time())
    # Load stored tokens (access_token, refresh_token, expires_at)
    stored_access_token, stored_refresh_token, expires_at = load_tokens()

    # Use the stored access token if it exists and is still valid.
    if stored_access_token and expires_at and current_time < expires_at:
        access_token = stored_access_token
        SolarPlatform.log("Using stored valid access token.")
        new_refresh_token = stored_refresh_token  # Retain the current refresh token
        expires_in = expires_at - current_time
    else:
        # If there is a stored refresh token, try using it to get a new access token.
        if stored_refresh_token:
            access_token, new_refresh_token, expires_in = EnphasePlatform.authenticate_enphase(
                ENPHASE_USER_EMAIL,
                ENPHASE_USER_PASSWORD,
                refresh_token=stored_refresh_token
            )
        else:
            access_token, new_refresh_token, expires_in = None, None, None

        # If the refresh token authentication failed, fall back to the password grant.
        if not access_token:
            access_token, new_refresh_token, expires_in = EnphasePlatform.authenticate_enphase(
                ENPHASE_USER_EMAIL,
                ENPHASE_USER_PASSWORD
            )

        if access_token:
            save_tokens(access_token, new_refresh_token, expires_in)
        else:
            SolarPlatform.log("Authentication failed, unable to retrieve tokens.")
            exit(1)

    # Now use the access token to retrieve systems and battery data.
    systems = EnphasePlatform.get_sites(access_token)
    if systems:
        system_id = systems[0].get("system_id")
        battery_data = EnphasePlatform.get_batteries_soc(system_id, access_token)
        print("Battery Data:", battery_data)
    else:
        SolarPlatform.log("No systems found.")
