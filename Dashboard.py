import streamlit as st
from datetime import datetime, timedelta
import diskcache

from FleetCollector import add_alert_if_not_exists, Alert, Battery, update_alert_history, \
update_battery_data, init_fleet_db, fetch_alerts, update_battery_data, fetch_low_batteries, fetch_all_batteries, collect_platform

from SolarEdge import SolarEdgePlatform

CACHE_DIR = "/tmp/"

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
st.set_page_config(page_title="Absolute Solar Monitoring", layout="wide")
init_fleet_db()
st.title("☀️ Absolute Solar Monitoring Dashboard ☀️")
if st.button("Run Collection"):
    run_collection()

if st.button("Show Cache Stats"):
    cache = diskcache.Cache(CACHE_DIR)

    stats = cache.stats()  # Get cache stats
    keys = list(cache.iterkeys())  # List all cache keys
    
    st.write("### Cache Statistics")
    st.json(stats)

    st.write(f"### Cached Items: {len(keys)}")
    
    if keys:
        st.write("### Cached Keys & Values")
        for key in keys:
            try:
                value = cache.get(key)
                st.write(f"**{key}** → {value}")
            except Exception as e:
                st.write(f"**{key}** → [Error fetching value] {e}")

st.markdown("---")

st.header("🚨 Active Alerts")
alerts_df = fetch_alerts()
# for idx, row in alerts_df.iterrows():
#     cols = st.columns([3, 1])
#     cols[0].write(f"**Name:** {row['Name']} | **Score:** {row['Score']}")
#     if cols[1].button("Action", key=idx):
#         st.write(f"Button clicked for {row['Name']}")

if not alerts_df.empty:
    # Sidebar filters
    st.sidebar.header("Filter Alerts")
    vendor_filter = st.sidebar.multiselect("Select Vendor(s)", alerts_df['vendor_code'].unique())
    alert_filter = st.sidebar.multiselect("Select Alert Type(s)", alerts_df['alert_type'].unique())
    severity_filter = st.sidebar.multiselect("Select Severity", alerts_df['severity'].unique())

    # Apply filters dynamically
    filtered_df = alerts_df.copy()
    if vendor_filter:
        filtered_df = filtered_df[filtered_df['vendor_code'].isin(vendor_filter)]
    if alert_filter:
        filtered_df = filtered_df[filtered_df['alert_type'].isin(alert_filter)]
    if severity_filter:
        filtered_df = filtered_df[filtered_df['severity'].isin(severity_filter)]

    st.dataframe(filtered_df, height=300, column_config={
    "site_url": st.column_config.LinkColumn(
        label="site_url",
        display_text=None) }
    )
        
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

