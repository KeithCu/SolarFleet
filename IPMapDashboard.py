import streamlit as st
from streamlit_folium import folium_static as st_folium
import folium
import requests
import time
import json
import os

from geoip2.database import Reader
reader = Reader('GeoLite2-City.mmdb')

# Predefined addresses to display on the map
PREDEFINED_ADDRESSES = [

]

# Cache file for geocoding results
GEOCODE_CACHE_FILE = 'geocode_cache.json'
# File for storing location metadata
LOCATION_METADATA_FILE = 'location_metadata.json'
# File for storing saved addresses
SAVED_ADDRESSES_FILE = 'saved_addresses.json'

def load_geocode_cache():
    """Load existing geocoding cache from file"""
    if os.path.exists(GEOCODE_CACHE_FILE):
        try:
            with open(GEOCODE_CACHE_FILE, 'r') as f:
                return json.load(f)
        except (json.JSONDecodeError, FileNotFoundError):
            return {}
    return {}

def save_geocode_cache(cache):
    """Save geocoding cache to file"""
    try:
        with open(GEOCODE_CACHE_FILE, 'w') as f:
            json.dump(cache, f, indent=2)
    except Exception as e:
        st.error(f"Error saving geocode cache: {e}")

def load_location_metadata():
    """Load location metadata from file"""
    if os.path.exists(LOCATION_METADATA_FILE):
        try:
            with open(LOCATION_METADATA_FILE, 'r') as f:
                return json.load(f)
        except (json.JSONDecodeError, FileNotFoundError):
            return {}
    return {}

def save_location_metadata(metadata):
    """Save location metadata to file"""
    try:
        with open(LOCATION_METADATA_FILE, 'w') as f:
            json.dump(metadata, f, indent=2)
    except Exception as e:
        st.error(f"Error saving location metadata: {e}")

def load_saved_addresses():
    """Load saved addresses from file"""
    if os.path.exists(SAVED_ADDRESSES_FILE):
        try:
            with open(SAVED_ADDRESSES_FILE, 'r') as f:
                return json.load(f)
        except (json.JSONDecodeError, FileNotFoundError):
            return {'ip_addresses': [], 'physical_addresses': []}
    return {'ip_addresses': [], 'physical_addresses': []}

def save_addresses(ip_addresses, physical_addresses):
    """Save addresses to file"""
    try:
        data = {
            'ip_addresses': ip_addresses,
            'physical_addresses': physical_addresses,
            'last_updated': time.strftime('%Y-%m-%d %H:%M:%S')
        }
        with open(SAVED_ADDRESSES_FILE, 'w') as f:
            json.dump(data, f, indent=2)
    except Exception as e:
        st.error(f"Error saving addresses: {e}")

def get_location_key(lat, lon, label):
    """Generate a unique key for a location"""
    return f"{lat:.6f}_{lon:.6f}_{label}"

def get_location_from_ip(ip):
    """Get location from IP address using GeoIP2 database"""
    try:
        response = reader.city(ip)
        lat = response.location.latitude
        lon = response.location.longitude
        city = response.city.name if response.city else 'Unknown'
        country = response.country.name if response.country else 'Unknown'
        return lat, lon, city, country
    except:
        return None, None, None, None

def geocode_address(address):
    """Geocode an address using OpenStreetMap Nominatim API with persistent caching"""
    # Load cache
    cache = load_geocode_cache()
    
    # Check if address is already cached
    if address in cache:
        cached_result = cache[address]
        if cached_result[0] is not None and cached_result[1] is not None:
            # Check if it's a successful geocode or city center fallback
            was_successful = cached_result[2] if len(cached_result) > 2 else True  # Default to True for old cache format
            if was_successful:
                # st.success(f"✅ Cached successful result for '{address}': {cached_result[0]:.6f}, {cached_result[1]:.6f}")
                return cached_result[0], cached_result[1], f"Successfully geocoded: {address}", False  # False = not from API
            else:
                # st.warning(f"⚠️ Cached city center result for '{address}': {cached_result[0]:.6f}, {cached_result[1]:.6f}")
                return cached_result[0], cached_result[1], f"City center for {address}", False  # False = not from API
        else:
            # st.warning(f"❌ Cached failure for '{address}' - will retry")
            pass
    
    try:
        # Use Nominatim API for geocoding
        url = "https://nominatim.openstreetmap.org/search"
        params = {
            'q': address,
            'format': 'json',
            'limit': 1
        }
        headers = {
            'User-Agent': 'IPMapDashboard/1.0'
        }
        
        # st.info(f"🌐 Geocoding '{address}'...")
        response = requests.get(url, params=params, headers=headers)
        response.raise_for_status()
        
        data = response.json()
        if data:
            lat = float(data[0]['lat'])
            lon = float(data[0]['lon'])
            display_name = data[0]['display_name']
            
            # Cache the successful result with success flag
            cache[address] = [lat, lon, True]  # True = successful geocode
            save_geocode_cache(cache)
            
            # st.success(f"✅ Successfully geocoded '{address}': {lat:.6f}, {lon:.6f}")
            # st.info(f"📍 Location: {display_name}")
            
            return lat, lon, display_name, True  # True = from API
        else:
            # Try to get city center as fallback
            city_name = address.split(',')[1].strip() if ',' in address else "Lansing"
            # st.warning(f"❌ Address not found, trying city center for '{city_name}'...")
            
            city_response = requests.get(url, params={'q': f"{city_name}, MI", 'format': 'json', 'limit': 1}, headers=headers)
            city_data = city_response.json()
            
            if city_data:
                lat = float(city_data[0]['lat'])
                lon = float(city_data[0]['lon'])
                display_name = city_data[0]['display_name']
                
                # Cache the city center result with failure flag
                cache[address] = [lat, lon, False]  # False = city center fallback
                save_geocode_cache(cache)
                
                # st.warning(f"📍 Placed in city center: {lat:.6f}, {lon:.6f}")
                return lat, lon, f"City center for {address}", True  # True = from API
            else:
                # Cache the failure
                cache[address] = [None, None]
                save_geocode_cache(cache)
                
                # st.error(f"❌ Could not find address or city center for '{address}'")
                return None, None, None, True  # True = from API
                
    except Exception as e:
        # Cache the failure
        cache[address] = [None, None]
        save_geocode_cache(cache)
        
        # st.error(f"❌ Error geocoding address '{address}': {str(e)}")
        return None, None, None, True  # True = from API

def main():
    st.title('IP Address & Physical Address Map Viewer')
    
    # Load location metadata and saved addresses
    location_metadata = load_location_metadata()
    saved_addresses = load_saved_addresses()
    
    # Initialize session state for selected location
    if 'selected_location_index' not in st.session_state:
        st.session_state.selected_location_index = 0
    
    # Initialize input variables
    ip_list = []
    address_list = []
    
    # Sidebar with tabs
    sidebar_tab1, sidebar_tab2 = st.sidebar.tabs(["Map Options", "Debug"])
    
    with sidebar_tab1:
        st.header("Map Options")
        show_predefined = st.checkbox("Show predefined addresses", value=True)
        
        # Location editing interface (will be populated after locations are processed)
        st.header("Edit Location Details")
        st.write("Select a location to edit its details:")
        
        # Create a placeholder for the selectbox
        location_placeholder = st.empty()
    
    with sidebar_tab2:
        st.header("Debug Options")
        
        # Cache management
        st.subheader("Cache Management")
        if st.button("Clear Geocode Cache"):
            cache = load_geocode_cache()
            cache.clear()
            save_geocode_cache(cache)
            st.success("Cache cleared!")
        
        if st.button("Clear Location Metadata"):
            location_metadata.clear()
            save_location_metadata(location_metadata)
            st.success("Location metadata cleared!")
        
        if st.button("Clear All Saved Addresses"):
            saved_addresses['ip_addresses'] = []
            saved_addresses['physical_addresses'] = []
            save_addresses([], [])
            st.success("All saved addresses cleared!")
            st.rerun()
        
        cache_stats = load_geocode_cache()
        st.info(f"Cached addresses: {len(cache_stats)}")
        st.info(f"Location metadata entries: {len(location_metadata)}")
        st.info(f"Saved IP addresses: {len(saved_addresses.get('ip_addresses', []))}")
        st.info(f"Saved physical addresses: {len(saved_addresses.get('physical_addresses', []))}")
        
        # Manual coordinate entry for failed addresses
        st.subheader("Manual Coordinates")
        st.write("For addresses that can't be geocoded:")
        manual_address = st.text_input("Address name", placeholder="e.g., 2695 EATON RAPIDS RD")
        col1, col2 = st.columns(2)
        with col1:
            manual_lat = st.number_input("Latitude", value=42.7, format="%.6f")
        with col2:
            manual_lon = st.number_input("Longitude", value=-84.5, format="%.6f")
        
        if st.button("Add Manual Location") and manual_address:
            locations.append({
                'lat': manual_lat, 
                'lon': manual_lon, 
                'type': 'Manual',
                'label': f'Manual: {manual_address}',
                'popup': f'Manual Entry: {manual_address}<br>Coordinates: {manual_lat:.6f}, {manual_lon:.6f}',
                'icon': 'map-pin'
            })
            st.success(f"Added manual location for {manual_address}")
    

    
    # Process locations
    locations = []
    
    # Process saved addresses first
    saved_ip_list = saved_addresses.get('ip_addresses', [])
    saved_physical_list = saved_addresses.get('physical_addresses', [])
    
    # Process saved IP addresses
    if saved_ip_list:
        for ip in saved_ip_list:
            ip = ip.strip()
            if ip:
                lat, lon, city, country = get_location_from_ip(ip)
                if lat and lon:
                    locations.append({
                        'lat': lat, 
                        'lon': lon, 
                        'type': 'IP',
                        'label': f'IP: {ip}',
                        'popup': f'IP: {ip}<br>City: {city}<br>Country: {country}',
                        'icon': 'globe'
                    })
    
    # Process saved physical addresses
    if saved_physical_list:
        for address in saved_physical_list:
            address = address.strip()
            if address:
                lat, lon, display_name, from_api = geocode_address(address)
                if lat and lon:
                    locations.append({
                        'lat': lat, 
                        'lon': lon, 
                        'type': 'Address',
                        'label': f'Address: {address[:50]}...' if len(address) > 50 else f'Address: {address}',
                        'popup': f'Address: {address}<br>Location: {display_name}',
                        'icon': 'home'
                    })
                # Only sleep if we made an API call
                if from_api:
                    time.sleep(1)  # Rate limiting for Nominatim API
    
    # Process new IP addresses from input
    if ip_list:
        st.info("Processing IP addresses...")
        for ip in ip_list:
            ip = ip.strip()
            if ip:
                lat, lon, city, country = get_location_from_ip(ip)
                if lat and lon:
                    locations.append({
                        'lat': lat, 
                        'lon': lon, 
                        'type': 'IP',
                        'label': f'IP: {ip}',
                        'popup': f'IP: {ip}<br>City: {city}<br>Country: {country}',
                        'icon': 'globe'
                    })
    
    # Process physical addresses
    if address_list:
        st.info("Processing physical addresses...")
        for address in address_list:
            address = address.strip()
            if address:
                lat, lon, display_name, from_api = geocode_address(address)
                if lat and lon:
                    locations.append({
                        'lat': lat, 
                        'lon': lon, 
                        'type': 'Address',
                        'label': f'Address: {address[:50]}...' if len(address) > 50 else f'Address: {address}',
                        'popup': f'Address: {address}<br>Location: {display_name}',
                        'icon': 'home'
                    })
                # Only sleep if we made an API call
                if from_api:
                    time.sleep(1)  # Rate limiting for Nominatim API

    
    # Add predefined addresses if selected
    if show_predefined:
        st.info("Processing predefined addresses...")
        for address in PREDEFINED_ADDRESSES:
            lat, lon, display_name, from_api = geocode_address(address)
            if lat and lon:
                locations.append({
                    'lat': lat, 
                    'lon': lon, 
                    'type': 'Address',  # Changed from 'Predefined' to 'Address' to get proper coloring
                    'label': f'Predefined: {address[:50]}...' if len(address) > 50 else f'Predefined: {address}',
                    'popup': f'Predefined Address: {address}<br>Location: {display_name}',
                    'icon': 'star'
                })
            # Only sleep if we made an API call
            if from_api:
                time.sleep(1)  # Rate limiting for Nominatim API

    
    # Display map
    if locations:
        st.subheader("Map View")
        
        # Create map
        m = folium.Map(location=[0, 0], zoom_start=2)
        
        # Add markers with different colors for different types
        for i, loc in enumerate(locations):
            # Generate unique key for this location
            location_key = get_location_key(loc['lat'], loc['lon'], loc['label'])
            
            # Get metadata for this location
            metadata = location_metadata.get(location_key, {})
            notes = metadata.get('notes', '')
            is_complete = metadata.get('is_complete', False)
            
            # Determine icon color based on completion status and type
            if loc['type'] == 'IP':
                icon_color = 'blue'
                icon = 'globe'
            elif loc['type'] == 'Address':
                if is_complete:
                    icon_color = 'green'  # Green for completed addresses
                else:
                    icon_color = 'orange'  # Orange for incomplete addresses
                icon = 'home'
            elif loc['type'] == 'Manual':
                if is_complete:
                    icon_color = 'green'
                else:
                    icon_color = 'purple'
                icon = 'map-pin'
            else:
                if is_complete:
                    icon_color = 'green'
                else:
                    icon_color = 'orange'
                icon = 'star'
            
            # Add notes and completion status to popup
            popup_content = loc['popup']
            if notes:
                popup_content += f"<br><br><strong>Notes:</strong> {notes}"
            if is_complete:
                popup_content += "<br><br>✅ <strong>Status: Complete</strong>"
            else:
                popup_content += "<br><br>⏳ <strong>Status: Incomplete</strong>"
            
            # Create enhanced tooltip with address and status
            tooltip_text = f"{loc['label']}"
            if notes:
                tooltip_text += f" | Notes: {notes[:50]}{'...' if len(notes) > 50 else ''}"
            if is_complete:
                tooltip_text += " | ✅ Complete"
            else:
                tooltip_text += " | ⏳ Incomplete"
            
            # Create marker with click handler
            marker = folium.Marker(
                [loc['lat'], loc['lon']], 
                popup=folium.Popup(popup_content, max_width=300),
                tooltip=tooltip_text,
                icon=folium.Icon(color=icon_color, icon=icon)
            )
            
            # Add click handler to select this location in sidebar
            marker.add_to(m)
            

        
        # Fit bounds to show all markers
        if len(locations) > 1:
            bounds = [[loc['lat'], loc['lon']] for loc in locations]
            m.fit_bounds(bounds)
        
        st_folium(m, width=800, height=600)
        
        # Location editing interface in sidebar
        if locations:
            # Create location options for the sidebar (remove "Predefined:" prefix for cleaner display)
            location_options = []
            for loc in locations:
                # Remove "Predefined:" prefix from labels for cleaner dropdown
                clean_label = loc['label'].replace('Predefined: ', '') if loc['label'].startswith('Predefined: ') else loc['label']
                location_options.append(f"{clean_label} ({loc['lat']:.6f}, {loc['lon']:.6f})")
            
            # Update the sidebar with the location selector
            with sidebar_tab1:
                # Add search functionality
                st.subheader("Search & Edit Locations")
                
                # Search box
                search_term = st.text_input("🔍 Search for address or location:", 
                                          placeholder="e.g., Lansing, Eaton Rapids, 2695...",
                                          help="Type any part of the address to filter the list")
                
                # Filter options based on search
                if search_term:
                    filtered_options = [opt for opt in location_options if search_term.lower() in opt.lower()]
                    if filtered_options:
                        st.success(f"Found {len(filtered_options)} matching locations")
                    else:
                        st.warning("No locations found matching your search")
                        filtered_options = location_options
                else:
                    filtered_options = location_options
                
                # Use session state to track selected location
                selected_index = st.session_state.selected_location_index
                if selected_index >= len(location_options):
                    selected_index = 0
                    st.session_state.selected_location_index = 0
                
                # Show filtered dropdown
                if filtered_options:
                    selected_location = st.selectbox("Choose location to edit:", filtered_options, index=0)
                    
                    # Find the actual index in the full list
                    if selected_location in location_options:
                        actual_index = location_options.index(selected_location)
                        st.session_state.selected_location_index = actual_index
                else:
                    selected_location = None
                

                
                if selected_location:
                    # Find the selected location
                    try:
                        # Find the index in the cleaned options list
                        selected_index = location_options.index(selected_location)
                        selected_loc = locations[selected_index]
                        location_key = get_location_key(selected_loc['lat'], selected_loc['lon'], selected_loc['label'])
                        
                        # Get current metadata
                        metadata = location_metadata.get(location_key, {})
                        current_notes = metadata.get('notes', '')
                        current_complete = metadata.get('is_complete', False)
                        
                        # Create editing form
                        with st.form(f"edit_form_{location_key}"):
                            st.write(f"**Editing:** {selected_loc['label']}")
                            
                            new_notes = st.text_area("Notes:", value=current_notes, 
                                                    placeholder="e.g., need to check roof seam, customer prefers morning visits...")
                            new_complete = st.checkbox("Mark as complete", value=current_complete)
                            
                            col1, col2 = st.columns(2)
                            with col1:
                                if st.form_submit_button("Save Changes"):
                                    location_metadata[location_key] = {
                                        'notes': new_notes,
                                        'is_complete': new_complete,
                                        'last_updated': time.strftime('%Y-%m-%d %H:%M:%S')
                                    }
                                    save_location_metadata(location_metadata)
                                    st.success("Location details updated!")
                                    st.rerun()
                            
                            with col2:
                                if st.form_submit_button("Clear Details"):
                                    if location_key in location_metadata:
                                        del location_metadata[location_key]
                                        save_location_metadata(location_metadata)
                                        st.success("Location details cleared!")
                                        st.rerun()
                    except (ValueError, IndexError):
                        pass
        
        # Display summary
        st.subheader("Summary")
        ip_count = len([loc for loc in locations if loc['type'] == 'IP'])
        address_count = len([loc for loc in locations if loc['type'] == 'Address'])
        manual_count = len([loc for loc in locations if loc['type'] == 'Manual'])
        
        # Count predefined addresses (those with "Predefined:" in the label)
        predefined_count = len([loc for loc in locations if loc['type'] == 'Address' and 'Predefined:' in loc['label']])
        regular_address_count = address_count - predefined_count
        
        # Count completed locations
        completed_count = 0
        for loc in locations:
            location_key = get_location_key(loc['lat'], loc['lon'], loc['label'])
            metadata = location_metadata.get(location_key, {})
            if metadata.get('is_complete', False):
                completed_count += 1
        
        st.write(f"Total locations: {len(locations)}")
        st.write(f"Completed locations: {completed_count}")
        st.write(f"Incomplete locations: {len(locations) - completed_count}")
        st.write(f"IP addresses: {ip_count}")
        st.write(f"Physical addresses: {regular_address_count}")
        st.write(f"Predefined addresses: {predefined_count}")
        st.write(f"Manual entries: {manual_count}")
        
        # Input areas at the bottom
        st.subheader("Add New Locations")
        
        # Show current saved addresses
        col1, col2 = st.columns([1, 1])
        with col1:
            st.subheader("Current Saved IP Addresses")
            if saved_ip_list:
                for ip in saved_ip_list:
                    st.write(f"• {ip}")
            else:
                st.write("No saved IP addresses")
        
        with col2:
            st.subheader("Current Saved Physical Addresses")
            if saved_physical_list:
                for addr in saved_physical_list:
                    st.write(f"• {addr}")
            else:
                st.write("No saved physical addresses")
        
        # Add new addresses
        col1, col2 = st.columns([1, 1])
        
        with col1:
            st.subheader("Add IP Addresses")
            ip_list_str = st.text_area('Paste new IP addresses, one per line', 
                                      placeholder="8.8.8.8\n1.1.1.1\n208.67.222.222")
            ip_list = ip_list_str.splitlines() if ip_list_str.strip() else []
        
        with col2:
            st.subheader("Add Physical Addresses")
            address_input = st.text_area('Paste new physical addresses, one per line',
                                        placeholder="123 Main St, Lansing, MI 48911\n456 Oak Ave, Grand Rapids, MI 49503")
            address_list = address_input.splitlines() if address_input.strip() else []
        
        # Process new locations
        new_locations = []
        
        # Process IP addresses
        if ip_list:
            for ip in ip_list:
                ip = ip.strip()
                if ip:
                    lat, lon, city, country = get_location_from_ip(ip)
                    if lat and lon:
                        new_locations.append({
                            'lat': lat, 
                            'lon': lon, 
                            'type': 'IP',
                            'label': f'IP: {ip}',
                            'popup': f'IP: {ip}<br>City: {city}<br>Country: {country}',
                            'icon': 'globe'
                        })
        
        # Process physical addresses
        if address_list:
            for address in address_list:
                address = address.strip()
                if address:
                    lat, lon, display_name, from_api = geocode_address(address)
                    if lat and lon:
                        new_locations.append({
                            'lat': lat, 
                            'lon': lon, 
                            'type': 'Address',
                            'label': f'Address: {address[:50]}...' if len(address) > 50 else f'Address: {address}',
                            'popup': f'Address: {address}<br>Location: {display_name}',
                            'icon': 'home'
                        })
                    # Only sleep if we made an API call
                    if from_api:
                        time.sleep(1)  # Rate limiting for Nominatim API
        
        # Add new locations to the main list (when locations exist)
        if new_locations:
            locations.extend(new_locations)
            
            # Save new addresses to persistent storage
            if ip_list:
                new_ip_addresses = [ip.strip() for ip in ip_list if ip.strip()]
                saved_addresses['ip_addresses'].extend(new_ip_addresses)
                # Remove duplicates
                saved_addresses['ip_addresses'] = list(set(saved_addresses['ip_addresses']))
            
            if address_list:
                new_physical_addresses = [addr.strip() for addr in address_list if addr.strip()]
                saved_addresses['physical_addresses'].extend(new_physical_addresses)
                # Remove duplicates
                saved_addresses['physical_addresses'] = list(set(saved_addresses['physical_addresses']))
            
            # Save to file
            save_addresses(saved_addresses['ip_addresses'], saved_addresses['physical_addresses'])
            
            st.success(f"Added {len(new_locations)} new locations to the map and saved addresses!")
            st.rerun()
        
    else:
        st.warning('No valid locations found. Please add some IP addresses or physical addresses.')
        
        # Input areas when no locations exist
        st.subheader("Add New Locations")
        
        # Show current saved addresses
        col1, col2 = st.columns([1, 1])
        with col1:
            st.subheader("Current Saved IP Addresses")
            if saved_ip_list:
                for ip in saved_ip_list:
                    st.write(f"• {ip}")
            else:
                st.write("No saved IP addresses")
        
        with col2:
            st.subheader("Current Saved Physical Addresses")
            if saved_physical_list:
                for addr in saved_physical_list:
                    st.write(f"• {addr}")
            else:
                st.write("No saved physical addresses")
        
        # Add new addresses
        col1, col2 = st.columns([1, 1])
        
        with col1:
            st.subheader("Add IP Addresses")
            ip_list_str = st.text_area('Paste new IP addresses, one per line', 
                                      placeholder="8.8.8.8\n1.1.1.1\n208.67.222.222")
            ip_list = ip_list_str.splitlines() if ip_list_str.strip() else []
        
        with col2:
            st.subheader("Add Physical Addresses")
            address_input = st.text_area('Paste new physical addresses, one per line',
                                        placeholder="123 Main St, Lansing, MI 48911\n456 Oak Ave, Grand Rapids, MI 49503")
            address_list = address_input.splitlines() if address_input.strip() else []
        
        # Process new locations
        new_locations = []
        
        # Process IP addresses
        if ip_list:
            for ip in ip_list:
                ip = ip.strip()
                if ip:
                    lat, lon, city, country = get_location_from_ip(ip)
                    if lat and lon:
                        new_locations.append({
                            'lat': lat, 
                            'lon': lon, 
                            'type': 'IP',
                            'label': f'IP: {ip}',
                            'popup': f'IP: {ip}<br>City: {city}<br>Country: {country}',
                            'icon': 'globe'
                        })
        
        # Process physical addresses
        if address_list:
            for address in address_list:
                address = address.strip()
                if address:
                    lat, lon, display_name, from_api = geocode_address(address)
                    if lat and lon:
                        new_locations.append({
                            'lat': lat, 
                            'lon': lon, 
                            'type': 'Address',
                            'label': f'Address: {address[:50]}...' if len(address) > 50 else f'Address: {address}',
                            'popup': f'Address: {address}<br>Location: {display_name}',
                            'icon': 'home'
                        })
                    # Only sleep if we made an API call
                    if from_api:
                        time.sleep(1)  # Rate limiting for Nominatim API
        
        # Add new locations to the main list (when no locations exist)
        if new_locations:
            locations.extend(new_locations)
            
            # Save new addresses to persistent storage
            if ip_list:
                new_ip_addresses = [ip.strip() for ip in ip_list if ip.strip()]
                saved_addresses['ip_addresses'].extend(new_ip_addresses)
                # Remove duplicates
                saved_addresses['ip_addresses'] = list(set(saved_addresses['ip_addresses']))
            
            if address_list:
                new_physical_addresses = [addr.strip() for addr in address_list if addr.strip()]
                saved_addresses['physical_addresses'].extend(new_physical_addresses)
                # Remove duplicates
                saved_addresses['physical_addresses'] = list(set(saved_addresses['physical_addresses']))
            
            # Save to file
            save_addresses(saved_addresses['ip_addresses'], saved_addresses['physical_addresses'])
            
            st.success(f"Added {len(new_locations)} new locations to the map and saved addresses!")
            st.rerun()

if __name__ == '__main__':
    main()