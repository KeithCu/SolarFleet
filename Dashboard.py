import streamlit as st
from datetime import datetime, timedelta
import pandas as pd
import numpy as np
import plotly.express as px
import SqlModels as Sql
import Database as db
import SolarPlatform

from SolarEdge import SolarEdgePlatform
import requests
import streamlit.components.v1 as components
from FleetCollector import collect_platform

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
    import folium
    from streamlit_folium import folium_static

    # Create a map centered around the average coordinates
    avg_lat = sites_df['latitude'].mean()
    avg_lon = sites_df['longitude'].mean()
    m = folium.Map(location=[avg_lat, avg_lon], zoom_start=5)

    # Add markers for each site
    for _, row in sites_df.iterrows():
        folium.Marker(
            location=[row['latitude'], row['longitude']],
            popup=f"{row['site_name']} ({row['site_id']})",
            tooltip=row['site_name']
        ).add_to(m)

    # Display the map in Streamlit
    folium_static(m)

def filter_and_sort_alerts(alerts_df, vendor_filter, alert_filter, severity_filter, sort_by, ascending):
    filtered_df = alerts_df.copy()
    if vendor_filter:
        filtered_df = filtered_df[filtered_df['vendor_code'].isin(vendor_filter)]
    if alert_filter:
        filtered_df = filtered_df[filtered_df['alert_type'].isin(alert_filter)]
    if severity_filter:
        filtered_df = filtered_df[filtered_df['severity'].isin(severity_filter)]
    if sort_by:
        filtered_df = filtered_df.sort_values(by=sort_by, ascending=ascending)
    return filtered_df

def run_collection():
    platform = SolarEdgePlatform()
    collect_platform(platform)

def get_site_coordinates(sites):
    site_data = []
    for site_id, site_info in sites.items():
        zipcode = site_info.zipcode
        if isinstance(zipcode, pd.Series):
            zipcode = zipcode.iloc[0]  # Ensure it's a single value
        lat, lon = SolarPlatform.get_coordinates(zipcode)
        if lat and lon:
            site_data.append({
                "site_id": site_id,
                 "site_name": site_info.name,
                "latitude": lat,
                "longitude": lon,
                "zipcode": zipcode
            })
    return pd.DataFrame(site_data)

def display_map_with_production():
    platform = SolarEdgePlatform()
    sites = platform.get_sites_map()
    site_df = get_site_coordinates(sites)

    # Fetch production data
    production_data = db.fetch_production_data()
    site_df = site_df.merge(production_data, on="site_id", how="left")

    create_map_view(site_df)

# Streamlit UI
# Setup page and initialize DB
st.set_page_config(page_title="Absolute Solar Monitoring", layout="wide")
Sql.init_fleet_db()
st.title("☀️Absolute Solar Monitoring Dashboard")
if st.button("Run Collection"):
    run_collection()

st.markdown("---")

st.header("🚨 Active Alerts")
alerts_df = db.fetch_alerts()

if not alerts_df.empty:
    # Sidebar filters
    st.sidebar.header("Filter Alerts")
    vendor_filter = st.sidebar.multiselect("Select Vendor(s)", alerts_df['vendor_code'].unique())
    alert_filter = st.sidebar.multiselect("Select Alert Type(s)", alerts_df['alert_type'].unique())
    severity_filter = st.sidebar.multiselect("Select Severity", alerts_df['severity'].unique())
    sort_by = st.sidebar.selectbox("Sort By", options=["vendor_code", "alert_type", "severity"], index=0)
    ascending = st.sidebar.checkbox("Ascending", value=True)

    # Apply filters dynamically on a copy of the alerts dataframe
    filtered_df = filter_and_sort_alerts(alerts_df, vendor_filter, alert_filter, severity_filter, sort_by, ascending)

    # Create multiple views (tabs) from the filtered data
    tab1, tab2, tab3 = st.tabs(["Detailed Alerts", "Alerts Summary", "Alert Cards"])

    with tab1:
        st.subheader("Detailed Alerts")
        st.dataframe(filtered_df, height=300, column_config={
            "site_url": st.column_config.LinkColumn(
                label="site_url",
                display_text=None
            )
        })

    with tab2:
        st.subheader("Alerts Summary")
        # Example summary: count alerts by alert_type
        if not filtered_df.empty:
            summary_df = filtered_df.groupby("alert_type").size().reset_index(name="Count")
            st.dataframe(summary_df)
            st.bar_chart(summary_df.set_index("alert_type"))
        else:
            st.info("No data to summarize.")

    with tab3:
        st.subheader("Alert Cards")
        # Using your previously commented-out alert card style for each row
        for idx, row in filtered_df.iterrows():
            cols = st.columns([3, 1])
            cols[0].markdown(f"**Name:** {row.get('Name', 'N/A')} | **Score:** {row.get('Score', 'N/A')}")
            if cols[1].button("Action", key=idx):
                st.write(f"Action clicked for {row.get('Name', 'this alert')}")
                
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
    if not all_batteries_df.empty:
        st.dataframe(all_batteries_df, height=400)
    else:
        st.success("No battery data available.")

st.header("🌍 Site Map with Production Data")

# Fetch production data for all sites
production_data = db.fetch_production_data()

display_map_with_production()

if not production_data.empty:
    # Create a DataFrame with the production data and sort for a cleaner look
    df = production_data.sort_values("noon_production", ascending=True)

    # Streamlit dashboard header
    st.title("Fleet Production at Noon")

    # Create a horizontal bar chart using Plotly Express
    fig = px.bar(
        df,
        x="noon_production",
        y="site_id",
        orientation='h',  # Horizontal bars so that site names are on the y-axis
        title="Noon Production per Site",
        labels={"noon_production": "Production (kW)", "site_id": "Site ID"}
    )

    # Adjust the layout to be tall enough for all site names.
    # For example, allocate roughly 20 pixels per site.
    fig.update_layout(
        height=len(df) * 20,
        margin=dict(l=150, r=50, t=50, b=50)
    )

    # Duplicate the x-axis on the top by creating a second x-axis that overlays the original
    fig.update_layout(
        # The original x-axis remains with its title at the bottom.
        # Now, define a second x-axis (xaxis2) that overlays x and is positioned at the top.
        xaxis2=dict(
            side='top',
            overlaying='x',  # This makes xaxis2 share the same domain as x
            showgrid=False,  # Optionally, disable grid lines for clarity
            title=dict(text="Production (kW)")
        )
    )
    # Display the chart in Streamlit
    st.plotly_chart(fig, use_container_width=True)
else:
    st.info("No production data available.")

