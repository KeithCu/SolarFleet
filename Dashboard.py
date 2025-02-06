import streamlit as st
from datetime import datetime, timedelta

from FleetCollector import add_alert_if_not_exists, Alert, Battery, update_alert_history, \
update_battery_data, init_fleet_db, fetch_alerts, update_battery_data, fetch_low_batteries, fetch_all_batteries

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

def collect_platform(platform):
    platform.log("Testing get_sites() API call...")
    try:
        sites = platform.get_sites()
        if sites:
            for site in sites:
                site_id = site['siteId']
                battery_data = platform.get_batteries_soe(site_id)
                for battery in battery_data:                    
                    update_battery_data(platform.get_vendorcode(), site_id, battery['serialNumber'], battery['model'], battery['stateOfEnergy'], "")
                    platform.log(f"Site {site_id} Battery Data: {battery_data}")
        else:
            platform.log("No sites found.")
            return  # Nothing to test if no sites are found.
    except Exception as e:
        platform.log(f"Error while fetching sites: {e}")
        return

def run_collection():
    platform = SolarEdgePlatform()
    collect_platform(platform)


# Streamlit UI
st.set_page_config(page_title="Absolute Solar Monitoring", layout="wide")
init_fleet_db()
st.title("☀️ Absolute Solar Monitoring Dashboard ☀️")
if st.button("Run Collection"):
    run_collection()

st.markdown("---")

col1, col2 = st.columns(2)

with col1:
    st.header("🚨 Active Alerts")
    alerts_df = fetch_alerts()
    if not alerts_df.empty:
        st.dataframe(alerts_df, height=300)
    else:
        st.success("No active alerts.")
    
    st.header("📝 Update Alert History")
    st.markdown("Append a new entry to an alert's history log.")
    
    # Use a form for better UX and to group inputs together
    with st.form("update_history_form", clear_on_submit=True):
        vendor_code = st.text_input("Vendor Code (3 characters)")
        system_id   = st.text_input("System ID")
        new_entry   = st.text_area("New History Entry")
        
        submit = st.form_submit_button("Update History")
        
        if submit:
            # Simple validation: ensure all fields are provided
            if not vendor_code or not system_id or not new_entry.strip():
                st.error("Please fill in all fields.")
            else:
                # Call your update function (make sure it appends a timestamp inside the function or here)
                timestamp_str = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")
                entry_with_timestamp = f"[{timestamp_str}] {new_entry.strip()}"
                
                success = update_alert_history(vendor_code, system_id, entry_with_timestamp)
                if success:
                    st.success("Alert history updated successfully!")
                else:
                    st.error("Failed to update alert history. Please verify the alert exists.")

    with st.expander("Add New Alert"):
        inverter = st.text_input("Inverter ID")
        alert_type = st.text_input("Alert Type")
        message = st.text_area("Message")
        if st.button("Submit Alert"):
            add_alert(inverter, alert_type, message)
            st.experimental_rerun()

with col2:
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
