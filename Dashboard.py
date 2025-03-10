from datetime import datetime
from dataclasses import asdict

import pandas as pd
import streamlit as st
import streamlit_authenticator as stauth
import yaml
from yaml.loader import SafeLoader

import SolarPlatform
import SqlModels as Sql
import Database as db
from FleetCollector import run_collection, save_site_yearly_production
from SolarEdge import SolarEdgePlatform
from Enphase import EnphasePlatform
import auth
import ui_components as ui

#
# Main Streamlit code/UI starts here
#

def main():

    title = "☀️ Absolute Solar Monitoring"
    st.set_page_config(page_title=title, layout="wide")
    Sql.init_fleet_db()
    st.title(title)

    with open('./config.yaml', encoding="utf-8") as file:
        config = yaml.load(file, Loader=SafeLoader)

    credentials = auth.load_credentials()

    authenticator = stauth.Authenticate(
        credentials['credentials'],
        config['cookie']['name'],
        config['cookie']['key'],
        config['cookie']['expiry_days'],
    )

    if "authentication_status" not in st.session_state:
        st.session_state["authentication_status"] = None

    try:
        auth_result = authenticator.login(location='main', key='Login')
    except Exception as e:
        st.error(f"Login error: {e}")
        auth_result = None

    if auth_result is not None:
        name, authentication_status, username = auth_result
    else:
        authentication_status = st.session_state.get("authentication_status", None)

    if authentication_status == True:
        authenticator.logout('Logout', 'main')
       
        #
        # After authentication
        #

        platform = SolarEdgePlatform()
        sites = platform.get_sites_map()

        platform = EnphasePlatform()
        sites_enphase = platform.get_sites_map()

        #depend on solaredge platform for now
        platform = SolarEdgePlatform()

        sites.update(sites_enphase)

        tab_content, tab_settings, tab_cache, tab_logs, tab_production, tab_users = st.tabs(["Content ", "Settings", "Cache", "Logs", "Production History", "Users"])
        with tab_content:
            st.metric("Active Sites In Fleet", len(sites))
            st.metric("Active Batteries", db.fetch_battery_count())

        with tab_settings:
            all_timezones = sorted(SolarPlatform.SELECT_TIMEZONES)
            current_timezone = SolarPlatform.cache.get('TimeZone', SolarPlatform.DEFAULT_TIMEZONE)      
            with st.expander("Time Zone Configuration", expanded=True):
                selected_timezone_str = st.selectbox(
                    "Select Time Zone",
                    options=all_timezones,
                    index=all_timezones.index(current_timezone) if current_timezone in all_timezones else 0 # Default to first if default_timezone not found
                )
                SolarPlatform.cache.add("TimeZone", selected_timezone_str)

            st.subheader("Ignored Sites")
            ignored_sites = db.get_ignored_sites()

            for site_id in ignored_sites:
                col1, col2 = st.columns([3, 1])
                col1.write(site_id)
                if col2.button("Remove", key=f"remove_{site_id}"):
                    db.remove_ignored_site(site_id)
                    st.rerun()

            site_id_to_ignore = st.text_input("Enter site_id to ignore (e.g., SE:12345)", key="ignore_site_id")
            if st.button("Add to Ignored"):
                if site_id_to_ignore:
                    db.add_ignored_site(site_id_to_ignore)
                    st.rerun()


        with tab_cache:
            st.subheader("Refresh Device Data Cache")
            site_id_to_refresh = st.text_input("Enter site_id to refresh device data (e.g., SE:12345 or EN:67890)")
            if st.button("Refresh Cache"):
                if site_id_to_refresh:
                    try:
                        vendor_code = SolarPlatform.extract_vendor_code(site_id_to_refresh)
                        raw_site_id = SolarPlatform.SolarPlatform.strip_vendorcodeprefix(site_id_to_refresh)
                        if vendor_code == "SE":
                            platform = SolarEdgePlatform()  # Instantiate temporarily
                            platform.delete_device_cache(raw_site_id)
                            st.success(f"Cache refreshed for SolarEdge site {raw_site_id}. Next collection will fetch fresh data.")
                        elif vendor_code == "EN":
                            platform = EnphasePlatform()  # Instantiate temporarily
                            platform.delete_device_cache(raw_site_id)
                            st.success(f"Cache refreshed for Enphase system {raw_site_id}. Next collection will fetch fresh data.")
                        else:
                            st.error(f"Unknown vendor code: {vendor_code}")
                    except ValueError as e:
                        st.error(f"Invalid site_id: {str(e)}")
                else:
                    st.warning("Please enter a site_id")


            if st.button("Delete Alerts (Test)"):
                db.delete_all_alerts()
                st.success("All alerts deleted!")
            if st.button("Delete Alerts API Cache (Test)"):
                alerts_cache_keys = [key for key in SolarPlatform.cache.iterkeys() if key.startswith("get_alerts")]
                for key in alerts_cache_keys:
                    del SolarPlatform.cache[key]
                st.success("Alerts cache cleared!")
            if st.button("Delete Battery data (Test)"):
                db.delete_all_batteries()
                st.success("Battery data cleared!")
            if st.button("convert api_keys to keyring"):
                SolarPlatform.set_keyring_from_api_keys()

        with tab_logs:
            with st.expander("Show Logs", expanded=False):
                st.text_area("Logs", value = SolarPlatform.cache.get("global_logs", ""), height=150)
            if st.button("Clear Logs"):
                SolarPlatform.cache.delete("global_logs")
                st.success("Logs cleared!")

        with tab_production:
            # UI elements
            site_ids_input = st.text_input("Enter site ID or comma-separated site IDs (e.g., SE:3148836, SE:3148837)", "")
            all_sites = st.checkbox("Select All Sites")

            current_year = pd.Timestamp.now().year
            years = list(range(current_year - 5, current_year + 1))
            selected_year = st.selectbox("Select Year", years, index=years.index(current_year - 1))

            # Process the input
            if all_sites:
                site_ids = None
            else:
                # Parse the input into a list, handling single or multiple site IDs
                site_ids = [site_id.strip() for site_id in site_ids_input.split(",") if site_id.strip()]

            # Ensure at least one site ID is provided or "All" is selected
            if not site_ids and not all_sites:
                st.warning("Please enter at least one site ID or select 'All Sites'.")
            else:
                if st.button("Fetch Production Data"):
                    # Call the API to generate production data for the given site IDs
                    platform_t = SolarEdgePlatform()
                    file_name = save_site_yearly_production(platform_t, selected_year, site_ids)
                    st.success("Production data saved successfully.")
                    with open(file_name, "rb") as file:
                        st.download_button(
                            label="Download Production Data",
                            data=file,
                            file_name=file_name,
                            mime="text/csv",
                        )

        with tab_users:
            user_name = st.text_input("User Name")
            hashed_password = st.text_input("Hashed Password", type="default")
            email = st.text_input("Email Address", type="default")

            if st.button("Create User"):
                auth.add_user(user_name, hashed_password, email)
                st.success(f"User '{user_name}' created successfully!")
                st.write(f"Email: {email}")
                st.write(f"Hashed Password: {hashed_password}")

            credentials_data = auth.load_credentials()
            usernames = list(credentials_data['credentials']['usernames'].keys()) if 'credentials' in credentials_data and 'usernames' in credentials_data['credentials'] else []
            user_to_delete = st.selectbox("Select User to Delete", options=usernames)

            if st.button("Delete User"):
                if user_to_delete:
                    if auth.delete_user(user_to_delete):
                        st.success(f"User '{user_to_delete}' deleted successfully!")
                else:
                    st.warning("No users available to delete or no user selected.")

        st.header("📊 Noon Production Data")
        ui.display_historical_chart()

        valid_production_dates = db.get_valid_production_dates()
        recent_noon = valid_production_dates[-1]

        platform.log("Starting application at " + str(datetime.now()))

        #Button to start

        if st.button("Run Fleet Data Collection") and not SolarPlatform.cache['collection_running']:
            st.write("Collection started. Logs will appear below:")

            #Starts 1 thread per platform
            run_collection()

            # Display completion message
            st.success("Collection complete!")
            #st.stop()

        st.markdown("---")

        production_set = db.get_production_set(recent_noon)
        df_prod = pd.DataFrame([asdict(record) for record in production_set])

        st.header("🚨 Active Alerts")

        alerts_df = db.fetch_alerts()

        # Generate synthetic alerts for sites with production below 0.1 kW
        existing_alert_sites = set(alerts_df['site_id'].unique())
        synthetic_alerts = []
        for record in production_set:
            if SolarPlatform.has_low_production(record.production_kw, None, None) is SolarPlatform.ProductionStatus.ISSUE and record.site_id not in existing_alert_sites:
                synthetic_alert = SolarPlatform.SolarAlert(
                    site_id=record.site_id,
                    alert_type=SolarPlatform.AlertType.PRODUCTION_ERROR,
                    severity=100,
                    details="",
                    first_triggered=SolarPlatform.get_now()
                )
                synthetic_alerts.append(synthetic_alert)

        if synthetic_alerts:
            synthetic_df = pd.DataFrame([asdict(alert) for alert in synthetic_alerts])
            alerts_df = pd.concat([alerts_df, synthetic_df], ignore_index=True)

        site_df = pd.DataFrame([asdict(site_info) for site_info in sites.values()])

        # Fetch the site history
        sites_history_df = db.fetch_sites()[["site_id", "history"]]

        if not alerts_df.empty:
            ui.create_alert_section(site_df, alerts_df, sites_history_df)
        else:
            st.success("No active alerts.")

        ui.display_battery_section(site_df)

        st.header("🌍 Site Map with Production Data")

        selected_date = st.date_input(
            "Select Date",
            recent_noon,
            min_value=min(valid_production_dates),
            max_value=max(valid_production_dates)
        )

        production_set = db.get_production_set(selected_date)
        df_prod = pd.DataFrame([asdict(record) for record in production_set])

        if not df_prod.empty and 'latitude' in site_df.columns:
            site_df["vendor_code"] = site_df["site_id"].apply(SolarPlatform.extract_vendor_code)
            site_df = site_df.merge(df_prod, on="site_id", how="left")
            site_df = site_df.sort_values(by="site_id")

            site_df['production_kw_total'] = site_df['production_kw'].apply(SolarPlatform.calculate_production_kw)
            site_df['production_kw'] = site_df['production_kw'].round(2)

            fleet_avg = site_df['production_kw_total'].mean()
            fleet_std = site_df['production_kw_total'].std()

            offline_sites = alerts_df[alerts_df['alert_type'] == 'NO_COMMUNICATION']['site_id'].unique()
            site_df['is_offline'] = site_df['site_id'].isin(offline_sites)

            ui.create_map_view(site_df, fleet_avg, fleet_std)
            st.markdown("---")

            if SolarPlatform.FAKE_DATA:
                site_df["site_id"] = site_df["site_id"].apply(lambda x: SolarPlatform.generate_fake_site_id())       
                site_df["name"] = site_df["site_id"].apply(lambda x: SolarPlatform.generate_fake_address())

            ui.display_production_chart(site_df)

        else:
            st.info("No production data available.")

        site_data_tab, device_cache_tab = st.tabs(["Site Data", "Device Cache"])


        with site_data_tab:
            st.dataframe(site_df)

        with device_cache_tab:
            st.subheader("Manage Device Cache")
            # Inject CSS for smaller buttons and text
            st.markdown("""
            <style>
            div.stButton > button {
              font-size: 10px;
              padding: 0.25rem 0.5rem;
            }
            </style>
            """, unsafe_allow_html=True)
            for i in range(0, len(site_df), 2):
                cols = st.columns(2)
                for j, col in enumerate(cols):
                    if i + j < len(site_df):
                        row = site_df.iloc[i + j]
                        if col.button(f"Delete {row['site_id']} - {row.get('name')}", key=f"delete_cache_{row['site_id']}"):
                            vendor_code = SolarPlatform.extract_vendor_code(row['site_id'])
                            raw_site_id = SolarPlatform.SolarPlatform.strip_vendorcodeprefix(row['site_id'])
                            if vendor_code == "SE":
                                platform_instance = SolarEdgePlatform()
                            elif vendor_code == "EN":
                                platform_instance = EnphasePlatform()
                            else:
                                st.error(f"Unknown vendor code: {vendor_code}")
                                continue
                            platform_instance.delete_device_cache(raw_site_id)
                            st.success(f"Cache deleted for site {row['site_id']}")

    elif authentication_status == False:
        st.error('Username/password is incorrect')
    elif authentication_status == None:
        st.warning('Please enter your username and password')

if __name__ == "__main__":
    main()
