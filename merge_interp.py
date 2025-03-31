import pandas as pd
import argparse
import os
import sys

def merge_and_interpolate(file1_path, file2_path):
    """
    Merges two time-series CSV files, interpolating data from the first
    file onto the timestamps of the second file.

    Args:
        file1_path (str): Path to the first CSV file (e.g., ExternalProduction).
                          Expected columns: 'Time', 'Total Production'.
                          Time format example: '3/1/25, 12:00 AM'
        file2_path (str): Path to the second CSV file (e.g., Granular House Load).
                          Expected column: 'Time', plus other data.
                          Time format example: '2025-03-01 00:04:26'

    Returns:
        str: The path to the generated output CSV file. Returns None if an error occurs.
    """
    try:
        # --- Read File 1 (External Production - less frequent) ---
        # Attempt to parse dates, trying multiple formats if necessary
        try:
            df1 = pd.read_csv(file1_path, parse_dates=['Time'], dayfirst=False)
        except (ValueError, TypeError):
             # If default parsing fails, try specific format
            try:
                df1 = pd.read_csv(file1_path)
                # Clean up potential extra spaces in column names
                df1.columns = df1.columns.str.strip()
                df1['Time'] = pd.to_datetime(df1['Time'], format='%m/%d/%y, %I:%M %p')
            except Exception as e:
                print(f"Error parsing date format in File 1 ({file1_path}): {e}", file=sys.stderr)
                print("Please ensure the 'Time' column format matches 'M/D/YY, H:MM AM/PM'.", file=sys.stderr)
                return None

        df1.columns = df1.columns.str.strip() # Ensure column names have no leading/trailing spaces
        if 'Total Production' not in df1.columns:
             print(f"Error: 'Total Production' column not found in {file1_path}", file=sys.stderr)
             return None
        df1 = df1.set_index('Time')
        df1 = df1.sort_index()
        # Select only the relevant column for interpolation
        df1_prod = df1[['Total Production']].copy()


        # --- Read File 2 (Granular House Load - more frequent) ---
        try:
            # Standard ISO-like format usually parsed correctly
            df2 = pd.read_csv(file2_path, parse_dates=['Time'], dayfirst=False)
        except (ValueError, TypeError):
            try:
                 df2 = pd.read_csv(file2_path)
                 df2.columns = df2.columns.str.strip()
                 df2['Time'] = pd.to_datetime(df2['Time'], format='%Y-%m-%d %H:%M:%S')
            except Exception as e:
                print(f"Error parsing date format in File 2 ({file2_path}): {e}", file=sys.stderr)
                print("Please ensure the 'Time' column format matches 'YYYY-MM-DD HH:MM:SS'.", file=sys.stderr)
                return None

        df2.columns = df2.columns.str.strip() # Clean column names
        df2 = df2.set_index('Time')
         # Handle potential duplicate timestamps in granular data (keep first)
        df2 = df2[~df2.index.duplicated(keep='first')]
        df2 = df2.sort_index()


        # --- Combine and Interpolate ---
        # Concatenate the two dataframes' indices to get all unique timestamps
        # Reindex the production data (df1) to this combined index. This creates NaNs
        # where df1 didn't originally have data.
        combined_index = df1_prod.index.union(df2.index).sort_values()
        df_prod_reindexed = df1_prod.reindex(combined_index)

        # Interpolate the 'Total Production' column using time-based linear interpolation
        # This fills the NaNs based on the time difference between known points.
        df_prod_interpolated = df_prod_reindexed['Total Production'].interpolate(method='time')

        # --- Merge Interpolated Data with Granular Data ---
        # Join the interpolated production data back onto the granular dataframe (df2)
        # We use a left join to keep all rows from df2 and add the matching interpolated values.
        df_final = df2.join(df_prod_interpolated, how='left')

        # Optional: Fill any remaining NaNs in 'Total Production'
        # This might happen if granular data extends beyond the time range of production data.
        # Filling with 0 might be appropriate for production.
        df_final['Total Production'].fillna(0, inplace=True)


        # --- Prepare Output ---
        # Construct the output filename based on the second input file's name
        base, ext = os.path.splitext(file2_path)
        output_filename = f"{base}-AggregatePV{ext}"

        # Save the result, including the Time index
        df_final.to_csv(output_filename, index=True)
        print(f"Successfully merged and interpolated data into: {output_filename}")
        return output_filename

    except FileNotFoundError as e:
        print(f"Error: File not found - {e}", file=sys.stderr)
        return None
    except KeyError as e:
         print(f"Error: Missing expected column - {e}. Please check CSV headers.", file=sys.stderr)
         return None
    except Exception as e:
        print(f"An unexpected error occurred: {e}", file=sys.stderr)
        return None

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Merge two CSV time-series files, interpolating 'Total Production' "
                    "from the first file onto the timestamps of the second file."
    )
    parser.add_argument("file1", help="Path to the first CSV file (e.g., ExternalProduction, hourly data).")
    parser.add_argument("file2", help="Path to the second CSV file (e.g., Granular House Load, frequent data).")

    args = parser.parse_args()

    merge_and_interpolate(args.file1, args.file2)
