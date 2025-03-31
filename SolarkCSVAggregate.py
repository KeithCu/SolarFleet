import pandas as pd
import os
import glob
import argparse
from io import StringIO

def find_header_row(filepath, time_col_name="Time"):
    """
    Reads the beginning of a CSV file to find the row index containing
    the specified time column name, assuming this is the header row.
    """
    try:
        with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
            for i, line in enumerate(f):
                if time_col_name in line.split(','):
                    return i
                if i > 20: # Stop searching after 20 lines to avoid reading huge files
                    break
    except Exception as e:
        print(f"  Error reading start of {filepath} to find header: {e}")
    return None # Header row not found

def process_csv_files(output_filename):
    """
    Finds all CSV files in the current directory, extracts specified columns,
    concatenates them, sorts by time, and saves to a single output file.
    """
    # Define the columns to extract based on the sample provided
    time_column = "Time"
    column1 = "GenToMiPower(W)/166"
    column2 = "LoadTotalPower(W)/178"
    columns_to_extract = [time_column, column1, column2]

    all_dataframes = []
    current_directory = '.'

    print(f"Searching for CSV files in: {os.path.abspath(current_directory)}")

    # Use glob to find all CSV files (case-insensitive) in the current directory
    csv_files = glob.glob(os.path.join(current_directory, '*.csv')) + \
                glob.glob(os.path.join(current_directory, '*.CSV'))

    if not csv_files:
        print("No CSV files found in the current directory.")
        return

    print(f"Found {len(csv_files)} CSV files. Processing...")

    for filepath in csv_files:
        filename = os.path.basename(filepath)
        print(f"\nProcessing file: {filename}")

        # Skip the output file itself if it already exists
        if filename == output_filename:
            print(f"  Skipping output file: {filename}")
            continue

        header_row_index = find_header_row(filepath, time_column)

        if header_row_index is None:
            print(f"  Could not find header row containing '{time_column}' in {filename}. Skipping.")
            continue

        print(f"  Detected header at row {header_row_index + 1}")

        try:
            # Read the CSV, skipping metadata rows and using the detected header row
            df = pd.read_csv(filepath, header=header_row_index, encoding='utf-8', low_memory=False)

            # Check if required columns exist
            missing_cols = [col for col in columns_to_extract if col not in df.columns]
            if missing_cols:
                print(f"  Warning: Missing columns {missing_cols} in {filename}. Skipping this file.")
                continue

            # Select only the required columns
            df_subset = df[columns_to_extract].copy()

            # Convert 'Time' column to datetime objects, coercing errors
            df_subset[time_column] = pd.to_datetime(df_subset[time_column], errors='coerce')

            # Drop rows where time conversion failed
            original_rows = len(df_subset)
            df_subset = df_subset.dropna(subset=[time_column])
            if len(df_subset) < original_rows:
                 print(f"  Dropped {original_rows - len(df_subset)} rows due to invalid time format.")

            # Ensure 'Time' column is formatted consistently
            df_subset[time_column] = df_subset[time_column].dt.strftime('%Y-%m-%d %H:%M:%S')

            # Convert power columns to numeric, coercing errors to NaN
            df_subset[column1] = pd.to_numeric(df_subset[column1], errors='coerce')
            df_subset[column2] = pd.to_numeric(df_subset[column2], errors='coerce')

            all_dataframes.append(df_subset)
            print(f"  Successfully processed {len(df_subset)} rows.")

        except pd.errors.EmptyDataError:
             print(f"  Warning: File {filename} is empty or failed to parse after header. Skipping.")
        except Exception as e:
            print(f"  Error processing file {filename}: {e}")

    if not all_dataframes:
        print("\nNo data extracted from any CSV file.")
        return

    # Concatenate all dataframes
    print("\nConcatenating data...")
    combined_df = pd.concat(all_dataframes, ignore_index=True)
    print(f"Total rows before sorting: {len(combined_df)}")


    # Sort by the 'Time' column
    print("Sorting data by time...")
    combined_df = combined_df.sort_values(by=time_column)

    # Save the combined and sorted dataframe to the output file
    try:
        combined_df.to_csv(output_filename, index=False, encoding='utf-8-sig')  # Use utf-8-sig for better compatibility
        print(f"\nSuccessfully saved combined data to: {output_filename}")
        print(f"Total rows in output: {len(combined_df)}")
    except Exception as e:
        print(f"\nError saving combined data to {output_filename}: {e}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Combine specific columns from CSV files in the current directory.")
    parser.add_argument("output_file", help="Name of the output CSV file (e.g., combined_data.csv)")

    args = parser.parse_args()

    process_csv_files(args.output_file)