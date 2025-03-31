import sys
import os  # Import os module for file operations
import pandas as pd

if len(sys.argv) <= 1:
    print("Error: No input file specified. Please provide the CSV filename as a command-line argument.")
    sys.exit(1)

csv_filename = sys.argv[1]

# --- Ensure your column names match exactly ---
load_col = 'LoadTotalPower(W)/178'
prod_col = 'Total Production'

try:
    # Load the CSV, parsing the 'Time' column as dates
    df = pd.read_csv(csv_filename, index_col='Time')
    df.index = pd.to_datetime(df.index, format="%Y-%m-%d %H:%M:%S", errors='coerce')  # Adjust format to match your data
    if df.index.isnull().any():
        print("\nRows with unparsed dates:")
        print(df[df.index.isnull()])
        raise ValueError("Error: Some dates could not be parsed. Please check the format of the 'Time' column.")
    df.sort_index(inplace=True) # Ensure data is sorted by time
    print(f"Loaded {len(df)} rows from {csv_filename}")
    
    # Display first few rows and data types to verify
    print("\nFirst few rows:")
    print(df.head())
    print("\nData types:")
    print(df.info())
    
    # --- Check if required columns exist ---
    if load_col not in df.columns or prod_col not in df.columns:
        print(f"Error: Required columns ('{load_col}', '{prod_col}') not found in the CSV.")
        print(f"Available columns: {df.columns.tolist()}")
        exit()

    # Ensure columns are numeric (they should be from the previous script, but good practice)
    df[load_col] = pd.to_numeric(df[load_col].astype(str).str.strip().str.replace(',', ''), errors='coerce')
    df[prod_col] = pd.to_numeric(df[prod_col].astype(str).str.strip().str.replace(',', ''), errors='coerce')
    # Handle any non-numeric values if necessary (e.g., fill with 0 or drop)
    df.dropna(subset=[load_col, prod_col], inplace=True)

    df['NetLoad(W)'] = df[load_col] - df[prod_col]

    print("\nCalculated NetLoad(W):")
    print(df[['NetLoad(W)', load_col, prod_col]].head())

    # --- Add this after calculating NetLoad(W) ---

    # Calculate time difference between consecutive rows in seconds
    # df.index should be the datetime index from step 1
    time_diff_seconds = df.index.to_series().diff().dt.total_seconds()

    # Assume the first interval is the same as the second for calculation purposes
    if pd.isna(time_diff_seconds.iloc[0]) and len(time_diff_seconds) > 1:
        time_diff_seconds.iloc[0] = time_diff_seconds.iloc[1]
    elif len(time_diff_seconds) == 1:
        # Handle case with only one row - need a default assumption (e.g., 5 mins)
        print("Warning: Only one data point found. Assuming a 5-minute interval for energy calculation.")
        time_diff_seconds.iloc[0] = 300 # Default to 300 seconds (5 minutes)

    # Convert interval to hours
    time_interval_hours = time_diff_seconds / 3600.0

    # Calculate Net Energy in kWh for each interval (Power in W * hours / 1000)
    df['NetEnergy(kWh)'] = (df['NetLoad(W)'] * time_interval_hours) / 1000.0

    # Check for unusual time intervals
    print("\nTime interval stats (seconds):")
    print(time_diff_seconds.describe())
    if time_diff_seconds.nunique() > 5: # Arbitrary threshold to flag irregularity
        print("Warning: Time intervals seem irregular. Review stats above.")
        print("Unique intervals (seconds):", time_diff_seconds.unique())

    print("\nCalculated NetEnergy(kWh):")
    # Show relevant columns including the interval for verification
    print(df[['NetLoad(W)', 'NetEnergy(kWh)']].head().assign(Interval_sec=time_diff_seconds))

    # Optional: Calculate Production and Load Energy as well
    df['ProductionEnergy(kWh)'] = (df[prod_col] * time_interval_hours) / 1000.0
    df['LoadEnergy(kWh)'] = (df[load_col] * time_interval_hours) / 1000.0

    # Round calculated columns to 2 decimal places
    df['NetEnergy(kWh)'] = df['NetEnergy(kWh)'].round(2)
    df['ProductionEnergy(kWh)'] = df['ProductionEnergy(kWh)'].round(2)
    df['LoadEnergy(kWh)'] = df['LoadEnergy(kWh)'].round(2)

    # --- Save the processed DataFrame to a new CSV ---
    base, ext = os.path.splitext(csv_filename)
    output_filename = f"{base}_processed{ext}"
    df.to_csv(output_filename)
    print(f"\nData saved to {output_filename}")

except FileNotFoundError:
    print(f"Error: File not found at {csv_filename}")
    exit()
except Exception as e:
    print(f"Error loading CSV: {e}")
    exit()

