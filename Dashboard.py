from datetime import datetime, timedelta
from dataclasses import asdict
import requests
import numpy as np
import pandas as pd
import folium
import altair as alt
import streamlit as st
import streamlit.components.v1 as components
from streamlit_folium import st_folium

import SolarPlatform
import SqlModels as Sql
import Database as db
from FleetCollector import collect_platform, run_collection
from SolarEdge import SolarEdgePlatform

from api_keys import STREAMLIT_PASSWORD

# to do:

# General

#     Nearest Neighbor Calculation: The code for calculating the nearest neighbor for each site appears to be commented out. This feature seems important for providing context and comparisons. You might want to complete and enable this functionality.

# Sanity Checks: The sanity check in process_bulk_solar_production to prevent calibration on cloudy days is commented out. Consider enabling this check to ensure data quality.
# Timezone Hardcoding: The get_recent_noon function hardcodes the Eastern timezone. You might want to make this more flexible to handle sites in different timezones.

# SolarEdge.py

#     Alert Details: The alert_details variable in the get_alerts function is hardcoded to an empty string. You should fetch the actual alert details from the SolarEdge API.

# Error Handling: The get_alerts function has a general try-except block. Consider adding more specific exception handling for different types of requests.exceptions.RequestException to provide better error messages and recovery.

# Database.py

#     Production History Query: The query in get_production_set doesn't seem to respect the production_day filter correctly. This might lead to inaccurate historical data.

# Dashboard.py

#     Password Security: The STREAMLIT_PASSWORD is stored directly in the api_keys.py file. Consider using a more secure method for storing and managing passwords, such as environment variables or a secrets management service.
#     Map View Bounds: The create_map_view function uses a hardcoded bounding box for Michigan. This might not be suitable if you have sites outside of Michigan. You could calculate the map bounds dynamically based on the site locations.

# Data Validation: The create_map_view function includes checks to ensure latitude and longitude values are within reasonable bounds. Consider adding similar validation for other data points, such as production values, to prevent unexpected errors or visualizations.

# Enphase.py

#     Alert Severity: The severity for Enphase alerts is hardcoded to 50. You might want to implement a more accurate way to determine the severity based on the specific alert details.

# Error Handling: Similar to SolarEdge.py, consider adding more granular exception handling for different types of requests.exceptions.RequestException in the API calls.

# Additional Suggestions

#     Logging: The SolarPlatform class has a basic logging mechanism. You could enhance this by using a dedicated logging library like logging to provide more structured logging with different levels (debug, info, warning, error).

# Testing: Add unit tests to verify the functionality of individual functions and classes. This will help catch bugs early and ensure code changes don't break existing functionality.
# Documentation: Add docstrings to functions and classes to explain their purpose, parameters, and return values. This will improve code readability and maintainability.
# Code Style: Consider using a code linter to enforce consistent code style and formatting.

# Helper Functions


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


def create_map_view(sites_df):
    """
    Create a folium map that shows each site's current noon production.
    The icon background color is red if there is no production (power == 0),
    otherwise it remains blue.
    """
    # Center the map at the average location of all sites (initially)
    avg_lat = sites_df['latitude'].mean()
    avg_lon = sites_df['longitude'].mean()
    m = folium.Map(location=[avg_lat, avg_lon], zoom_start=5, width='100%')

    # Create a list to collect marker coordinates
    marker_coords = []

    # Define an approximate bounding box for Michigan.
    MIN_LAT, MAX_LAT = 41.7, 48.3
    MIN_LON, MAX_LON = -90, -82

    # Iterate over the DataFrame and add markers
    for _, row in sites_df.iterrows():
        lat = row['latitude']
        lon = row['longitude']

        # Sanity check: ignore if lat/lon is NaN or outside Michigan's bounding box.
        if np.isnan(lat) or np.isnan(lon) or lat < MIN_LAT or lat > MAX_LAT or lon < MIN_LON or lon > MAX_LON:
            print(
                f"Skipping marker for {row.get('site_id')} - {row.get('name')}: coordinates ({lat}, {lon}) out of bounds")
            continue

        marker_coords.append([lat, lon])

        if np.isnan(row['production_kw']) or row['production_kw'] < 0.1:
            color = "#FF0000"
        else:
            color = "#2A81CB"

        popup_html = (
            f"<strong>{row['name']} ({row['site_id']})</strong><br>"
            f"Production: {row['production_kw']} W"
        )

        folium.Marker(
            location=[lat, lon],
            popup=folium.Popup(popup_html, max_width=300),
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
                        {row['production_kw']}
                    </div>
                """
            )
        ).add_to(m)

    if marker_coords:
        m.fit_bounds(marker_coords)

    st_folium(m, width=1200)


def display_historical_chart(historical_df, site_ids):
    if not site_ids:
        site_data = historical_df.copy()
    else:
        site_data = historical_df[historical_df['site_id'].isin(site_ids)]

    # Aggregate the production by date (summing the production values)
    agg_data = site_data.groupby("date", as_index=False)["production_kw"].sum()

    chart = alt.Chart(agg_data).mark_line(size=5).encode(
        x=alt.X('date:T', title='Date'),
        y=alt.Y('power:Q', title='Aggregated Production (W)'),
        tooltip=['date:T', 'power:Q']
    ).properties(
        title="Aggregated Historical Production Data"
    )

    st.altair_chart(chart, use_container_width=True)


def filter_and_sort_alerts(alerts_df, alert_filter, severity_filter, sort_by, ascending):
    filtered_df = alerts_df.copy()
    if alert_filter:
        filtered_df = filtered_df[filtered_df['alert_type'].isin(alert_filter)]
    if severity_filter:
        filtered_df = filtered_df[filtered_df['severity'].isin(
            severity_filter)]
    if sort_by:
        filtered_df = filtered_df.sort_values(by=sort_by, ascending=ascending)
    return filtered_df


def login():
    password = st.text_input("Enter the password", type="password")
    if st.button("Login"):
        if password == STREAMLIT_PASSWORD:
            st.session_state.authenticated = True
            st.success("Logged in successfully!")
        else:
            st.error("Incorrect password. Please try again.")


def process_alert_section(df, header_title, editor_key, save_button_label, column_config, drop_columns=None, alert_type=None, use_container_width=True):
    """
    Helper to process an alert section.

    If alert_type is provided, it filters the dataframe accordingly.
    Optionally drops specified columns before rendering the data editor.
    Saves any history updates and removes that alert type from the dataframe.
    """
    st.header(header_title)
    if alert_type is not None:
        section_df = df[df['alert_type'] == alert_type].copy()
    else:
        section_df = df.copy()
    if drop_columns:
        section_df.drop(columns=drop_columns, inplace=True)
    edited_df = st.data_editor(
        section_df,
        key=editor_key,
        use_container_width=use_container_width,
        column_config=column_config
    )
    if st.button(save_button_label, key=editor_key + "_save"):
        for _, row in edited_df.iterrows():
            db.update_site_history(row['site_id'], row['history'])
    if alert_type is not None:
        df = df[df['alert_type'] != alert_type]
    return df


def assign_site_type(site_id):
    return site_id[:2]


# Main Streamlit UI

st.set_page_config(page_title="Absolute Solar Monitoring", layout="wide")
Sql.init_fleet_db()
st.title("☀️Absolute Solar Monitoring Dashboard")

if st.button("Run Collection"):
    run_collection()

if st.button("Delete All Alerts (Test)"):
    db.delete_all_alerts()
    st.success("All alerts deleted!")

st.markdown("---")

st.header("🚨 Active Alerts")

alerts_df = db.fetch_alerts()
sites_history_df = db.fetch_sites()[["site_id", "history"]]

if not alerts_df.empty:
    # Filter out unwanted alert types
    alerts_df = alerts_df[alerts_df['alert_type'] != 'SNOW_ON_SITE']
    # Merge site history once for all alerts
    merged_alerts_df = alerts_df.merge(
        sites_history_df, on="site_id", how="left")

    merged_alerts_df = process_alert_section(
        merged_alerts_df,
        header_title="Site Production failure",
        alert_type="INVERTER_BELOW_THRESHOLD_LIMIT",
        editor_key="production_production",
        save_button_label="Save Production Site History Updates",
        column_config={
            "url": st.column_config.LinkColumn(label="Site url", display_text="Link")
        }
    )

    merged_alerts_df = process_alert_section(
        merged_alerts_df,
        header_title="Site Communication failure",
        alert_type="SITE_COMMUNICATION_FAULT",
        editor_key="comms_editor",
        save_button_label="Save Communication Site History Updates",
        column_config={
            "url": st.column_config.LinkColumn(label="Site url", display_text="Link"),
            "history": st.column_config.TextColumn(label="History                                                                                                     X")
        },
        drop_columns=["alert_type", "details", "severity"],
        use_container_width=False
    )

    merged_alerts_df = process_alert_section(
        merged_alerts_df,
        header_title="Panel-level failures",
        alert_type="PANEL_COMMUNICATION_FAULT",
        editor_key="panel_editor",
        save_button_label="Save Panel Site History Updates",
        column_config={
            "url": st.column_config.LinkColumn(label="Site url", display_text="Link")
        }
    )

    process_alert_section(
        merged_alerts_df,
        header_title="System Configuration failure",
        editor_key="sysconf_editor",
        save_button_label="Save System Config Site History Updates",
        column_config={
            "url": st.column_config.LinkColumn(label="Site url", display_text="Link")
        },
        alert_type=None
    )
else:
    st.success("No active alerts.")

st.header("🔋 Batteries Below 10%")
low_batteries_df = db.fetch_low_batteries()
if not low_batteries_df.empty:
    st.dataframe(low_batteries_df, height=300)
else:
    st.success("All batteries above 10%.")

with st.expander("🔋 Full Battery List (Sorted by SOC, Hidden by Default)"):
    all_batteries_df = db.fetch_all_batteries()
    if all_batteries_df is not None and not all_batteries_df.empty:
        st.dataframe(all_batteries_df, height=400)
    else:
        st.success("No battery data available.")

st.header("🌍 Site Map with Production Data")

production_set = db.get_production_set(SolarPlatform.get_recent_noon())
df = pd.DataFrame([asdict(record) for record in production_set])

platform = SolarEdgePlatform()
sites = platform.get_sites_map()

site_df = pd.DataFrame([asdict(site_info) for site_info in sites.values()])
site_df["vendor_code"] = site_df["site_id"].apply(
    SolarPlatform.extract_vendor_code)

if not df.empty and 'latitude' in site_df.columns:
    site_df = site_df.merge(df, on="site_id", how="left")
    site_df['production_kw'] = site_df['production_kw'].round(2)
    create_map_view(site_df)

    site_df.sort_values("production_kw", ascending=False, inplace=True)
    color_scale = alt.Scale(
        domain=["EN", "SE", "SMA"],
        range=["orange", "#8B0000", "steelblue"]
    )

    chart = alt.Chart(site_df).mark_bar().encode(
        x=alt.X('production_kw:Q', title='Production (kW)'),
        y=alt.Y(
            'name:N',
            title='Site Name',
            sort=alt.SortField(field='production_kw', order='descending')
        ),
        color=alt.Color('vendor_code:N', scale=color_scale, title='Site Type'),
        tooltip=[
            alt.Tooltip('name:N', title='Site Name'),
            alt.Tooltip('production_kw:Q', title='Production (kW)')
        ]
    ).properties(
        title="Noon Production per Site",
        height=len(site_df) * 25
    )

    st.altair_chart(chart, use_container_width=True)
else:
    st.info("No production data available.")
