import streamlit as st
from datetime import datetime, timedelta
import pandas as pd
import numpy as np
import plotly.express as px
from FleetCollector import add_alert_if_not_exists, Alert, Battery, update_alert_history, \
update_battery_data, init_fleet_db, fetch_alerts, update_battery_data, fetch_low_batteries, fetch_all_batteries, collect_platform

from SolarEdge import SolarEdgePlatform

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

def run_collection():
    platform = SolarEdgePlatform()
    collect_platform(platform)

# Streamlit UI
# Setup page and initialize DB
st.set_page_config(page_title="Absolute Solar Monitoring", layout="wide")
init_fleet_db()
st.title("☀️Absolute Solar Monitoring Dashboard")
if st.button("Run Collection"):
    run_collection()

st.markdown("---")

st.header("🚨 Active Alerts")
alerts_df = fetch_alerts()

if not alerts_df.empty:
    # Sidebar filters
    st.sidebar.header("Filter Alerts")
    vendor_filter = st.sidebar.multiselect("Select Vendor(s)", alerts_df['vendor_code'].unique())
    alert_filter = st.sidebar.multiselect("Select Alert Type(s)", alerts_df['alert_type'].unique())
    severity_filter = st.sidebar.multiselect("Select Severity", alerts_df['severity'].unique())

    # Apply filters dynamically on a copy of the alerts dataframe
    filtered_df = alerts_df.copy()
    if vendor_filter:
        filtered_df = filtered_df[filtered_df['vendor_code'].isin(vendor_filter)]
    if alert_filter:
        filtered_df = filtered_df[filtered_df['alert_type'].isin(alert_filter)]
    if severity_filter:
        filtered_df = filtered_df[filtered_df['severity'].isin(severity_filter)]

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
low_batteries_df = fetch_low_batteries()
if not low_batteries_df.empty:
    st.dataframe(low_batteries_df, height=300)
else:
    st.success("All batteries above 10%.")

with st.expander("🔋 Full Battery List (Sorted by SOC, Hidden by Default)"):
    all_batteries_df = fetch_all_batteries()
    if not all_batteries_df.empty:
        st.dataframe(all_batteries_df, height=400)
    else:
        st.success("No battery data available.")


# Generate data for 250 sites
num_sites = 250
sites = [f"Site {i+1}" for i in range(num_sites)]
# Create random production data between 10 and 150 kW for noon production
production_values = np.random.randint(10, 150, size=num_sites)

# Create a DataFrame with the data and sort for a cleaner look
df = pd.DataFrame({
    "Site": sites,
    "Noon Production (kW)": production_values
}).sort_values("Noon Production (kW)", ascending=True)

# Streamlit dashboard header
st.title("Fleet Production Yesterday at Noon")

# Create a horizontal bar chart using Plotly Express
fig = px.bar(
    df,
    x="Noon Production (kW)",
    y="Site",
    orientation='h',  # Horizontal bars so that site names are on the y-axis
    title="Noon Production per Site",
    labels={"Noon Production (kW)": "Production (kW)", "Site": "Site Name"}
)

# Adjust the layout to be tall enough for all site names.
# For example, allocate roughly 20 pixels per site.
fig.update_layout(
    height=num_sites * 20,
    margin=dict(l=150, r=50, t=50, b=50)
)

# Display the chart in Streamlit
st.plotly_chart(fig, use_container_width=True)

    # st.header("📝 Update Alert History")
    # st.markdown("Append a new entry to an alert's history log.")
    
    # # Use a form for better UX and to group inputs together
    # with st.form("update_history_form", clear_on_submit=True):
    #     vendor_code = st.text_input("Vendor Code (3 characters)")
    #     system_id   = st.text_input("System ID")
    #     new_entry   = st.text_area("New History Entry")
        
    #     submit = st.form_submit_button("Update History")
        
    #     if submit:
    #         # Simple validation: ensure all fields are provided
    #         if not vendor_code or not system_id or not new_entry.strip():
    #             st.error("Please fill in all fields.")
    #         else:
    #             # Call your update function (make sure it appends a timestamp inside the function or here)
    #             timestamp_str = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")
    #             entry_with_timestamp = f"[{timestamp_str}] {new_entry.strip()}"
                
    #             success = update_alert_history(vendor_code, system_id, entry_with_timestamp)
    #             if success:
    #                 st.success("Alert history updated successfully!")
    #             else:
    #                 st.error("Failed to update alert history. Please verify the alert exists.")

    # with st.expander("Add New Alert"):
    #     inverter = st.text_input("Inverter ID")
    #     alert_type = st.text_input("Alert Type")
    #     message = st.text_area("Message")
    #     if st.button("Submit Alert"):
    #         add_alert(inverter, alert_type, message)
    #         st.experimental_rerun()

