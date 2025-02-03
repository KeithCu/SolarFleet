import requests
import base64

# Enphase API Handling
ENPHASE_BASE_URL = "https://api.enphaseenergy.com/"
from api_keys import ENPHASE_CLIENT_ID, ENPHASE_CLIENT_SECRET, ENPHASE_API_KEY

def get_basic_auth_header(client_id, client_secret):
    """Generate a Basic auth header value from client ID and client secret."""
    credentials = f"{client_id}:{client_secret}"
    encoded_credentials = base64.b64encode(credentials.encode()).decode()
    return {"Authorization": f"Basic {encoded_credentials}"}

def authenticate_enphase(auth_code, redirect_uri):
    """
    Authenticate with Enphase API v4 using the authorization code flow.
    
    Parameters:
        auth_code (str): The authorization code obtained after user approval.
        redirect_uri (str): The redirect URI used during authorization.
    
    Returns:
        tuple: (access_token, refresh_token) on success or (None, None) on failure.
    """
    url = f"{ENPHASE_BASE_URL}/oauth/token"
    data = {
        "grant_type": "authorization_code",
        "code": auth_code,
        "redirect_uri": redirect_uri
    }
    headers = get_basic_auth_header(ENPHASE_CLIENT_ID, ENPHASE_CLIENT_SECRET)
    try:
        response = requests.post(url, data=data, headers=headers)
        response.raise_for_status()
        tokens = response.json()
        return tokens.get("access_token"), tokens.get("refresh_token")
    except requests.exceptions.RequestException as e:
        print(f"Authentication failed: {e}")
        return None, None
    
def get_enphase_systems(access_token):
    """
    Retrieve the list of Enphase systems.
    
    Parameters:
      access_token (str): A valid OAuth2 access token.
    
    Returns:
      list: List of systems or an empty list on error.
    """
    url = f"{ENPHASE_BASE_URL}/api/v4/systems"
    headers = {
        "Authorization": f"Bearer {access_token}",
        "key": ENPHASE_API_KEY  # The API key is required in the header
    }
    try:
         response = requests.get(url, headers=headers)
         response.raise_for_status()
         data = response.json()
         return data.get("systems", [])
    except requests.exceptions.RequestException as e:
         print(f"Failed to retrieve Enphase systems: {e}")
         return []

def get_enphase_battery_state_of_energy(system_id, access_token):
    """
    Retrieve the latest battery state of energy for a given system.
    
    Parameters:
      system_id (str or int): The Enphase system ID.
      access_token (str): A valid OAuth2 access token.
    
    Returns:
      list: Battery data or an empty list on error.
    """
    url = f"{ENPHASE_BASE_URL}/api/v4/systems/{system_id}/summary"
    headers = {
         "Authorization": f"Bearer {access_token}",
         "key": ENPHASE_API_KEY
    }
    try:
         response = requests.get(url, headers=headers)
         response.raise_for_status()
         data = response.json()
         return data.get("batteries", [])
    except requests.exceptions.RequestException as e:
         print(f"Failed to retrieve Enphase battery data: {e}")
         return []

# Example usage:
if __name__ == "__main__":
    # Replace these values with those obtained from your OAuth flow.
    auth_code = "your_authorization_code"
    redirect_uri = "https://api.enphaseenergy.com/oauth/redirect_uri"  # or your custom URI
    
    access_token, refresh_token = authenticate_enphase(auth_code, redirect_uri)
    if access_token:
        systems = get_enphase_systems(access_token)
        print("Enphase Systems:", systems)
        if systems:
            # Assuming you want data for the first system
            system_id = systems[0].get("system_id")
            battery_data = get_enphase_battery_state_of_energy(system_id, access_token)
            print("Battery Data:", battery_data)
    else:
        print("Could not authenticate with Enphase API.")
