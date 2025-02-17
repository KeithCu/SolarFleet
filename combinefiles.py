def find_encoding_issue(py_files=None):
    """
    Identify which file and what position causes an encoding error.
    
    :param py_files: A list of Python files to check for encoding issues.
    """
    if py_files is None:
        py_files = [
            "SolarPlatform.py",
            "SqlModels.py",
            "SolarEdge.py",
            "Database.py",
            "FleetCollector.py",
            "Dashboard.py",
	        "Enphase.py",
            "Solis.py",
        ]
    
    for py_file in py_files:
        try:
            with open(py_file, 'r', encoding='utf-8') as infile:
                for line_number, line in enumerate(infile, start=1):
                    line.encode('utf-8')  # Try encoding to catch the error
        except UnicodeDecodeError as e:
            print(f"Encoding issue in file: {py_file}")
            print(f"Error at line {line_number}, character {e.start}: {e.reason}")
            print(f"Problematic character: {repr(line[e.start:e.end])}")
            return

    print("No encoding issues found.")




def concatenate_py_files(py_files=None, output_file="concatenated_scripts.txt"):
    """
    Concatenates multiple .py files into a single .txt file with UTF-8 encoding.

    :param py_files: A list of Python files to read. If None, a default list is used.
    :param output_file: The output file to write the concatenated content.
    """
    if py_files is None:
        py_files = [
            "SolarPlatform.py",
            "SqlModels.py",
            "Database.py",
            "FleetCollector.py",
            "Dashboard.py",
            "SolarEdge.py",
	        "Enphase.py",
            "Solis.py",
            
        ]
    
    with open(output_file, 'w', encoding='utf-8') as outfile:  # Ensures UTF-8 encoding
        for py_file in py_files:
            with open(py_file, 'r', encoding='utf-8', errors='replace') as infile:
                outfile.write(f"# --- Start of {py_file} ---\n")  # Optional separator
                outfile.write(infile.read())
                outfile.write("\n\n")  # Adds spacing between files

    print(f"Concatenated {len(py_files)} files into '{output_file}' successfully.")


if __name__ == "__main__":
    find_encoding_issue()
    concatenate_py_files()
