from datetime import datetime, timedelta
from dataclasses import asdict
import numpy as np
import pandas as pd
import folium
import plotly.express as px
import requests
import streamlit as st
import streamlit.components.v1 as components
from streamlit_folium import st_folium
import SolarPlatform
import SqlModels as Sql
import Database as db
from FleetCollector import collect_platform, run_collection
from SolarEdge import SolarEdgePlatform
import altair as alt

from api_keys import STREAMLIT_PASSWORD

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
    import numpy as np
    import folium
    from streamlit_folium import st_folium

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
            print(f"Skipping marker for {row.get('site_id')} - {row.get('name')}: coordinates ({lat}, {lon}) out of bounds")
            continue  # Skip this marker
        
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
    
    st_folium(m, width=1200) #, zoom=5, zoom_snap=0.1)

def display_historical_chart(historical_df, site_ids):
    if not site_ids:
        site_data = historical_df.copy()
    else:
        site_data = historical_df[historical_df['site_id'].isin(site_ids)]
    
    # Aggregate the production by date (summing the production values)
    agg_data = site_data.groupby("date", as_index=False)["production_kw"].sum()
    
    # Create a thick line by specifying the size parameter in mark_line.
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
        filtered_df = filtered_df[filtered_df['severity'].isin(severity_filter)]
    if sort_by:
        filtered_df = filtered_df.sort_values(by=sort_by, ascending=ascending)
    return filtered_df


def login():
    # Create a password input widget that masks the input
    password = st.text_input("Enter the password", type="password")
    
    # When the login button is clicked, validate the password
    if st.button("Login"):
        if password == STREAMLIT_PASSWORD:
            st.session_state.authenticated = True
            st.success("Logged in successfully!")
        else:
            st.error("Incorrect password. Please try again.")

# Streamlit UI
# Setup page and initialize DB
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
# Retrieve site history from the database
sites_history_df = db.fetch_sites()[["site_id", "history"]]

if not alerts_df.empty:
    # Filter out unwanted alert types
    alerts_df = alerts_df[alerts_df['alert_type'] != 'SNOW_ON_SITE']

    # --- Site Production failure ---
    st.header("Site Production failure")
    production_df = alerts_df[alerts_df['alert_type'] == 'INVERTER_BELOW_THRESHOLD_LIMIT']
    production_df = production_df.merge(sites_history_df, on="site_id", how="left")
    edited_production_df = st.data_editor(
        production_df,
        key="production_production",
        column_config={
            "url": st.column_config.LinkColumn(
                label="Site url",
                display_text="Link"
            )
        }
    )
    if st.button("Save Production Site History Updates", key="save_prod_history"):
        for _, row in edited_production_df.iterrows():
            db.update_site_history(row['site_id'], row['history'])
    alerts_df = alerts_df[alerts_df['alert_type'] != 'INVERTER_BELOW_THRESHOLD_LIMIT']

    # --- Site Communication failure ---
    st.header("Site Communication failure")
    comms_df = alerts_df[alerts_df['alert_type'] == 'SITE_COMMUNICATION_FAULT']
    comms_df = comms_df.merge(sites_history_df, on="site_id", how="left")
    comms_df = comms_df.drop(columns=["alert_type", "details", "severity"])
    edited_comms_df = st.data_editor(
        comms_df,
        key="comms_editor",
        use_container_width=False,
        column_config={
            "url": st.column_config.LinkColumn(
                label="Site url",
                display_text="Link"
            ),
            "history": st.column_config.TextColumn(label="History                                                                                                     X")
        }
    )
    if st.button("Save Communication Site History Updates", key="save_comms_history"):
        for _, row in edited_comms_df.iterrows():
            db.update_site_history(row['site_id'], row['history'])
    alerts_df = alerts_df[alerts_df['alert_type'] != 'SITE_COMMUNICATION_FAULT']

    # --- Panel-level failures ---
    st.header("Panel-level failures")
    panel_df = alerts_df[alerts_df['alert_type'] == 'PANEL_COMMUNICATION_FAULT']
    panel_df = panel_df.merge(sites_history_df, on="site_id", how="left")
    edited_panel_df = st.data_editor(
        panel_df,
        key="panel_editor",
        column_config={
            "url": st.column_config.LinkColumn(
                label="Site url",
                display_text="Link"
            )
        }
    )
    if st.button("Save Panel Site History Updates", key="save_panel_history"):
        for _, row in edited_panel_df.iterrows():
            db.update_site_history(row['site_id'], row['history'])

    alerts_df = alerts_df[alerts_df['alert_type'] != 'PANEL_COMMUNICATION_FAULT']

    # --- System Configuration failure ---
    st.header("System Configuration failure")
    sysconf_df = alerts_df.copy()
    sysconf_df = sysconf_df.merge(sites_history_df, on="site_id", how="left")
    edited_sysconf_df = st.data_editor(
        sysconf_df,
        key="sysconf_editor",
        column_config={
            "url": st.column_config.LinkColumn(
                label="Site url",
                display_text="Link"
            )
        }
    )
    if st.button("Save System Config Site History Updates", key="save_sysconf_history"):
        for _, row in edited_sysconf_df.iterrows():
            db.update_site_history(row['site_id'], row['history'])
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

# Fetch recent production data for all sites
production_set = db.get_production_set(SolarPlatform.get_recent_noon())
df = pd.DataFrame([asdict(record) for record in production_set])

#FIXME, not 100% correct yet
platform = SolarEdgePlatform()
sites = platform.get_sites_map()

site_df = pd.DataFrame([asdict(site_info) for site_info in sites.values()])

def assign_site_type(site_id):
    return site_id[:2]

site_df["vendor_code"] = site_df["site_id"].apply(assign_site_type)

#Merge the production data with the site data
if not df.empty and 'latitude' in site_df.columns:
    site_df = site_df.merge(df, on="site_id", how="left")

    #Trim the values to 2 decimal places
    site_df['production_kw'] = site_df['production_kw'].round(2)

    create_map_view(site_df)

    # Sort the DataFrame in place by production_kw in descending order.
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
        height=len(site_df) * 25  # Approximately 25 pixels per site row.
    )        
    st.altair_chart(chart, use_container_width=True)
else:
    st.info("No production data available.")


    # # Duplicate the x-axis on the top by creating a second x-axis that overlays the original
    # fig.update_layout(
    #     # The original x-axis remains with its title at the bottom.
    #     # Now, define a second x-axis (xaxis2) that overlays x and is positioned at the top.
    #     xaxis2=dict(
    #         side='top',
    #         overlaying='x',  # This makes xaxis2 share the same domain as x
    #         showgrid=False,  # Optionally, disable grid lines for clarity
    #         title=dict(text="Production (kW)")
    #     )
    # )
    # Display the chart in Streamlit

    #     with tab2:
    #     st.subheader("Alerts Summary")
    #     # Example summary: count alerts by alert_type
    #     if not filtered_df.empty:
    #         summary_df = filtered_df.groupby("alert_type").size().reset_index(name="Count")
    #         st.dataframe(summary_df)
    #         st.bar_chart(summary_df.set_index("alert_type"))
    #     else:
    #         st.info("No data to summarize.")

    # with tab3:
    #     st.subheader("Alert Cards")
    #     # Using your previously commented-out alert card style for each row
    #     for idx, row in filtered_df.iterrows():
    #         cols = st.columns([3, 1])
    #         cols[0].markdown(f"**Name:** {row.get('Name', 'N/A')} | **Score:** {row.get('Score', 'N/A')}")
    #         if cols[1].button("Action", key=idx):
    #             st.write(f"Action clicked for {row.get('Name', 'this alert')}")
                