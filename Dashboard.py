from datetime import datetime, timedelta
from datetime import date
from dataclasses import asdict
import numpy as np
import pandas as pd
import folium
import altair as alt
import yaml
from yaml.loader import SafeLoader

import streamlit as st
import streamlit.components.v1 as components
from streamlit_folium import st_folium
import streamlit_authenticator as stauth

import SolarPlatform
import SqlModels as Sql
import Database as db
from FleetCollector import collect_platform, run_collection
from SolarEdge import SolarEdgePlatform
from Enphase import EnphasePlatform

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
    if isinstance(production_kw, list):
        formatted_list = [f"{item:.2f}" for item in production_kw]
        return f"[{', '.join(formatted_list)}]"
    else:
        return f"{production_kw:.2f}"


# Return low production if any inverter is producing less than 100 watts

def has_low_production(production):
    if isinstance(production, list):
        for production in production:
            if np.isnan(production) or production < 0.1:
                return True
        return False
    else: # Assume it's a single float
        production = production
        return np.isnan(production) or production < 0.1
    
def create_map_view(sites_df):
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

        # Check if any inverter is below the threshold
        if has_low_production(row["production_kw"]):
            color = "#FF0000"
        else:
            color = "#228B22"

        production_data = row["production_kw"] # Get production_kw for the current row

        # Format production_kw for the tooltip
        tooltip_content = format_production_tooltip(production_data)

        # Display the list of production values in the popup
        popup_html = (
            f"<strong>{row['name']} ({row['site_id']})</strong><br>"
            f"Production: {tooltip_content}"
        )

        total_production = SolarPlatform.calculate_production_kw(production_data)

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
                        {total_production:.2f}
                    </div>
                """
            )
        ).add_to(m)

    if marker_coords:
        m.fit_bounds(marker_coords)

    st_folium(m, width=1200)


def display_historical_chart(historical_df):

    chart = alt.Chart(historical_df).mark_line(size=5).encode(
        x=alt.X('production_day:T', title='Date'),
        y=alt.Y('total_noon_kw:Q', title='Aggregated Production (KW)'),
        tooltip=['production_day:T', 'total_noon_kw:Q']
    ).properties(
        title="Historical Production Data"
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


def process_alert_section(df, header_title, editor_key, save_button_label, column_config, drop_columns=None, alert_type=None, use_container_width=True):
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

def create_alert_section(site_df, alerts_df):

    # Merge alerts_df with site_df to add 'name' and 'url'
    alerts_df = alerts_df.merge(site_df[['site_id', 'name', 'url']], on="site_id", how="left")

    alerts_df = alerts_df.drop(columns=["history"], errors="ignore")

    #Reorder columns
    alerts_df = alerts_df[['site_id', 'name', 'url'] + [col for col in alerts_df.columns if col not in ['site_id', 'name', 'url']]]
        
    # Merge site history once for all alerts
    merged_alerts_df = alerts_df.merge(
        sites_history_df, on="site_id", how="left")

    merged_alerts_df = process_alert_section(
        merged_alerts_df,
        header_title="Site Production failure",
        alert_type=SolarPlatform.AlertType.PRODUCTION_ERROR,
        editor_key="production_production",
        save_button_label="Save Production Site History Updates",
        column_config={
            "url": st.column_config.LinkColumn(label="Site url", display_text="Link")
        },
        drop_columns=["alert_type", "details", "resolved_date"],
    )

    merged_alerts_df = process_alert_section(
        merged_alerts_df,
        header_title="Site Communication failure",
        alert_type=SolarPlatform.AlertType.NO_COMMUNICATION,
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
        alert_type= SolarPlatform.AlertType.PANEL_ERROR,
        editor_key="panel_editor",
        save_button_label="Save Panel Site History Updates",
        column_config={
            "url": st.column_config.LinkColumn(label="Site url", display_text="Link")
        },
        drop_columns=["alert_type", "details"],
    )

    process_alert_section(
        merged_alerts_df,
        header_title="System Configuration failure",
        editor_key="sysconf_editor",
        save_button_label="Save System Config Site History Updates",
        column_config={
            "url": st.column_config.LinkColumn(label="Site url", display_text="Link")
        },
        drop_columns=["alert_type"],
        alert_type=None
    )

def display_battery_section():
    st.header("🔋 Batteries Below 10%")
    low_batteries_df = db.fetch_low_batteries()
    if not low_batteries_df.empty:
        # Merge battery info with site data to include 'name' and 'url'
        low_batteries_df = low_batteries_df.merge(
            site_df[['site_id', 'name', 'url']],
            on="site_id",
            how="left"
        )
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


def load_credentials():
    with open('./credentials.yaml') as file:
        credentials = yaml.load(file, Loader=SafeLoader) or {'credentials': {'usernames': {}}}
        return credentials

def save_credentials(credentials):
    with open('./credentials.yaml', 'w') as file:
        yaml.dump(credentials, file)

def add_user(user_name, hashed_password, email):
    credentials = load_credentials()
    if 'credentials' not in credentials:
        credentials = {'credentials': {'usernames': {}}}
    if 'usernames' not in credentials['credentials']:
        credentials['credentials']['usernames'] = {}

    if user_name in credentials['credentials']['usernames']:
        st.error(f"Username '{user_name}' already exists. Please choose a different username.")
        return False

    credentials['credentials']['usernames'][user_name] = {
        'name': user_name, # You can store name separately if needed, otherwise username is name
        'password': hashed_password,
        'email': email
    }
    save_credentials(credentials)
    return True

def delete_user(user_name):
    credentials = load_credentials()
    if 'credentials' in credentials and 'usernames' in credentials['credentials'] and user_name in credentials['credentials']['usernames']:
        del credentials['credentials']['usernames'][user_name]
        save_credentials(credentials)
        return True
    else:
        st.error(f"User '{user_name}' not found.")
        return False

#    
# Main Streamlit code/UI starts here
#

title = "☀️ Absolute Solar Monitoring"
st.set_page_config(page_title=title, layout="wide")
Sql.init_fleet_db()
st.title(title)

with open('./config.yaml') as file:
    config = yaml.load(file, Loader=SafeLoader)

with open('./credentials.yaml') as file:
    credentials = yaml.load(file, Loader=SafeLoader)    

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

    sites.update(sites_enphase)

    num_sites = len(sites)
    st.metric("Sites In Fleet", num_sites)

    st.header("📊 Historical Production Data")
    historical_df = db.get_total_noon_kw()
    display_historical_chart(historical_df)

    valid_production_dates = db.get_valid_production_dates()
    recent_noon = valid_production_dates[-1]

    with st.expander("Show Logs", expanded=False):
        st.text_area("Logs", value = SolarPlatform.cache.get("global_logs", ""), height=150)

    platform.log("Starting application at " + str(datetime.now()))

    if st.button("Run Fleet Data Collection"):
        run_collection()
        st.success("Collection complete!")

    with st.expander("Create New User"):
        user_name = st.text_input("User Name")
        hashed_password = st.text_input("Hashed Password", type="default")
        email = st.text_input("Email Address", type="default")

        if st.button("Create User"):
            add_user(user_name, hashed_password, email)
            st.success(f"User '{user_name}' created successfully!")
            st.write(f"Email: {email}")
            st.write(f"Hashed Password: {hashed_password}")

    with st.expander("Delete User"):
        credentials_data = load_credentials()
        usernames = list(credentials_data['credentials']['usernames'].keys()) if 'credentials' in credentials_data and 'usernames' in credentials_data['credentials'] else []
        user_to_delete = st.selectbox("Select User to Delete", options=usernames)

        if st.button("Delete User"):
            if user_to_delete:
                if delete_user(user_to_delete):
                    st.success(f"User '{user_to_delete}' deleted successfully!")
            else:
                st.warning("No users available to delete or no user selected.")

    with st.expander("Configuration Settings"):

        # Create columns
        col1, col2, col3, col4, col5 = st.columns(5)

        with col1:
            if st.button("Delete Alerts (Test)"):
                db.delete_all_alerts()
                st.success("All alerts deleted!")
        with col2:
            if st.button("Delete Alerts API Cache (Test)"):
                alerts_cache_keys = [key for key in SolarPlatform.cache.iterkeys() if key.startswith("get_alerts")]
                for key in alerts_cache_keys:
                    del SolarPlatform.cache[key]
                st.success("Alerts cache cleared!")
        with col3:
            if st.button("Delete Battery data (Test)"):
                db.delete_all_batteries()
                st.success("Battery data cleared!")
        with col4:
            if st.button("convert api_keys to keyring"):
                SolarPlatform.set_keyring_from_api_keys()
        with col5:
            if st.button("Clear Logs"):
                SolarPlatform.cache.delete("global_logs")
                st.success("Battery data cleared!")
    
    st.markdown("---")

    production_set = db.get_production_set(recent_noon)
    df_prod = pd.DataFrame([asdict(record) for record in production_set])

    st.header("🚨 Active Alerts")

    alerts_df = db.fetch_alerts()
    alerts_df = alerts_df.drop(columns=["name", "url"], errors="ignore")

    # Generate synthetic alerts for sites with production below 0.1 kW
    existing_alert_sites = set(alerts_df['site_id'].unique())
    synthetic_alerts = []
    for record in production_set:
        if has_low_production(record.production_kw) and record.site_id not in existing_alert_sites:
            synthetic_alert = SolarPlatform.SolarAlert(
                site_id=record.site_id,
                alert_type=SolarPlatform.AlertType.PRODUCTION_ERROR,
                severity=100,
                details="",
                first_triggered=datetime.utcnow()
            )
            synthetic_alerts.append(synthetic_alert)

    if synthetic_alerts:
        synthetic_df = pd.DataFrame([asdict(alert) for alert in synthetic_alerts])
        alerts_df = pd.concat([alerts_df, synthetic_df], ignore_index=True)

    site_df = pd.DataFrame([asdict(site_info) for site_info in sites.values()])

    # Fetch the site history
    sites_history_df = db.fetch_sites()[["site_id", "history"]]

    if not alerts_df.empty:
        create_alert_section(site_df, alerts_df)
    else:
        st.success("No active alerts.")

    display_battery_section()

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

        site_df['production_kw_total'] = site_df['production_kw'].apply(SolarPlatform.calculate_production_kw)
        site_df['production_kw'] = site_df['production_kw'].round(2)


        create_map_view(site_df)
        st.markdown("---")    
        display_production_chart(site_df)

    else:
        st.info("No production data available.")

    #Show all sites
    st.dataframe(site_df)

elif authentication_status == False:
    st.error('Username/password is incorrect')
elif authentication_status == None:
    st.warning('Please enter your username and password')
