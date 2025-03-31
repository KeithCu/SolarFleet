import os
import pandas as pd

def convert_xlsx_to_csv(start_dir='.'):
    """
    Recursively finds all .xlsx files in start_dir and its subdirectories
    and converts them to .csv files in the same location.
    """
    print(f"Starting conversion process in directory: {os.path.abspath(start_dir)}")

    for dirpath, dirnames, filenames in os.walk(start_dir):
        for filename in filenames:
            # Check for .xlsx extension, case-insensitive
            if filename.lower().endswith(".xlsx"):
                xlsx_filepath = os.path.join(dirpath, filename)
                base_name = os.path.splitext(filename)[0]
                csv_filename = base_name + ".csv"
                csv_filepath = os.path.join(dirpath, csv_filename)

                print(f"Found Excel file: {xlsx_filepath}")

                try:
                    # Read the first sheet of the Excel file
                    # To read all sheets, use sheet_name=None, which returns a dict
                    # You'd then need to decide how to save multiple sheets (e.g., separate CSVs)
                    excel_data = pd.read_excel(xlsx_filepath, sheet_name=0)

                    # Write the DataFrame to CSV
                    # index=False prevents pandas from writing the DataFrame index as a column
                    # encoding='utf-8' is generally recommended for compatibility
                    excel_data.to_csv(csv_filepath, index=False, encoding='utf-8')

                    print(f"Successfully converted to: {csv_filepath}")

                except Exception as e:
                    print(f"Error converting file {xlsx_filepath}: {e}")
            # Optional: uncomment to see which files are being skipped
            # else:
            #     print(f"Skipping non-xlsx file: {os.path.join(dirpath, filename)}")

    print("\nConversion process finished.")

if __name__ == "__main__":
    # Run the conversion starting from the current directory
    convert_xlsx_to_csv('.')