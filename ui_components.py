import numpy as np
import pandas as pd
import folium
import altair as alt
import streamlit as st
from streamlit_folium import folium_static as st_folium


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

def create_map_view(sites_df, fleet_avg, fleet_std):
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

        if row.get('is_offline', False):
            color = 'blue'
        else:
            status = SolarPlatform.has_low_production(row['production_kw'], fleet_avg, fleet_std)
        
            # FIXME: Equals doesn't work, only is
            if status is SolarPlatform.ProductionStatus.GOOD:
                color = '#228B22'  # Green
            elif status is SolarPlatform.ProductionStatus.ISSUE:
                color = '#FF0000'  # Red
            elif status is SolarPlatform.ProductionStatus.SNOWY:
                color = '#c9c9c9'  # Gray

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