import math
import os
from datetime import datetime

# Third-party imports
import requests
import numpy as np
import pandas as pd
import folium
import altair as alt
import streamlit as st
from streamlit_folium import folium_static as st_folium

# Local application imports
import Database as db
import SolarPlatform

def send_browser_notification(title, message):
    js_code = f"""
    if ("Notification" in window) {{
        if (Notification.permission === "granted") {{
            new Notification("{title}", {{ body: "{message}" }});
        }} else if (Notification.permission !== "denied") {{
            Notification.requestPermission().then(permission => {{
                if (permission === "granted") {{
                    new Notification("{title}", {{ body: "{message}" }});
                }}
            }});
        }}
    }}
    """
    st.components.v1.html(f"<script>{js_code}</script>", height=0)


def format_production_tooltip(production_kw):
    if not isinstance(production_kw, dict):
        return str(production_kw)  # Handle unexpected types gracefully
    formatted_dict = ', '.join(f"{key}: {value:.2f}" for key, value in production_kw.items())
    return f"{{{formatted_dict}}}"

def display_historical_chart():
    historical_df = db.get_total_noon_kw()

    historical_df['production_day'] = pd.to_datetime(historical_df['production_day'])
    historical_df['production_day'] = historical_df['production_day'].dt.normalize() + pd.Timedelta('12h') # Set time to noon

    chart = alt.Chart(historical_df).mark_line(size=5).encode(
        x=alt.X('production_day:T', title='Date', axis=alt.Axis(format='%m-%d')),  # Show only the date
        y=alt.Y('total_noon_kw:Q', title='Aggregated Production (KW)'),
        tooltip=['production_day:T', 'total_noon_kw:Q']
    )

    st.altair_chart(chart, use_container_width=True)

def display_production_chart(site_df):
    #Strip out all sites with no production.
    chart_df = site_df[site_df['production_kw_total'] != 0]

    chart_df = chart_df.copy() 
    chart_df.sort_values("production_kw_total", ascending=False, inplace=True)
    color_scale = alt.Scale(
        domain=["EN", "SE", "SMA", "Solis"],
        range=["orange", "#8B0000", "steelblue", "#A65E2E"]
    )

    chart = alt.Chart(chart_df).mark_bar().encode(
        x=alt.X('production_kw_total:Q', title='Production (kW)', axis=alt.Axis(orient='top')),
        y=alt.Y(
            'name:N',
            title='Site Name',
            sort=alt.SortField(field='production_kw_total', order='descending')
        ),
        color=alt.Color('vendor_code:N', scale=color_scale, title='Site Type'),
        tooltip=[
            alt.Tooltip('name:N', title='Site Name'),
            alt.Tooltip('production_kw_total:Q', title='Production (kW)')
        ]
    ).properties(
        title="Noon Production per Site",
        height=len(chart_df) * 25
    )

    st.altair_chart(chart, use_container_width=True)

# Define a sorting key based on status to separate green from non-green
def get_sort_key(row):
    if row.get('is_offline', False):
        return 1  # Non-green (offline)
    status = SolarPlatform.has_low_production(row['production_kw'], None, None)
    if status == SolarPlatform.ProductionStatus.GOOD:
        return 0  # Green
    return 1  # Non-green (ISSUE or SNOWY)


def create_map_view(sites_df, fleet_avg, fleet_std):
    # Center the map at the average location of all sites
    avg_lat = sites_df['latitude'].mean()
    avg_lon = sites_df['longitude'].mean()
    m = folium.Map(location=[avg_lat, avg_lon], zoom_start=5, width='100%')

    # Define an approximate bounding box for Michigan
    MIN_LAT, MAX_LAT = 41.7, 48.3
    MIN_LON, MAX_LON = -90, -82

    marker_coords = []  # List to collect all marker coordinates for fitting the map

    # Group sites by (latitude, longitude) since same zip code means same coordinates
    for (lat, lon), group in sites_df.groupby(['latitude', 'longitude']):
        if pd.isna(lat) or pd.isna(lon) or lat < MIN_LAT or lat > MAX_LAT or lon < MIN_LON or lon > MAX_LON:
            print(f"Skipping markers for zipcode: {group['zipcode'].iloc[0]} - coordinates ({lat}, {lon}) out of bounds")
            continue

        # Get list of (index, row) from the group
        rows = list(group.iterrows())

        # Sort rows: green (0) first, non-green (1) last
        rows_sorted = sorted(rows, key=lambda r: get_sort_key(r[1]))

        # Calculate positions for markers
        N = len(rows_sorted)
        if N == 1:
            positions = [(lat, lon)]
        else:
            base_radius = 0.002  # Base radius in degrees
            R = base_radius * math.sqrt(N)  # Radius scales with sqrt(N)
            positions = []
            for i in range(N):
                theta = 360 * i / N  # Angle in degrees
                offset_lat = R * math.cos(math.radians(theta))
                offset_lon = R * math.sin(math.radians(theta))
                positions.append((lat + offset_lat, lon + offset_lon))

        # Add markers in the sorted order
        for i, (idx, row) in enumerate(rows_sorted):
            marker_lat, marker_lon = positions[i]
            marker_coords.append([marker_lat, marker_lon])

            # Determine marker color based on status (same logic as sorting)
            if row.get('is_offline', False):
                color = 'blue'  # Offline
            else:
                status = SolarPlatform.has_low_production(row['production_kw'], fleet_avg, fleet_std)
                if status is SolarPlatform.ProductionStatus.GOOD:
                    color = '#228B22'  # Green
                elif status is SolarPlatform.ProductionStatus.ISSUE:
                    color = '#FF0000'  # Red
                elif status is SolarPlatform.ProductionStatus.SNOWY:
                    color = '#c9c9c9'  # Gray

            production_data = row["production_kw"]
            tooltip_content = format_production_tooltip(production_data)
            total_production = SolarPlatform.calculate_production_kw(production_data)

            # Add the marker to the map
            folium.Marker(
                location=[marker_lat, marker_lon],
                popup=folium.Popup(
                    f"<strong>{row['name']} ({row['site_id']})</strong><br>Production: {tooltip_content}",
                    max_width=300
                ),
                icon=folium.DivIcon(
                    html=f"""
                        <div style="
                            background-color: {color};
                            border-radius: 50%;
                            width: 30px;
                            height: 30px;
                            display: flex;
                            align-items: center;
                            justify-content: center;
                            color: white;
                            border: 2px solid #fff;
                            font-weight: bold;">
                            {total_production:.2f}
                        </div>
                    """
                )
            ).add_to(m)

    # Fit the map to include all markers
    if marker_coords:
        m.fit_bounds(marker_coords)

    st_folium(m, width=1200)

def display_battery_section(site_df):
    st.header("🔋 Batteries Below 10%")
    low_batteries_df = db.fetch_low_batteries()
    if not low_batteries_df.empty:
        # Merge battery info with site data to include 'name' and 'url'
        low_batteries_df = low_batteries_df.merge(
            site_df[['site_id', 'name', 'url']],
            on="site_id",
            how="left"
        )
        if SolarPlatform.FAKE_DATA:
            low_batteries_df["site_id"] = low_batteries_df["site_id"].apply(lambda x: SolarPlatform.generate_fake_site_id())
            low_batteries_df["name"] = low_batteries_df["site_id"].apply(lambda x: SolarPlatform.generate_fake_address())

        # Reorder columns: site_id, name, url first, then the rest.
        cols = low_batteries_df.columns.tolist()
        new_order = ['site_id', 'name', 'url'] + [c for c in cols if c not in ['site_id', 'name', 'url']]
        low_batteries_df = low_batteries_df[new_order]

        st.data_editor(
            low_batteries_df,
            key="low_batteries_editor",
            use_container_width=True,
            column_config={
                "url": st.column_config.LinkColumn(label="Site URL", display_text="Link")
            },
            disabled=True
        )
    else:
        st.success("All batteries above 10%.")

    with st.expander("🔋 Full Battery List (Sorted by SOC, Hidden by Default)"):
        all_batteries_df = db.fetch_all_batteries()
        if all_batteries_df is not None and not all_batteries_df.empty:
            all_batteries_df = all_batteries_df.merge(
                site_df[['site_id', 'name', 'url']],
                on="site_id",
                how="left"
            )

            if SolarPlatform.FAKE_DATA:
                low_batteries_df["site_id"] = low_batteries_df["site_id"].apply(lambda x: SolarPlatform.generate_fake_site_id())
                low_batteries_df["name"] = low_batteries_df["site_id"].apply(lambda x: SolarPlatform.generate_fake_address())

            # Reorder columns: site_id, name, url first, then the rest.
            cols = all_batteries_df.columns.tolist()
            new_order = ['site_id', 'name', 'url'] + [c for c in cols if c not in ['site_id', 'name', 'url']]
            all_batteries_df = all_batteries_df[new_order]

            st.data_editor(
                all_batteries_df,
                key="all_batteries_editor",
                use_container_width=True,
                column_config={
                    "url": st.column_config.LinkColumn(label="Site URL", display_text="Link")
                },
                disabled=True
            )

def process_alert_section(df, header_title, editor_key, column_config, alert_type=None, use_container_width=True):
    st.header(header_title)
    
    if alert_type is not None:
        section_df = df[df['alert_type'] == alert_type].copy()
        section_df = section_df.drop(columns=['details'])
    else:
        section_df = df.copy()
    
    #drop alert_type section
    section_df = section_df.drop(columns=['alert_type'])


    section_df['first_triggered'] = pd.to_datetime(section_df['first_triggered'], utc=True)
    section_df['first_triggered'] = pd.to_datetime(section_df['first_triggered']).dt.date
    section_df = section_df.sort_values('first_triggered', ascending=False)

    original_key = f"original_{editor_key}"
    
    if original_key not in st.session_state:
        st.session_state[original_key] = section_df.copy()
    
    edited_df = st.data_editor(
        data=st.session_state[original_key],
        key=editor_key,
        use_container_width=use_container_width,
        column_config=column_config
    )
    
    changed_rows = edited_df[edited_df['history'] != st.session_state[original_key]['history']]
    
    if not changed_rows.empty:
        for _, row in changed_rows.iterrows():
            db.update_site_history(row['site_id'], row['history'])
        st.session_state[original_key]['history'] = edited_df['history'].copy()
        st.success(f"Changes saved for {header_title}")
        st.rerun()

def create_alert_section(site_df, alerts_df, sites_history_df):
    alerts_df = alerts_df.merge(site_df[['site_id', 'name', 'url']], on="site_id", how="left")
    merged_alerts_df = alerts_df.merge(sites_history_df, on="site_id", how="left")
        
    merged_alerts_df = merged_alerts_df[
        ['site_id', 'name', 'url'] + 
        [col for col in merged_alerts_df.columns if col not in ['site_id', 'name', 'url']]
    ]
    
    column_config = {
        "url": st.column_config.LinkColumn(label="Site url", display_text="Link"),
        "history": st.column_config.TextColumn(label="History")
    }
    
    process_alert_section(
        df=merged_alerts_df,
        header_title="Site Production failure",
        editor_key="production_editor",
        column_config=column_config,
        alert_type=SolarPlatform.AlertType.PRODUCTION_ERROR
    )
    
    process_alert_section(
        df=merged_alerts_df,
        header_title="Site Communication failure",
        editor_key="comms_editor",
        column_config=column_config,
        alert_type=SolarPlatform.AlertType.NO_COMMUNICATION
    )
    
    process_alert_section(
        df=merged_alerts_df,
        header_title="Panel-level failures",
        editor_key="panel_editor",
        column_config=column_config,
        alert_type=SolarPlatform.AlertType.PANEL_ERROR
    )
    
    excluded_alert_types = [
        SolarPlatform.AlertType.PRODUCTION_ERROR,
        SolarPlatform.AlertType.NO_COMMUNICATION,
        SolarPlatform.AlertType.PANEL_ERROR
    ]
    
    config_failure_df = merged_alerts_df[~merged_alerts_df['alert_type'].isin(excluded_alert_types)]
    
    process_alert_section(
        df=config_failure_df,
        header_title="System Configuration failure",
        editor_key="sysconf_editor",
        column_config=column_config,
        alert_type=None
    )

# --- Streamlit Weather Widget ---


WEATHER_API_KEY = os.getenv("WEATHER_API_KEY")
WEATHER_CACHE_TIMEOUT = 3600 * 12  # 12 hours
DEFAULT_WEATHER_LAT = "42.3297"
DEFAULT_WEATHER_LON = "83.0425"

# --- Weather cache bucketing helpers ---
WEATHER_BUCKET_PRECISION = 1  # Decimal places for lat/lon rounding

def _round_coord(val, precision=WEATHER_BUCKET_PRECISION):
    return round(float(val), int(precision))

def _bucket_key(lat, lon, precision=WEATHER_BUCKET_PRECISION):
    return f"{_round_coord(lat, precision):.{precision}f},{_round_coord(lon, precision):.{precision}f}"

def _weather_cache_key(lat, lon, date_str=None):
    if date_str is None:
        date_str = datetime.now().date().isoformat()
    key = _bucket_key(lat, lon)
    return f"weather:{key}:{date_str}"

def get_browser_location():
    """Request browser geolocation and store in st.session_state['browser_location']."""
    if 'browser_location' not in st.session_state:
        st.session_state['browser_location'] = None
        st.components.v1.html('''
            <script>
            navigator.geolocation.getCurrentPosition(
                function(pos) {
                    const coords = pos.coords.latitude + "," + pos.coords.longitude;
                    window.parent.postMessage({type: 'streamlit:setComponentValue', value: coords}, '*');
                }
            );
            </script>
        ''', height=0)
    # The rest is handled by Streamlit's session state and component communication.

@SolarPlatform.disk_cache(SolarPlatform.CACHE_EXPIRE_HOUR * 4)
def fetch_weather_data(lat, lon):
    """Fetch and process 5-day weather forecast from OpenWeatherMap."""
    url = f"https://api.openweathermap.org/data/2.5/forecast?lat={lat}&lon={lon}&units=imperial&appid={WEATHER_API_KEY}"
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        weather_data = response.json()
        daily_data = {}
        for entry in weather_data.get("list", []):
            date_str = entry.get("dt_txt", "")[:10]
            daily_data.setdefault(date_str, []).append(entry)
        processed = []
        for i, (date, entries) in enumerate(sorted(daily_data.items())[:5]):
            temp_mins = [e["main"]["temp_min"] for e in entries if "main" in e and "temp_min" in e["main"]]
            temp_maxs = [e["main"]["temp_max"] for e in entries if "main" in e and "temp_max" in e["main"]]
            pops = [e.get("pop", 0) for e in entries]
            rain_total = sum(e.get("rain", {}).get("3h", 0) for e in entries if "rain" in e)
            is_today = datetime.strptime(date, "%Y-%m-%d").date() == datetime.now().date()
            preferred_entry = entries[0] if is_today else next((e for e in entries if "12:00:00" in e.get("dt_txt", "")), entries[0])
            weather_main = preferred_entry["weather"][0]["main"] if preferred_entry.get("weather") and len(preferred_entry["weather"]) > 0 else "N/A"
            weather_icon = preferred_entry["weather"][0]["icon"] if preferred_entry.get("weather") and len(preferred_entry["weather"]) > 0 else "01d"
            processed.append({
                "dt": int(datetime.strptime(date, "%Y-%m-%d").timestamp()),
                "temp_min": min(temp_mins) if temp_mins else None,
                "temp_max": max(temp_maxs) if temp_maxs else None,
                "precipitation": round(max(pops) * 100) if pops else 0,
                "rain": round(rain_total, 2),
                "weather": weather_main,
                "weather_icon": weather_icon
            })
        return processed
    except Exception as e:
        st.warning(f"Could not fetch weather data: {e}")
        return None

def display_weather(lat=None, lon=None):
    """Display a 5-day weather forecast in Streamlit, using browser location if available and bucketed diskcache."""
    get_browser_location()
    browser_loc = st.session_state.get('browser_location', None)
    if browser_loc and len(browser_loc) == 2:
        lat, lon = browser_loc
    lat = lat or DEFAULT_WEATHER_LAT
    lon = lon or DEFAULT_WEATHER_LON

    # Always round down to the bucket precision before fetching weather data
    lat = math.floor(float(lat) * 10 ** WEATHER_BUCKET_PRECISION) / 10 ** WEATHER_BUCKET_PRECISION
    lon = math.floor(float(lon) * 10 ** WEATHER_BUCKET_PRECISION) / 10 ** WEATHER_BUCKET_PRECISION

    forecast = fetch_weather_data(lat, lon)

    st.markdown("### 5-Day Weather Forecast")
    if forecast:
        cols = st.columns(len(forecast))
        for i, day in enumerate(forecast):
            d = datetime.fromtimestamp(day["dt"])
            day_name = "Today" if d.date() == datetime.now().date() else d.strftime("%a")
            temp_max = round(day.get("temp_max", 0))
            temp_min = round(day.get("temp_min", 0))
            precipitation = round(day.get("precipitation", 0))
            weather_icon = day.get("weather_icon", "01d")
            weather_desc = day.get("weather", "N/A")
            with cols[i]:
                st.markdown(f"**{day_name}**")
                st.image(f"https://openweathermap.org/img/wn/{weather_icon}.png", width=60)
                st.markdown(f"{weather_desc}")
                st.markdown(f"**{temp_max}\u00b0 / {temp_min}\u00b0**")
                st.markdown(f"{precipitation}% precip")
    else:
        st.info("Weather data not available.")
