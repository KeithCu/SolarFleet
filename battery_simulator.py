import pandas as pd
import argparse
import os
import sys  # Used for exiting on error
import time  # Used for simulation delay

# Global debug flag
DEBUG = False

def debug_print(message):
    """Print debug messages if DEBUG is True."""
    if DEBUG:
        print(message)

def get_total_iterations(input_csv_filename):
    """
    Calculate the total number of iterations based on the input CSV file.

    Args:
        input_csv_filename (str): Path to the input CSV file.

    Returns:
        int: Total number of iterations (rows in the CSV file).
    """
    try:
        df = pd.read_csv(input_csv_filename)
        return len(df)
    except Exception as e:
        print(f"Error calculating total iterations: {e}")
        return 0

def calculate_charging_recommendations(df, pv_share_percent=50):
    """
    Calculate recommendations for charging and discharging times based on simulation results.
    
    Args:
        df (DataFrame): The simulation results dataframe
        pv_share_percent (float): Percentage of PV production available
    
    Returns:
        dict: Dictionary containing recommendations and supporting data
    """
    recommendations = {}
    
    # Calculate potential charge (PV minus load)
    if 'Production_kWh' in df.columns and 'Load_kWh' in df.columns:
        # Calculate potential charge (our share of PV minus our load)
        pv_share_decimal = pv_share_percent / 100.0
        df['PotentialCharge_kWh'] = (df['Production_kWh'] * pv_share_decimal) - df['Load_kWh']
        # Any negative values mean no potential charge
        df['PotentialCharge_kWh'] = df['PotentialCharge_kWh'].apply(lambda x: max(0, x))
        
        # Charging: Find hour where PotentialCharge_kWh (PV share minus load) is at least 5 kWh
        charge_candidates = df[df['PotentialCharge_kWh'] >= 5]
        if not charge_candidates.empty:
            pv_surplus_by_hour = charge_candidates.groupby(charge_candidates.index.hour)['PotentialCharge_kWh'].sum()
            best_charge_hour = pv_surplus_by_hour.idxmax()
            recommendations['best_charge_hour'] = best_charge_hour
            recommendations['charge_hour_data'] = pv_surplus_by_hour
        else:
            recommendations['best_charge_hour'] = None
    
    # Discharging: Find hour when unmet load is at least 5 kWh (load exceeds our PV share)
    if 'UnmetLoad_kWh' in df.columns:
        discharge_candidates = df[df['UnmetLoad_kWh'] >= 5]
        if not discharge_candidates.empty:
            load_deficit_by_hour = discharge_candidates.groupby(discharge_candidates.index.hour)['UnmetLoad_kWh'].sum()
            best_discharge_hour = load_deficit_by_hour.idxmax()
            recommendations['best_discharge_hour'] = best_discharge_hour
            recommendations['discharge_hour_data'] = load_deficit_by_hour
        else:
            recommendations['best_discharge_hour'] = None
    
    # Calculate recommended hours for grid charging and battery discharging
    if 'Hour' not in df.columns:
        df['Hour'] = df.index.hour
        
    unmet_by_hour = df.groupby(df['Hour'])['UnmetLoad_kWh'].sum()
    grid_charge_hour = unmet_by_hour.idxmax()
    recommendations['grid_charge_hour'] = grid_charge_hour
    recommendations['unmet_by_hour'] = unmet_by_hour
    
    exported_by_hour = df.groupby(df['Hour'])['ExportedEnergy_kWh'].sum()
    battery_discharge_hour = exported_by_hour.idxmax()
    recommendations['battery_discharge_hour'] = battery_discharge_hour
    recommendations['exported_by_hour'] = exported_by_hour
    
    # Daily summaries
    daily_unmet = df.groupby(df.index.floor('D'))['UnmetLoad_kWh'].sum()
    daily_exported = df.groupby(df.index.floor('D'))['ExportedEnergy_kWh'].sum()
    recommendations['daily_unmet'] = daily_unmet
    recommendations['daily_exported'] = daily_exported
    
    return recommendations

def run_battery_simulation(input_csv_filename, output_csv_filename=None, simulation_delay=0, progress_callback=None, num_battery_stacks=1, pv_share_percent=50):
    """
    Loads pre-processed CSV data with Time, LoadTotalPower, Total Production, and Interval(Days),
    calculates NetEnergy based on these values, runs a battery simulation based on defined parameters,
    prints summary results, and optionally saves the full results.

    Args:
        input_csv_filename (str): Path to the input CSV file.
        output_csv_filename (str, optional): Path to save the results CSV.
                                            If None, results are not saved.
        simulation_delay (float, optional): Delay in seconds between each simulation step.
        progress_callback (callable, optional): Function to call with progress updates.
        num_battery_stacks (int, optional): Number of battery stacks to simulate (38.4 kWh each).
        pv_share_percent (float, optional): Percentage of total PV production available to this system.
    """
    TIME_COL = 'Time'
    NET_ENERGY_COL = 'NetEnergy(kWh)'
    INTERVAL_COL = 'Interval(Days)'
    LOAD_POWER_COL = 'LoadTotalPower(W)/178'
    PROD_POWER_COL = 'Total Production'

    pv_share_decimal = pv_share_percent / 100.0

    BATTERY_CAPACITY_KWH = 38.4 * num_battery_stacks
    USABLE_DOD_PERCENT = 70.0
    MAX_CHARGE_RATE_KW = 10000.0 
    MAX_DISCHARGE_RATE_KW = 13750.0 
    CHARGE_EFFICIENCY_PERCENT = 95.0
    DISCHARGE_EFFICIENCY_PERCENT = 95.0
    INITIAL_SOC_PERCENT = 100.0

    print(f"Loading data from: {input_csv_filename}")
    try:
        df = pd.read_csv(input_csv_filename)
        df[TIME_COL] = df[TIME_COL].str.replace('+AC0-', '-', regex=False)
        df[TIME_COL] = pd.to_datetime(df[TIME_COL], errors='coerce')
    except FileNotFoundError:
        print(f"Error: Input file not found at {input_csv_filename}")
        sys.exit(1)
    except Exception as e:
        print(f"Error loading CSV: {e}")
        sys.exit(1)

    required_cols = [TIME_COL, LOAD_POWER_COL, PROD_POWER_COL, INTERVAL_COL]
    missing_cols = [col for col in required_cols if col not in df.columns]
    if missing_cols:
        print(f"Error: Input CSV is missing required columns: {missing_cols}")
        print(f"Available columns: {df.columns.tolist()}")
        sys.exit(1)

    try:
        df[LOAD_POWER_COL] = pd.to_numeric(df[LOAD_POWER_COL], errors='coerce')
        df[PROD_POWER_COL] = pd.to_numeric(df[PROD_POWER_COL], errors='coerce')
        df[INTERVAL_COL] = pd.to_numeric(df[INTERVAL_COL], errors='coerce')
        
        interval_hours = df[INTERVAL_COL] * 24.0
        df[NET_ENERGY_COL] = ((df[PROD_POWER_COL] * 0.001 * pv_share_decimal) - (df[LOAD_POWER_COL] * 0.001)) * interval_hours
        print(f"NetEnergy(kWh) calculated from production and load data ({pv_share_percent}% of production is available)")
    except Exception as e:
        print(f"Error processing required columns: {e}")
        sys.exit(1)

    try:
        df.set_index(TIME_COL, inplace=True)
        df.sort_index(inplace=True)
        if not isinstance(df.index, pd.DatetimeIndex):
            raise TypeError("Time column did not parse as datetime correctly.")
        print(f"Loaded and indexed {len(df)} rows.")
    except Exception as e:
        print(f"Error setting or sorting Time index: {e}")
        sys.exit(1)

    USABLE_CAPACITY_KWH = BATTERY_CAPACITY_KWH * (USABLE_DOD_PERCENT / 100.0)
    MIN_USABLE_SOC_KWH = BATTERY_CAPACITY_KWH * (1.0 - (USABLE_DOD_PERCENT / 100.0))
    CHARGE_EFFICIENCY = CHARGE_EFFICIENCY_PERCENT / 100.0
    DISCHARGE_EFFICIENCY = DISCHARGE_EFFICIENCY_PERCENT / 100.0
    INITIAL_SOC_KWH = BATTERY_CAPACITY_KWH * (INITIAL_SOC_PERCENT / 100.0)
    MAX_SOC_KWH = BATTERY_CAPACITY_KWH

    print("\n--- Battery Simulation Parameters ---")
    print(f"Total Capacity: {BATTERY_CAPACITY_KWH:.2f} kWh")
    print(f"Usable Capacity: {USABLE_CAPACITY_KWH:.2f} kWh")
    print(f"SoC Range (Abs): {MIN_USABLE_SOC_KWH:.2f} kWh to {MAX_SOC_KWH:.2f} kWh")
    print(f"Max Charge/Discharge Rate: {MAX_CHARGE_RATE_KW:.2f} kW / {MAX_DISCHARGE_RATE_KW:.2f} kW")
    print(f"Efficiency (Charge/Discharge): {CHARGE_EFFICIENCY_PERCENT:.1f}% / {DISCHARGE_EFFICIENCY_PERCENT:.1f}%")
    print(f"Initial SoC: {INITIAL_SOC_PERCENT:.1f}% ")
    print("------------------------------------")

    df['SoC_kWh'] = 0.0
    df['BatteryCharge_kWh'] = 0.0
    df['BatteryDischarge_kWh'] = 0.0
    df['UnmetLoad_kWh'] = 0.0
    df['ExportedEnergy_kWh'] = 0.0
    df['SoC_Start_kWh'] = 0.0
    
    df['Load_kWh'] = df[LOAD_POWER_COL] * 0.001 * (df[INTERVAL_COL] * 24.0)
    df['Production_kWh'] = df[PROD_POWER_COL] * 0.001 * (df[INTERVAL_COL] * 24.0)
    has_load_data = True
    has_production_data = True

    current_soc_kwh = INITIAL_SOC_KWH
    full_battery_count = 0
    cumulative_surplus = 0
    running_total_unmet = 0
    running_total_exported = 0

    print("Running battery simulation...")
    daily_cumulative_unmet = {}
    for iteration, (index, row) in enumerate(df.iterrows()):
        net_energy_kwh = row[NET_ENERGY_COL]
        interval_d = row[INTERVAL_COL]
        interval_h = interval_d * 24.0

        debug_print(f"[DEBUG] Interval: {index}, NetEnergy: {net_energy_kwh:.3f} kWh, Interval (Days): {interval_d:.3f}, Interval (Hours): {interval_h:.3f}")

        df.loc[index, 'SoC_Start_kWh'] = current_soc_kwh

        if interval_h <= 0:
            print(f"Warning: Skipping row {index} due to non-positive time interval ({interval_h} hours).")
            df.loc[index, 'SoC_kWh'] = current_soc_kwh
            continue

        max_charge_energy_rate_limit = MAX_CHARGE_RATE_KW * interval_h
        max_discharge_energy_rate_limit = MAX_DISCHARGE_RATE_KW * interval_h

        charge_space_available = MAX_SOC_KWH - current_soc_kwh
        discharge_energy_available_abs = current_soc_kwh - MIN_USABLE_SOC_KWH

        charge_kwh = 0.0
        discharge_kwh = 0.0
        unmet_load_kwh = 0.0
        exported_kwh = 0.0

        if net_energy_kwh > 0:
            load_value = row['Load_kWh']
            pv_production = row['Production_kWh']
            
            our_share_pv = pv_production * pv_share_decimal
            
            our_surplus = our_share_pv - load_value
            
            debug_print(f"[DEBUG] Load: {load_value:.3f} kWh, " 
                        f"Total PV Production: {pv_production:.3f} kWh, "
                        f"Our share PV ({pv_share_percent}%): {our_share_pv:.3f} kWh, "
                        f"Our Surplus: {our_surplus:.3f} kWh")
            
            if our_surplus > 0:
                potential_charge_kwh = our_surplus * CHARGE_EFFICIENCY
                actual_charge_to_storage = min(potential_charge_kwh, max_charge_energy_rate_limit, charge_space_available)
                actual_charge_to_storage = max(0, actual_charge_to_storage)
                charge_kwh = actual_charge_to_storage
                current_soc_kwh += charge_kwh
                cumulative_surplus += actual_charge_to_storage
                
                if potential_charge_kwh > actual_charge_to_storage and CHARGE_EFFICIENCY > 0:
                    exported_kwh = (potential_charge_kwh - actual_charge_to_storage) / CHARGE_EFFICIENCY
                    exported_kwh = max(0, exported_kwh)
                else:
                    exported_kwh = 0
                    
                debug_print(f"[DEBUG] Battery Charged: {charge_kwh:.3f} kWh, "
                            f"Exported: {exported_kwh:.3f} kWh")
            else:
                charge_kwh = 0
                exported_kwh = 0
                debug_print(f"[DEBUG] No surplus available for charging")

        elif net_energy_kwh < 0:
            debug_print(f"[DEBUG] Energy Deficit: {net_energy_kwh:.3f} kWh")
            
            load_value = row['Load_kWh']
            pv_production = row['Production_kWh']
            
            our_share_pv = pv_production * pv_share_decimal
            
            debug_print(f"[DEBUG] Load: {load_value:.3f} kWh, " 
                        f"Total PV Production: {pv_production:.3f} kWh, "
                        f"Our share PV ({pv_share_percent}%): {our_share_pv:.3f} kWh")
            
            energy_needed_kwh = abs(net_energy_kwh)
            max_discharge_from_soc_delivered = discharge_energy_available_abs * DISCHARGE_EFFICIENCY
            actual_discharge_delivered = min(energy_needed_kwh, max_discharge_energy_rate_limit, max_discharge_from_soc_delivered)
            debug_print(f"[DEBUG] Max Discharge Deliverable: {max_discharge_from_soc_delivered:.3f} kWh, Actual Discharge Delivered: {actual_discharge_delivered:.3f} kWh")
            actual_discharge_delivered = max(0, actual_discharge_delivered)
            if DISCHARGE_EFFICIENCY > 0:
                discharge_kwh = actual_discharge_delivered / DISCHARGE_EFFICIENCY
                discharge_kwh = max(0, discharge_kwh)
            else:
                discharge_kwh = 0
            current_soc_kwh -= discharge_kwh
            unmet_load_kwh = energy_needed_kwh - actual_discharge_delivered
            unmet_load_kwh = max(0, unmet_load_kwh)
            debug_print(f"[DEBUG] Unmet Load for Interval: {unmet_load_kwh:.3f} kWh")

        debug_print(f"[DEBUG] SoC: {current_soc_kwh:.3f} kWh, Charge: {charge_kwh:.3f} kWh, Discharge: {discharge_kwh:.3f} kWh")
        
        if exported_kwh > 0:
            debug_print(f"[DEBUG] Energy Exported to Grid: {exported_kwh:.3f} kWh")

        current_soc_kwh = max(MIN_USABLE_SOC_KWH, min(MAX_SOC_KWH, current_soc_kwh))
        if current_soc_kwh >= MAX_SOC_KWH:
            full_battery_count += 1

        running_total_unmet += unmet_load_kwh
        running_total_exported += exported_kwh

        df.loc[index, 'SoC_kWh'] = current_soc_kwh
        df.loc[index, 'BatteryCharge_kWh'] = charge_kwh
        df.loc[index, 'BatteryDischarge_kWh'] = discharge_kwh
        df.loc[index, 'UnmetLoad_kWh'] = unmet_load_kwh
        df.loc[index, 'ExportedEnergy_kWh'] = exported_kwh
        df.loc[index, 'RunningTotalUnmet_kWh'] = running_total_unmet
        df.loc[index, 'RunningTotalExported_kWh'] = running_total_exported

        current_day = index.date()
        if current_day not in daily_cumulative_unmet:
            daily_cumulative_unmet[current_day] = 0.0
        daily_cumulative_unmet[current_day] += unmet_load_kwh

        debug_print(f"[TEMP] Cumulative Grid Draw for {current_day}: {daily_cumulative_unmet[current_day]:.3f} kWh")

        if progress_callback is not None:
            callback_data = {
                'Time': index,
                'SoC_kWh': current_soc_kwh,
                'BatteryCharge_kWh': charge_kwh,
                'BatteryDischarge_kWh': discharge_kwh,
                'UnmetLoad_kWh': unmet_load_kwh,
                'ExportedEnergy_kWh': exported_kwh,
                'Load_kWh': row['Load_kWh'],
                'Production_kWh': row['Production_kWh'],
                'RunningTotalUnmet_kWh': running_total_unmet,
                'RunningTotalExported_kWh': running_total_exported,
                'FullBatteryCount': full_battery_count if current_soc_kwh >= MAX_SOC_KWH else 0
            }
            
            progress_callback(iteration, callback_data)
            
        if simulation_delay > 0:
            time.sleep(simulation_delay)

    print("Simulation complete.")

    total_unmet_load = df['UnmetLoad_kWh'].sum()
    total_exported = df['ExportedEnergy_kWh'].sum()
    final_soc_kwh = df['SoC_kWh'].iloc[-1]
    final_soc_percent_usable = 0
    if USABLE_CAPACITY_KWH > 0:
        final_soc_percent_usable = ((final_soc_kwh - MIN_USABLE_SOC_KWH) / USABLE_CAPACITY_KWH) * 100
        final_soc_percent_usable = max(0, min(100, final_soc_percent_usable))

    print("\n--- Simulation Summary ---")
    print(f"Number of Battery Stacks: {num_battery_stacks} x 38.4 kWh")
    print(f"Total Unmet Load: {total_unmet_load:.3f} kWh")
    print(f"Energy Exported to Grid: {total_exported:.3f} kWh")
    print(f"IMPORTANT: This simulation assumes exactly {pv_share_percent}% of the external PV production is available to this system")
    print("-------------------------")

    if not output_csv_filename:
        base_name, _ = os.path.splitext(input_csv_filename)
        output_csv_filename = f"{base_name}-battery_sim.csv"

    try:
        df_to_save = df.reset_index()
        df_to_save.to_csv(output_csv_filename, index=False, encoding='utf-8')
        print(f"\nFull simulation results saved to: {output_csv_filename}")
    except Exception as e:
        print(f"\nError saving results to {output_csv_filename}: {e}")

    summary_metrics = {
        'total_unmet_load': total_unmet_load,
        'total_exported': total_exported,
        'final_soc_kwh': final_soc_kwh,
        'final_soc_percent_usable': final_soc_percent_usable,
        'full_battery_count': full_battery_count,
        'cumulative_surplus': cumulative_surplus,
        'daily_cumulative_unmet': daily_cumulative_unmet
    }
    
    recommendations = calculate_charging_recommendations(df, pv_share_percent)

    return df, total_unmet_load, summary_metrics, recommendations

def analyze_battery_stack_requirements(input_csv_filename, max_stacks=10, target_coverage_pcts=[30, 40, 50, 80, 90, 95, 99, 100], pv_share_percent=50):
    """
    Analyze how many battery stacks would be needed to cover different percentages of energy needs.
    
    Args:
        input_csv_filename (str): Path to the input CSV file.
        max_stacks (int): Maximum number of battery stacks to simulate.
        target_coverage_pcts (list): Target coverage percentages to analyze.
        pv_share_percent (float): Percentage of total PV production available to this system.
        
    Returns:
        dict: Results of the analysis
    """
    print("\n====== Battery Stack Requirement Analysis ======")
    print(f"Running simulations with increasing battery stacks until full coverage is achieved (max: {max_stacks}).")
    print("Analysis will stop once 100% coverage is reached or maximum stacks is tested.")
    print("This may take some time depending on the size of your dataset...\n")
    
    print("Running baseline simulation (no battery)...")
    base_name, ext = os.path.splitext(input_csv_filename)
    baseline_output = f"{base_name}-battery_sim-0stacks.csv"
    
    baseline_df, baseline_unmet, _, _ = run_battery_simulation(
        input_csv_filename, 
        output_csv_filename=baseline_output,
        num_battery_stacks=0,
        pv_share_percent=pv_share_percent
    )
    
    total_load = baseline_unmet
    print(f"Total energy deficit without battery: {total_load:.2f} kWh\n")
    
    results = []
    achieved_targets = {pct: False for pct in target_coverage_pcts}
    full_coverage_achieved = False
    
    for num_stacks in range(1, max_stacks + 1):
        print(f"Simulating with {num_stacks} battery stack(s)...")
        
        output_filename = f"{base_name}-battery_sim-{num_stacks}stacks.csv"
        
        sim_df, unmet_load, _, _ = run_battery_simulation(
            input_csv_filename, 
            output_csv_filename=output_filename,
            num_battery_stacks=num_stacks,
            pv_share_percent=pv_share_percent
        )
        
        covered_load = total_load - unmet_load
        coverage_pct = (covered_load / total_load) * 100 if total_load > 0 else 100
        
        print(f"Coverage achieved: {coverage_pct:.2f}% ({covered_load:.2f} kWh covered, {unmet_load:.2f} kWh unmet)")
        
        results.append({
            'num_stacks': num_stacks,
            'capacity_kwh': num_stacks * 38.4,
            'unmet_load_kwh': unmet_load,
            'covered_load_kwh': covered_load,
            'coverage_pct': coverage_pct,
            'incremental_coverage_pct': coverage_pct if num_stacks == 1 else coverage_pct - results[-1]['coverage_pct']
        })
        
        for pct in sorted(target_coverage_pcts):
            if not achieved_targets[pct] and coverage_pct >= pct:
                achieved_targets[pct] = num_stacks
                print(f" {pct}% coverage achieved with {num_stacks} stack(s)")
        
        if unmet_load <= 0.1:
            full_coverage_achieved = True
            print(f"\nFull coverage (100%) achieved with {num_stacks} battery stack(s)!")
            print(f"Analysis complete - stopping as requested since full coverage was achieved.")
            break
    
    print("\n====== Battery Stack Analysis Results ======")
    print(f"{'Stacks':<6}{'Capacity':<10}{'Covered':<10}{'Coverage':<10}{'Increment':<10}")
    print(f"{'#':<6}{'(kWh)':<10}{'(kWh)':<10}{'(%)':<10}{'(%)':<10}")
    print("-" * 46)
    
    for result in results:
        print(f"{result['num_stacks']:<6}{result['capacity_kwh']:<10.1f}{result['covered_load_kwh']:<10.2f}"
              f"{result['coverage_pct']:<10.2f}{result['incremental_coverage_pct']:<10.2f}")
    
    print("\n====== Recommendations ======")
    for pct in sorted(target_coverage_pcts):
        if achieved_targets[pct]:
            print(f"For {pct}% coverage: {achieved_targets[pct]} battery stack(s) needed")
        else:
            print(f"For {pct}% coverage: More than {max_stacks} battery stacks needed")
    
    if not full_coverage_achieved:
        print(f"\nNote: Full coverage was not achieved with {max_stacks} battery stacks.")
        print("Consider running the analysis with a higher maximum number of stacks.")
    
    return results

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run battery simulation on pre-processed load/production data.")
    parser.add_argument("input_csv", help="Path to the input CSV file (must contain Time, LoadTotalPower, Total Production, Interval(Days))")
    parser.add_argument("-o", "--output_csv", help="Optional: Path to save the detailed simulation results CSV.", default=None)
    parser.add_argument("-s", "--stacks", type=int, help="Number of battery stacks to simulate (38.4 kWh each)", default=1)
    parser.add_argument("--analyze-stacks", action="store_true", help="Run analysis to determine optimal number of battery stacks")
    parser.add_argument("--max-stacks", type=int, help="Maximum number of stacks to analyze", default=10)
    parser.add_argument("--pv-share", type=float, help="Percentage of total PV production available to this system", default=50)

    args = parser.parse_args()

    if args.analyze_stacks:
        analyze_battery_stack_requirements(
            args.input_csv, 
            max_stacks=args.max_stacks,
            pv_share_percent=args.pv_share
        )
    else:
        simulation_results_df, _, summary_metrics, recommendations = run_battery_simulation(
            args.input_csv, 
            args.output_csv, 
            num_battery_stacks=args.stacks,
            pv_share_percent=args.pv_share
        )
