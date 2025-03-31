import streamlit as st
import battery_simulator
import tempfile
import altair as alt
import pandas as pd
from io import BytesIO
import os

# Configuration parameters
PATH = "c:/Users/keith/OneDrive/Desktop/Python/Rowley"
CHART_POINT_SIZE = 10
MINIMUM_USABLE_CAPACITY_PERCENT = 30  # Minimum usable battery capacity percentage

def battery_simulator_tab():
    """
    Main function to render the battery simulator tab
    """
    # Initialize battery simulator specific session state variables
    if "battery_sim_paused" not in st.session_state:
        st.session_state["battery_sim_paused"] = False

    # Add a configurable base file path
    base_file_path = st.text_input(
        "Base File Path", 
        value = PATH,
        help = "Path to the directory containing your data files"
    )

    # Add radio button for file selection
    file_selection = st.radio(
        "Select Data Source",
        ["Upload File", "Mechanical-AggregatePV", "Lights-AggregatePV"],
        horizontal=True
    )

    # Show file uploader only if "Upload File" is selected
    if file_selection == "Upload File":
        uploaded_file = st.file_uploader("Upload CSV File", type="csv")
    else:
        uploaded_file = None

    # Create a row with two columns for simulation parameters
    col1, col2 = st.columns(2)
    
    with col1:
        simulation_speed = st.slider("Simulation delay per iteration (in seconds)", 0.0, 2.0, 0.0, 0.1)
        num_battery_stacks = st.number_input("Number of Battery Stacks (38.4 kWh each)", min_value=1, max_value=16, value=1, step=1)
    
    with col2:
        # Add slider for PV share percentage
        pv_share_percent = st.slider(
            "PV Share Percentage", 
            min_value=1, 
            max_value=200, 
            value=50, 
            step=1,
            help="Percentage of external PV production available to this system"
        )

    # Calculate maximum capacity for chart scaling
    max_battery_capacity = num_battery_stacks * 38.4
    min_usable_capacity = (MINIMUM_USABLE_CAPACITY_PERCENT / 100) * max_battery_capacity

    # Create UI containers inside the function scope
    progress_bar = st.progress(0)
    progress_area = st.empty()
    
    # Add containers for running totals
    running_totals_container = st.container()
    with running_totals_container:
        col1, col2 = st.columns(2)
        unmet_total_metric = col1.empty()
        exported_total_metric = col2.empty()
    
    result_area = st.empty()
    download_area = st.empty()
    live_chart_area = st.empty()

    # Replace the pause/resume button with a checkbox to avoid page reset
    st.session_state["battery_sim_paused"] = st.checkbox("Pause Simulation", value=st.session_state["battery_sim_paused"])

    # Determine if we can run the simulation (either upload or valid selection)
    can_run_simulation = (file_selection == "Upload File" and uploaded_file is not None) or file_selection in ["Mechanical-AggregatePV", "Lights-AggregatePV"]

    if st.button("Run Simulation") and can_run_simulation:
        # Handle the different file sources
        if file_selection == "Upload File":
            # Use the uploaded file
            with tempfile.NamedTemporaryFile(delete=False, suffix=".csv") as tmp:
                tmp.write(uploaded_file.getvalue())
                tmp_filename = tmp.name
        else:
            # Use the hardcoded file options
            filename = f"{file_selection.lower()}.csv"
            tmp_filename = os.path.join(base_file_path, filename)
            if not os.path.exists(tmp_filename):
                st.error(f"File not found: {tmp_filename}")
                st.stop()
            st.info(f"Using data from: {tmp_filename}")

        progress_data = []
        
        # Preload data to determine max values for scaling
        try:
            preload_df = pd.read_csv(tmp_filename)
            if 'LoadTotalPower(W)/178' in preload_df.columns:
                max_load = preload_df['LoadTotalPower(W)/178'].max() * 0.001  # Convert to kW
            else:
                max_load = max_battery_capacity
                
            if 'Total Production' in preload_df.columns:
                max_production = preload_df['Total Production'].max() * 0.001  # Convert to kW
            else:
                max_production = max_battery_capacity
                
            chart_y_max = max(max_battery_capacity, max_load, max_production) * 1.1  # Add 10% buffer
        except Exception as e:
            st.warning(f"Could not pre-analyze data for chart scaling: {e}")
            chart_y_max = max_battery_capacity * 1.5  # Fallback value
        
        def progress_callback(index, state, total_iterations):
            # Use the battery-specific pause state
            while st.session_state["battery_sim_paused"]:
                st.sleep(0.1)
            progress_area.text(
                f"Time: {state['Time']} | SoC: {state['SoC_kWh']:.2f} kWh | Charge: {state['BatteryCharge_kWh']:.2f} kWh | "
                f"Discharge: {state['BatteryDischarge_kWh']:.2f} kWh | Unmet: {state['UnmetLoad_kWh']:.2f} kWh | "
                f"Exported: {state['ExportedEnergy_kWh']:.2f} kWh"
            )
            
            # Update the running total metrics in real-time
            unmet_total_metric.metric(
                "Total Unmet Load", 
                f"{state.get('RunningTotalUnmet_kWh', 0):.2f} kWh",
                delta=f"{state.get('UnmetLoad_kWh', 0):.2f} kWh"
            )
            
            exported_total_metric.metric(
                "Total Exported to Grid", 
                f"{state.get('RunningTotalExported_kWh', 0):.2f} kWh",
                delta=f"{state.get('ExportedEnergy_kWh', 0):.2f} kWh"
            )
            
            progress_data.append(state)
            progress_bar.progress(min((index + 1) / total_iterations, 1.0))
            
            # Update live chart less frequently (every 10 iterations or on final iteration)
            if (index % 10 == 0) or (index == total_iterations - 1):
                live_df = pd.DataFrame(progress_data)
                if not live_df.empty:
                    current_time = live_df.iloc[-1]['Time']
                    live_df = live_df[live_df['Time'] >= (current_time - pd.Timedelta(days=2))]
                    
                    chart_df = pd.DataFrame({
                        'Time': live_df['Time'],
                        'SoC_kWh': live_df['SoC_kWh'],
                        'Adjusted_SoC_kWh': [max(0, soc - min_usable_capacity) for soc in live_df['SoC_kWh']],
                        'Production_kWh': live_df['Production_kWh'],
                        'Load_kWh': live_df['Load_kWh'],
                        'ExportedEnergy_kWh': live_df['ExportedEnergy_kWh'],
                        'UnmetLoad_kWh': live_df['UnmetLoad_kWh'],
                        'RunningTotalUnmet_kWh': live_df.get('RunningTotalUnmet_kWh', 0),
                        'RunningTotalExported_kWh': live_df.get('RunningTotalExported_kWh', 0),
                        'LoadSource': ['Renewable' if unmet <= 0.01 else 'Grid' for unmet in live_df['UnmetLoad_kWh']]
                    })
                    
                    # Create separate charts with different scales
                    # SOC chart with its own scale
                    soc_chart = alt.Chart(chart_df).mark_line(color='#1f77b4').encode(
                        x='Time:T',
                        y=alt.Y('Adjusted_SoC_kWh:Q', 
                                scale=alt.Scale(domain=[0, max_battery_capacity - min_usable_capacity]),
                                title='Usable SoC (kWh)'),
                        tooltip=['Time:T', 'SoC_kWh:Q', 'Adjusted_SoC_kWh:Q']
                    )
                    
                    # Other metrics with their own scale limited to around 10 kWh
                    production_chart = alt.Chart(chart_df).mark_point(size=CHART_POINT_SIZE).encode(
                        x='Time:T',
                        y=alt.Y('Production_kWh:Q', 
                               scale=alt.Scale(domain=[0, min(10, chart_y_max)]),
                               title='Production/Load/Export (kWh)'),
                        color=alt.value('#2ca02c'),
                        tooltip=['Time:T', 'Production_kWh:Q']
                    )
                    
                    load_chart = alt.Chart(chart_df).mark_point(size=CHART_POINT_SIZE).encode(
                        x='Time:T',
                        y=alt.Y('Load_kWh:Q', 
                               scale=alt.Scale(domain=[0, min(10, chart_y_max)]),
                               title='Production/Load/Export (kWh)'),
                        color=alt.Color('LoadSource:N', scale=alt.Scale(
                            domain=['Renewable', 'Grid'],
                            range=['#8cc63f', '#ff7f0e']
                        )),
                        tooltip=['Time:T', 'Load_kWh:Q', 'LoadSource:N']
                    )
                    
                    # Layer the production and load charts (sharing the same scale)
                    metrics_chart = alt.layer(production_chart, load_chart)
                    
                    # Add export data to the metrics chart if available
                    grid_export_data = chart_df[chart_df['ExportedEnergy_kWh'] > 0].copy()
                    if not grid_export_data.empty:
                        grid_export_chart = alt.Chart(grid_export_data).mark_point(size=CHART_POINT_SIZE).encode(
                            x='Time:T',
                            y=alt.Y('ExportedEnergy_kWh:Q', 
                                   scale=alt.Scale(domain=[0, min(10, chart_y_max)]),
                                   title='Production/Load/Export (kWh)'),
                            color=alt.value('#00C5CD'),
                            tooltip=['Time:T', alt.Tooltip('ExportedEnergy_kWh:Q', title='Grid Export (kWh)')]
                        )
                        metrics_chart = alt.layer(metrics_chart, grid_export_chart)

                    # Create multi-layer chart with three independent scales
                    combined_chart = alt.layer(
                        soc_chart, 
                        metrics_chart
                    ).resolve_scale(
                        y='independent'  # Creates the multi y-axis
                    ).properties(
                        title="Live Energy Monitoring",
                        height=600
                    )
                    
                    live_chart_area.altair_chart(combined_chart, use_container_width=True)

        # Pass the total number of iterations to the simulation function
        total_iterations = battery_simulator.get_total_iterations(tmp_filename)
        # Updated call to get more return values
        df, total_unmet_load, summary_metrics, recommendations = battery_simulator.run_battery_simulation(
            tmp_filename,
            simulation_delay=simulation_speed,
            progress_callback=lambda index, state: progress_callback(index, state, total_iterations),
            num_battery_stacks=num_battery_stacks,  # Pass the number of battery stacks
            pv_share_percent=pv_share_percent,  # Pass the PV share percentage
        )
        st.success("Simulation Complete")
        progress_bar.empty()
        
        # Display battery configuration information
        st.write(f"Battery Configuration: {num_battery_stacks} stack(s) × 38.4 kWh = {num_battery_stacks * 38.4:.1f} kWh total capacity")
        st.write(f"Minimum usable capacity: {min_usable_capacity:.1f} kWh ({MINIMUM_USABLE_CAPACITY_PERCENT}% of total)")
        st.write(f"Displayed usable capacity range: 0-{max_battery_capacity - min_usable_capacity:.1f} kWh")
        
        # Display detailed simulation metrics from the simulator
        st.subheader("Simulation Metrics")
        metrics_cols = st.columns(3)
        
        with metrics_cols[0]:
            st.metric("Total Unmet Load", f"{summary_metrics['total_unmet_load']:.2f} kWh")
            st.metric("Times Battery 100% Full", f"{summary_metrics['full_battery_count']} intervals")
        
        with metrics_cols[1]:
            st.metric("Total Exported to Grid", f"{summary_metrics['total_exported']:.2f} kWh")
            st.metric("Final SoC", f"{summary_metrics['final_soc_kwh']:.2f} kWh")
        
        with metrics_cols[2]:
            st.metric("Cumulative Surplus", f"{summary_metrics['cumulative_surplus']:.2f} kWh")
            st.metric("Final SoC (% of Usable)", f"{summary_metrics['final_soc_percent_usable']:.1f}%")
        
        # Add a clear explanation about the PV sharing assumption
        st.info(f"⚡ IMPORTANT: All calculations assume this system receives exactly {pv_share_percent}% of the external PV production. This reduction is applied only once in the simulation.")
        
        # Use recommendations from simulator
        st.subheader("Charging and Discharging Recommendations")
        if 'best_charge_hour' in recommendations and recommendations['best_charge_hour'] is not None:
            st.write(f"Best hour to start charging battery: {recommendations['best_charge_hour']}:00 (our {pv_share_percent}% PV share exceeds load)")
        else:
            st.write("No hour meets the ≥5 kWh threshold for battery charging recommendation.")
            
        if 'best_discharge_hour' in recommendations and recommendations['best_discharge_hour'] is not None:
            st.write(f"Best hour to start discharging battery: {recommendations['best_discharge_hour']}:00 (home load exceeds our PV share)")
        else:
            st.write("No hour meets the ≥5 kWh threshold for battery discharging recommendation.")
            
        st.write(f"Recommended start hour for grid charging: {recommendations['grid_charge_hour']}:00")
        st.write(f"Recommended start hour for battery discharging: {recommendations['battery_discharge_hour']}:00")
        
        # Display hourly charts for recommendations
        reco_cols = st.columns(2)
        
        with reco_cols[0]:
            if 'unmet_by_hour' in recommendations:
                unmet_hour_df = pd.DataFrame({
                    'Hour': recommendations['unmet_by_hour'].index,
                    'UnmetLoad_kWh': recommendations['unmet_by_hour'].values
                })
                unmet_chart = alt.Chart(unmet_hour_df).mark_bar().encode(
                    x='Hour:O',
                    y='UnmetLoad_kWh:Q',
                    tooltip=['Hour:O', 'UnmetLoad_kWh:Q']
                ).properties(
                    title="Unmet Load by Hour of Day",
                    height=300
                )
                st.altair_chart(unmet_chart, use_container_width=True)
        
        with reco_cols[1]:
            if 'exported_by_hour' in recommendations:
                exported_hour_df = pd.DataFrame({
                    'Hour': recommendations['exported_by_hour'].index,
                    'ExportedEnergy_kWh': recommendations['exported_by_hour'].values
                })
                exported_chart = alt.Chart(exported_hour_df).mark_bar().encode(
                    x='Hour:O',
                    y='ExportedEnergy_kWh:Q',
                    tooltip=['Hour:O', 'ExportedEnergy_kWh:Q']
                ).properties(
                    title="Exported Energy by Hour of Day",
                    height=300
                )
                st.altair_chart(exported_chart, use_container_width=True)
        
        # Add adjusted SoC to the dataframe
        df['Adjusted_SoC_kWh'] = df['SoC_kWh'].apply(lambda x: max(0, x - min_usable_capacity))
        
        # Altair Line Chart for battery SoC - now using dual y-axis for final chart
        soc_line_chart = alt.Chart(df.reset_index()).mark_line(color='#1f77b4').encode(
            x='Time:T',
            y=alt.Y('Adjusted_SoC_kWh:Q', 
                    title='Usable SoC (kWh)', 
                    scale=alt.Scale(domain=[0, max_battery_capacity - min_usable_capacity]))
        )
        
        # Add production and load data if available
        if 'Production_kWh' in df.columns and 'Load_kWh' in df.columns:
            production_line = alt.Chart(df.reset_index()).mark_line(color='#2ca02c').encode(
                x='Time:T',
                y=alt.Y('Production_kWh:Q', 
                        title='Production/Load (kWh)',
                        scale=alt.Scale(domain=[0, min(10, df['Production_kWh'].max() * 1.1)]))
            )
            
            load_line = alt.Chart(df.reset_index()).mark_line(color='#ff7f0e').encode(
                x='Time:T',
                y=alt.Y('Load_kWh:Q', 
                        title='Production/Load (kWh)',
                        scale=alt.Scale(domain=[0, min(10, df['Load_kWh'].max() * 1.1)]))
            )
            
            metrics_line = alt.layer(production_line, load_line)
            
            final_chart = alt.layer(
                soc_line_chart,
                metrics_line
            ).resolve_scale(
                y='independent'
            ).properties(
                title="Energy Monitoring Over Time",
                height=600
            )
        else:
            final_chart = soc_line_chart.properties(
                title="Usable State of Charge over Time (Adjusted to Show Minimum 30% as 0)",
                height=600
            )
        
        st.altair_chart(final_chart, use_container_width=True)

        # Daily summaries from recommendations
        st.subheader("Daily Summaries")
        daily_cols = st.columns(2)
        
        with daily_cols[0]:
            st.write("Unmet Load (kWh):")
            st.dataframe(recommendations['daily_unmet'])
        
        with daily_cols[1]:
            st.write("Exported Energy (kWh):")
            st.dataframe(recommendations['daily_exported'])

        # Download results
        csv = df.to_csv(index=False).encode('utf-8')
        download_area.download_button(
            label="Download Simulation Results",
            data=csv,
            file_name="simulation_results.csv",
            mime="text/csv"
        )

# Only run this when the script is executed directly (not when imported)
if __name__ == "__main__":
    st.title("Battery Simulator Live Visualization")
    battery_simulator_tab()
